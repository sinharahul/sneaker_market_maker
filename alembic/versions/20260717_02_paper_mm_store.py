"""Create additive Continuous Paper Market-Maker persistence tables.

Revision ID: 20260717_02
Revises: 20260717_01
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260717_02"
down_revision = "20260717_01"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(20, 2)


def upgrade() -> None:
    op.create_table(
        "paper_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", sa.String(128), nullable=False),
        sa.Column("dataset_version", sa.String(128), nullable=False),
        sa.Column("checksum_sha256", sa.String(128), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "paper_capital",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("paper_runs.id"),
            primary_key=True,
        ),
        sa.Column("initial", MONEY, nullable=False),
        sa.Column("cash", MONEY, nullable=False),
        sa.Column("reserved_buy_principal", MONEY, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "paper_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("paper_runs.id"),
            nullable=False,
        ),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("price", MONEY, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("product_family", sa.String(64), nullable=False),
        sa.Column("style_code", sa.String(64), nullable=False),
        sa.Column("shoe_size", MONEY, nullable=False),
        sa.Column("principal", MONEY, nullable=False),
        sa.Column("replaced_order_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_table(
        "paper_fills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("paper_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("paper_orders.id"),
            nullable=False,
        ),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("quoted_price", MONEY, nullable=False),
        sa.Column("execution_price", MONEY, nullable=False),
        sa.Column("slippage", MONEY, nullable=False),
        sa.Column("fee_schedule_version", sa.String(64), nullable=False),
        sa.Column("slippage_version", sa.String(64), nullable=False),
        sa.Column("total_fees", MONEY, nullable=False),
        sa.Column("source_event_id", sa.String(128), nullable=False),
        sa.Column("product_family", sa.String(64), nullable=False),
        sa.Column("style_code", sa.String(64), nullable=False),
        sa.Column("shoe_size", MONEY, nullable=False),
        sa.Column("simulation_time", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "paper_lots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("paper_runs.id"),
            nullable=False,
        ),
        sa.Column("product_family", sa.String(64), nullable=False),
        sa.Column("style_code", sa.String(64), nullable=False),
        sa.Column("shoe_size", MONEY, nullable=False),
        sa.Column("landed_cost", MONEY, nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("source_fill_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "paper_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("paper_runs.id"),
            nullable=False,
        ),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "sequence"),
    )


def downgrade() -> None:
    op.drop_table("paper_audit_events")
    op.drop_table("paper_lots")
    op.drop_table("paper_fills")
    op.drop_table("paper_orders")
    op.drop_table("paper_capital")
    op.drop_table("paper_runs")
