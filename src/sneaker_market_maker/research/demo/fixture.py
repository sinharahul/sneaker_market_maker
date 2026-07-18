"""Pinned fixture events for the deterministic guided demo."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from sneaker_market_maker.research.contracts.action import ActionCategory, HybridAction

DEMO_SEED = 20260717

FEE_KEYS: tuple[str, ...] = (
    "seller_fee",
    "processor_fee",
    "inbound_shipping",
    "outbound_shipping",
    "authentication",
    "slippage",
)

ZERO_FEES: Mapping[str, Decimal] = MappingProxyType(
    {key: Decimal("0") for key in FEE_KEYS},
)

NO_OP = HybridAction(ActionCategory.NO_OP, 0.0, 0, 0)
BID_QUOTE = HybridAction(ActionCategory.QUOTE, 0.4, -1, 0)
ASK_QUOTE = HybridAction(ActionCategory.QUOTE, 0.35, 0, 2)
AGGRESSIVE_QUOTE = HybridAction(ActionCategory.QUOTE, 0.6, -2, 1)


def _fees(**overrides: Decimal) -> Mapping[str, Decimal]:
    values = {key: Decimal("0") for key in FEE_KEYS}
    values.update(overrides)
    return MappingProxyType(values)


@dataclass(frozen=True)
class DemoEvent:
    simulation_second: int
    beat: str
    deterministic_action: HybridAction
    pfhedge_score: float
    iql_shadow_action: HybridAction
    final_action: HybridAction
    inventory_state: str
    fees: Mapping[str, Decimal]
    cash: Decimal
    nav: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal


DEMO_EVENTS: tuple[DemoEvent, ...] = (
    DemoEvent(
        simulation_second=0,
        beat="healthy_spread",
        deterministic_action=NO_OP,
        pfhedge_score=0.18,
        iql_shadow_action=NO_OP,
        final_action=NO_OP,
        inventory_state="flat",
        fees=ZERO_FEES,
        cash=Decimal("2500.00"),
        nav=Decimal("2500.00"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
    ),
    DemoEvent(
        simulation_second=60,
        beat="deterministic_bid",
        deterministic_action=BID_QUOTE,
        pfhedge_score=0.71,
        iql_shadow_action=HybridAction(ActionCategory.QUOTE, 0.5, -2, 0),
        final_action=BID_QUOTE,
        inventory_state="bid_open",
        fees=ZERO_FEES,
        cash=Decimal("2500.00"),
        nav=Decimal("2500.00"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
    ),
    DemoEvent(
        simulation_second=120,
        beat="paper_buy_fill",
        deterministic_action=NO_OP,
        pfhedge_score=0.42,
        iql_shadow_action=NO_OP,
        final_action=NO_OP,
        inventory_state="pending_logistics",
        fees=ZERO_FEES,
        cash=Decimal("2312.00"),
        nav=Decimal("2498.00"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("-2.00"),
    ),
    DemoEvent(
        simulation_second=180,
        beat="shipping_authenticated",
        deterministic_action=NO_OP,
        pfhedge_score=0.55,
        iql_shadow_action=NO_OP,
        final_action=NO_OP,
        inventory_state="authenticated",
        fees=ZERO_FEES,
        cash=Decimal("2312.00"),
        nav=Decimal("2502.00"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("2.00"),
    ),
    DemoEvent(
        simulation_second=240,
        beat="inventory_ask_sale",
        deterministic_action=ASK_QUOTE,
        pfhedge_score=0.63,
        iql_shadow_action=HybridAction(ActionCategory.QUOTE, 0.45, 0, 3),
        final_action=ASK_QUOTE,
        inventory_state="sold",
        fees=_fees(
            seller_fee=Decimal("15.00"),
            processor_fee=Decimal("4.50"),
            inbound_shipping=Decimal("8.00"),
            outbound_shipping=Decimal("2.00"),
        ),
        cash=Decimal("2524.50"),
        nav=Decimal("2524.50"),
        realized_pnl=Decimal("24.50"),
        unrealized_pnl=Decimal("0"),
    ),
    DemoEvent(
        simulation_second=300,
        beat="risk_gate_rejection",
        deterministic_action=BID_QUOTE,
        pfhedge_score=0.84,
        iql_shadow_action=AGGRESSIVE_QUOTE,
        final_action=NO_OP,
        inventory_state="flat",
        fees=ZERO_FEES,
        cash=Decimal("2524.50"),
        nav=Decimal("2524.50"),
        realized_pnl=Decimal("24.50"),
        unrealized_pnl=Decimal("0"),
    ),
)
