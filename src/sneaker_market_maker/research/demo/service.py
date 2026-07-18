"""Deterministic guided demo playback service."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from sneaker_market_maker.research.contracts.action import HybridAction
from sneaker_market_maker.research.demo.fixture import DEMO_EVENTS, DemoEvent


@dataclass(frozen=True)
class DemoSnapshot:
    index: int
    simulation_second: int
    paused: bool
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


class DemoService:
    def __init__(self, events: tuple[DemoEvent, ...] = DEMO_EVENTS) -> None:
        self._events = events
        self._index = 0
        self._paused = True

    def pause(self) -> DemoSnapshot:
        self._paused = True
        return self.snapshot()

    def resume(self) -> DemoSnapshot:
        self._paused = False
        return self.snapshot()

    def restart(self) -> DemoSnapshot:
        self._index = 0
        self._paused = True
        return self.snapshot()

    def step(self) -> DemoSnapshot:
        if self._index < len(self._events) - 1:
            self._index += 1
        return self.snapshot()

    def snapshot(self) -> DemoSnapshot:
        event = self._events[self._index]
        return DemoSnapshot(
            index=self._index,
            simulation_second=event.simulation_second,
            paused=self._paused,
            beat=event.beat,
            deterministic_action=event.deterministic_action,
            pfhedge_score=event.pfhedge_score,
            iql_shadow_action=event.iql_shadow_action,
            final_action=event.final_action,
            inventory_state=event.inventory_state,
            fees=event.fees,
            cash=event.cash,
            nav=event.nav,
            realized_pnl=event.realized_pnl,
            unrealized_pnl=event.unrealized_pnl,
        )
