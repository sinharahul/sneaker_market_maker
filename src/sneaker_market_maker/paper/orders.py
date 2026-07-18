"""Quantity-one Paper Order state."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from sneaker_market_maker.paper.intents import Side


class OrderStatus(str, Enum):
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass
class PaperOrder:
    order_id: str
    side: Side
    price: Decimal
    quantity: int
    status: OrderStatus
    product_family: str
    style_code: str
    shoe_size: Decimal
    principal: Decimal
    replaced_order_id: str | None = None

    def __post_init__(self) -> None:
        if self.quantity != 1:
            raise ValueError("Paper Order quantity must be exactly one")
