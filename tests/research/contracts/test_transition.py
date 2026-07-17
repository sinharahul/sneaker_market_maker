from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

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


def complete_transition() -> OfflineTransition:
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


def test_complete_transition_is_trainable() -> None:
    complete_transition().validate_trainable()


def test_missing_next_state_is_rejected() -> None:
    with pytest.raises(ValueError, match="next state is required"):
        replace(complete_transition(), next_state={}).validate_trainable()


def test_unreconciled_reward_is_rejected() -> None:
    transition = complete_transition()
    reward = replace(transition.reward, reconciled=False)
    with pytest.raises(ValueError, match="reward is not reconciled"):
        replace(transition, reward=reward).validate_trainable()


@pytest.mark.parametrize(
    "field",
    ["state_schema_version", "action_schema_version", "reward_schema_version"],
)
def test_absent_schema_version_is_rejected(field: str) -> None:
    with pytest.raises(ValueError, match="schema versions are required"):
        replace(complete_transition(), **{field: ""}).validate_trainable()


@pytest.mark.parametrize(
    "changes",
    [{"source_record_ids": ()}, {"content_hash": ""}],
)
def test_missing_source_hashes_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="provenance is incomplete"):
        replace(complete_transition(), **changes).validate_trainable()


@pytest.mark.parametrize(
    ("done", "terminal_reason"),
    [(True, None), (False, "inventory_limit")],
)
def test_terminal_reason_must_match_done(
    done: bool,
    terminal_reason: str | None,
) -> None:
    with pytest.raises(ValueError, match="terminal reason must match done"):
        replace(
            complete_transition(),
            done=done,
            terminal_reason=terminal_reason,
        ).validate_trainable()


def test_deterministic_policy_rejects_nonzero_density() -> None:
    with pytest.raises(ValueError, match="deterministic propensity values must be absent"):
        BehaviorPolicy(
            version="behavior-v1",
            collection_mode="deterministic",
            categorical_propensity=None,
            active_continuous_log_density=0.1,
            joint_log_propensity=None,
            deterministic=True,
            support_method="point-mass",
            support_version="support-v1",
            missingness_reason="policy is deterministic",
        )


def test_deterministic_policy_requires_missingness_reason() -> None:
    with pytest.raises(ValueError, match="missingness reason"):
        replace(
            complete_transition().behavior,
            deterministic=True,
            categorical_propensity=None,
            active_continuous_log_density=None,
            joint_log_propensity=None,
            missingness_reason=None,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"categorical_propensity": None},
        {"categorical_propensity": 0.0},
        {"categorical_propensity": float("nan")},
        {"active_continuous_log_density": float("inf")},
        {"joint_log_propensity": float("-inf")},
    ],
)
def test_stochastic_policy_requires_valid_propensities(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="propensity"):
        replace(complete_transition().behavior, **changes)
