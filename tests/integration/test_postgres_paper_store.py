"""Postgres integration: paper book survives restart via Authoritative Store."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import inspect

from alembic import command
from sneaker_market_maker.paper.capital import PaperCapital
from sneaker_market_maker.paper.intents import Side
from sneaker_market_maker.paper.inventory import LotState
from sneaker_market_maker.paper.orders import OrderStatus
from sneaker_market_maker.persistence.database import create_session_factory
from sneaker_market_maker.persistence.paper_repository import (
    PaperBookSnapshot,
    PersistedFill,
    PersistedLot,
    PersistedOrder,
    SqlAlchemyPaperStore,
)
from tests.integration.postgres_fixtures import DATABASE_URL, alembic_config

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL is required"),
]


def test_paper_tables_present_after_migration(engine) -> None:
    command.upgrade(alembic_config(), "head")
    names = set(inspect(engine).get_table_names())
    for table in (
        "paper_runs",
        "paper_capital",
        "paper_orders",
        "paper_fills",
        "paper_lots",
        "paper_audit_events",
    ):
        assert table in names


def test_paper_book_survives_new_session_and_audit_is_append_only(engine, session_factory) -> None:
    store = SqlAlchemyPaperStore(session_factory)
    run_id = store.create_run(
        dataset_id="golden-stockx-v1",
        dataset_version="1.0.0",
        checksum_sha256="deadbeef",
        seed=42,
    )
    order_id = uuid4()
    fill_id = uuid4()
    lot_id = uuid4()
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    snapshot = PaperBookSnapshot(
        run_id=run_id,
        capital=PaperCapital(
            initial=Decimal("2500.00"),
            cash=Decimal("2295.00"),
            reserved_buy_principal=Decimal("0.00"),
        ),
        orders=(
            PersistedOrder(
                order_id=order_id,
                side=Side.BUY,
                price=Decimal("200.00"),
                quantity=1,
                status=OrderStatus.FILLED,
                product_family="jordan_1_retro",
                style_code="555088-001",
                shoe_size=Decimal("10.00"),
                principal=Decimal("200.00"),
                replaced_order_id=None,
            ),
        ),
        fills=(
            PersistedFill(
                fill_id=fill_id,
                order_id=order_id,
                side=Side.BUY,
                quantity=1,
                quoted_price=Decimal("200.00"),
                execution_price=Decimal("200.00"),
                slippage=Decimal("1.00"),
                fee_schedule_version="fees-v1",
                slippage_version="slippage-v1",
                total_fees=Decimal("5.00"),
                source_event_id="m1",
                product_family="jordan_1_retro",
                style_code="555088-001",
                shoe_size=Decimal("10.00"),
                simulation_time=now,
            ),
        ),
        lots=(
            PersistedLot(
                lot_id=lot_id,
                product_family="jordan_1_retro",
                style_code="555088-001",
                shoe_size=Decimal("10.00"),
                landed_cost=Decimal("205.00"),
                state=LotState.AVAILABLE,
                source_fill_id=str(fill_id),
                created_at=now,
            ),
        ),
    )
    store.save_book(snapshot)
    store.append_audit(run_id, "gate.accepted", {"intent": "place", "side": "buy"})
    store.append_audit(run_id, "lot.transition", {"to": "available"})

    # New store instance simulates process restart against the same Postgres.
    restarted = SqlAlchemyPaperStore(create_session_factory(engine))
    loaded = restarted.load_book(run_id)
    assert loaded is not None
    assert loaded.capital.cash == Decimal("2295.00")
    assert type(loaded.capital.cash) is Decimal
    assert len(loaded.orders) == 1
    assert loaded.orders[0].status is OrderStatus.FILLED
    assert len(loaded.fills) == 1
    assert loaded.fills[0].total_fees == Decimal("5.00")
    assert loaded.lots[0].state is LotState.AVAILABLE

    audit = restarted.list_audit(run_id)
    assert [event.event_type for event in audit] == ["gate.accepted", "lot.transition"]
    assert audit[0].sequence == 1
    assert audit[1].sequence == 2
