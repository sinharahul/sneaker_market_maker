"""Physical Inventory Lots for Continuous Paper Market-Maker."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from sneaker_market_maker.paper.capital import _money
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.paper.execution import FeeAwareFill


class LotState(str, Enum):
    PURCHASED = "purchased"
    IN_TRANSIT = "in_transit"
    AUTHENTICATING = "authenticating"
    AVAILABLE = "available"
    RESERVED_FOR_SALE = "reserved_for_sale"
    SOLD = "sold"
    SETTLED = "settled"
    AUTH_FAILED = "auth_failed"
    RETURNED = "returned"
    LOST = "lost"


LEGAL_TRANSITIONS: dict[LotState, frozenset[LotState]] = {
    LotState.PURCHASED: frozenset(
        {LotState.IN_TRANSIT, LotState.AUTH_FAILED, LotState.RETURNED, LotState.LOST}
    ),
    LotState.IN_TRANSIT: frozenset(
        {LotState.AUTHENTICATING, LotState.RETURNED, LotState.LOST}
    ),
    LotState.AUTHENTICATING: frozenset(
        {LotState.AVAILABLE, LotState.AUTH_FAILED, LotState.LOST}
    ),
    LotState.AVAILABLE: frozenset(
        {LotState.RESERVED_FOR_SALE, LotState.RETURNED, LotState.LOST}
    ),
    LotState.RESERVED_FOR_SALE: frozenset(
        {LotState.AVAILABLE, LotState.SOLD, LotState.LOST}
    ),
    LotState.SOLD: frozenset({LotState.SETTLED}),
    LotState.SETTLED: frozenset(),
    LotState.AUTH_FAILED: frozenset(),
    LotState.RETURNED: frozenset(),
    LotState.LOST: frozenset(),
}


class InventoryError(PaperError):
    """Fail-closed inventory lifecycle error."""


@dataclass
class InventoryLot:
    lot_id: str
    product_family: str
    style_code: str
    shoe_size: Decimal
    landed_cost: Decimal
    state: LotState
    source_fill_id: str
    created_at: datetime


@dataclass(frozen=True)
class LotAuditEntry:
    lot_id: str
    from_state: LotState | None
    to_state: LotState
    at: datetime


@dataclass
class InventoryLedger:
    """Tracks physical lots; only AVAILABLE lots may back asks."""

    _lots: dict[str, InventoryLot] = field(default_factory=dict)
    _audit: list[LotAuditEntry] = field(default_factory=list)

    @property
    def audit(self) -> tuple[LotAuditEntry, ...]:
        return tuple(self._audit)

    def get(self, lot_id: str) -> InventoryLot:
        try:
            return self._lots[lot_id]
        except KeyError as error:
            raise InventoryError("unknown_lot", f"lot {lot_id!r} not found") from error

    def lots(self) -> tuple[InventoryLot, ...]:
        return tuple(self._lots.values())

    def create_from_buy_fill(self, fill: FeeAwareFill) -> InventoryLot:
        if fill.side.value != "buy":
            raise InventoryError("invalid_fill", "only buy fills create Inventory Lots")
        lot = InventoryLot(
            lot_id=str(uuid4()),
            product_family=fill.product_family,
            style_code=fill.style_code,
            shoe_size=fill.shoe_size,
            landed_cost=_money(fill.execution_price + fill.total_fees),
            state=LotState.PURCHASED,
            source_fill_id=fill.fill_id,
            created_at=fill.simulation_time,
        )
        self._lots[lot.lot_id] = lot
        self._audit.append(
            LotAuditEntry(lot.lot_id, None, LotState.PURCHASED, fill.simulation_time)
        )
        return lot

    def transition(
        self,
        lot_id: str,
        to_state: LotState,
        *,
        at: datetime | None = None,
    ) -> InventoryLot:
        lot = self.get(lot_id)
        allowed = LEGAL_TRANSITIONS[lot.state]
        if to_state not in allowed:
            raise InventoryError(
                "illegal_transition",
                f"cannot move lot from {lot.state.value} to {to_state.value}",
            )
        when = at or datetime.now(timezone.utc)
        self._audit.append(LotAuditEntry(lot.lot_id, lot.state, to_state, when))
        lot.state = to_state
        return lot

    def available_lot_count(
        self,
        product_family: str,
        style_code: str,
        shoe_size: Decimal,
    ) -> int:
        return sum(
            1
            for lot in self._lots.values()
            if lot.state is LotState.AVAILABLE
            and lot.product_family == product_family
            and lot.style_code == style_code
            and lot.shoe_size == shoe_size
        )

    def reserve_for_ask(
        self,
        product_family: str,
        style_code: str,
        shoe_size: Decimal,
    ) -> str:
        candidates = sorted(
            (
                lot
                for lot in self._lots.values()
                if lot.state is LotState.AVAILABLE
                and lot.product_family == product_family
                and lot.style_code == style_code
                and lot.shoe_size == shoe_size
            ),
            key=lambda item: item.lot_id,
        )
        if not candidates:
            raise InventoryError(
                "no_available_lot",
                "no AVAILABLE Inventory Lot can back this ask",
            )
        lot = candidates[0]
        self.transition(lot.lot_id, LotState.RESERVED_FOR_SALE)
        return lot.lot_id

    def release_reservation(self, lot_id: str) -> InventoryLot:
        lot = self.get(lot_id)
        if lot.state is not LotState.RESERVED_FOR_SALE:
            raise InventoryError(
                "not_reserved",
                "lot is not reserved for sale",
            )
        return self.transition(lot_id, LotState.AVAILABLE)

    def mark_sold(self, lot_id: str) -> InventoryLot:
        return self.transition(lot_id, LotState.SOLD)

    def advance_to_available(self, lot_id: str) -> InventoryLot:
        """Test/helper path: move a new purchase through logistics to AVAILABLE."""

        self.transition(lot_id, LotState.IN_TRANSIT)
        self.transition(lot_id, LotState.AUTHENTICATING)
        return self.transition(lot_id, LotState.AVAILABLE)

    def find_reserved(
        self,
        product_family: str,
        style_code: str,
        shoe_size: Decimal,
    ) -> str | None:
        for lot in sorted(self._lots.values(), key=lambda item: item.lot_id):
            if (
                lot.state is LotState.RESERVED_FOR_SALE
                and lot.product_family == product_family
                and lot.style_code == style_code
                and lot.shoe_size == shoe_size
            ):
                return lot.lot_id
        return None
