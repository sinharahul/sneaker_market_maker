"""Export paper run checkpoints into the research transition repository (R1-04)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sneaker_market_maker.paper.capital import PaperCapital, _money
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.paper.inventory import InventoryLedger, LotState
from sneaker_market_maker.paper.reward_projection import project_paper_reward
from sneaker_market_maker.paper.transition_bridge import (
    PaperTransitionDraft,
    assemble_paper_transition,
)
from sneaker_market_maker.persistence.research_repository import (
    AddResult,
    TransitionRepository,
)
from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    ActionMask,
    HybridAction,
)
from sneaker_market_maker.research.contracts.transition import OfflineTransition, StepEffects
from sneaker_market_maker.research.episodes.events import DecisionPoint, EventKind
from sneaker_market_maker.research.rewards.builder import AccountingProjection

_CLOSED = {
    LotState.SOLD,
    LotState.SETTLED,
    LotState.AUTH_FAILED,
    LotState.RETURNED,
    LotState.LOST,
}
_ZERO = Decimal("0.00")
_DEFAULT_ACTION = HybridAction(ActionCategory.NO_OP, 0.0, 0, 0)
_MASK = ActionMask(True, True, True)
_BOUNDS = ActionBounds(-5, 5, -5, 5)


@dataclass(frozen=True)
class PaperStepCheckpoint:
    index: int
    simulation_time: datetime | None
    source_event_ids: tuple[str, ...]
    accounting: AccountingProjection
    state: dict[str, object]
    proposed_action: HybridAction
    post_gate_action: HybridAction
    order_ids_added: tuple[str, ...]
    fill_ids_added: tuple[str, ...]
    lot_ids_added: tuple[str, ...]


@dataclass(frozen=True)
class ExportSummary:
    created: int
    existing: int
    quarantined: int
    trainable: int
    transition_ids: tuple[str, ...]


def paper_equity(capital: PaperCapital, ledger: InventoryLedger) -> Decimal:
    open_lots = [lot for lot in ledger.lots() if lot.state not in _CLOSED]
    inventory_cost = _money(sum((lot.landed_cost for lot in open_lots), _ZERO))
    return _money(capital.cash + inventory_cost)


def build_paper_accounting(
    *,
    capital: PaperCapital,
    ledger: InventoryLedger,
    ledger_entry_ids: tuple[str, ...],
    seller_fees: Decimal,
    processor_fees: Decimal,
    shipping: Decimal,
    authentication: Decimal,
    slippage: Decimal,
) -> AccountingProjection:
    open_lots = [lot for lot in ledger.lots() if lot.state not in _CLOSED]
    return AccountingProjection(
        nav=paper_equity(capital, ledger),
        ledger_entry_ids=ledger_entry_ids,
        seller_fees=_money(seller_fees),
        processor_fees=_money(processor_fees),
        shipping=_money(shipping),
        authentication=_money(authentication),
        slippage=_money(slippage),
        open_reservations=(),
        physical_lots=tuple(str(lot.lot_id) for lot in open_lots),
    )


def paper_decision_state(
    *,
    capital: PaperCapital,
    ledger: InventoryLedger,
) -> dict[str, object]:
    open_lots = [lot for lot in ledger.lots() if lot.state not in _CLOSED]
    return {
        "cash": capital.cash,
        "reserved_buy_principal": capital.reserved_buy_principal,
        "equity": paper_equity(capital, ledger),
        "inventory_lots": Decimal(len(open_lots)),
    }


def _decision_point(
    *,
    episode_id: UUID,
    index: int,
    checkpoint: PaperStepCheckpoint,
) -> DecisionPoint:
    sim_time = checkpoint.simulation_time or datetime(1970, 1, 1, tzinfo=timezone.utc)
    return DecisionPoint(
        episode_id=episode_id,
        index=index,
        simulation_time=sim_time,
        elapsed_seconds=60,
        reasons=(EventKind.FILL if checkpoint.fill_ids_added else EventKind.BOOK,),
        source_ids=checkpoint.source_event_ids or (f"paper-step-{index}",),
        provenances=("historical",),
        discount=0.99,
        state=checkpoint.state,
        action_mask=_MASK,
        action_bounds=_BOUNDS,
    )


def export_checkpoints(
    *,
    checkpoints: tuple[PaperStepCheckpoint, ...],
    paper_run_id: UUID,
    dataset_version: str,
    random_seed: int,
    repository: TransitionRepository,
) -> ExportSummary:
    """Pair adjacent checkpoints into OfflineTransitions and persist append-only."""

    if len(checkpoints) < 2:
        raise PaperError(
            "export_insufficient",
            "need at least two paper step checkpoints to export transitions",
        )

    created = existing = quarantined = trainable = 0
    transition_ids: list[str] = []
    episode_id = paper_run_id

    for index in range(len(checkpoints) - 1):
        before = checkpoints[index]
        after = checkpoints[index + 1]
        try:
            reward = project_paper_reward(
                before=before.accounting,
                after=after.accounting,
                terminal=False,
            )
        except PaperError:
            # Incomplete fee ledger — still persist a quarantined shell via unreconciled skip:
            # assemble with a placeholder is wrong; count as quarantined without inventing reward.
            quarantined += 1
            continue

        new_ledger = tuple(
            entry
            for entry in after.accounting.ledger_entry_ids
            if entry not in before.accounting.ledger_entry_ids
        )
        logistics = tuple(f"logistics:{lot_id}" for lot_id in after.lot_ids_added)
        if not logistics:
            logistics = (f"logistics:noop:{after.source_event_ids[0] if after.source_event_ids else index}",)

        draft = PaperTransitionDraft(
            current=_decision_point(
                episode_id=episode_id, index=index, checkpoint=before
            ),
            next=_decision_point(
                episode_id=episode_id, index=index + 1, checkpoint=after
            ),
            proposed_action=after.proposed_action or _DEFAULT_ACTION,
            post_gate_action=after.post_gate_action or _DEFAULT_ACTION,
            reward=reward,
            effects=StepEffects(
                order_ids=after.order_ids_added,
                fill_ids=after.fill_ids_added,
                fee_ledger_ids=new_ledger,
                inventory_transition_ids=after.lot_ids_added,
                logistics_transition_ids=logistics,
                settlement_ids=(),
            ),
            paper_run_id=paper_run_id,
            dataset_version=dataset_version,
            random_seed=random_seed,
        )
        transition = assemble_paper_transition(draft)
        result = repository.add_transition(transition)
        transition_ids.append(str(transition.transition_id))
        if result is AddResult.CREATED:
            created += 1
        else:
            existing += 1
        if transition.trainability_status == "trainable":
            trainable += 1
        else:
            quarantined += 1

    return ExportSummary(
        created=created,
        existing=existing,
        quarantined=quarantined,
        trainable=trainable,
        transition_ids=tuple(transition_ids),
    )


def summarize_transitions(
    transitions: tuple[OfflineTransition, ...],
) -> dict[str, object]:
    return {
        "count": len(transitions),
        "trainable": sum(
            1 for row in transitions if row.trainability_status == "trainable"
        ),
        "quarantined": sum(
            1 for row in transitions if row.trainability_status == "quarantined"
        ),
    }
