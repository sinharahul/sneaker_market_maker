"""Paper Decision State builder (ticket 03)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sneaker_market_maker.paper.allowlist import ProductFamily
from sneaker_market_maker.paper.capital import PaperCapital
from sneaker_market_maker.paper.decision_state import (
    PAPER_DECISION_SCHEMA,
    DecisionStateError,
    build_paper_decision_state,
)
from sneaker_market_maker.paper.intents import Side
from sneaker_market_maker.paper.inventory import InventoryLot, LotState
from sneaker_market_maker.paper.orders import OrderStatus, PaperOrder
from sneaker_market_maker.paper.replay.loader import MarketReplayEvent
from sneaker_market_maker.research.contracts.state import StateSchema


def _event(**overrides: object) -> MarketReplayEvent:
    values: dict[str, object] = {
        "event_id": "g1",
        "product_family": ProductFamily.JORDAN_1_RETRO,
        "style_code": "555088-001",
        "shoe_size": Decimal("10"),
        "highest_bid": Decimal("220.00"),
        "lowest_ask": Decimal("275.00"),
        "source_timestamp": datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return MarketReplayEvent(**values)  # type: ignore[arg-type]


def test_builder_produces_schema_valid_state_from_paper_book() -> None:
    capital = PaperCapital(
        initial=Decimal("2500.00"),
        cash=Decimal("2295.00"),
        reserved_buy_principal=Decimal("200.00"),
    )
    orders = (
        PaperOrder(
            order_id="o1",
            side=Side.BUY,
            price=Decimal("221.00"),
            quantity=1,
            status=OrderStatus.OPEN,
            product_family="jordan_1_retro",
            style_code="555088-001",
            shoe_size=Decimal("10"),
            principal=Decimal("221.00"),
        ),
    )
    lots = (
        InventoryLot(
            lot_id="l1",
            product_family="jordan_1_retro",
            style_code="555088-001",
            shoe_size=Decimal("10"),
            landed_cost=Decimal("226.00"),
            state=LotState.AVAILABLE,
            source_fill_id="f1",
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
    )
    state = build_paper_decision_state(
        event=_event(),
        capital=capital,
        orders=orders,
        lots=lots,
    )
    assert state.schema_version == PAPER_DECISION_SCHEMA.version
    PAPER_DECISION_SCHEMA.validate(state.payload)
    assert state.payload["highest_bid"] == 220.0
    assert state.payload["lowest_ask"] == 275.0
    assert state.payload["spread"] == 55.0
    assert state.payload["cash"] == 2295.0
    assert state.payload["reserved_buy_principal"] == 200.0
    assert state.payload["available_cash"] == 2095.0
    assert state.payload["open_buy_count"] == 1.0
    assert state.payload["open_sell_count"] == 0.0
    assert state.payload["available_lot_count"] == 1.0
    assert state.payload["inventory_landed_cost"] == 226.0
    assert state.payload["shoe_size"] == 10.0


def test_missing_required_schema_field_fails_closed() -> None:
    strict = StateSchema(
        version="paper-decision-v1-strict",
        feature_names=("highest_bid", "lowest_ask", "mystery"),
        required_fields=("highest_bid", "lowest_ask", "mystery"),
    )
    with pytest.raises(DecisionStateError) as exc:
        build_paper_decision_state(
            event=_event(),
            capital=PaperCapital.initial_state(),
            orders=(),
            lots=(),
            schema=strict,
        )
    assert exc.value.code == "schema_mismatch"


def test_non_positive_touch_fails_closed() -> None:
    with pytest.raises(DecisionStateError) as exc:
        build_paper_decision_state(
            event=_event(highest_bid=Decimal("0"), lowest_ask=Decimal("275.00")),
            capital=PaperCapital.initial_state(),
            orders=(),
            lots=(),
        )
    assert exc.value.code == "invalid_market"
