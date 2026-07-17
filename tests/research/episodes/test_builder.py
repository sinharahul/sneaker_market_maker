import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from sneaker_market_maker.research.episodes.builder import EpisodeBuilder, EpisodeConfig
from sneaker_market_maker.research.episodes.events import EventKind, NormalizedEvent

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def event(
    seconds: int,
    source_id: str,
    kind: EventKind,
    *,
    stable_order: int = 0,
    provenance: str = "historical",
) -> NormalizedEvent:
    return NormalizedEvent(
        source_id=source_id,
        simulation_time=START + timedelta(seconds=seconds),
        stable_order=stable_order,
        kind=kind,
        payload={},
        provenance=provenance,  # type: ignore[arg-type]
    )


def config(**overrides: object) -> EpisodeConfig:
    values = {
        "episode_id": uuid4(),
        "start": START,
        "split_end": START + timedelta(days=30),
        "discount_rate": 0.01,
    }
    values.update(overrides)
    return EpisodeConfig(**values)  # type: ignore[arg-type]


def test_reduces_same_timestamp_events_in_stable_order() -> None:
    episode = EpisodeBuilder().build(
        [
            event(30, "fill", EventKind.FILL, stable_order=2),
            event(30, "book", EventKind.BOOK, stable_order=1),
            event(30, "synthetic", EventKind.REGIME, stable_order=3, provenance="synthetic"),
        ],
        config(),
    )

    assert episode.decisions[0].reasons == (
        EventKind.BOOK,
        EventKind.FILL,
        EventKind.REGIME,
    )
    assert episode.decisions[0].source_ids == ("book", "fill", "synthetic")


def test_material_event_on_maintenance_boundary_is_one_decision() -> None:
    episode = EpisodeBuilder().build(
        [event(60, "fill", EventKind.FILL), event(61, "coverage", EventKind.BOOK)],
        config(duration=timedelta(seconds=60)),
    )

    assert len(episode.decisions) == 1
    assert episode.decisions[0].simulation_time == START + timedelta(seconds=60)
    assert episode.decisions[0].reasons == (EventKind.FILL,)


def test_maintenance_ticks_follow_simulation_time_not_replay_speed() -> None:
    events = [
        event(30, "material", EventKind.QUOTE),
        event(155, "late", EventKind.BOOK),
    ]

    episode = EpisodeBuilder().build(events, config())

    assert [point.simulation_time for point in episode.decisions] == [
        START + timedelta(seconds=30),
        START + timedelta(seconds=90),
        START + timedelta(seconds=150),
        START + timedelta(seconds=155),
    ]
    assert [point.reasons for point in episode.decisions] == [
        (EventKind.QUOTE,),
        (EventKind.FRESHNESS,),
        (EventKind.FRESHNESS,),
        (EventKind.BOOK,),
    ]


def test_episode_closes_exactly_at_fourteen_days() -> None:
    horizon = START + timedelta(days=14)

    episode = EpisodeBuilder().build(
        [event(14 * 24 * 60 * 60 + 1, "coverage", EventKind.BOOK)],
        config(),
    )

    assert episode.end == horizon
    assert episode.decisions[-1].simulation_time == horizon
    assert episode.terminal_reason == "duration_elapsed"
    assert len([point for point in episode.decisions if point.simulation_time == horizon]) == 1


def test_rejects_episode_that_crosses_split_boundary() -> None:
    with pytest.raises(ValueError, match="episode crosses split boundary"):
        EpisodeBuilder().build([], config(split_end=START + timedelta(days=13)))


def test_exhausted_replay_is_an_explicit_terminal_reason() -> None:
    episode = EpisodeBuilder().build(
        [event(150, "last", EventKind.SETTLEMENT)],
        config(),
    )

    assert episode.end == START + timedelta(seconds=150)
    assert episode.terminal_reason == "replay_exhausted"
    assert episode.decisions[-1].source_ids == ("last",)


def test_discount_uses_elapsed_simulation_seconds() -> None:
    episode = EpisodeBuilder().build(
        [event(90, "quote", EventKind.QUOTE)],
        config(discount_rate=0.01),
    )

    point = episode.decisions[-1]
    assert point.elapsed_seconds == 30
    assert point.discount == pytest.approx(math.exp(-0.01 * 30))
