"""Paper book snapshot models and store protocol."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from sneaker_market_maker.paper.capital import PaperCapital
from sneaker_market_maker.paper.intents import Side
from sneaker_market_maker.paper.inventory import LotState
from sneaker_market_maker.paper.orders import OrderStatus


def money(value: Decimal | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, default=str))


@dataclass(frozen=True)
class PersistedOrder:
    order_id: UUID
    side: Side
    price: Decimal
    quantity: int
    status: OrderStatus
    product_family: str
    style_code: str
    shoe_size: Decimal
    principal: Decimal
    replaced_order_id: UUID | None


@dataclass(frozen=True)
class PersistedFill:
    fill_id: UUID
    order_id: UUID
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


@dataclass(frozen=True)
class PersistedLot:
    lot_id: UUID
    product_family: str
    style_code: str
    shoe_size: Decimal
    landed_cost: Decimal
    state: LotState
    source_fill_id: str
    created_at: datetime


@dataclass(frozen=True)
class PaperBookSnapshot:
    run_id: UUID
    capital: PaperCapital
    orders: tuple[PersistedOrder, ...]
    fills: tuple[PersistedFill, ...]
    lots: tuple[PersistedLot, ...]


@dataclass(frozen=True)
class PaperAuditEvent:
    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class PaperStore(Protocol):
    def create_run(
        self,
        *,
        dataset_id: str,
        dataset_version: str,
        checksum_sha256: str,
        seed: int,
        status: str = "loaded",
    ) -> UUID: ...

    def save_book(self, snapshot: PaperBookSnapshot) -> None: ...

    def load_book(self, run_id: UUID) -> PaperBookSnapshot | None: ...

    def append_audit(
        self,
        run_id: UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> int: ...

    def list_audit(
        self, run_id: UUID, *, after_sequence: int = 0
    ) -> tuple[PaperAuditEvent, ...]: ...
