"""Simulator port tests: load/start/pause/resume/stop + deterministic clock."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sneaker_market_maker.paper.allowlist import ALLOWLIST_VERSION
from sneaker_market_maker.paper.replay.loader import load_golden_historical_replay
from sneaker_market_maker.paper.replay.simulator import (
    HistoricalReplaySimulator,
    ReplayStatus,
)


def _write_replay(tmp_path: Path, events: list[dict[str, object]]) -> Path:
    body = "".join(json.dumps(event, sort_keys=True) + "\n" for event in events)
    (tmp_path / "events.jsonl").write_text(body, encoding="utf-8")
    checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_id": "golden-clock-test",
                "version": "1.0.0",
                "checksum_sha256": checksum,
                "source_kind": "historical",
                "schema_version": "market-event-v1",
                "allowlist_version": ALLOWLIST_VERSION,
                "product_families": ["jordan_1_retro", "nike_dunk_low"],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _event(
    event_id: str,
    family: str,
    ts: str,
    *,
    style: str = "555088-001",
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "product_family": family,
        "style_code": style,
        "shoe_size": "10",
        "highest_bid": "200",
        "lowest_ask": "250",
        "source_timestamp": ts,
    }


@pytest.fixture
def same_timestamp_replay(tmp_path: Path):
    path = _write_replay(
        tmp_path,
        [
            _event("b", "jordan_1_retro", "2026-01-01T12:00:00+00:00"),
            _event("a", "nike_dunk_low", "2026-01-01T12:00:00+00:00", style="DD1391-100"),
            _event("c", "jordan_1_retro", "2026-01-01T12:00:01+00:00"),
        ],
    )
    return load_golden_historical_replay(path)


def test_same_timestamp_events_have_stable_order(same_timestamp_replay) -> None:
    assert [e.event_id for e in same_timestamp_replay.events] == ["a", "b", "c"]


def test_load_start_pause_resume_stop_and_projection(same_timestamp_replay) -> None:
    sim = HistoricalReplaySimulator()
    assert sim.projection().status is ReplayStatus.EMPTY

    sim.load(same_timestamp_replay, seed=7, speed=1)
    proj = sim.projection()
    assert proj.status is ReplayStatus.LOADED
    assert proj.seed == 7
    assert proj.speed == 1
    assert proj.events_total == 3
    assert proj.events_emitted == 0
    assert proj.dataset_id == "golden-clock-test"
    assert proj.simulation_time is None

    sim.start()
    assert sim.projection().status is ReplayStatus.RUNNING
    first = sim.tick()
    assert len(first) == 1 and first[0].event_id == "a"
    assert sim.projection().events_emitted == 1
    assert sim.projection().simulation_time == datetime(
        2026, 1, 1, 12, 0, tzinfo=timezone.utc
    )

    sim.pause()
    assert sim.projection().status is ReplayStatus.PAUSED
    assert sim.tick() == ()
    assert sim.projection().events_emitted == 1

    sim.resume()
    assert sim.projection().status is ReplayStatus.RUNNING
    second = sim.tick()
    assert len(second) == 1 and second[0].event_id == "b"

    sim.stop()
    proj = sim.projection()
    assert proj.status is ReplayStatus.STOPPED
    assert proj.events_emitted == 0
    assert proj.simulation_time is None


def test_speed_emits_multiple_events_per_tick(same_timestamp_replay) -> None:
    sim = HistoricalReplaySimulator()
    sim.load(same_timestamp_replay, seed=1, speed=2)
    sim.start()
    batch = sim.tick()
    assert [e.event_id for e in batch] == ["a", "b"]
    assert sim.projection().events_emitted == 2


def test_same_dataset_and_seed_is_deterministic(same_timestamp_replay) -> None:
    def run() -> list[str]:
        sim = HistoricalReplaySimulator()
        sim.load(same_timestamp_replay, seed=42, speed=1)
        sim.start()
        ids: list[str] = []
        while True:
            batch = sim.tick()
            if not batch:
                break
            ids.extend(event.event_id for event in batch)
        return ids

    assert run() == run() == ["a", "b", "c"]


def test_bundled_golden_replay_drives_clock() -> None:
    root = Path(__file__).resolve().parents[2] / "data" / "paper" / "golden_v1"
    replay = load_golden_historical_replay(root)
    sim = HistoricalReplaySimulator()
    sim.load(replay, seed=0, speed=1)
    sim.start()
    emitted: list[str] = []
    while True:
        batch = sim.tick()
        if not batch:
            break
        emitted.extend(event.event_id for event in batch)
    assert len(emitted) == len(replay.events)
    assert sim.projection().status is ReplayStatus.RUNNING
    assert sim.projection().events_emitted == len(replay.events)
