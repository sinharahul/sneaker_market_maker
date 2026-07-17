"""Deterministic construction of fixed-horizon research episodes."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import groupby
from typing import Literal
from uuid import UUID

from sneaker_market_maker.research.episodes.events import EventKind, NormalizedEvent


@dataclass(frozen=True)
class EpisodeConfig:
    episode_id: UUID
    start: datetime
    split_end: datetime
    discount_rate: float
    maintenance_seconds: int = 60
    duration: timedelta = timedelta(days=14)

    def __post_init__(self) -> None:
        if self.maintenance_seconds <= 0:
            raise ValueError("maintenance_seconds must be positive")
        if self.duration <= timedelta(0):
            raise ValueError("duration must be positive")
        if not math.isfinite(self.discount_rate) or self.discount_rate < 0:
            raise ValueError("discount_rate must be finite and non-negative")


@dataclass(frozen=True)
class DecisionPoint:
    index: int
    simulation_time: datetime
    elapsed_seconds: int
    reasons: tuple[EventKind, ...]
    source_ids: tuple[str, ...]
    provenances: tuple[Literal["historical", "synthetic"], ...]
    discount: float


@dataclass(frozen=True)
class Episode:
    episode_id: UUID
    start: datetime
    end: datetime
    decisions: tuple[DecisionPoint, ...]
    terminal_reason: str


class EpisodeBuilder:
    def build(self, events: Sequence[NormalizedEvent], config: EpisodeConfig) -> Episode:
        """Build an episode using simulation time and replay-stable ordering."""
        horizon = config.start + config.duration
        end = min(horizon, config.split_end)
        if end != horizon:
            raise ValueError("episode crosses split boundary")
        ordered = sorted(events, key=lambda event: (event.simulation_time, event.stable_order))
        return self._reduce_with_ticks(ordered, config, end)

    def _reduce_with_ticks(
        self,
        ordered: Sequence[NormalizedEvent],
        config: EpisodeConfig,
        horizon: datetime,
    ) -> Episode:
        replay_end = max(
            (event.simulation_time for event in ordered if event.simulation_time >= config.start),
            default=config.start,
        )
        closes_at_horizon = replay_end >= horizon
        end = horizon if closes_at_horizon else replay_end
        terminal_reason = "duration_elapsed" if closes_at_horizon else "replay_exhausted"

        event_groups = [
            (simulation_time, tuple(group))
            for simulation_time, group in groupby(
                (
                    event
                    for event in ordered
                    if config.start <= event.simulation_time <= end
                ),
                key=lambda event: event.simulation_time,
            )
        ]
        schedule: list[tuple[datetime, tuple[NormalizedEvent, ...]]] = []
        interval = timedelta(seconds=config.maintenance_seconds)
        previous_time = config.start
        next_tick = previous_time + interval
        for simulation_time, grouped_events in event_groups:
            while next_tick < simulation_time:
                schedule.append((next_tick, ()))
                previous_time = next_tick
                next_tick = previous_time + interval
            schedule.append((simulation_time, grouped_events))
            previous_time = simulation_time
            next_tick = previous_time + interval
        while next_tick <= end:
            schedule.append((next_tick, ()))
            previous_time = next_tick
            next_tick = previous_time + interval
        if not schedule or schedule[-1][0] < end:
            schedule.append((end, ()))

        decisions: list[DecisionPoint] = []
        previous_time = config.start
        for simulation_time, grouped_events in schedule:
            elapsed_seconds = int((simulation_time - previous_time).total_seconds())
            decisions.append(
                DecisionPoint(
                    index=len(decisions),
                    simulation_time=simulation_time,
                    elapsed_seconds=elapsed_seconds,
                    reasons=(
                        tuple(event.kind for event in grouped_events)
                        if grouped_events
                        else (EventKind.FRESHNESS,)
                    ),
                    source_ids=tuple(event.source_id for event in grouped_events),
                    provenances=tuple(event.provenance for event in grouped_events),
                    discount=math.exp(-config.discount_rate * elapsed_seconds),
                )
            )
            previous_time = simulation_time

        return Episode(
            episode_id=config.episode_id,
            start=config.start,
            end=end,
            decisions=tuple(decisions),
            terminal_reason=terminal_reason,
        )
