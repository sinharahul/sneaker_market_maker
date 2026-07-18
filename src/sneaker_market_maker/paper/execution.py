"""Paper execution engine: intents → orders → Fee-Aware Fills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sneaker_market_maker.core import FeeSchedule
from sneaker_market_maker.paper.capital import PaperCapital, _money
from sneaker_market_maker.paper.gate import DeterministicGate
from sneaker_market_maker.paper.intents import IntentKind, QuoteIntent, Side
from sneaker_market_maker.paper.orders import OrderStatus, PaperOrder
from sneaker_market_maker.paper.replay.loader import MarketReplayEvent


@dataclass(frozen=True)
class VersionedFees:
    version: str
    schedule: FeeSchedule


@dataclass(frozen=True)
class SlippageModel:
    version: str
    buy_slippage: Decimal
    sell_slippage: Decimal


@dataclass(frozen=True)
class FeeAwareFill:
    fill_id: str
    order_id: str
    side: Side
    quantity: int
    quoted_price: Decimal
    execution_price: Decimal
    slippage: Decimal
    fee_schedule_version: str
    slippage_version: str
    total_fees: Decimal
    source_event_id: str
    product_family: str
    style_code: str
    shoe_size: Decimal
    simulation_time: datetime


class PaperExecutionEngine:
    """Match quantity-one Paper Orders against replay events with fee-aware fills."""

    def __init__(
        self,
        *,
        capital: PaperCapital,
        gate: DeterministicGate,
        fees: VersionedFees,
        slippage: SlippageModel,
    ) -> None:
        self._capital = capital
        self._gate = gate
        self._fees = fees
        self._slippage = slippage
        self._orders: dict[str, PaperOrder] = {}
        self._fills: list[FeeAwareFill] = []
        self._open_by_key: dict[tuple[str, str, str, Side], str] = {}

    @property
    def capital(self) -> PaperCapital:
        return self._capital

    @property
    def orders(self) -> dict[str, PaperOrder]:
        return self._orders

    @property
    def fills(self) -> tuple[FeeAwareFill, ...]:
        return tuple(self._fills)

    def open_orders(self) -> tuple[PaperOrder, ...]:
        return tuple(o for o in self._orders.values() if o.status is OrderStatus.OPEN)

    def submit(self, intent: QuoteIntent) -> PaperOrder | None:
        decision = self._gate.evaluate(intent, self._capital)
        if not decision.accepted:
            return None
        if decision.capital_after is not None:
            self._capital = decision.capital_after

        if intent.kind is IntentKind.PLACE:
            return self._place(intent)
        if intent.kind in (IntentKind.REPLACE, IntentKind.REVISE):
            return self._replace(intent)
        if intent.kind is IntentKind.CANCEL:
            return self._cancel(intent)
        return None

    def match(
        self,
        event: MarketReplayEvent,
        *,
        simulation_time: datetime,
    ) -> tuple[FeeAwareFill, ...]:
        produced: list[FeeAwareFill] = []
        for order in list(self.open_orders()):
            if order.product_family != event.product_family.value:
                continue
            if order.style_code != event.style_code or order.shoe_size != event.shoe_size:
                continue
            fill = self._try_fill(order, event, simulation_time)
            if fill is not None:
                produced.append(fill)
        return tuple(produced)

    def _place(self, intent: QuoteIntent) -> PaperOrder:
        if intent.price is None or intent.style_code is None or intent.shoe_size is None:
            raise ValueError("place intent requires price, style_code, and shoe_size")
        order = PaperOrder(
            order_id=str(uuid4()),
            side=intent.side,
            price=intent.price,
            quantity=1,
            status=OrderStatus.OPEN,
            product_family=intent.product_family,
            style_code=intent.style_code,
            shoe_size=intent.shoe_size,
            principal=intent.principal,
        )
        self._orders[order.order_id] = order
        self._open_by_key[self._key(order)] = order.order_id
        return order

    def _replace(self, intent: QuoteIntent) -> PaperOrder | None:
        existing_id = self._open_by_key.get(
            (
                intent.product_family,
                intent.style_code or "",
                str(intent.shoe_size or ""),
                intent.side,
            )
        )
        if existing_id is None:
            return self._place(intent)
        old = self._orders[existing_id]
        old.status = OrderStatus.CANCELLED
        del self._open_by_key[self._key(old)]
        placed = self._place(intent)
        placed.replaced_order_id = old.order_id
        return placed

    def _cancel(self, intent: QuoteIntent) -> PaperOrder | None:
        key = (
            intent.product_family,
            intent.style_code or "",
            str(intent.shoe_size or ""),
            intent.side,
        )
        order_id = self._open_by_key.get(key)
        if order_id is None:
            return None
        order = self._orders[order_id]
        order.status = OrderStatus.CANCELLED
        del self._open_by_key[key]
        return order

    def _try_fill(
        self,
        order: PaperOrder,
        event: MarketReplayEvent,
        simulation_time: datetime,
    ) -> FeeAwareFill | None:
        if order.side is Side.BUY:
            if event.lowest_ask > order.price:
                return None
            raw = _money(event.lowest_ask + self._slippage.buy_slippage)
            execution = min(order.price, raw)
            slippage = _money(execution - event.lowest_ask)
            total_cost = self._fees.schedule.total_purchase_cost(execution)
            total_fees = _money(total_cost - execution)
            self._capital = self._capital.apply_buy_fill(
                principal_released=order.principal,
                total_cost=total_cost,
            )
        else:
            if event.highest_bid < order.price:
                return None
            raw = _money(event.highest_bid - self._slippage.sell_slippage)
            execution = max(order.price, raw)
            slippage = _money(event.highest_bid - execution)
            proceeds = self._fees.schedule.sale_proceeds(execution)
            total_fees = _money(execution - proceeds)
            self._capital = self._capital.apply_sell_fill(proceeds=proceeds)

        order.status = OrderStatus.FILLED
        self._open_by_key.pop(self._key(order), None)
        fill = FeeAwareFill(
            fill_id=str(uuid4()),
            order_id=order.order_id,
            side=order.side,
            quantity=1,
            quoted_price=order.price,
            execution_price=execution,
            slippage=slippage,
            fee_schedule_version=self._fees.version,
            slippage_version=self._slippage.version,
            total_fees=total_fees,
            source_event_id=event.event_id,
            product_family=order.product_family,
            style_code=order.style_code,
            shoe_size=order.shoe_size,
            simulation_time=simulation_time,
        )
        self._fills.append(fill)
        return fill

    @staticmethod
    def _key(order: PaperOrder) -> tuple[str, str, str, Side]:
        return (order.product_family, order.style_code, str(order.shoe_size), order.side)
