"""Build Authoritative Store snapshots from live paper engines."""

from __future__ import annotations

from uuid import UUID

from sneaker_market_maker.paper.execution import PaperExecutionEngine
from sneaker_market_maker.paper.inventory import InventoryLedger
from sneaker_market_maker.persistence.paper_models import (
    PaperBookSnapshot,
    PersistedFill,
    PersistedLot,
    PersistedOrder,
)


def book_snapshot(
    *,
    run_id: UUID,
    execution: PaperExecutionEngine,
    ledger: InventoryLedger,
) -> PaperBookSnapshot:
    return PaperBookSnapshot(
        run_id=run_id,
        capital=execution.capital,
        orders=tuple(
            PersistedOrder(
                order_id=UUID(order.order_id),
                side=order.side,
                price=order.price,
                quantity=order.quantity,
                status=order.status,
                product_family=order.product_family,
                style_code=order.style_code,
                shoe_size=order.shoe_size,
                principal=order.principal,
                replaced_order_id=(
                    UUID(order.replaced_order_id) if order.replaced_order_id else None
                ),
            )
            for order in execution.orders.values()
        ),
        fills=tuple(
            PersistedFill(
                fill_id=UUID(fill.fill_id),
                order_id=UUID(fill.order_id),
                side=fill.side,
                quantity=fill.quantity,
                quoted_price=fill.quoted_price,
                execution_price=fill.execution_price,
                slippage=fill.slippage,
                fee_schedule_version=fill.fee_schedule_version,
                slippage_version=fill.slippage_version,
                total_fees=fill.total_fees,
                source_event_id=fill.source_event_id,
                product_family=fill.product_family,
                style_code=fill.style_code,
                shoe_size=fill.shoe_size,
                simulation_time=fill.simulation_time,
            )
            for fill in execution.fills
        ),
        lots=tuple(
            PersistedLot(
                lot_id=UUID(lot.lot_id),
                product_family=lot.product_family,
                style_code=lot.style_code,
                shoe_size=lot.shoe_size,
                landed_cost=lot.landed_cost,
                state=lot.state,
                source_fill_id=lot.source_fill_id,
                created_at=lot.created_at,
            )
            for lot in ledger.lots()
        ),
    )
