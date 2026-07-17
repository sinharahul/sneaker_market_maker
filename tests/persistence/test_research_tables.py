from sqlalchemy import ForeignKeyConstraint, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from sneaker_market_maker.persistence.research_tables import (
    action_schemas,
    decision_points,
    mdp_state_schemas,
    offline_transitions,
    reward_schemas,
)


def _unique_columns(table: object) -> set[tuple[str, ...]]:
    constraints = table.constraints  # type: ignore[attr-defined]
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _foreign_key_paths() -> set[tuple[tuple[str, ...], tuple[str, ...]]]:
    return {
        (
            tuple(column.name for column in constraint.columns),
            tuple(element.target_fullname for element in constraint.elements),
        )
        for constraint in offline_transitions.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }


def test_transition_lineage_foreign_keys_are_complete() -> None:
    assert _foreign_key_paths() >= {
        (("behavior_policy_id",), ("behavior_policies.id",)),
        (
            ("episode_id", "decision_index"),
            ("decision_points.episode_id", "decision_points.decision_index"),
        ),
        (("state_schema_version",), ("mdp_state_schemas.version",)),
        (("action_schema_version",), ("action_schemas.version",)),
        (("reward_schema_version",), ("reward_schemas.version",)),
    }


def test_foreign_key_targets_have_unique_keys() -> None:
    assert ("episode_id", "decision_index") in _unique_columns(decision_points)
    for table in (mdp_state_schemas, action_schemas, reward_schemas):
        assert ("version",) in _unique_columns(table)


def test_transition_identity_is_unique() -> None:
    assert (
        "episode_id",
        "decision_index",
        "state_schema_version",
        "action_schema_version",
        "reward_schema_version",
    ) in _unique_columns(offline_transitions)


def test_transition_money_and_payload_types_are_postgresql_native() -> None:
    for column_name in ("reward_total", "nav_delta"):
        column_type = offline_transitions.c[column_name].type
        assert isinstance(column_type, Numeric)
        assert (column_type.precision, column_type.scale) == (38, 18)

    for column_name in (
        "state",
        "proposed_action",
        "post_gate_action",
        "reward",
        "next_state",
        "action_mask",
        "action_bounds",
        "source_record_ids",
    ):
        assert isinstance(offline_transitions.c[column_name].type, JSONB)
