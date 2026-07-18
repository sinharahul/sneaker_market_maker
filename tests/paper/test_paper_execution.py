"""Paper execution: quantity-one orders, matching, and Fee-Aware Fills."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sneaker_market_maker.core import FeeSchedule
from sneaker_market_maker.paper.allowlist import ProductFamily
from sneaker_market_maker.paper.capital import PaperCapital
from sneaker_market_maker.paper.execution import (
    FeeAwareFill,
    PaperExecutionEngine,
    SlippageModel,
    VersionedFees,
)
from sneaker_market_maker.paper.gate import DeterministicGate
from sneaker_market_maker.paper.intents import IntentKind, QuoteIntent, Side
from sneaker_market_maker.paper.orders import OrderStatus
from sneaker_market_maker.paper.replay.loader import MarketReplayEvent

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
FEES = VersionedFees(
    version="fees-v1",
    schedule=FeeSchedule(
        seller_rate=Decimal("0.10"),
        processor_rate=Decimal("0.03"),
        inbound_shipping=Decimal("5.00"),
        outbound_shipping=Decimal("2.00"),
    ),
)
SLIP = SlippageModel(
    version="slippage-v1",
    buy_slippage=Decimal("1.00"),
    sell_slippage=Decimal("1.00"),
)


def _event(
    *,
    event_id: str = "m1",
    bid: str = "200",
    ask: str = "210",
    family: ProductFamily = ProductFamily.JORDAN_1_RETRO,
) -> MarketReplayEvent:
    return MarketReplayEvent(
        event_id=event_id,
        product_family=family,
        style_code="555088-001",
        shoe_size=Decimal("10"),
        highest_bid=Decimal(bid),
        lowest_ask=Decimal(ask),
        source_timestamp=T0,
    )


@pytest.fixture
def engine() -> PaperExecutionEngine:
    return PaperExecutionEngine(
        capital=PaperCapital.initial_state(),
        gate=DeterministicGate(),
        fees=FEES,
        slippage=SLIP,
    )


def test_accepted_place_creates_quantity_one_open_order(engine: PaperExecutionEngine) -> None:
    intent = QuoteIntent(
        kind=IntentKind.PLACE,
        side=Side.BUY,
        principal=Decimal("200.00"),
        expected_fees_and_slippage=Decimal("10.00"),
        product_family="jordan_1_retro",
        price=Decimal("200.00"),
        style_code="555088-001",
        shoe_size=Decimal("10"),
    )
    order = engine.submit(intent)
    assert order is not None
    assert order.quantity == 1
    assert order.status is OrderStatus.OPEN
    assert engine.capital.reserved_buy_principal == Decimal("200.00")


def test_buy_fills_in_full_when_ask_crosses_bid(engine: PaperExecutionEngine) -> None:
    engine.submit(
        QuoteIntent(
            kind=IntentKind.PLACE,
            side=Side.BUY,
            principal=Decimal("200.00"),
            expected_fees_and_slippage=Decimal("10.00"),
            product_family="jordan_1_retro",
            price=Decimal("200.00"),
            style_code="555088-001",
            shoe_size=Decimal("10"),
        )
    )
    fills = engine.match(_event(ask="199.00", bid="190.00"), simulation_time=T0)
    assert len(fills) == 1
    fill = fills[0]
    assert isinstance(fill, FeeAwareFill)
    assert fill.quantity == 1
    assert fill.quoted_price == Decimal("200.00")
    assert fill.execution_price == Decimal("200.00")  # ask 199 + slip 1
    assert fill.slippage == Decimal("1.00")
    assert fill.fee_schedule_version == "fees-v1"
    assert fill.slippage_version == "slippage-v1"
    assert fill.source_event_id == "m1"
    assert fill.total_fees == Decimal("5.00")  # inbound shipping only on purchase cost delta
    order = engine.orders[fill.order_id]
    assert order.status is OrderStatus.FILLED
    # cash: 2500 - total_purchase_cost(200) = 2500 - 205 = 2295; reservation cleared
    assert engine.capital.reserved_buy_principal == Decimal("0.00")
    assert engine.capital.cash == Decimal("2295.00")


def test_sell_fills_when_bid_crosses_ask(engine: PaperExecutionEngine) -> None:
    engine.submit(
        QuoteIntent(
            kind=IntentKind.PLACE,
            side=Side.SELL,
            principal=Decimal("0.00"),
            expected_fees_and_slippage=Decimal("0.00"),
            product_family="jordan_1_retro",
            price=Decimal("210.00"),
            style_code="555088-001",
            shoe_size=Decimal("10"),
        )
    )
    fills = engine.match(_event(bid="211.00", ask="220.00"), simulation_time=T0)
    assert len(fills) == 1
    fill = fills[0]
    assert fill.side is Side.SELL
    assert fill.execution_price == Decimal("210.00")  # bid 211 - slip 1
    # proceeds = 210 - 13% - 2 = 210 - 27.30 - 2 = 180.70
    assert fill.total_fees == Decimal("29.30")
    assert engine.capital.cash == Decimal("2680.70")


def test_no_partial_fills_and_deterministic_match(engine: PaperExecutionEngine) -> None:
    engine.submit(
        QuoteIntent(
            kind=IntentKind.PLACE,
            side=Side.BUY,
            principal=Decimal("200.00"),
            expected_fees_and_slippage=Decimal("5.00"),
            product_family="jordan_1_retro",
            price=Decimal("200.00"),
            style_code="555088-001",
            shoe_size=Decimal("10"),
        )
    )
    # ask above bid — no fill
    assert engine.match(_event(ask="201.00"), simulation_time=T0) == ()
    assert list(engine.open_orders())[0].status is OrderStatus.OPEN
    # same state + same event twice after fill path
    fills_a = engine.match(_event(ask="200.00", event_id="x"), simulation_time=T0)
    engine2 = PaperExecutionEngine(
        capital=PaperCapital.initial_state(),
        gate=DeterministicGate(),
        fees=FEES,
        slippage=SLIP,
    )
    engine2.submit(
        QuoteIntent(
            kind=IntentKind.PLACE,
            side=Side.BUY,
            principal=Decimal("200.00"),
            expected_fees_and_slippage=Decimal("5.00"),
            product_family="jordan_1_retro",
            price=Decimal("200.00"),
            style_code="555088-001",
            shoe_size=Decimal("10"),
        )
    )
    fills_b = engine2.match(_event(ask="200.00", event_id="x"), simulation_time=T0)
    assert fills_a[0].execution_price == fills_b[0].execution_price
    assert fills_a[0].total_fees == fills_b[0].total_fees
    assert fills_a[0].quantity == fills_b[0].quantity == 1


def test_reject_intent_does_not_create_order(engine: PaperExecutionEngine) -> None:
    order = engine.submit(
        QuoteIntent(
            kind=IntentKind.PLACE,
            side=Side.BUY,
            principal=Decimal("1501.00"),
            expected_fees_and_slippage=Decimal("0.00"),
            product_family="jordan_1_retro",
            price=Decimal("1501.00"),
            style_code="555088-001",
            shoe_size=Decimal("10"),
        )
    )
    assert order is None
    assert engine.orders == {}
    assert engine.capital.reserved_buy_principal == Decimal("0.00")


def test_cancel_removes_open_order(engine: PaperExecutionEngine) -> None:
    placed = engine.submit(
        QuoteIntent(
            kind=IntentKind.PLACE,
            side=Side.BUY,
            principal=Decimal("200.00"),
            expected_fees_and_slippage=Decimal("10.00"),
            product_family="jordan_1_retro",
            price=Decimal("200.00"),
            style_code="555088-001",
            shoe_size=Decimal("10"),
        )
    )
    assert placed is not None
    cancelled = engine.submit(
        QuoteIntent(
            kind=IntentKind.CANCEL,
            side=Side.BUY,
            principal=Decimal("0.00"),
            expected_fees_and_slippage=Decimal("0.00"),
            product_family="jordan_1_retro",
            replaces_reservation=Decimal("200.00"),
            price=Decimal("200.00"),
            style_code="555088-001",
            shoe_size=Decimal("10"),
        )
    )
    assert cancelled is not None
    assert cancelled.status is OrderStatus.CANCELLED
    assert engine.capital.reserved_buy_principal == Decimal("0.00")
    assert engine.match(_event(ask="199.00"), simulation_time=T0) == ()


def test_filled_order_never_fills_again(engine: PaperExecutionEngine) -> None:
    engine.submit(
        QuoteIntent(
            kind=IntentKind.PLACE,
            side=Side.BUY,
            principal=Decimal("200.00"),
            expected_fees_and_slippage=Decimal("10.00"),
            product_family="jordan_1_retro",
            price=Decimal("200.00"),
            style_code="555088-001",
            shoe_size=Decimal("10"),
        )
    )
    first = engine.match(_event(ask="200.00", event_id="a"), simulation_time=T0)
    second = engine.match(_event(ask="200.00", event_id="b"), simulation_time=T0)
    assert len(first) == 1
    assert second == ()
