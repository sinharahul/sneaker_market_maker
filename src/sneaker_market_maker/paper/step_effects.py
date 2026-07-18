"""Append-only paper step effects capture (R1 ticket 01)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sneaker_market_maker.paper.capital import _money
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.persistence.paper_models import PaperBookSnapshot

STEP_EFFECTS_EVENT = "paper.step_effects"


@dataclass(frozen=True)
class PaperBookDeltaView:
    """Lightweight book view for diffing; money may be missing (fail-closed)."""

    cash: Decimal | None
    reserved_buy_principal: Decimal | None
    order_ids: frozenset[str]
    fill_ids: frozenset[str]
    lot_ids: frozenset[str]


@dataclass(frozen=True)
class PaperStepEffects:
    run_id: UUID
    simulation_time: datetime | None
    source_event_ids: tuple[str, ...]
    cash_before: Decimal
    cash_after: Decimal
    reserved_buy_principal_before: Decimal
    reserved_buy_principal_after: Decimal
    order_ids_added: tuple[str, ...]
    fill_ids_added: tuple[str, ...]
    lot_ids_added: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "run_id": str(self.run_id),
            "simulation_time": (
                self.simulation_time.isoformat() if self.simulation_time else None
            ),
            "source_event_ids": list(self.source_event_ids),
            "cash_before": str(self.cash_before),
            "cash_after": str(self.cash_after),
            "reserved_buy_principal_before": str(self.reserved_buy_principal_before),
            "reserved_buy_principal_after": str(self.reserved_buy_principal_after),
            "order_ids_added": list(self.order_ids_added),
            "fill_ids_added": list(self.fill_ids_added),
            "lot_ids_added": list(self.lot_ids_added),
        }


class _BookLike(Protocol):
    cash: Decimal | None
    reserved_buy_principal: Decimal | None
    order_ids: frozenset[str]
    fill_ids: frozenset[str]
    lot_ids: frozenset[str]


def view_from_snapshot(snapshot: PaperBookSnapshot) -> PaperBookDeltaView:
    return PaperBookDeltaView(
        cash=snapshot.capital.cash,
        reserved_buy_principal=snapshot.capital.reserved_buy_principal,
        order_ids=frozenset(str(order.order_id) for order in snapshot.orders),
        fill_ids=frozenset(str(fill.fill_id) for fill in snapshot.fills),
        lot_ids=frozenset(str(lot.lot_id) for lot in snapshot.lots),
    )


def _as_view(book: PaperBookSnapshot | PaperBookDeltaView) -> _BookLike:
    if isinstance(book, PaperBookSnapshot):
        return view_from_snapshot(book)
    return book


def _require_money(value: Decimal | None, *, field: str) -> Decimal:
    if value is None:
        raise PaperError(
            "incomplete_money",
            f"incomplete money: {field} is missing",
        )
    return _money(value)


def capture_paper_step_effects(
    *,
    run_id: UUID,
    simulation_time: datetime | None,
    source_event_ids: tuple[str, ...],
    before: PaperBookSnapshot | PaperBookDeltaView,
    after: PaperBookSnapshot | PaperBookDeltaView,
) -> PaperStepEffects:
    """Diff before/after paper book into Decimal-honest step effects."""

    left = _as_view(before)
    right = _as_view(after)
    cash_before = _require_money(left.cash, field="cash_before")
    cash_after = _require_money(right.cash, field="cash_after")
    reserved_before = _require_money(
        left.reserved_buy_principal, field="reserved_buy_principal_before"
    )
    reserved_after = _require_money(
        right.reserved_buy_principal, field="reserved_buy_principal_after"
    )
    return PaperStepEffects(
        run_id=run_id,
        simulation_time=simulation_time,
        source_event_ids=tuple(source_event_ids),
        cash_before=cash_before,
        cash_after=cash_after,
        reserved_buy_principal_before=reserved_before,
        reserved_buy_principal_after=reserved_after,
        order_ids_added=tuple(sorted(right.order_ids - left.order_ids)),
        fill_ids_added=tuple(sorted(right.fill_ids - left.fill_ids)),
        lot_ids_added=tuple(sorted(right.lot_ids - left.lot_ids)),
    )
