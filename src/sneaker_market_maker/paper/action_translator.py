"""Versioned Action Translator: research HybridAction → paper desired quotes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sneaker_market_maker.paper.capital import _money
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.research.contracts.action import ActionCategory, HybridAction


class TranslatorError(PaperError):
    """Fail-closed Action Translator error."""


@dataclass(frozen=True)
class DesiredTwoSidedQuote:
    bid_price: Decimal
    ask_price: Decimal
    quantity: int


@dataclass(frozen=True)
class ActionTranslator:
    """Maps QUOTE HybridActions to touch ± (ticks × tick_size) at quantity one."""

    version: str
    tick_size: Decimal

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise TranslatorError("invalid_version", "translator version is required")
        if self.tick_size <= 0:
            raise TranslatorError("invalid_tick_size", "tick_size must be positive")

    def translate_quote(
        self,
        action: HybridAction,
        *,
        highest_bid: Decimal,
        lowest_ask: Decimal,
    ) -> DesiredTwoSidedQuote:
        if action.category is not ActionCategory.QUOTE:
            raise TranslatorError(
                "not_quote",
                f"translate_quote requires QUOTE, got {action.category.value}",
            )
        # Allocation is intentionally ignored for Paper Order sizing (always qty 1).
        _ = action.allocation
        bid = _money(highest_bid + Decimal(action.bid_offset_ticks) * self.tick_size)
        ask = _money(lowest_ask + Decimal(action.ask_offset_ticks) * self.tick_size)
        return DesiredTwoSidedQuote(bid_price=bid, ask_price=ask, quantity=1)
