"""Paper Ops session: golden replay → strategy → gate → fills → store."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sneaker_market_maker.core import FeeSchedule
from sneaker_market_maker.paper.artifact_bind import (
    ArtifactBindError,
    BoundModelLineage,
    bind_checkpoint_to_session,
    ensure_ci_pinned_artifact,
)
from sneaker_market_maker.paper.book_snapshot import book_snapshot
from sneaker_market_maker.paper.capital import PaperCapital, _money
from sneaker_market_maker.paper.decision_state import (
    DecisionStateError,
    build_paper_decision_state,
)
from sneaker_market_maker.paper.execution import (
    PaperExecutionEngine,
    SlippageModel,
    VersionedFees,
)
from sneaker_market_maker.paper.export_transitions import (
    PaperStepCheckpoint,
    build_paper_accounting,
    export_checkpoints,
    paper_decision_state,
)
from sneaker_market_maker.paper.gate import DeterministicGate
from sneaker_market_maker.paper.inference import (
    InferenceError,
    InferenceOutcome,
    IqlInferencePort,
    TimedIqlInference,
)
from sneaker_market_maker.paper.intents import IntentKind, QuoteIntent, Side
from sneaker_market_maker.paper.inventory import InventoryLedger, LotState
from sneaker_market_maker.paper.mode_path import apply_strategy_mode
from sneaker_market_maker.paper.ops_mode import PaperModeControls
from sneaker_market_maker.paper.projections import (
    capital_projection,
    fill_dict,
    lot_dict,
    order_dict,
    pnl_projection,
    replay_projection,
    status_projection,
)
from sneaker_market_maker.paper.promote import (
    PromoteError,
    promote_registry_model,
    unlocked_modes_for,
)
from sneaker_market_maker.paper.quote_engine import QuoteEngine, QuoteEngineConfig
from sneaker_market_maker.paper.replay import load_golden_historical_replay
from sneaker_market_maker.paper.replay.loader import MarketReplayEvent
from sneaker_market_maker.paper.replay.simulator import HistoricalReplaySimulator
from sneaker_market_maker.paper.step_effects import (
    STEP_EFFECTS_EVENT,
    capture_paper_step_effects,
)
from sneaker_market_maker.paper.strategy_mode import QualificationError, StrategyMode
from sneaker_market_maker.persistence.paper_models import PaperBookSnapshot
from sneaker_market_maker.persistence.paper_repository import InMemoryPaperStore
from sneaker_market_maker.persistence.research_repository import InMemoryResearchRepository
from sneaker_market_maker.research.contracts.action import ActionCategory, HybridAction
from sneaker_market_maker.research.registry.service import RegistryService, RegistryState

PAUSE_OPERATOR = "operator"
PAUSE_IQL = "iql_unavailable"

DEFAULT_GOLDEN_ROOT = Path(__file__).resolve().parents[3] / "data" / "paper" / "golden_v1"
DEFAULT_FEES = VersionedFees(
    version="fees-v1",
    schedule=FeeSchedule(
        seller_rate=Decimal("0.10"),
        processor_rate=Decimal("0.03"),
        inbound_shipping=Decimal("5.00"),
    ),
)
DEFAULT_SLIPPAGE = SlippageModel("slippage-v1", Decimal("0.00"), Decimal("0.00"))

@dataclass(frozen=True)
class PaperEventEnvelope:
    sequence: int
    event_id: UUID
    event_type: str
    simulation_time: datetime | None
    wall_time: datetime
    correlation_id: UUID
    payload: dict[str, Any]


class PaperOpsSession:
    """In-process Continuous Paper Market-Maker control plane backend."""
    def __init__(
        self,
        *,
        store: InMemoryPaperStore | None = None,
        golden_root: Path | None = None,
    ) -> None:
        self._store = store or InMemoryPaperStore()
        self._golden_root = golden_root or DEFAULT_GOLDEN_ROOT
        self._simulator = HistoricalReplaySimulator()
        self._gate = DeterministicGate()
        self._fees = DEFAULT_FEES
        self._slippage = DEFAULT_SLIPPAGE
        self._ledger = InventoryLedger()
        capital = PaperCapital.initial_state()
        self._quotes = QuoteEngine(
            gate=self._gate,
            capital=capital,
            inventory=self._ledger,
            config=QuoteEngineConfig(expected_buy_fees_and_slippage=Decimal("10.00")),
        )
        self._execution = PaperExecutionEngine(
            capital=capital,
            gate=self._gate,
            fees=self._fees,
            slippage=self._slippage,
            inventory=self._ledger,
        )
        self._run_id: UUID | None = None
        self._correlation_id = uuid4()
        self._idempotency: dict[str, tuple[str, UUID]] = {}
        self._events: list[PaperEventEnvelope] = []
        self._mode = PaperModeControls()
        self._inference: IqlInferencePort | None = None
        self._bound_lineage: BoundModelLineage | None = None
        self._registry: RegistryService | None = None
        self._last_promote: dict[str, Any] | None = None
        self._last_inference: InferenceOutcome | None = None
        self._pause_reason: str | None = None
        self._fallback_reason: str | None = None
        self._last_iql_action: dict[str, Any] | None = None
        self._last_market_event: MarketReplayEvent | None = None
        self._transition_repo = InMemoryResearchRepository()
        self._checkpoints: list[PaperStepCheckpoint] = []
        self._fee_ledger_ids: tuple[str, ...] = ("opening",)
        self._seller_fees = Decimal("0.00")
        self._processor_fees = Decimal("0.00")
        self._shipping = Decimal("0.00")
        self._authentication = Decimal("0.00")
        self._slippage_fees = Decimal("0.00")
        self._dataset_version = "unknown"
        self._random_seed = 0
        self._last_export: dict[str, Any] | None = None

    def bind_transition_repository(self, repository: InMemoryResearchRepository) -> None:
        """Inject research transition repository used by export-from-run."""

        self._transition_repo = repository

    def attach_registry(self, registry: RegistryService) -> None:
        """Attach shared RegistryService used by promote-model."""

        self._registry = registry

    def bind_active_model(self, *, model_id: str, registry_state: RegistryState) -> None:
        """Bind the research registry model used for Model Qualification."""

        self._mode.bind_active_model(model_id=model_id, registry_state=registry_state)

    def bind_inference(self, port: IqlInferencePort) -> None:
        """Inject the IQL inference port (stub or production). Clears bound lineage."""

        self._inference = port
        self._bound_lineage = None

    def apply_bound_artifact(
        self,
        *,
        lineage: BoundModelLineage,
        port: IqlInferencePort,
    ) -> None:
        """Apply a fail-closed production bind (weights + qualification metadata)."""

        self._mode.bind_active_model(
            model_id=lineage.model_id,
            registry_state=lineage.registry_state,
        )
        self._inference = port
        self._bound_lineage = lineage

    def execute(self, command: str, payload: dict[str, Any], idempotency_key: str) -> UUID:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        previous = self._idempotency.get(idempotency_key)
        if previous is not None:
            if previous[0] != normalized:
                raise ValueError("idempotency key reused")
            return previous[1]
        handlers = {
            "load": self._cmd_load,
            "start": self._cmd_start,
            "pause": self._cmd_pause,
            "resume": self._cmd_resume,
            "stop": self._cmd_stop,
            "enable": self._cmd_enable,
            "disable": self._cmd_disable,
            "cancel": self._cmd_cancel,
            "tick": self._cmd_tick,
            "set-mode": self._cmd_set_mode,
            "set-budget": self._cmd_set_budget,
            "bind-model": self._cmd_bind_model,
            "promote-model": self._cmd_promote_model,
            "export-from-run": self._cmd_export_from_run,
        }
        if command not in handlers:
            raise KeyError(command)
        result = handlers[command](payload)
        self._idempotency[idempotency_key] = (normalized, result)
        return result

    def get(self, resource: str) -> dict[str, Any]:
        if resource == "status":
            lineage = self._bound_lineage
            return status_projection(
                run_id=str(self._run_id) if self._run_id else None,
                quotes=self._quotes,
                execution=self._execution,
                ledger=self._ledger,
                simulator=self._simulator,
                audit_sequence=len(self._events),
                strategy_mode=self._mode.machine.mode.value,
                registry_model_id=self._mode.model_id,
                registry_state=(
                    None
                    if self._mode.registry_state is None
                    else self._mode.registry_state.value
                ),
                registry_artifact_hash=(
                    None if lineage is None else lineage.artifact_hash
                ),
                encoder_version=None if lineage is None else lineage.encoder_version,
                state_schema_version=(
                    None if lineage is None else lineage.state_schema_version
                ),
                action_translator_version=(
                    None if lineage is None else lineage.action_translator_version
                ),
                unlocked_modes=list(unlocked_modes_for(self._mode.registry_state)),
                last_promote=self._last_promote,
                inference_latency_budget_ms=self._mode.budget.limit_ms,
                pause_reason=self._pause_reason,
                fallback_reason=self._fallback_reason,
                last_iql_action=self._last_iql_action,
            )
        if resource == "capital":
            return capital_projection(self._execution.capital)
        if resource == "orders":
            return {"orders": [order_dict(o) for o in self._execution.orders.values()]}
        if resource == "fills":
            return {"fills": [fill_dict(f) for f in self._execution.fills]}
        if resource == "lots":
            return {"lots": [lot_dict(lot) for lot in self._ledger.lots()]}
        if resource == "pnl":
            return pnl_projection(self._execution.capital, self._ledger)
        if resource == "replay":
            return replay_projection(self._simulator)
        if resource == "transitions":
            rows = self._transition_repo.transitions
            return {
                "count": len(rows),
                "trainable": sum(
                    1 for row in rows if row.trainability_status == "trainable"
                ),
                "quarantined": sum(
                    1 for row in rows if row.trainability_status == "quarantined"
                ),
                "transition_ids": [str(row.transition_id) for row in rows],
                "last_export": self._last_export,
            }
        raise KeyError(resource)

    def after(self, sequence: int) -> tuple[PaperEventEnvelope, ...]:
        return tuple(event for event in self._events if event.sequence > sequence)

    def _cmd_load(self, payload: dict[str, Any]) -> UUID:
        seed = int(payload.get("seed", 0))
        speed = int(payload.get("speed", 1))
        replay = load_golden_historical_replay(self._golden_root)
        self._reset_book()
        self._simulator.load(replay, seed=seed, speed=speed)
        self._run_id = self._store.create_run(
            dataset_id=replay.manifest.dataset_id,
            dataset_version=replay.manifest.version,
            checksum_sha256=replay.manifest.checksum_sha256,
            seed=seed,
            status="loaded",
        )
        self._dataset_version = replay.manifest.dataset_id
        self._random_seed = seed
        self._append_opening_checkpoint()
        self._persist_and_emit("replay.loaded", {"dataset_id": replay.manifest.dataset_id})
        assert self._run_id is not None
        return self._run_id

    def _cmd_start(self, _payload: dict[str, Any]) -> UUID:
        self._simulator.start()
        return self._emit("replay.started", {})

    def _cmd_pause(self, _payload: dict[str, Any]) -> UUID:
        self._simulator.pause()
        self._pause_reason = PAUSE_OPERATOR
        return self._emit("replay.paused", {"reason": PAUSE_OPERATOR})

    def _cmd_resume(self, _payload: dict[str, Any]) -> UUID:
        if (
            self._pause_reason == PAUSE_IQL
            and self._mode.machine.mode is StrategyMode.IQL_PRIMARY
            and not self._iql_healthy()
        ):
            raise ValueError(
                "replay paused for IQL unavailability; switch mode or restore healthy IQL"
            )
        self._simulator.resume()
        self._pause_reason = None
        return self._emit("replay.resumed", {})

    def _cmd_stop(self, _payload: dict[str, Any]) -> UUID:
        self._simulator.stop()
        self._pause_reason = None
        return self._emit("replay.stopped", {})

    def _cmd_enable(self, _payload: dict[str, Any]) -> UUID:
        self._quotes.enable()
        return self._emit("strategy.enabled", {})

    def _cmd_disable(self, _payload: dict[str, Any]) -> UUID:
        results = self._quotes.disable()
        for intent, decision in results:
            if decision.accepted:
                self._execution.submit(intent, preapproved=decision)
        self._quotes.sync_capital(self._execution.capital)
        self._persist_and_emit("strategy.disabled", {"cancelled": len(results)})
        return self._events[-1].event_id

    def _cmd_cancel(self, payload: dict[str, Any]) -> UUID:
        side = Side(str(payload["side"]))
        open_order = next(
            (
                order
                for order in self._execution.open_orders()
                if order.side is side
                and order.product_family == str(payload["product_family"])
                and order.style_code == str(payload.get("style_code", order.style_code))
            ),
            None,
        )
        replaces = (
            open_order.principal
            if open_order is not None and side is Side.BUY
            else (None if side is Side.SELL else Decimal("0.00"))
        )
        intent = QuoteIntent(
            kind=IntentKind.CANCEL,
            side=side,
            principal=Decimal("0.00"),
            expected_fees_and_slippage=Decimal("0.00"),
            product_family=str(payload["product_family"]),
            replaces_reservation=replaces,
            price=open_order.price if open_order else Decimal("0.00"),
            style_code=str(payload.get("style_code", "")),
            shoe_size=(
                Decimal(str(payload["shoe_size"]))
                if payload.get("shoe_size") is not None
                else (open_order.shoe_size if open_order else None)
            ),
        )
        decision = self._gate.evaluate(intent, self._execution.capital)
        if decision.accepted:
            self._execution.submit(intent, preapproved=decision)
            self._quotes.sync_capital(self._execution.capital)
            self._quotes.clear_active(side)
        self._persist_and_emit(
            "order.cancel", {"accepted": decision.accepted, "side": side.value}
        )
        return self._events[-1].event_id

    def _cmd_tick(self, _payload: dict[str, Any]) -> UUID:
        batch = self._simulator.tick()
        assert self._run_id is not None
        before = book_snapshot(
            run_id=self._run_id,
            execution=self._execution,
            ledger=self._ledger,
        )
        for event in batch:
            self._last_market_event = event
            fills = self._execution.match(event, simulation_time=event.source_timestamp)
            for fill in fills:
                self._attribute_fill_fees(fill)
                if fill.side is Side.BUY:
                    for lot in self._ledger.lots():
                        if lot.source_fill_id == fill.fill_id and lot.state is LotState.PURCHASED:
                            self._ledger.advance_to_available(lot.lot_id)
            self._quotes.sync_capital(self._execution.capital)
            self._last_inference = self._inference_for_event(event)
            tick = apply_strategy_mode(
                mode=self._mode.machine.mode,
                quotes=self._quotes,
                event=event,
                simulation_time=event.source_timestamp,
                inference=self._last_inference,
            )
            action = (
                HybridAction(ActionCategory.QUOTE, 0.0, 0, 0)
                if tick.intents
                else HybridAction(ActionCategory.NO_OP, 0.0, 0, 0)
            )
            self._fallback_reason = None if tick.pause_for_iql else tick.fallback_reason
            if tick.last_action_summary is not None:
                self._last_iql_action = tick.last_action_summary
            if tick.fallback_reason is not None and not tick.pause_for_iql:
                self._persist_and_emit(
                    "strategy.advisory_fallback",
                    {"reason": tick.fallback_reason},
                )
            if tick.pause_for_iql:
                self._simulator.pause()
                self._pause_reason = PAUSE_IQL
                self._persist_and_emit(
                    "replay.paused_iql",
                    {"reason": tick.fallback_reason or "invalid_inference"},
                )
                self._emit_step_effects(
                    before=before,
                    source_event_id=event.event_id,
                    simulation_time=event.source_timestamp,
                    proposed_action=action,
                    post_gate_action=action,
                )
                break
            for intent, decision in tick.intents:
                if decision.accepted:
                    self._execution.submit(intent, preapproved=decision)
            self._quotes.sync_capital(self._execution.capital)
            before = self._emit_step_effects(
                before=before,
                source_event_id=event.event_id,
                simulation_time=event.source_timestamp,
                proposed_action=action,
                post_gate_action=action,
            )
        self._persist_and_emit(
            "replay.ticked",
            {"events": len(batch), "event_ids": [event.event_id for event in batch]},
        )
        return self._events[-1].event_id

    def _emit_step_effects(
        self,
        *,
        before: PaperBookSnapshot,
        source_event_id: str,
        simulation_time: datetime | None,
        proposed_action: HybridAction,
        post_gate_action: HybridAction,
    ) -> PaperBookSnapshot:
        assert self._run_id is not None
        after = book_snapshot(
            run_id=self._run_id,
            execution=self._execution,
            ledger=self._ledger,
        )
        effects = capture_paper_step_effects(
            run_id=self._run_id,
            simulation_time=simulation_time,
            source_event_ids=(source_event_id,),
            before=before,
            after=after,
        )
        self._persist_and_emit(STEP_EFFECTS_EVENT, effects.to_payload())
        accounting = build_paper_accounting(
            capital=self._execution.capital,
            ledger=self._ledger,
            ledger_entry_ids=self._fee_ledger_ids,
            seller_fees=self._seller_fees,
            processor_fees=self._processor_fees,
            shipping=self._shipping,
            authentication=self._authentication,
            slippage=self._slippage_fees,
        )
        self._checkpoints.append(
            PaperStepCheckpoint(
                index=len(self._checkpoints),
                simulation_time=simulation_time,
                source_event_ids=(source_event_id,),
                accounting=accounting,
                state=paper_decision_state(
                    capital=self._execution.capital,
                    ledger=self._ledger,
                ),
                proposed_action=proposed_action,
                post_gate_action=post_gate_action,
                order_ids_added=effects.order_ids_added,
                fill_ids_added=effects.fill_ids_added,
                lot_ids_added=effects.lot_ids_added,
            )
        )
        return after

    def _attribute_fill_fees(self, fill: Any) -> None:
        fee = _money(fill.total_fees)
        if fee <= 0:
            return
        if fill.side is Side.BUY:
            self._shipping = _money(self._shipping + fee)
            self._fee_ledger_ids = (*self._fee_ledger_ids, f"shipping:{fill.fill_id}")
        else:
            self._seller_fees = _money(self._seller_fees + fee)
            self._fee_ledger_ids = (*self._fee_ledger_ids, f"seller_fees:{fill.fill_id}")

    def _append_opening_checkpoint(self) -> None:
        accounting = build_paper_accounting(
            capital=self._execution.capital,
            ledger=self._ledger,
            ledger_entry_ids=self._fee_ledger_ids,
            seller_fees=self._seller_fees,
            processor_fees=self._processor_fees,
            shipping=self._shipping,
            authentication=self._authentication,
            slippage=self._slippage_fees,
        )
        self._checkpoints.append(
            PaperStepCheckpoint(
                index=0,
                simulation_time=None,
                source_event_ids=("paper-open",),
                accounting=accounting,
                state=paper_decision_state(
                    capital=self._execution.capital,
                    ledger=self._ledger,
                ),
                proposed_action=HybridAction(ActionCategory.NO_OP, 0.0, 0, 0),
                post_gate_action=HybridAction(ActionCategory.NO_OP, 0.0, 0, 0),
                order_ids_added=(),
                fill_ids_added=(),
                lot_ids_added=(),
            )
        )

    def _cmd_export_from_run(self, payload: dict[str, Any]) -> UUID:
        assert self._run_id is not None
        requested = payload.get("run_id")
        if requested is not None and str(requested) != str(self._run_id):
            raise ValueError("export run_id does not match active paper run")
        summary = export_checkpoints(
            checkpoints=tuple(self._checkpoints),
            paper_run_id=self._run_id,
            dataset_version=self._dataset_version,
            random_seed=self._random_seed,
            repository=self._transition_repo,
        )
        event_payload = {
            "run_id": str(self._run_id),
            "created": summary.created,
            "existing": summary.existing,
            "quarantined": summary.quarantined,
            "trainable": summary.trainable,
            "transition_ids": list(summary.transition_ids),
        }
        self._last_export = event_payload
        self._persist_and_emit("transitions.exported", event_payload)
        return self._events[-1].event_id

    def _inference_for_event(self, event: MarketReplayEvent) -> InferenceOutcome | None:
        """Run IQL only when Strategy Mode is not deterministic."""

        if self._mode.machine.mode is StrategyMode.DETERMINISTIC:
            return None
        if self._inference is None:
            return InferenceOutcome(
                valid=False,
                action=None,
                latency_ms=0.0,
                reason="no_inference_port",
            )
        try:
            state = build_paper_decision_state(
                event=event,
                capital=self._execution.capital,
                orders=tuple(self._execution.orders.values()),
                lots=self._ledger.lots(),
            )
        except DecisionStateError as error:
            return InferenceOutcome(
                valid=False,
                action=None,
                latency_ms=0.0,
                reason=error.code,
            )
        return TimedIqlInference(self._inference, self._mode.budget).infer(state)

    def _cmd_bind_model(self, payload: dict[str, Any]) -> UUID:
        """Bind a registry-pinned checkpoint (CI pin or checkpoint_dir + ops_lineage)."""

        from sneaker_market_maker.paper.artifact_bind import load_ops_lineage

        model_id = str(payload.get("model_id") or "ops-bound-model")
        state_raw = payload.get("registry_state", RegistryState.ADVISORY_APPROVED.value)
        try:
            registry_state = RegistryState(str(state_raw))
        except ValueError as error:
            raise ValueError(f"unknown registry_state: {state_raw!r}") from error

        use_ci = bool(payload.get("use_ci_pin", True)) and not payload.get(
            "checkpoint_dir"
        )
        try:
            if use_ci:
                artifact = ensure_ci_pinned_artifact()
            else:
                checkpoint_dir = Path(str(payload["checkpoint_dir"]))
                if (checkpoint_dir / "ops_lineage.json").exists():
                    artifact = load_ops_lineage(checkpoint_dir)
                else:
                    raise ArtifactBindError(
                        "incomplete_bind",
                        "checkpoint_dir requires ops_lineage.json sidecar",
                    )
            lineage = bind_checkpoint_to_session(
                self,
                model_id=model_id,
                registry_state=registry_state,
                artifact=artifact,
            )
        except ArtifactBindError as error:
            self._persist_and_emit(
                "strategy.bind_rejected",
                {"code": error.code, "message": str(error)},
            )
            raise ValueError(str(error)) from error

        self._persist_and_emit(
            "strategy.model_bound",
            {
                "model_id": lineage.model_id,
                "registry_state": lineage.registry_state.value,
                "artifact_hash": lineage.artifact_hash,
                "feature_map_version": lineage.encoder_version,
                "state_schema_version": lineage.state_schema_version,
                "action_translator_version": lineage.action_translator_version,
            },
        )
        return self._events[-1].event_id

    def _cmd_promote_model(self, payload: dict[str, Any]) -> UUID:
        """Promote a registry model one legal edge; sync Ops qualification state."""

        if self._registry is None:
            raise ValueError("registry is not attached")
        try:
            result = promote_registry_model(
                self._registry,
                model_id=str(payload["model_id"]),
                target=str(payload["target"]),
                actor=str(payload.get("actor", "")),
                reason=str(payload.get("reason", "")),
            )
        except PromoteError as error:
            self._persist_and_emit(
                "strategy.promote_rejected",
                {"code": error.code, "message": str(error)},
            )
            raise ValueError(str(error)) from error
        except KeyError as error:
            raise ValueError(f"missing promote field: {error.args[0]}") from error

        model_id = str(result.model.model_id)
        # Sync qualification metadata when promoting the active Ops model.
        if self._mode.model_id is None or self._mode.model_id == model_id:
            self._mode.bind_active_model(
                model_id=model_id,
                registry_state=result.target,
            )
        self._last_promote = {
            "model_id": model_id,
            "actor": result.actor,
            "reason": result.reason,
            "source": None if result.source is None else result.source.value,
            "target": result.target.value,
        }
        self._persist_and_emit("strategy.model_promoted", dict(self._last_promote))
        return self._events[-1].event_id

    def _iql_healthy(self) -> bool:
        if self._inference is None or self._last_market_event is None:
            return False
        outcome = self._inference_for_event(self._last_market_event)
        return outcome is not None and outcome.valid

    def _cmd_set_mode(self, payload: dict[str, Any]) -> UUID:
        mode = StrategyMode(str(payload["mode"]))
        try:
            _changed, event_payload = self._mode.set_mode(mode)
        except QualificationError as error:
            self._persist_and_emit(
                "strategy.mode_rejected",
                self._mode.rejection_payload(mode, error),
            )
            raise ValueError(str(error)) from error
        if (
            mode is StrategyMode.DETERMINISTIC
            and self._pause_reason == PAUSE_IQL
        ):
            self._pause_reason = PAUSE_OPERATOR
        self._persist_and_emit("strategy.mode_set", event_payload)
        return self._events[-1].event_id

    def _cmd_set_budget(self, payload: dict[str, Any]) -> UUID:
        limit_ms = int(payload["limit_ms"])
        try:
            event_payload = self._mode.set_budget(limit_ms)
        except InferenceError as error:
            self._persist_and_emit(
                "inference.budget_rejected",
                {"limit_ms": limit_ms, "code": error.code},
            )
            raise ValueError(str(error)) from error
        self._persist_and_emit("inference.budget_set", event_payload)
        return self._events[-1].event_id

    def _reset_book(self) -> None:
        capital = PaperCapital.initial_state()
        self._ledger = InventoryLedger()
        self._quotes = QuoteEngine(
            gate=self._gate,
            capital=capital,
            inventory=self._ledger,
            config=QuoteEngineConfig(expected_buy_fees_and_slippage=Decimal("10.00")),
        )
        self._execution = PaperExecutionEngine(
            capital=capital,
            gate=self._gate,
            fees=self._fees,
            slippage=self._slippage,
            inventory=self._ledger,
        )
        self._events.clear()
        self._run_id = None
        self._checkpoints.clear()
        self._fee_ledger_ids = ("opening",)
        self._seller_fees = Decimal("0.00")
        self._processor_fees = Decimal("0.00")
        self._shipping = Decimal("0.00")
        self._authentication = Decimal("0.00")
        self._slippage_fees = Decimal("0.00")
        self._last_export = None
        self._dataset_version = "unknown"
        self._random_seed = 0

    def _persist_and_emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._run_id is not None:
            self._store.save_book(
                book_snapshot(
                    run_id=self._run_id,
                    execution=self._execution,
                    ledger=self._ledger,
                )
            )
            self._store.append_audit(self._run_id, event_type, payload)
        self._emit(event_type, payload)

    def _emit(self, event_type: str, payload: dict[str, Any]) -> UUID:
        event_id = uuid4()
        self._events.append(
            PaperEventEnvelope(
                sequence=len(self._events) + 1,
                event_id=event_id,
                event_type=event_type,
                simulation_time=self._simulator.projection().simulation_time,
                wall_time=datetime.now(timezone.utc),
                correlation_id=self._correlation_id,
                payload=payload,
            )
        )
        return event_id
