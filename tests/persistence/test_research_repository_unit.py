from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from sneaker_market_maker.persistence.research_repository import (
    AddResult,
    InMemoryResearchRepository,
    TransitionConflict,
    TransitionRepository,
)
from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    ActionMask,
    HybridAction,
)
from sneaker_market_maker.research.contracts.transition import (
    BehaviorPolicy,
    OfflineTransition,
    RewardRecord,
)


def transition() -> OfflineTransition:
    action = HybridAction(ActionCategory.QUOTE, 0.5, -1, 1)
    return OfflineTransition(
        transition_id=uuid4(),
        episode_id=uuid4(),
        decision_index=0,
        state={"inventory": 0.0},
        proposed_action=action,
        post_gate_action=action,
        reward=RewardRecord(
            version="reward-v1",
            total=Decimal("1.25"),
            nav_delta=Decimal("1.50"),
            penalties={"inventory": Decimal("0.25")},
            explanatory_costs={"fees": Decimal("0.50")},
            ledger_entry_ids=("ledger-1",),
            reconciled=True,
        ),
        next_state={"inventory": 0.5},
        done=False,
        terminal_reason=None,
        elapsed_seconds=60,
        discount=0.99,
        action_mask=ActionMask(True, True, True),
        action_bounds=ActionBounds(-5, 5, -5, 5),
        behavior=BehaviorPolicy(
            version="behavior-v1",
            collection_mode="stochastic",
            categorical_propensity=0.5,
            active_continuous_log_density=-0.25,
            joint_log_propensity=-0.9431471805599453,
            deterministic=False,
            support_method="bounded-gaussian",
            support_version="support-v1",
            missingness_reason=None,
        ),
        state_schema_version="state-v1",
        action_schema_version="action-v1",
        reward_schema_version="reward-v1",
        source_record_ids=("source-sha256",),
        provenance_label="historical",
        dataset_version="dataset-v1",
        scenario_version="scenario-v1",
        simulator_version="simulator-v1",
        gate_policy_version="gate-v1",
        code_revision="abc123",
        random_seed=7,
        content_hash="content-sha256",
    )


def repository() -> TransitionRepository:
    return InMemoryResearchRepository()


def test_first_insert_creates_and_can_be_read() -> None:
    repo = repository()
    item = transition()

    assert repo.add_transition(item) is AddResult.CREATED
    assert repo.get_transition(item.transition_id) == item


def test_identical_identity_and_hash_is_idempotent() -> None:
    repo = repository()
    item = transition()
    assert repo.add_transition(item) is AddResult.CREATED

    assert repo.add_transition(item) is AddResult.EXISTING


def test_same_identity_with_different_hash_fails_closed() -> None:
    repo = repository()
    item = transition()
    assert repo.add_transition(item) is AddResult.CREATED

    with pytest.raises(TransitionConflict, match="immutable transition identity"):
        repo.add_transition(replace(item, content_hash="different-sha256"))
