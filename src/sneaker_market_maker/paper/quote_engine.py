"""Deterministic Strategy quote engine emitting gated Quote Intents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sneaker_market_maker.paper.capital import PaperCapital, _money
from sneaker_market_maker.paper.gate import DeterministicGate, GateDecision
from sneaker_market_maker.paper.intents import IntentKind, QuoteIntent, Side
from sneaker_market_maker.paper.inventory_stub import QuoteInventory
from sneaker_market_maker.paper.replay.loader import MarketReplayEvent


@dataclass(frozen=True)
class QuoteEngineConfig:
    bid_offset: Decimal = Decimal("1.00")
    ask_offset: Decimal = Decimal("1.00")
    price_revise_threshold: Decimal = Decimal("2.00")
    max_quote_age_seconds: int = 300
    expected_buy_fees_and_slippage: Decimal = Decimal("10.00")


@dataclass(frozen=True)
class ActiveQuote:
    quote_id: str
    side: Side
    price: Decimal
    principal: Decimal
    product_family: str
    style_code: str
    shoe_size: Decimal
    placed_at: datetime
    reserved_lot_id: str | None = None


class QuoteEngine:
    """Emit place/revise/cancel/replace Quote Intents through the Deterministic Gate."""

    def __init__(
        self,
        *,
        gate: DeterministicGate,
        capital: PaperCapital,
        inventory: QuoteInventory,
        config: QuoteEngineConfig | None = None,
    ) -> None:
        self._gate = gate
        self._capital = capital
        self._inventory = inventory
        self._config = config or QuoteEngineConfig()
        self._enabled = False
        self._active_bid: ActiveQuote | None = None
        self._active_ask: ActiveQuote | None = None
        self._desired_bid: Decimal | None = None
        self._desired_ask: Decimal | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def active_bid(self) -> ActiveQuote | None:
        return self._active_bid

    @property
    def active_ask(self) -> ActiveQuote | None:
        return self._active_ask

    @property
    def desired_bid(self) -> Decimal | None:
        return self._desired_bid

    @property
    def desired_ask(self) -> Decimal | None:
        return self._desired_ask

    @property
    def capital(self) -> PaperCapital:
        return self._capital

    def enable(self) -> None:
        self._enabled = True

    def sync_capital(self, capital: PaperCapital) -> None:
        """Align quote-engine capital with the execution book after fills or submits."""

        self._capital = capital

    def clear_active(self, side: Side) -> None:
        if side is Side.BUY:
            self._active_bid = None
        else:
            self._active_ask = None

    def disable(self) -> tuple[tuple[QuoteIntent, GateDecision], ...]:
        """Stop maintaining quotes: cancel actives through the Deterministic Gate."""

        self._enabled = False
        self._desired_bid = None
        self._desired_ask = None
        results: list[tuple[QuoteIntent, GateDecision]] = []
        if self._active_bid is not None:
            results.extend(self._cancel_active(self._active_bid))
        if self._active_ask is not None:
            results.extend(self._cancel_active(self._active_ask))
        return tuple(results)

    def on_market(
        self,
        event: MarketReplayEvent,
        *,
        simulation_time: datetime,
    ) -> tuple[tuple[QuoteIntent, GateDecision], ...]:
        if not self._enabled:
            self._desired_bid = None
            self._desired_ask = None
            return ()

        desired_bid = _money(event.highest_bid + self._config.bid_offset)
        lots = self._inventory.available_lot_count(
            event.product_family.value,
            event.style_code,
            event.shoe_size,
        )
        desired_ask = (
            _money(event.lowest_ask - self._config.ask_offset) if lots > 0 else None
        )
        if desired_ask is not None and desired_ask <= desired_bid:
            desired_ask = None

        self._desired_bid = desired_bid
        self._desired_ask = desired_ask

        results: list[tuple[QuoteIntent, GateDecision]] = []
        results.extend(
            self._reconcile_side(
                side=Side.BUY,
                desired_price=desired_bid,
                event=event,
                simulation_time=simulation_time,
            )
        )
        results.extend(
            self._reconcile_side(
                side=Side.SELL,
                desired_price=desired_ask,
                event=event,
                simulation_time=simulation_time,
            )
        )
        return tuple(results)

    def _reconcile_side(
        self,
        *,
        side: Side,
        desired_price: Decimal | None,
        event: MarketReplayEvent,
        simulation_time: datetime,
    ) -> list[tuple[QuoteIntent, GateDecision]]:
        active = self._active_bid if side is Side.BUY else self._active_ask
        if desired_price is None:
            return self._cancel_active(active) if active is not None else []

        if active is None:
            return self._submit_place(side, desired_price, event, simulation_time)

        age = (simulation_time - active.placed_at).total_seconds()
        price_delta = abs(desired_price - active.price)
        needs_update = (
            price_delta >= self._config.price_revise_threshold
            or age >= self._config.max_quote_age_seconds
        )
        if not needs_update:
            return []
        return self._submit_replace(active, desired_price, event, simulation_time)

    def _submit_place(
        self,
        side: Side,
        price: Decimal,
        event: MarketReplayEvent,
        simulation_time: datetime,
    ) -> list[tuple[QuoteIntent, GateDecision]]:
        reserved_lot_id: str | None = None
        if side is Side.SELL:
            reserved_lot_id = self._inventory.reserve_for_ask(
                event.product_family.value,
                event.style_code,
                event.shoe_size,
            )
        intent = QuoteIntent(
            kind=IntentKind.PLACE,
            side=side,
            principal=price if side is Side.BUY else Decimal("0.00"),
            expected_fees_and_slippage=(
                self._config.expected_buy_fees_and_slippage
                if side is Side.BUY
                else Decimal("0.00")
            ),
            product_family=event.product_family.value,
            price=price,
            style_code=event.style_code,
            shoe_size=event.shoe_size,
        )
        decision = self._gate.evaluate(intent, self._capital)
        if not decision.accepted:
            if reserved_lot_id is not None:
                self._inventory.release_reservation(reserved_lot_id)
            return [(intent, decision)]
        if decision.capital_after is not None:
            self._capital = decision.capital_after
        quote = ActiveQuote(
            quote_id=str(uuid4()),
            side=side,
            price=price,
            principal=intent.principal,
            product_family=event.product_family.value,
            style_code=event.style_code,
            shoe_size=event.shoe_size,
            placed_at=simulation_time,
            reserved_lot_id=reserved_lot_id,
        )
        self._set_active(quote)
        return [(intent, decision)]

    def _submit_replace(
        self,
        active: ActiveQuote,
        price: Decimal,
        event: MarketReplayEvent,
        simulation_time: datetime,
    ) -> list[tuple[QuoteIntent, GateDecision]]:
        intent = QuoteIntent(
            kind=IntentKind.REPLACE,
            side=active.side,
            principal=price if active.side is Side.BUY else Decimal("0.00"),
            expected_fees_and_slippage=(
                self._config.expected_buy_fees_and_slippage
                if active.side is Side.BUY
                else Decimal("0.00")
            ),
            product_family=event.product_family.value,
            replaces_reservation=active.principal if active.side is Side.BUY else None,
            price=price,
            style_code=event.style_code,
            shoe_size=event.shoe_size,
        )
        decision = self._gate.evaluate(intent, self._capital)
        if decision.accepted:
            if decision.capital_after is not None:
                self._capital = decision.capital_after
            quote = ActiveQuote(
                quote_id=active.quote_id,
                side=active.side,
                price=price,
                principal=intent.principal,
                product_family=event.product_family.value,
                style_code=event.style_code,
                shoe_size=event.shoe_size,
                placed_at=simulation_time,
                reserved_lot_id=active.reserved_lot_id,
            )
            self._set_active(quote)
        return [(intent, decision)]

    def _cancel_active(
        self, active: ActiveQuote | None
    ) -> list[tuple[QuoteIntent, GateDecision]]:
        if active is None:
            return []
        intent = QuoteIntent(
            kind=IntentKind.CANCEL,
            side=active.side,
            principal=Decimal("0.00"),
            expected_fees_and_slippage=Decimal("0.00"),
            product_family=active.product_family,
            replaces_reservation=active.principal if active.side is Side.BUY else None,
            price=active.price,
            style_code=active.style_code,
            shoe_size=active.shoe_size,
        )
        decision = self._gate.evaluate(intent, self._capital)
        if decision.accepted:
            if decision.capital_after is not None:
                self._capital = decision.capital_after
            if active.side is Side.SELL and active.reserved_lot_id is not None:
                self._inventory.release_reservation(active.reserved_lot_id)
            if active.side is Side.BUY:
                self._active_bid = None
            else:
                self._active_ask = None
        return [(intent, decision)]

    def _set_active(self, quote: ActiveQuote) -> None:
        if quote.side is Side.BUY:
            self._active_bid = quote
        else:
            self._active_ask = quote
