"""Deterministic Gate — final authority on Quote Intents."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from sneaker_market_maker.paper.allowlist import assert_family_allowed
from sneaker_market_maker.paper.capital import PaperCapital, _money
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.paper.intents import IntentKind, QuoteIntent, Side


class GateReason(str, Enum):
    ACCEPTED = "accepted"
    UNSUPPORTED_PRODUCT_FAMILY = "unsupported_product_family"
    OPEN_BUY_CAP_EXCEEDED = "open_buy_cap_exceeded"
    INSUFFICIENT_CASH = "insufficient_cash"
    INVALID_INTENT = "invalid_intent"


@dataclass(frozen=True)
class GateDecision:
    accepted: bool
    reason: GateReason
    capital_after: PaperCapital | None = None


class DeterministicGate:
    """Fail-closed capital and allowlist checks before paper order mutation."""

    def evaluate(self, intent: QuoteIntent, capital: PaperCapital) -> GateDecision:
        try:
            assert_family_allowed(intent.product_family)
        except PaperError:
            return GateDecision(False, GateReason.UNSUPPORTED_PRODUCT_FAMILY)

        if intent.side is Side.SELL:
            if intent.kind is IntentKind.CANCEL:
                return GateDecision(True, GateReason.ACCEPTED, capital)
            if intent.kind in (IntentKind.PLACE, IntentKind.REVISE, IntentKind.REPLACE):
                return GateDecision(True, GateReason.ACCEPTED, capital)
            return GateDecision(False, GateReason.INVALID_INTENT)

        if intent.kind is IntentKind.CANCEL:
            return self._cancel(intent, capital)
        if intent.kind in (IntentKind.PLACE, IntentKind.REVISE):
            return self._reserve_buy(intent, capital, release=Decimal("0.00"))
        if intent.kind is IntentKind.REPLACE:
            if intent.replaces_reservation is None:
                return GateDecision(False, GateReason.INVALID_INTENT)
            return self._reserve_buy(intent, capital, release=intent.replaces_reservation)
        return GateDecision(False, GateReason.INVALID_INTENT)

    def _cancel(self, intent: QuoteIntent, capital: PaperCapital) -> GateDecision:
        release = intent.replaces_reservation
        if release is None or release < 0 or release > capital.reserved_buy_principal:
            return GateDecision(False, GateReason.INVALID_INTENT)
        return GateDecision(
            True,
            GateReason.ACCEPTED,
            capital.with_reservation(capital.reserved_buy_principal - release),
        )

    def _reserve_buy(
        self,
        intent: QuoteIntent,
        capital: PaperCapital,
        *,
        release: Decimal,
    ) -> GateDecision:
        if intent.principal <= 0 or intent.expected_fees_and_slippage < 0:
            return GateDecision(False, GateReason.INVALID_INTENT)
        if release < 0 or release > capital.reserved_buy_principal:
            return GateDecision(False, GateReason.INVALID_INTENT)

        reserved_after_release = _money(capital.reserved_buy_principal - release)
        available_after_release = _money(capital.cash - reserved_after_release)
        needed = _money(intent.principal + intent.expected_fees_and_slippage)
        if needed > available_after_release:
            return GateDecision(False, GateReason.INSUFFICIENT_CASH)

        provisional_reserved = _money(reserved_after_release + intent.principal)
        if provisional_reserved > capital.open_buy_principal_cap:
            return GateDecision(False, GateReason.OPEN_BUY_CAP_EXCEEDED)

        return GateDecision(
            True,
            GateReason.ACCEPTED,
            capital.with_reservation(provisional_reserved),
        )
