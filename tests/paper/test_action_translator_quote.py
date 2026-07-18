"""Action Translator QUOTE mapping (ticket 01)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from sneaker_market_maker.paper.action_translator import ActionTranslator, TranslatorError
from sneaker_market_maker.research.contracts.action import ActionCategory, HybridAction


def test_quote_maps_ticks_times_tick_size_at_quantity_one() -> None:
    translator = ActionTranslator(version="translator-v1", tick_size=Decimal("1.00"))
    action = HybridAction(
        category=ActionCategory.QUOTE,
        allocation=0.75,
        bid_offset_ticks=-1,
        ask_offset_ticks=2,
    )
    desired = translator.translate_quote(
        action,
        highest_bid=Decimal("220.00"),
        lowest_ask=Decimal("275.00"),
    )
    assert desired.quantity == 1
    assert desired.bid_price == Decimal("219.00")
    assert desired.ask_price == Decimal("277.00")


def test_allocation_does_not_change_quantity() -> None:
    translator = ActionTranslator(version="translator-v1", tick_size=Decimal("0.50"))
    full = HybridAction(ActionCategory.QUOTE, 1.0, 0, 0)
    empty = HybridAction(ActionCategory.QUOTE, 0.0, 0, 0)
    touch = dict(highest_bid=Decimal("100.00"), lowest_ask=Decimal("110.00"))
    assert translator.translate_quote(full, **touch).quantity == 1
    assert translator.translate_quote(empty, **touch).quantity == 1
    assert translator.translate_quote(full, **touch).bid_price == Decimal("100.00")


def test_translator_version_and_tick_size_are_pinable() -> None:
    translator = ActionTranslator(version="translator-v1", tick_size=Decimal("0.25"))
    assert translator.version == "translator-v1"
    assert translator.tick_size == Decimal("0.25")
    action = HybridAction(ActionCategory.QUOTE, 0.5, 4, -4)
    desired = translator.translate_quote(
        action,
        highest_bid=Decimal("200.00"),
        lowest_ask=Decimal("210.00"),
    )
    assert desired.bid_price == Decimal("201.00")
    assert desired.ask_price == Decimal("209.00")


def test_non_quote_category_rejected_in_quote_mapper() -> None:
    translator = ActionTranslator(version="translator-v1", tick_size=Decimal("1.00"))
    with pytest.raises(TranslatorError) as exc:
        translator.translate_quote(
            HybridAction(ActionCategory.NO_OP, 0.0, 0, 0),
            highest_bid=Decimal("100.00"),
            lowest_ask=Decimal("110.00"),
        )
    assert exc.value.code == "not_quote"
