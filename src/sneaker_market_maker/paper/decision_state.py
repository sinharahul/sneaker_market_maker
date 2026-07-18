"""Build research-compatible Paper Decision State from the live paper book."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from sneaker_market_maker.paper.capital import PaperCapital, _money
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.paper.intents import Side
from sneaker_market_maker.paper.inventory import InventoryLot, LotState
from sneaker_market_maker.paper.orders import OrderStatus, PaperOrder
from sneaker_market_maker.paper.replay.loader import MarketReplayEvent
from sneaker_market_maker.research.contracts.state import StateSchema, StateValidationError

PAPER_DECISION_FEATURES: tuple[str, ...] = (
    "highest_bid",
    "lowest_ask",
    "spread",
    "cash",
    "reserved_buy_principal",
    "available_cash",
    "open_buy_count",
    "open_sell_count",
    "available_lot_count",
    "inventory_landed_cost",
    "shoe_size",
)

PAPER_DECISION_SCHEMA = StateSchema(
    version="paper-decision-v1",
    feature_names=PAPER_DECISION_FEATURES,
    required_fields=PAPER_DECISION_FEATURES,
)


class DecisionStateError(PaperError):
    """Fail-closed Paper Decision State construction error."""


@dataclass(frozen=True)
class PaperDecisionState:
    schema_version: str
    payload: Mapping[str, float]


def build_paper_decision_state(
    *,
    event: MarketReplayEvent,
    capital: PaperCapital,
    orders: Sequence[PaperOrder],
    lots: Sequence[InventoryLot],
    schema: StateSchema = PAPER_DECISION_SCHEMA,
) -> PaperDecisionState:
    """Map paper book + market event into a finite numeric decision payload."""

    if event.highest_bid <= 0 or event.lowest_ask <= 0:
        raise DecisionStateError(
            "invalid_market",
            "highest_bid and lowest_ask must be positive",
        )
    if event.lowest_ask < event.highest_bid:
        raise DecisionStateError(
            "invalid_market",
            "lowest_ask must be greater than or equal to highest_bid",
        )

    open_buys = sum(
        1 for order in orders if order.status is OrderStatus.OPEN and order.side is Side.BUY
    )
    open_sells = sum(
        1 for order in orders if order.status is OrderStatus.OPEN and order.side is Side.SELL
    )
    matching_lots = [
        lot
        for lot in lots
        if lot.product_family == event.product_family.value
        and lot.style_code == event.style_code
        and lot.shoe_size == event.shoe_size
    ]
    available = sum(1 for lot in matching_lots if lot.state is LotState.AVAILABLE)
    open_inventory = [
        lot
        for lot in matching_lots
        if lot.state
        not in {
            LotState.SOLD,
            LotState.SETTLED,
            LotState.AUTH_FAILED,
            LotState.RETURNED,
            LotState.LOST,
        }
    ]
    landed = _money(sum((lot.landed_cost for lot in open_inventory), Decimal("0.00")))

    payload: dict[str, float] = {
        "highest_bid": float(event.highest_bid),
        "lowest_ask": float(event.lowest_ask),
        "spread": float(_money(event.lowest_ask - event.highest_bid)),
        "cash": float(capital.cash),
        "reserved_buy_principal": float(capital.reserved_buy_principal),
        "available_cash": float(capital.available_cash),
        "open_buy_count": float(open_buys),
        "open_sell_count": float(open_sells),
        "available_lot_count": float(available),
        "inventory_landed_cost": float(landed),
        "shoe_size": float(event.shoe_size),
    }
    try:
        schema.validate(payload)
    except StateValidationError as error:
        raise DecisionStateError("schema_mismatch", str(error)) from error

    return PaperDecisionState(schema_version=schema.version, payload=payload)
