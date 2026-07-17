import json
from dataclasses import replace
from decimal import Decimal

import pytest

from sneaker_market_maker.persistence.research_repository import (
    AddResult,
    InMemoryResearchRepository,
    TransitionConflict,
    TransitionRepository,
)
from sneaker_market_maker.persistence.research_serialization import (
    transition_from_row,
    transition_values,
)
from tests.persistence.fixtures import transition


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


def test_decimal_states_are_recursively_json_safe_strings() -> None:
    item = replace(
        transition(),
        state={
            "inventory": Decimal("1.20"),
            "nested": {"costs": [Decimal("0.10"), Decimal("0.20")]},
        },
        next_state={"inventory": Decimal("2.30")},
    )

    values = transition_values(item)

    assert values["state"] == {
        "inventory": "1.20",
        "nested": {"costs": ["0.10", "0.20"]},
    }
    assert values["next_state"] == {"inventory": "2.30"}
    json.dumps(values["state"])
    json.dumps(values["next_state"])


@pytest.mark.parametrize(
    "missing_field",
    ["effects", "trainability_status", "non_trainable_reason"],
)
def test_deserialization_rejects_missing_persisted_fields(missing_field: str) -> None:
    item = transition()
    row = transition_values(item)
    policy = item.behavior
    row.update(
        {
            "behavior_version": policy.version,
            "behavior_collection_mode": policy.collection_mode,
            "behavior_categorical_propensity": policy.categorical_propensity,
            "behavior_active_continuous_log_density": policy.active_continuous_log_density,
            "behavior_joint_log_propensity": policy.joint_log_propensity,
            "behavior_deterministic": policy.deterministic,
            "behavior_support_method": policy.support_method,
            "behavior_support_version": policy.support_version,
            "behavior_missingness_reason": policy.missingness_reason,
        }
    )
    del row[missing_field]

    with pytest.raises(KeyError, match=missing_field):
        transition_from_row(row)
