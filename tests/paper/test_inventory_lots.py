"""Inventory Lot lifecycle and ask-backing reservation."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sneaker_market_maker.paper.execution import FeeAwareFill
from sneaker_market_maker.paper.intents import Side
from sneaker_market_maker.paper.inventory import (
    InventoryError,
    InventoryLedger,
    LotState,
)


def _buy_fill(**overrides: object) -> FeeAwareFill:
    values: dict[str, object] = {
        "fill_id": "fill-1",
        "order_id": "ord-1",
        "side": Side.BUY,
        "quantity": 1,
        "quoted_price": Decimal("200.00"),
        "execution_price": Decimal("200.00"),
        "slippage": Decimal("0.00"),
        "fee_schedule_version": "fees-v1",
        "slippage_version": "slippage-v1",
        "total_fees": Decimal("5.00"),
        "source_event_id": "m1",
        "product_family": "jordan_1_retro",
        "style_code": "555088-001",
        "shoe_size": Decimal("10"),
        "simulation_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return FeeAwareFill(**values)  # type: ignore[arg-type]


def test_buy_fill_creates_lot_with_landed_cost() -> None:
    ledger = InventoryLedger()
    lot = ledger.create_from_buy_fill(_buy_fill())
    assert lot.state is LotState.PURCHASED
    assert lot.landed_cost == Decimal("205.00")
    assert lot.product_family == "jordan_1_retro"
    assert ledger.available_lot_count("jordan_1_retro", "555088-001", Decimal("10")) == 0


def test_only_available_lots_back_asks() -> None:
    ledger = InventoryLedger()
    lot = ledger.create_from_buy_fill(_buy_fill())
    ledger.transition(lot.lot_id, LotState.IN_TRANSIT)
    ledger.transition(lot.lot_id, LotState.AUTHENTICATING)
    ledger.transition(lot.lot_id, LotState.AVAILABLE)
    assert ledger.available_lot_count("jordan_1_retro", "555088-001", Decimal("10")) == 1


def test_reserve_is_exclusive_double_reserve_fails() -> None:
    ledger = InventoryLedger()
    lot = ledger.create_from_buy_fill(_buy_fill())
    for state in (LotState.IN_TRANSIT, LotState.AUTHENTICATING, LotState.AVAILABLE):
        ledger.transition(lot.lot_id, state)
    reserved_id = ledger.reserve_for_ask("jordan_1_retro", "555088-001", Decimal("10"))
    assert reserved_id == lot.lot_id
    assert ledger.get(lot.lot_id).state is LotState.RESERVED_FOR_SALE
    assert ledger.available_lot_count("jordan_1_retro", "555088-001", Decimal("10")) == 0
    with pytest.raises(InventoryError) as exc:
        ledger.reserve_for_ask("jordan_1_retro", "555088-001", Decimal("10"))
    assert exc.value.code == "no_available_lot"


def test_sale_settlement_and_exception_paths() -> None:
    ledger = InventoryLedger()
    lot = ledger.create_from_buy_fill(_buy_fill())
    for state in (LotState.IN_TRANSIT, LotState.AUTHENTICATING, LotState.AVAILABLE):
        ledger.transition(lot.lot_id, state)
    ledger.reserve_for_ask("jordan_1_retro", "555088-001", Decimal("10"))
    ledger.transition(lot.lot_id, LotState.SOLD)
    ledger.transition(lot.lot_id, LotState.SETTLED)
    assert ledger.get(lot.lot_id).state is LotState.SETTLED

    failed = ledger.create_from_buy_fill(_buy_fill(fill_id="fill-2", order_id="ord-2"))
    ledger.transition(failed.lot_id, LotState.AUTH_FAILED)
    assert ledger.get(failed.lot_id).state is LotState.AUTH_FAILED

    codes = [entry.to_state for entry in ledger.audit]
    assert LotState.SETTLED in codes
    assert LotState.AUTH_FAILED in codes


def test_illegal_transition_fails_closed() -> None:
    ledger = InventoryLedger()
    lot = ledger.create_from_buy_fill(_buy_fill())
    with pytest.raises(InventoryError) as exc:
        ledger.transition(lot.lot_id, LotState.AVAILABLE)
    assert exc.value.code == "illegal_transition"


def test_release_reservation_returns_to_available() -> None:
    ledger = InventoryLedger()
    lot = ledger.create_from_buy_fill(_buy_fill())
    for state in (LotState.IN_TRANSIT, LotState.AUTHENTICATING, LotState.AVAILABLE):
        ledger.transition(lot.lot_id, state)
    ledger.reserve_for_ask("jordan_1_retro", "555088-001", Decimal("10"))
    ledger.release_reservation(lot.lot_id)
    assert ledger.get(lot.lot_id).state is LotState.AVAILABLE
    assert ledger.available_lot_count("jordan_1_retro", "555088-001", Decimal("10")) == 1


def test_execution_buy_fill_creates_lot_and_ask_requires_available() -> None:
    from sneaker_market_maker.core import FeeSchedule
    from sneaker_market_maker.paper.allowlist import ProductFamily
    from sneaker_market_maker.paper.capital import PaperCapital
    from sneaker_market_maker.paper.execution import (
        PaperExecutionEngine,
        SlippageModel,
        VersionedFees,
    )
    from sneaker_market_maker.paper.gate import DeterministicGate
    from sneaker_market_maker.paper.intents import IntentKind, QuoteIntent
    from sneaker_market_maker.paper.quote_engine import QuoteEngine, QuoteEngineConfig
    from sneaker_market_maker.paper.replay.loader import MarketReplayEvent

    ledger = InventoryLedger()
    fees = VersionedFees(
        version="fees-v1",
        schedule=FeeSchedule(
            seller_rate=Decimal("0.10"),
            processor_rate=Decimal("0.03"),
            inbound_shipping=Decimal("5.00"),
        ),
    )
    execution = PaperExecutionEngine(
        capital=PaperCapital.initial_state(),
        gate=DeterministicGate(),
        fees=fees,
        slippage=SlippageModel("slippage-v1", Decimal("0"), Decimal("0")),
        inventory=ledger,
    )
    execution.submit(
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
    event = MarketReplayEvent(
        event_id="m1",
        product_family=ProductFamily.JORDAN_1_RETRO,
        style_code="555088-001",
        shoe_size=Decimal("10"),
        highest_bid=Decimal("190"),
        lowest_ask=Decimal("200"),
        source_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    fills = execution.match(event, simulation_time=event.source_timestamp)
    assert len(fills) == 1
    assert len(ledger.lots()) == 1
    lot = ledger.lots()[0]
    ledger.advance_to_available(lot.lot_id)

    quotes = QuoteEngine(
        gate=DeterministicGate(),
        capital=PaperCapital.initial_state(),
        inventory=ledger,
        config=QuoteEngineConfig(expected_buy_fees_and_slippage=Decimal("5.00")),
    )
    quotes.enable()
    results = quotes.on_market(event, simulation_time=event.source_timestamp)
    assert any(intent.side is Side.SELL and decision.accepted for intent, decision in results)
    assert ledger.get(lot.lot_id).state is LotState.RESERVED_FOR_SALE
