"""Action Translator CANCEL / NO_OP and fail-closed ticks (ticket 02)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from sneaker_market_maker.paper.action_translator import (
    ActionTranslator,
    TranslatedKind,
    TranslatorError,
)
from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    HybridAction,
)


def _translator() -> ActionTranslator:
    return ActionTranslator(version="translator-v1", tick_size=Decimal("1.00"))


def test_cancel_means_cancel_without_placing_quotes() -> None:
    result = _translator().translate(
        HybridAction(ActionCategory.CANCEL, 0.0, 0, 0),
        highest_bid=Decimal("220.00"),
        lowest_ask=Decimal("275.00"),
    )
    assert result.kind is TranslatedKind.CANCEL
    assert result.desired is None


def test_noop_emits_no_new_intents() -> None:
    result = _translator().translate(
        HybridAction(ActionCategory.NO_OP, 0.0, 0, 0),
        highest_bid=Decimal("220.00"),
        lowest_ask=Decimal("275.00"),
    )
    assert result.kind is TranslatedKind.NO_OP
    assert result.desired is None


def test_quote_still_available_via_translate() -> None:
    result = _translator().translate(
        HybridAction(ActionCategory.QUOTE, 0.5, -1, 2),
        highest_bid=Decimal("220.00"),
        lowest_ask=Decimal("275.00"),
    )
    assert result.kind is TranslatedKind.QUOTE
    assert result.desired is not None
    assert result.desired.quantity == 1
    assert result.desired.bid_price == Decimal("219.00")
    assert result.desired.ask_price == Decimal("277.00")


def test_out_of_bounds_ticks_fail_closed() -> None:
    bounds = ActionBounds(bid_low=-2, bid_high=2, ask_low=-2, ask_high=2)
    with pytest.raises(TranslatorError) as exc:
        _translator().translate(
            HybridAction(ActionCategory.QUOTE, 0.5, 5, 0),
            highest_bid=Decimal("100.00"),
            lowest_ask=Decimal("110.00"),
            bounds=bounds,
        )
    assert exc.value.code == "out_of_bounds"


def test_cancel_with_nonzero_offsets_fails_closed() -> None:
    with pytest.raises(TranslatorError) as exc:
        _translator().translate(
            HybridAction(ActionCategory.CANCEL, 0.0, 1, 0),
            highest_bid=Decimal("100.00"),
            lowest_ask=Decimal("110.00"),
        )
    assert exc.value.code == "invalid_neutral_action"


def test_crossed_quote_after_mapping_fails_closed() -> None:
    with pytest.raises(TranslatorError) as exc:
        _translator().translate(
            HybridAction(ActionCategory.QUOTE, 0.5, 20, -20),
            highest_bid=Decimal("100.00"),
            lowest_ask=Decimal("110.00"),
        )
    assert exc.value.code == "crossed_quote"
