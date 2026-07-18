"""Controllable deterministic historical replay simulation clock."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sneaker_market_maker.paper.replay.loader import LoadedReplay, MarketReplayEvent


class ReplayStatus(str, Enum):
    EMPTY = "empty"
    LOADED = "loaded"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass(frozen=True)
class ReplayProjection:
    status: ReplayStatus
    seed: int | None
    speed: int
    simulation_time: datetime | None
    events_emitted: int
    events_total: int
    dataset_id: str | None
    source_kind: str | None


class HistoricalReplaySimulator:
    """Operator-controlled replay clock that emits ordered market events."""

    def __init__(self) -> None:
        self._replay: LoadedReplay | None = None
        self._status = ReplayStatus.EMPTY
        self._seed: int | None = None
        self._speed = 1
        self._cursor = 0
        self._simulation_time: datetime | None = None

    def load(self, replay: LoadedReplay, *, seed: int = 0, speed: int = 1) -> None:
        if speed < 1:
            raise ValueError("speed must be >= 1")
        self._replay = replay
        self._seed = seed
        self._speed = speed
        self._cursor = 0
        self._simulation_time = None
        self._status = ReplayStatus.LOADED

    def set_speed(self, speed: int) -> None:
        if speed < 1:
            raise ValueError("speed must be >= 1")
        self._speed = speed

    def start(self) -> None:
        self._require_loaded()
        if self._status is ReplayStatus.STOPPED:
            self._cursor = 0
            self._simulation_time = None
        self._status = ReplayStatus.RUNNING

    def pause(self) -> None:
        self._require_loaded()
        if self._status is ReplayStatus.RUNNING:
            self._status = ReplayStatus.PAUSED

    def resume(self) -> None:
        self._require_loaded()
        if self._status is ReplayStatus.PAUSED:
            self._status = ReplayStatus.RUNNING

    def stop(self) -> None:
        self._require_loaded()
        self._cursor = 0
        self._simulation_time = None
        self._status = ReplayStatus.STOPPED

    def tick(self) -> tuple[MarketReplayEvent, ...]:
        """Advance the clock by up to `speed` events while RUNNING."""

        if self._status is not ReplayStatus.RUNNING or self._replay is None:
            return ()
        events = self._replay.events
        if self._cursor >= len(events):
            return ()
        end = min(self._cursor + self._speed, len(events))
        batch = events[self._cursor : end]
        self._cursor = end
        if batch:
            self._simulation_time = batch[-1].source_timestamp
        return batch

    def projection(self) -> ReplayProjection:
        replay = self._replay
        return ReplayProjection(
            status=self._status,
            seed=self._seed,
            speed=self._speed,
            simulation_time=self._simulation_time,
            events_emitted=self._cursor,
            events_total=0 if replay is None else len(replay.events),
            dataset_id=None if replay is None else replay.manifest.dataset_id,
            source_kind=None if replay is None else replay.manifest.source_kind,
        )

    def _require_loaded(self) -> None:
        if self._replay is None or self._status is ReplayStatus.EMPTY:
            raise RuntimeError("replay dataset is not loaded")
