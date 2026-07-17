from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from sneaker_market_maker.persistence.research_repository import (
    AddResult,
    InMemoryResearchRepository,
)
from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    ActionMask,
    HybridAction,
)
from sneaker_market_maker.research.contracts.transition import BehaviorPolicy, RewardRecord
from sneaker_market_maker.research.episodes.events import DecisionPoint, EventKind
from sneaker_market_maker.research.transitions.service import (
    StepEffects,
    TransitionInput,
    TransitionLineage,
    TransitionService,
)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def point(index: int, inventory: Decimal, *, terminal_reason: str | None = None) -> DecisionPoint:
    return DecisionPoint(
        episode_id=EPISODE_ID,
        index=index,
        simulation_time=START + timedelta(minutes=index),
        elapsed_seconds=60,
        reasons=(EventKind.FILL,),
        source_ids=(f"event-{index}",),
        provenances=("historical",),
        discount=0.99,
        state={"inventory": inventory, "cash": Decimal("100.00") - inventory},
        action_mask=ActionMask(True, True, True),
        action_bounds=ActionBounds(-5, 5, -5, 5),
        terminal_reason=terminal_reason,
    )


EPISODE_ID = uuid4()
ACTION = HybridAction(ActionCategory.QUOTE, 0.5, -1, 1)
POST_GATE_ACTION = HybridAction(ActionCategory.CANCEL, 0.0, 0, 0)
BEHAVIOR = BehaviorPolicy(
    version="behavior-v1",
    collection_mode="stochastic",
    categorical_propensity=0.5,
    active_continuous_log_density=-0.25,
    joint_log_propensity=-0.9431471805599453,
    deterministic=False,
    support_method="bounded-gaussian",
    support_version="support-v1",
    missingness_reason=None,
)
REWARD = RewardRecord(
    version="reward-v1",
    total=Decimal("1.25"),
    nav_delta=Decimal("1.50"),
    penalties={"inventory": Decimal("0.25")},
    explanatory_costs={"fees": Decimal("0.50")},
    ledger_entry_ids=("ledger-1",),
    reconciled=True,
)
EFFECTS = StepEffects(
    order_ids=("order-1",),
    fill_ids=("fill-1",),
    fee_ledger_ids=("fee-1",),
    inventory_transition_ids=("inventory-1",),
    logistics_transition_ids=("logistics-1",),
    settlement_ids=("settlement-1",),
)
LINEAGE = TransitionLineage(
    state_schema_version="state-v1",
    action_schema_version="action-v1",
    reward_schema_version="reward-v1",
    dataset_version="dataset-v1",
    scenario_version="scenario-v1",
    simulator_version="simulator-v1",
    gate_policy_version="gate-v1",
    code_revision="abc123",
    random_seed=7,
    provenance_label="historical",
)


def transition_input(**overrides: object) -> TransitionInput:
    values = {
        "current": point(0, Decimal("0")),
        "next": point(1, Decimal("1")),
        "proposed_action": ACTION,
        "post_gate_action": POST_GATE_ACTION,
        "behavior": BEHAVIOR,
        "reward": REWARD,
        "effects": EFFECTS,
        "lineage": LINEAGE,
    }
    values.update(overrides)
    return TransitionInput(**values)  # type: ignore[arg-type]


def test_records_complete_adjacent_transition_and_attribution() -> None:
    repository = InMemoryResearchRepository()
    service = TransitionService(repository)

    assert service.record(transition_input()) is AddResult.CREATED
    transition = repository.transitions[0]

    assert transition.state["inventory"] == Decimal("0")
    assert transition.next_state["inventory"] == Decimal("1")
    assert transition.elapsed_seconds == 60
    assert transition.discount == 0.99
    assert transition.proposed_action == ACTION
    assert transition.post_gate_action == POST_GATE_ACTION
    assert transition.proposed_action != transition.post_gate_action
    assert transition.behavior is BEHAVIOR
    assert transition.effects == EFFECTS
    assert transition.source_record_ids == ("event-0", "event-1", *EFFECTS.all_ids)
    assert transition.trainability_status == "trainable"


def test_terminal_linkage_comes_from_next_decision() -> None:
    repository = InMemoryResearchRepository()
    terminal = point(1, Decimal("0"), terminal_reason="replay_exhausted")

    TransitionService(repository).record(transition_input(next=terminal))
    transition = repository.transitions[0]

    assert transition.done is True
    assert transition.terminal_reason == "replay_exhausted"
    assert transition.next_state == terminal.state


def test_hash_is_atomic_canonical_and_decimal_sensitive() -> None:
    first_repository = InMemoryResearchRepository()
    second_repository = InMemoryResearchRepository()
    first = transition_input()
    reordered = replace(
        first,
        current=replace(
            first.current,
            state={"cash": Decimal("100.00"), "inventory": Decimal("0")},
        ),
    )

    TransitionService(first_repository).record(first)
    TransitionService(second_repository).record(reordered)
    first_transition = first_repository.transitions[0]
    second_transition = second_repository.transitions[0]
    assert first_transition.content_hash == second_transition.content_hash

    changed_repository = InMemoryResearchRepository()
    changed = replace(first, reward=replace(first.reward, total=Decimal("1.250")))
    TransitionService(changed_repository).record(changed)
    assert changed_repository.transitions[0].content_hash != first_transition.content_hash


def test_retry_is_idempotent() -> None:
    repository = InMemoryResearchRepository()
    service = TransitionService(repository)
    item = transition_input()

    assert service.record(item) is AddResult.CREATED
    assert service.record(item) is AddResult.EXISTING
    assert len(repository.transitions) == 1


def test_unreconciled_reward_is_quarantined_with_stable_reason() -> None:
    repository = InMemoryResearchRepository()
    item = transition_input(reward=replace(REWARD, reconciled=False))

    assert TransitionService(repository).record(item) is AddResult.CREATED
    transition = repository.transitions[0]
    assert transition.trainability_status == "quarantined"
    assert transition.non_trainable_reason == "reward is not reconciled"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        (
            {
                "behavior": replace(
                    BEHAVIOR,
                    categorical_propensity=None,
                    active_continuous_log_density=None,
                    joint_log_propensity=None,
                    missingness_reason="legacy source omitted propensity",
                )
            },
            "behavior propensity is missing",
        ),
        (
            {"effects": replace(EFFECTS, logistics_transition_ids=())},
            "logistics outcomes are missing",
        ),
    ],
)
def test_legacy_missingness_is_quarantined_without_invented_values(
    changes: dict[str, object],
    reason: str,
) -> None:
    repository = InMemoryResearchRepository()

    TransitionService(repository).record(transition_input(**changes))
    transition = repository.transitions[0]

    assert transition.trainability_status == "quarantined"
    assert transition.non_trainable_reason == reason
    if "behavior" in changes:
        assert transition.behavior.categorical_propensity is None
    else:
        assert transition.effects.logistics_transition_ids == ()


def test_repository_failure_is_not_caught() -> None:
    class FailingRepository(InMemoryResearchRepository):
        def add_transition(self, transition):  # type: ignore[no-untyped-def]
            raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        TransitionService(FailingRepository()).record(transition_input())
