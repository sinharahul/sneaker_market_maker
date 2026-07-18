"""Inventory port used by the quote engine (stub or real ledger)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sneaker_market_maker.paper.inventory import InventoryError


class StubInventory:
    """Counter-based inventory for quote-engine unit tests."""

    def __init__(self) -> None:
        self._available: dict[tuple[str, str, str], int] = {}
        self._reservations: dict[str, tuple[str, str, str]] = {}

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

    def reserve_for_ask(
        self,
        product_family: str,
        style_code: str,
        shoe_size: Decimal,
    ) -> str:
        key = (product_family, style_code, str(shoe_size))
        if self._available.get(key, 0) < 1:
            raise InventoryError("no_available_lot", "no AVAILABLE Inventory Lot can back this ask")
        self._available[key] -= 1
        lot_id = str(uuid4())
        self._reservations[lot_id] = key
        return lot_id

    def release_reservation(self, lot_id: str) -> None:
        key = self._reservations.pop(lot_id, None)
        if key is None:
            raise InventoryError("not_reserved", "lot is not reserved for sale")
        self._available[key] = self._available.get(key, 0) + 1
