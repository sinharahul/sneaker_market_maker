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
from sneaker_market_maker.paper.book_snapshot import book_snapshot
from sneaker_market_maker.paper.capital import PaperCapital
from sneaker_market_maker.paper.execution import (
    PaperExecutionEngine,
    SlippageModel,
    VersionedFees,
)
from sneaker_market_maker.paper.gate import DeterministicGate
from sneaker_market_maker.paper.inference import InferenceError
from sneaker_market_maker.paper.intents import IntentKind, QuoteIntent, Side
from sneaker_market_maker.paper.inventory import InventoryLedger, LotState
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
from sneaker_market_maker.paper.quote_engine import QuoteEngine, QuoteEngineConfig
from sneaker_market_maker.paper.replay import load_golden_historical_replay
from sneaker_market_maker.paper.replay.simulator import HistoricalReplaySimulator
from sneaker_market_maker.paper.strategy_mode import QualificationError, StrategyMode
from sneaker_market_maker.persistence.paper_repository import InMemoryPaperStore
from sneaker_market_maker.research.registry.service import RegistryState

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

    def bind_active_model(self, *, model_id: str, registry_state: RegistryState) -> None:
        """Bind the research registry model used for Model Qualification."""

        self._mode.bind_active_model(model_id=model_id, registry_state=registry_state)

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
        }
        if command not in handlers:
            raise KeyError(command)
        result = handlers[command](payload)
        self._idempotency[idempotency_key] = (normalized, result)
        return result

    def get(self, resource: str) -> dict[str, Any]:
        if resource == "status":
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
                inference_latency_budget_ms=self._mode.budget.limit_ms,
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
        self._persist_and_emit("replay.loaded", {"dataset_id": replay.manifest.dataset_id})
        assert self._run_id is not None
        return self._run_id

    def _cmd_start(self, _payload: dict[str, Any]) -> UUID:
        self._simulator.start()
        return self._emit("replay.started", {})

    def _cmd_pause(self, _payload: dict[str, Any]) -> UUID:
        self._simulator.pause()
        return self._emit("replay.paused", {})

    def _cmd_resume(self, _payload: dict[str, Any]) -> UUID:
        self._simulator.resume()
        return self._emit("replay.resumed", {})

    def _cmd_stop(self, _payload: dict[str, Any]) -> UUID:
        self._simulator.stop()
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
        for event in batch:
            fills = self._execution.match(event, simulation_time=event.source_timestamp)
            for fill in fills:
                if fill.side is Side.BUY:
                    for lot in self._ledger.lots():
                        if lot.source_fill_id == fill.fill_id and lot.state is LotState.PURCHASED:
                            self._ledger.advance_to_available(lot.lot_id)
            self._quotes.sync_capital(self._execution.capital)
            for intent, decision in self._quotes.on_market(
                event, simulation_time=event.source_timestamp
            ):
                if decision.accepted:
                    self._execution.submit(intent, preapproved=decision)
            self._quotes.sync_capital(self._execution.capital)
        self._persist_and_emit(
            "replay.ticked",
            {"events": len(batch), "event_ids": [event.event_id for event in batch]},
        )
        return self._events[-1].event_id

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
