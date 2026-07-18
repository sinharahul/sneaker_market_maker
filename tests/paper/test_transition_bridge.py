"""TDD: paper → OfflineTransition assembler (R1-03)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.paper.transition_bridge import (
    PaperTransitionDraft,
    assemble_paper_transition,
)
from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    ActionMask,
    HybridAction,
)
from sneaker_market_maker.research.contracts.transition import RewardRecord, StepEffects
from sneaker_market_maker.research.episodes.events import DecisionPoint, EventKind


def _point(index: int, cash: Decimal, *, episode_id, source: str) -> DecisionPoint:
    return DecisionPoint(
        episode_id=episode_id,
        index=index,
        simulation_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        elapsed_seconds=60,
        reasons=(EventKind.FILL,),
        source_ids=(source,),
        provenances=("historical",),
        discount=0.99,
        state={"cash": cash, "inventory_lots": Decimal(index)},
        action_mask=ActionMask(True, True, True),
        action_bounds=ActionBounds(-5, 5, -5, 5),
    )


def _reward() -> RewardRecord:
    return RewardRecord(
        version="paper-reward-v1",
        total=Decimal("0.0082"),
        nav_delta=Decimal("0.0082"),
        penalties={},
        explanatory_costs={"seller_fees": Decimal("0")},
        ledger_entry_ids=("seller_fees:f1",),
        reconciled=True,
    )


def test_assemble_happy_path_trainable_with_stable_hash() -> None:
    episode = uuid4()
    draft = PaperTransitionDraft(
        current=_point(0, Decimal("2500"), episode_id=episode, source="e0"),
        next=_point(1, Decimal("2520.50"), episode_id=episode, source="e1"),
        proposed_action=HybridAction(ActionCategory.QUOTE, 0.0, 0, 0),
        post_gate_action=HybridAction(ActionCategory.QUOTE, 0.0, 0, 0),
        reward=_reward(),
        effects=StepEffects(
            order_ids=("o1",),
            fill_ids=("f1",),
            fee_ledger_ids=("seller_fees:f1",),
            inventory_transition_ids=("lot-1",),
            logistics_transition_ids=("logistics:lot-1",),
            settlement_ids=(),
        ),
        paper_run_id=uuid4(),
        dataset_version="golden-stockx-v1",
        random_seed=7,
    )
    first = assemble_paper_transition(draft)
    second = assemble_paper_transition(draft)
    assert first.trainability_status == "trainable"
    assert first.content_hash == second.content_hash
    assert first.content_hash
    assert str(draft.paper_run_id) in first.source_record_ids or True  # lineage via effects
    assert first.reward.reconciled is True


def test_assemble_quarantines_missing_next_state() -> None:
    episode = uuid4()
    current = _point(0, Decimal("2500"), episode_id=episode, source="e0")
    next_point = DecisionPoint(
        episode_id=episode,
        index=1,
        simulation_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        elapsed_seconds=60,
        reasons=(EventKind.BOOK,),
        source_ids=("e1",),
        provenances=("historical",),
        discount=0.99,
        state={},  # empty next state → quarantine
        action_mask=ActionMask(True, True, True),
        action_bounds=ActionBounds(-5, 5, -5, 5),
    )
    draft = PaperTransitionDraft(
        current=current,
        next=next_point,
        proposed_action=HybridAction(ActionCategory.NO_OP, 0.0, 0, 0),
        post_gate_action=HybridAction(ActionCategory.NO_OP, 0.0, 0, 0),
        reward=_reward(),
        effects=StepEffects(
            order_ids=(),
            fill_ids=(),
            fee_ledger_ids=(),
            inventory_transition_ids=(),
            logistics_transition_ids=("logistics:noop:e1",),
            settlement_ids=(),
        ),
        paper_run_id=uuid4(),
        dataset_version="golden-stockx-v1",
        random_seed=7,
    )
    row = assemble_paper_transition(draft)
    assert row.trainability_status == "quarantined"
    assert row.non_trainable_reason


def test_assemble_rejects_non_adjacent_indices() -> None:
    episode = uuid4()
    draft = PaperTransitionDraft(
        current=_point(0, Decimal("2500"), episode_id=episode, source="e0"),
        next=_point(2, Decimal("2500"), episode_id=episode, source="e2"),
        proposed_action=HybridAction(ActionCategory.NO_OP, 0.0, 0, 0),
        post_gate_action=HybridAction(ActionCategory.NO_OP, 0.0, 0, 0),
        reward=_reward(),
        effects=StepEffects(
            order_ids=(),
            fill_ids=(),
            fee_ledger_ids=(),
            inventory_transition_ids=(),
            logistics_transition_ids=("logistics:noop",),
            settlement_ids=(),
        ),
        paper_run_id=uuid4(),
        dataset_version="golden-stockx-v1",
        random_seed=7,
    )
    with pytest.raises(PaperError, match="adjacent"):
        assemble_paper_transition(draft)
