"""Versioned Action Translator: research HybridAction → paper quote directives."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from sneaker_market_maker.paper.capital import _money
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    HybridAction,
)


class TranslatorError(PaperError):
    """Fail-closed Action Translator error."""


class TranslatedKind(str, Enum):
    QUOTE = "quote"
    CANCEL = "cancel"
    NO_OP = "no_op"


@dataclass(frozen=True)
class DesiredTwoSidedQuote:
    bid_price: Decimal
    ask_price: Decimal
    quantity: int


@dataclass(frozen=True)
class TranslatedAction:
    kind: TranslatedKind
    desired: DesiredTwoSidedQuote | None


@dataclass(frozen=True)
class ActionTranslator:
    """Maps HybridActions to paper quote directives at quantity one."""

    version: str
    tick_size: Decimal

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise TranslatorError("invalid_version", "translator version is required")
        if self.tick_size <= 0:
            raise TranslatorError("invalid_tick_size", "tick_size must be positive")

    def translate(
        self,
        action: HybridAction,
        *,
        highest_bid: Decimal,
        lowest_ask: Decimal,
        bounds: ActionBounds | None = None,
    ) -> TranslatedAction:
        if action.category is ActionCategory.NO_OP:
            self._require_neutral(action)
            return TranslatedAction(TranslatedKind.NO_OP, None)
        if action.category is ActionCategory.CANCEL:
            self._require_neutral(action)
            return TranslatedAction(TranslatedKind.CANCEL, None)
        if action.category is ActionCategory.QUOTE:
            desired = self._quote_desired(
                action,
                highest_bid=highest_bid,
                lowest_ask=lowest_ask,
                bounds=bounds,
            )
            return TranslatedAction(TranslatedKind.QUOTE, desired)
        raise TranslatorError(
            "unsupported_category",
            f"unsupported action category {action.category!r}",
        )

    def translate_quote(
        self,
        action: HybridAction,
        *,
        highest_bid: Decimal,
        lowest_ask: Decimal,
        bounds: ActionBounds | None = None,
    ) -> DesiredTwoSidedQuote:
        if action.category is not ActionCategory.QUOTE:
            raise TranslatorError(
                "not_quote",
                f"translate_quote requires QUOTE, got {action.category.value}",
            )
        return self._quote_desired(
            action,
            highest_bid=highest_bid,
            lowest_ask=lowest_ask,
            bounds=bounds,
        )

    def _quote_desired(
        self,
        action: HybridAction,
        *,
        highest_bid: Decimal,
        lowest_ask: Decimal,
        bounds: ActionBounds | None,
    ) -> DesiredTwoSidedQuote:
        if bounds is not None and not (
            bounds.bid_low <= action.bid_offset_ticks <= bounds.bid_high
            and bounds.ask_low <= action.ask_offset_ticks <= bounds.ask_high
        ):
            raise TranslatorError(
                "out_of_bounds",
                "tick offsets are outside ActionBounds",
            )
        # Allocation is intentionally ignored for Paper Order sizing (always qty 1).
        _ = action.allocation
        bid = _money(highest_bid + Decimal(action.bid_offset_ticks) * self.tick_size)
        ask = _money(lowest_ask + Decimal(action.ask_offset_ticks) * self.tick_size)
        if bid >= ask:
            raise TranslatorError(
                "crossed_quote",
                "translated bid must be strictly below ask",
            )
        return DesiredTwoSidedQuote(bid_price=bid, ask_price=ask, quantity=1)

    @staticmethod
    def _require_neutral(action: HybridAction) -> None:
        if action.allocation != 0.0 or action.bid_offset_ticks != 0 or action.ask_offset_ticks != 0:
            raise TranslatorError(
                "invalid_neutral_action",
                f"{action.category.value} requires zero allocation and tick offsets",
            )
