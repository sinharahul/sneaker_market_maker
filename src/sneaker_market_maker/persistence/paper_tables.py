"""Additive SQLAlchemy tables for Continuous Paper Market-Maker state."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from sneaker_market_maker.persistence.research_tables import metadata

MONEY = Numeric(20, 2)

paper_runs = Table(
    "paper_runs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("dataset_id", String(128), nullable=False),
    Column("dataset_version", String(128), nullable=False),
    Column("checksum_sha256", String(128), nullable=False),
    Column("seed", BigInteger, nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

paper_capital = Table(
    "paper_capital",
    metadata,
    Column("run_id", UUID(as_uuid=True), ForeignKey("paper_runs.id"), primary_key=True),
    Column("initial", MONEY, nullable=False),
    Column("cash", MONEY, nullable=False),
    Column("reserved_buy_principal", MONEY, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

paper_orders = Table(
    "paper_orders",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("run_id", UUID(as_uuid=True), ForeignKey("paper_runs.id"), nullable=False),
    Column("side", String(8), nullable=False),
    Column("price", MONEY, nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("product_family", String(64), nullable=False),
    Column("style_code", String(64), nullable=False),
    Column("shoe_size", MONEY, nullable=False),
    Column("principal", MONEY, nullable=False),
    Column("replaced_order_id", UUID(as_uuid=True), nullable=True),
)

paper_fills = Table(
    "paper_fills",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("run_id", UUID(as_uuid=True), ForeignKey("paper_runs.id"), nullable=False),
    Column("order_id", UUID(as_uuid=True), ForeignKey("paper_orders.id"), nullable=False),
    Column("side", String(8), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("quoted_price", MONEY, nullable=False),
    Column("execution_price", MONEY, nullable=False),
    Column("slippage", MONEY, nullable=False),
    Column("fee_schedule_version", String(64), nullable=False),
    Column("slippage_version", String(64), nullable=False),
    Column("total_fees", MONEY, nullable=False),
    Column("source_event_id", String(128), nullable=False),
    Column("product_family", String(64), nullable=False),
    Column("style_code", String(64), nullable=False),
    Column("shoe_size", MONEY, nullable=False),
    Column("simulation_time", DateTime(timezone=True), nullable=False),
)

paper_lots = Table(
    "paper_lots",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("run_id", UUID(as_uuid=True), ForeignKey("paper_runs.id"), nullable=False),
    Column("product_family", String(64), nullable=False),
    Column("style_code", String(64), nullable=False),
    Column("shoe_size", MONEY, nullable=False),
    Column("landed_cost", MONEY, nullable=False),
    Column("state", String(32), nullable=False),
    Column("source_fill_id", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

paper_audit_events = Table(
    "paper_audit_events",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("run_id", UUID(as_uuid=True), ForeignKey("paper_runs.id"), nullable=False),
    Column("sequence", BigInteger, nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("run_id", "sequence"),
)
