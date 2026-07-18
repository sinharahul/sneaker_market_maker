"""Unit tests for paper Authoritative Store (in-memory double)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sneaker_market_maker.paper.capital import PaperCapital
from sneaker_market_maker.paper.intents import Side
from sneaker_market_maker.paper.inventory import LotState
from sneaker_market_maker.paper.orders import OrderStatus
from sneaker_market_maker.persistence.paper_repository import (
    InMemoryPaperStore,
    PaperBookSnapshot,
    PersistedFill,
    PersistedLot,
    PersistedOrder,
)


def test_in_memory_save_load_and_append_only_audit() -> None:
    store = InMemoryPaperStore()
    run_id = store.create_run(
        dataset_id="golden-stockx-v1",
        dataset_version="1.0.0",
        checksum_sha256="abc",
        seed=7,
    )
    order_id = uuid4()
    fill_id = uuid4()
    lot_id = uuid4()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
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
                slippage=Decimal("0.00"),
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
                state=LotState.PURCHASED,
                source_fill_id=str(fill_id),
                created_at=now,
            ),
        ),
    )
    store.save_book(snapshot)
    loaded = store.load_book(run_id)
    assert loaded == snapshot

    seq1 = store.append_audit(run_id, "intent.place", {"side": "buy", "price": "200.00"})
    seq2 = store.append_audit(run_id, "fill.created", {"fill_id": str(fill_id)})
    assert seq1 == 1 and seq2 == 2
    events = store.list_audit(run_id, after_sequence=1)
    assert len(events) == 1
    assert events[0].event_type == "fill.created"
    assert events[0].payload["fill_id"] == str(fill_id)


def test_money_fields_stay_decimal_not_float() -> None:
    store = InMemoryPaperStore()
    run_id = store.create_run(
        dataset_id="golden-stockx-v1",
        dataset_version="1.0.0",
        checksum_sha256="abc",
        seed=1,
    )
    snapshot = PaperBookSnapshot(
        run_id=run_id,
        capital=PaperCapital.initial_state(),
        orders=(),
        fills=(),
        lots=(),
    )
    store.save_book(snapshot)
    loaded = store.load_book(run_id)
    assert loaded is not None
    assert type(loaded.capital.cash) is Decimal
    assert not isinstance(loaded.capital.cash, float)
