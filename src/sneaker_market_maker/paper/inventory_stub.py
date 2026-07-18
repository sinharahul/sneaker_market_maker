"""Inventory stub until Inventory Lots land in ticket 06."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class StubInventory:
    _available: dict[tuple[str, str, str], int]

    def __init__(self) -> None:
        self._available = {}

    def set_available(
        self,
        product_family: str,
        style_code: str,
        shoe_size: Decimal,
        count: int,
    ) -> None:
        self._available[(product_family, style_code, str(shoe_size))] = count

    def available_lot_count(
        self,
        product_family: str,
        style_code: str,
        shoe_size: Decimal,
    ) -> int:
        return self._available.get((product_family, style_code, str(shoe_size)), 0)
