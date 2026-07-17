"""Additive SQLAlchemy Core tables for immutable research evidence."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData(
    naming_convention={
        "pk": "pk_%(table_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
    }
)

def evidence_columns() -> tuple[Column[object], ...]:
    return (
        Column("version", String(128), nullable=False),
        Column("content_hash", String(128), nullable=False),
        Column("provenance", JSONB, nullable=False),
    )


def evidence_table(name: str, *columns: Column[object], unique_version: bool = False) -> Table:
    constraints = (UniqueConstraint("version"),) if unique_version else ()
    return Table(
        name,
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True),
        *columns,
        *evidence_columns(),
        *constraints,
    )


mdp_state_schemas = evidence_table(
    "mdp_state_schemas",
    Column("payload", JSONB, nullable=False),
    unique_version=True,
)
action_schemas = evidence_table(
    "action_schemas",
    Column("payload", JSONB, nullable=False),
    unique_version=True,
)
reward_schemas = evidence_table(
    "reward_schemas",
    Column("payload", JSONB, nullable=False),
    unique_version=True,
)
encoder_versions = evidence_table(
    "encoder_versions",
    Column(
        "state_schema_id",
        UUID(as_uuid=True),
        ForeignKey("mdp_state_schemas.id"),
        nullable=False,
    ),
    Column("payload", JSONB, nullable=False),
    Column("artifact_hash", String(128), nullable=False),
    unique_version=True,
)
episode_manifests = evidence_table(
    "episode_manifests",
    Column("dataset_version", String(128), nullable=False),
    Column("scenario_version", String(128), nullable=False),
    Column("simulator_version", String(128), nullable=False),
    Column("source_window", JSONB, nullable=False),
    Column("split", String(32), nullable=False),
    Column("fold", String(64), nullable=False),
    Column("random_seed", BigInteger, nullable=False),
    Column("checksum", String(128), nullable=False),
    Column("provenance_label", String(32), nullable=False),
)
decision_points = evidence_table(
    "decision_points",
    Column("episode_id", UUID(as_uuid=True), ForeignKey("episode_manifests.id"), nullable=False),
    Column("decision_index", Integer, nullable=False),
    Column("event_reason", String(128), nullable=False),
    Column("maintenance_coalesced", Boolean, nullable=False),
    Column("source_time", DateTime(timezone=True), nullable=False),
    Column("simulation_time", DateTime(timezone=True), nullable=False),
    Column("wall_time", DateTime(timezone=True), nullable=False),
    Column("elapsed_seconds", Integer, nullable=False),
    UniqueConstraint("episode_id", "decision_index"),
)
behavior_policies = evidence_table(
    "behavior_policies",
    Column("collection_mode", String(64), nullable=False),
    Column("categorical_propensity", Float),
    Column("active_continuous_log_density", Float),
    Column("joint_log_propensity", Float),
    Column("deterministic", Boolean, nullable=False),
    Column("support_method", String(128), nullable=False),
    Column("support_version", String(128), nullable=False),
    Column("missingness_reason", Text),
)
offline_transitions = Table(
    "offline_transitions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("episode_id", UUID(as_uuid=True), nullable=False),
    Column("decision_index", Integer, nullable=False),
    Column(
        "behavior_policy_id",
        UUID(as_uuid=True),
        ForeignKey("behavior_policies.id"),
        nullable=False,
    ),
    Column("state", JSONB, nullable=False),
    Column("proposed_action", JSONB, nullable=False),
    Column("post_gate_action", JSONB, nullable=False),
    Column("reward", JSONB, nullable=False),
    Column("reward_total", Numeric(38, 18), nullable=False),
    Column("nav_delta", Numeric(38, 18), nullable=False),
    Column("next_state", JSONB, nullable=False),
    Column("done", Boolean, nullable=False),
    Column("terminal_reason", String(128)),
    Column("elapsed_seconds", Integer, nullable=False),
    Column("discount", Float, nullable=False),
    Column("action_mask", JSONB, nullable=False),
    Column("action_bounds", JSONB, nullable=False),
    Column("state_schema_version", String(128), nullable=False),
    Column("action_schema_version", String(128), nullable=False),
    Column("reward_schema_version", String(128), nullable=False),
    Column("source_record_ids", JSONB, nullable=False),
    Column("provenance_label", String(32), nullable=False),
    Column("dataset_version", String(128), nullable=False),
    Column("scenario_version", String(128), nullable=False),
    Column("simulator_version", String(128), nullable=False),
    Column("gate_policy_version", String(128), nullable=False),
    Column("code_revision", String(128), nullable=False),
    Column("random_seed", BigInteger, nullable=False),
    Column("content_hash", String(128), nullable=False),
    UniqueConstraint(
        "episode_id",
        "decision_index",
        "state_schema_version",
        "action_schema_version",
        "reward_schema_version",
        name="uq_offline_transitions_identity",
    ),
)
research_runs = evidence_table(
    "research_runs",
    Column("configuration", JSONB, nullable=False),
    Column("environment_lock", JSONB, nullable=False),
    Column("lineage_hash", String(128), nullable=False),
    Column("status", String(32), nullable=False),
)
research_artifacts = evidence_table(
    "research_artifacts",
    Column("run_id", UUID(as_uuid=True), ForeignKey("research_runs.id"), nullable=False),
    Column("artifact_type", String(64), nullable=False),
    Column("location", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
)
registry_models = evidence_table(
    "registry_models",
    Column("run_id", UUID(as_uuid=True), ForeignKey("research_runs.id"), nullable=False),
    Column("artifact_id", UUID(as_uuid=True), ForeignKey("research_artifacts.id"), nullable=False),
    Column("compatibility_contract", JSONB, nullable=False),
    Column("state", String(32), nullable=False),
    Column("benchmark_report", JSONB, nullable=False),
    Column("approvals", JSONB, nullable=False),
    Column("rollback_reason", Text),
    unique_version=True,
)
registry_status_history = evidence_table(
    "registry_status_history",
    Column("model_id", UUID(as_uuid=True), ForeignKey("registry_models.id"), nullable=False),
    Column("status", String(32), nullable=False),
    Column("reason", Text),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
)
recommendations = evidence_table(
    "recommendations",
    Column(
        "decision_point_id",
        UUID(as_uuid=True),
        ForeignKey("decision_points.id"),
        nullable=False,
    ),
    Column("model_id", UUID(as_uuid=True), ForeignKey("registry_models.id")),
    Column("deterministic_action", JSONB, nullable=False),
    Column("pfhedge_result", JSONB, nullable=False),
    Column("iql_shadow_action", JSONB, nullable=False),
    Column("canonical_action", JSONB, nullable=False),
    Column("gate_results", JSONB, nullable=False),
    Column("final_action", JSONB, nullable=False),
    Column("fallback", JSONB, nullable=False),
    Column("latency_ms", Numeric(38, 18), nullable=False),
    Column("outcome", JSONB, nullable=False),
)
