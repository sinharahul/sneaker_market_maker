"""Read-model projections for the Paper Ops Control Plane."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sneaker_market_maker.paper.capital import PaperCapital, _money
from sneaker_market_maker.paper.execution import FeeAwareFill, PaperExecutionEngine
from sneaker_market_maker.paper.inventory import InventoryLedger, LotState
from sneaker_market_maker.paper.orders import PaperOrder
from sneaker_market_maker.paper.quote_engine import QuoteEngine
from sneaker_market_maker.paper.replay.simulator import HistoricalReplaySimulator


def capital_projection(capital: PaperCapital) -> dict[str, Any]:
    return {
        "initial": str(capital.initial),
        "cash": str(capital.cash),
        "reserved_buy_principal": str(capital.reserved_buy_principal),
        "available_cash": str(capital.available_cash),
    }


def pnl_projection(capital: PaperCapital, ledger: InventoryLedger) -> dict[str, Any]:
    closed = {
        LotState.SOLD,
        LotState.SETTLED,
        LotState.AUTH_FAILED,
        LotState.RETURNED,
        LotState.LOST,
    }
    open_lots = [lot for lot in ledger.lots() if lot.state not in closed]
    inventory_cost = _money(sum((lot.landed_cost for lot in open_lots), Decimal("0.00")))
    equity = _money(capital.cash + inventory_cost)
    return {
        "equity": str(equity),
        "pnl": str(_money(equity - capital.initial)),
        "inventory_landed_cost": str(inventory_cost),
        "cash": str(capital.cash),
    }


def replay_projection(simulator: HistoricalReplaySimulator) -> dict[str, Any]:
    replay = simulator.projection()
    return {
        "status": replay.status.value,
        "speed": replay.speed,
        "events_emitted": replay.events_emitted,
        "events_total": replay.events_total,
        "dataset_id": replay.dataset_id,
        "source_kind": replay.source_kind,
        "simulation_time": (
            replay.simulation_time.isoformat() if replay.simulation_time else None
        ),
    }


def status_projection(
    *,
    run_id: str | None,
    quotes: QuoteEngine,
    execution: PaperExecutionEngine,
    ledger: InventoryLedger,
    simulator: HistoricalReplaySimulator,
    audit_sequence: int,
    strategy_mode: str = "deterministic",
    registry_model_id: str | None = None,
    registry_state: str | None = None,
    inference_latency_budget_ms: int = 100,
) -> dict[str, Any]:
    replay = simulator.projection()
    return {
        "run_id": run_id,
        "strategy_enabled": quotes.enabled,
        "strategy_mode": strategy_mode,
        "registry": {"model_id": registry_model_id, "state": registry_state},
        "inference_latency_budget_ms": inference_latency_budget_ms,
        "replay": replay_projection(simulator),
        "capital": capital_projection(execution.capital),
        "pnl": pnl_projection(execution.capital, ledger),
        "open_orders": len(execution.open_orders()),
        "fills": len(execution.fills),
        "lots": len(ledger.lots()),
        "audit_sequence": audit_sequence,
        "seed": replay.seed,
    }


def order_dict(order: PaperOrder) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "side": order.side.value,
        "price": str(order.price),
        "quantity": order.quantity,
        "status": order.status.value,
        "product_family": order.product_family,
        "style_code": order.style_code,
        "shoe_size": str(order.shoe_size),
    }


def fill_dict(fill: FeeAwareFill) -> dict[str, Any]:
    return {
        "fill_id": fill.fill_id,
        "order_id": fill.order_id,
        "side": fill.side.value,
        "quantity": fill.quantity,
        "quoted_price": str(fill.quoted_price),
        "execution_price": str(fill.execution_price),
        "total_fees": str(fill.total_fees),
        "source_event_id": fill.source_event_id,
    }


def lot_dict(lot: Any) -> dict[str, Any]:
    return {
        "lot_id": lot.lot_id,
        "product_family": lot.product_family,
        "style_code": lot.style_code,
        "shoe_size": str(lot.shoe_size),
        "landed_cost": str(lot.landed_cost),
        "state": lot.state.value,
        "source_fill_id": lot.source_fill_id,
    }
