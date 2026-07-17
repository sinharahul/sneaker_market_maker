"""Create the additive research persistence subsystem.

Revision ID: 20260717_01
Revises:
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260717_01"
down_revision = None
branch_labels = None
depends_on = None


def _evidence_table(
    name: str,
    *columns: sa.Column[object],
    unique_version: bool = False,
) -> None:
    constraints = (sa.UniqueConstraint("version"),) if unique_version else ()
    op.create_table(
        name,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *columns,
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        *constraints,
    )


def upgrade() -> None:
    """Create only the research subsystem tables in dependency order."""
    jsonb = postgresql.JSONB
    uuid = postgresql.UUID
    _evidence_table(
        "mdp_state_schemas",
        sa.Column("payload", jsonb(), nullable=False),
        unique_version=True,
    )
    _evidence_table(
        "action_schemas",
        sa.Column("payload", jsonb(), nullable=False),
        unique_version=True,
    )
    _evidence_table(
        "reward_schemas",
        sa.Column("payload", jsonb(), nullable=False),
        unique_version=True,
    )
    _evidence_table(
        "encoder_versions",
        sa.Column(
            "state_schema_id",
            uuid(as_uuid=True),
            sa.ForeignKey("mdp_state_schemas.id"),
            nullable=False,
        ),
        sa.Column("payload", jsonb(), nullable=False),
        sa.Column("artifact_hash", sa.String(128), nullable=False),
        unique_version=True,
    )
    _evidence_table(
        "episode_manifests",
        sa.Column("dataset_version", sa.String(128), nullable=False),
        sa.Column("scenario_version", sa.String(128), nullable=False),
        sa.Column("simulator_version", sa.String(128), nullable=False),
        sa.Column("source_window", jsonb(), nullable=False),
        sa.Column("split", sa.String(32), nullable=False),
        sa.Column("fold", sa.String(64), nullable=False),
        sa.Column("random_seed", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("provenance_label", sa.String(32), nullable=False),
    )
    _evidence_table(
        "decision_points",
        sa.Column(
            "episode_id",
            uuid(as_uuid=True),
            sa.ForeignKey("episode_manifests.id"),
            nullable=False,
        ),
        sa.Column("decision_index", sa.Integer(), nullable=False),
        sa.Column("event_reason", sa.String(128), nullable=False),
        sa.Column("maintenance_coalesced", sa.Boolean(), nullable=False),
        sa.Column("source_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("simulation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("wall_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("elapsed_seconds", sa.Integer(), nullable=False),
        sa.UniqueConstraint("episode_id", "decision_index"),
    )
    _evidence_table(
        "behavior_policies",
        sa.Column("collection_mode", sa.String(64), nullable=False),
        sa.Column("categorical_propensity", sa.Float()),
        sa.Column("active_continuous_log_density", sa.Float()),
        sa.Column("joint_log_propensity", sa.Float()),
        sa.Column("deterministic", sa.Boolean(), nullable=False),
        sa.Column("support_method", sa.String(128), nullable=False),
        sa.Column("support_version", sa.String(128), nullable=False),
        sa.Column("missingness_reason", sa.Text()),
    )
    op.create_table(
        "offline_transitions",
        sa.Column("id", uuid(as_uuid=True), primary_key=True),
        sa.Column("episode_id", uuid(as_uuid=True), nullable=False),
        sa.Column("decision_index", sa.Integer(), nullable=False),
        sa.Column(
            "behavior_policy_id",
            uuid(as_uuid=True),
            sa.ForeignKey("behavior_policies.id"),
            nullable=False,
        ),
        sa.Column("state", jsonb(), nullable=False),
        sa.Column("proposed_action", jsonb(), nullable=False),
        sa.Column("post_gate_action", jsonb(), nullable=False),
        sa.Column("reward", jsonb(), nullable=False),
        sa.Column("reward_total", sa.Numeric(38, 18), nullable=False),
        sa.Column("nav_delta", sa.Numeric(38, 18), nullable=False),
        sa.Column("next_state", jsonb(), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False),
        sa.Column("terminal_reason", sa.String(128)),
        sa.Column("elapsed_seconds", sa.Integer(), nullable=False),
        sa.Column("discount", sa.Float(), nullable=False),
        sa.Column("action_mask", jsonb(), nullable=False),
        sa.Column("action_bounds", jsonb(), nullable=False),
        sa.Column("state_schema_version", sa.String(128), nullable=False),
        sa.Column("action_schema_version", sa.String(128), nullable=False),
        sa.Column("reward_schema_version", sa.String(128), nullable=False),
        sa.Column("source_record_ids", jsonb(), nullable=False),
        sa.Column("provenance_label", sa.String(32), nullable=False),
        sa.Column("dataset_version", sa.String(128), nullable=False),
        sa.Column("scenario_version", sa.String(128), nullable=False),
        sa.Column("simulator_version", sa.String(128), nullable=False),
        sa.Column("gate_policy_version", sa.String(128), nullable=False),
        sa.Column("code_revision", sa.String(128), nullable=False),
        sa.Column("random_seed", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.UniqueConstraint(
            "episode_id",
            "decision_index",
            "state_schema_version",
            "action_schema_version",
            "reward_schema_version",
            name="uq_offline_transitions_identity",
        ),
    )
    _evidence_table(
        "research_runs",
        sa.Column("configuration", jsonb(), nullable=False),
        sa.Column("environment_lock", jsonb(), nullable=False),
        sa.Column("lineage_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    )
    _evidence_table(
        "research_artifacts",
        sa.Column(
            "run_id",
            uuid(as_uuid=True),
            sa.ForeignKey("research_runs.id"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("payload", jsonb(), nullable=False),
    )
    _evidence_table(
        "registry_models",
        sa.Column(
            "run_id",
            uuid(as_uuid=True),
            sa.ForeignKey("research_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            uuid(as_uuid=True),
            sa.ForeignKey("research_artifacts.id"),
            nullable=False,
        ),
        sa.Column("compatibility_contract", jsonb(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("benchmark_report", jsonb(), nullable=False),
        sa.Column("approvals", jsonb(), nullable=False),
        sa.Column("rollback_reason", sa.Text()),
        unique_version=True,
    )
    _evidence_table(
        "registry_status_history",
        sa.Column(
            "model_id",
            uuid(as_uuid=True),
            sa.ForeignKey("registry_models.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    _evidence_table(
        "recommendations",
        sa.Column(
            "decision_point_id",
            uuid(as_uuid=True),
            sa.ForeignKey("decision_points.id"),
            nullable=False,
        ),
        sa.Column("model_id", uuid(as_uuid=True), sa.ForeignKey("registry_models.id")),
        sa.Column("deterministic_action", jsonb(), nullable=False),
        sa.Column("pfhedge_result", jsonb(), nullable=False),
        sa.Column("iql_shadow_action", jsonb(), nullable=False),
        sa.Column("canonical_action", jsonb(), nullable=False),
        sa.Column("gate_results", jsonb(), nullable=False),
        sa.Column("final_action", jsonb(), nullable=False),
        sa.Column("fallback", jsonb(), nullable=False),
        sa.Column("latency_ms", sa.Numeric(38, 18), nullable=False),
        sa.Column("outcome", jsonb(), nullable=False),
    )


def downgrade() -> None:
    """Drop only the research subsystem tables in reverse FK order."""
    for table_name in (
        "recommendations",
        "registry_status_history",
        "registry_models",
        "research_artifacts",
        "research_runs",
        "offline_transitions",
        "behavior_policies",
        "decision_points",
        "episode_manifests",
        "encoder_versions",
        "reward_schemas",
        "action_schemas",
        "mdp_state_schemas",
    ):
        op.drop_table(table_name)
