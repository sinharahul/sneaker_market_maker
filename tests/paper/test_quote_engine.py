"""Quote engine tests: continuous place/revise/cancel/replace via Deterministic Gate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from sneaker_market_maker.paper.allowlist import ProductFamily
from sneaker_market_maker.paper.capital import PaperCapital
from sneaker_market_maker.paper.gate import DeterministicGate, GateReason
from sneaker_market_maker.paper.intents import IntentKind, Side
from sneaker_market_maker.paper.quote_engine import (
    QuoteEngine,
    QuoteEngineConfig,
    StubInventory,
)
from sneaker_market_maker.paper.replay.loader import MarketReplayEvent

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _event(
    *,
    event_id: str = "e1",
    family: ProductFamily = ProductFamily.JORDAN_1_RETRO,
    style: str = "555088-001",
    bid: str = "200",
    ask: str = "250",
    ts: datetime = T0,
) -> MarketReplayEvent:
    return MarketReplayEvent(
        event_id=event_id,
        product_family=family,
        style_code=style,
        shoe_size=Decimal("10"),
        highest_bid=Decimal(bid),
        lowest_ask=Decimal(ask),
        source_timestamp=ts,
    )


@pytest.fixture
def engine() -> QuoteEngine:
    return QuoteEngine(
        gate=DeterministicGate(),
        capital=PaperCapital.initial_state(),
        inventory=StubInventory(),
        config=QuoteEngineConfig(
            bid_offset=Decimal("1"),
            ask_offset=Decimal("1"),
            price_revise_threshold=Decimal("2.00"),
            max_quote_age_seconds=60,
            expected_buy_fees_and_slippage=Decimal("10.00"),
        ),
    )


def test_disabled_strategy_emits_no_intents(engine: QuoteEngine) -> None:
    results = engine.on_market(_event(), simulation_time=T0)
    assert results == ()
    assert engine.desired_bid is None


def test_place_bid_when_enabled_and_no_active(engine: QuoteEngine) -> None:
    engine.enable()
    results = engine.on_market(_event(bid="200", ask="250"), simulation_time=T0)
    assert len(results) == 1
    intent, decision = results[0]
    assert intent.kind is IntentKind.PLACE
    assert intent.side is Side.BUY
    assert intent.principal == Decimal("201.00")  # bid + offset
    assert decision.accepted is True
    assert engine.active_bid is not None
    assert engine.active_bid.price == Decimal("201.00")


def test_ask_withheld_without_inventory(engine: QuoteEngine) -> None:
    engine.enable()
    results = engine.on_market(_event(), simulation_time=T0)
    assert all(intent.side is Side.BUY for intent, _ in results)
    assert engine.active_ask is None
    assert engine.desired_ask is None


def test_ask_placed_when_inventory_available() -> None:
    inventory = StubInventory()
    inventory.set_available(
        ProductFamily.JORDAN_1_RETRO.value, "555088-001", Decimal("10"), 1
    )
    engine = QuoteEngine(
        gate=DeterministicGate(),
        capital=PaperCapital.initial_state(),
        inventory=inventory,
        config=QuoteEngineConfig(expected_buy_fees_and_slippage=Decimal("10.00")),
    )
    engine.enable()
    results = engine.on_market(_event(bid="200", ask="250"), simulation_time=T0)
    sides = {intent.side for intent, decision in results if decision.accepted}
    assert Side.BUY in sides
    assert Side.SELL in sides
    assert engine.active_ask is not None
    assert engine.active_ask.price == Decimal("249.00")


def test_no_thrash_within_price_threshold(engine: QuoteEngine) -> None:
    engine.enable()
    engine.on_market(_event(bid="200", ask="250"), simulation_time=T0)
    # +1 move is below 2.00 threshold
    results = engine.on_market(_event(bid="201", ask="250", event_id="e2"), simulation_time=T0)
    assert results == ()
    assert engine.active_bid is not None
    assert engine.active_bid.price == Decimal("201.00")


def test_replace_when_price_moves_beyond_threshold(engine: QuoteEngine) -> None:
    engine.enable()
    engine.on_market(_event(bid="200", ask="250"), simulation_time=T0)
    results = engine.on_market(_event(bid="210", ask="260", event_id="e2"), simulation_time=T0)
    assert len(results) == 1
    intent, decision = results[0]
    assert intent.kind is IntentKind.REPLACE
    assert intent.side is Side.BUY
    assert intent.principal == Decimal("211.00")
    assert intent.replaces_reservation == Decimal("201.00")
    assert decision.accepted is True
    assert engine.active_bid is not None
    assert engine.active_bid.price == Decimal("211.00")


def test_age_threshold_forces_replace(engine: QuoteEngine) -> None:
    engine.enable()
    engine.on_market(_event(bid="200", ask="250"), simulation_time=T0)
    later = T0 + timedelta(seconds=61)
    results = engine.on_market(_event(bid="200", ask="250", event_id="e2"), simulation_time=later)
    assert len(results) == 1
    assert results[0][0].kind is IntentKind.REPLACE
    assert results[0][1].accepted is True


def test_disable_cancels_active_quotes(engine: QuoteEngine) -> None:
    engine.enable()
    engine.on_market(_event(), simulation_time=T0)
    assert engine.active_bid is not None
    results = engine.disable()
    assert len(results) == 1
    intent, decision = results[0]
    assert intent.kind is IntentKind.CANCEL
    assert intent.side is Side.BUY
    assert decision.accepted is True
    assert engine.active_bid is None
    assert engine.enabled is False


def test_gate_rejection_does_not_mutate_active_book() -> None:
    engine = QuoteEngine(
        gate=DeterministicGate(),
        capital=PaperCapital.initial_state(),
        inventory=StubInventory(),
        config=QuoteEngineConfig(
            bid_offset=Decimal("1"),
            expected_buy_fees_and_slippage=Decimal("0.00"),
        ),
    )
    engine.enable()
    # principal = 1500 + 1 = 1501 exceeds $1,500 open-buy cap
    results = engine.on_market(_event(bid="1500", ask="1600"), simulation_time=T0)
    assert len(results) == 1
    intent, decision = results[0]
    assert intent.kind is IntentKind.PLACE
    assert decision.accepted is False
    assert decision.reason is GateReason.OPEN_BUY_CAP_EXCEEDED
    assert engine.active_bid is None


def test_continuous_revise_across_replay_ticks(engine: QuoteEngine) -> None:
    engine.enable()
    t1 = engine.on_market(_event(bid="200", ask="250", event_id="t1"), simulation_time=T0)
    t2 = engine.on_market(
        _event(bid="205", ask="255", event_id="t2"),
        simulation_time=T0 + timedelta(seconds=1),
    )
    assert t1[0][0].kind is IntentKind.PLACE
    assert t2[0][0].kind is IntentKind.REPLACE
    assert [r[0].kind for r in t1 + t2] == [IntentKind.PLACE, IntentKind.REPLACE]
