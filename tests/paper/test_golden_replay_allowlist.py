"""Tests for Product-Family Allowlist and Golden Historical Replay ingest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sneaker_market_maker.paper.allowlist import (
    ALLOWLIST_VERSION,
    ProductFamily,
    assert_family_allowed,
)
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.paper.replay.errors import ReplayLoadError
from sneaker_market_maker.paper.replay.loader import (
    load_golden_historical_replay,
    load_stockx_shaped_fixture,
)

TS = "2026-01-01T00:00:00+00:00"


def test_allowlist_accepts_jordan_and_dunk_only() -> None:
    assert assert_family_allowed("jordan_1_retro") is ProductFamily.JORDAN_1_RETRO
    assert assert_family_allowed("nike_dunk_low") is ProductFamily.NIKE_DUNK_LOW
    with pytest.raises(PaperError) as exc:
        assert_family_allowed("yeezy")
    assert exc.value.code == "unsupported_product_family"


def test_allowlist_version_is_pinned() -> None:
    assert ALLOWLIST_VERSION == "product-families-v1"


def _write_events(path: Path, events: list[dict[str, object]]) -> str:
    body = "".join(json.dumps(event, sort_keys=True) + "\n" for event in events)
    path.write_text(body, encoding="utf-8")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _manifest(checksum: str, *, source_kind: str = "historical") -> dict[str, object]:
    return {
        "dataset_id": "golden-test",
        "version": "1.0.0",
        "checksum_sha256": checksum,
        "source_kind": source_kind,
        "schema_version": "market-event-v1",
        "allowlist_version": ALLOWLIST_VERSION,
        "product_families": ["jordan_1_retro", "nike_dunk_low"],
    }


def test_golden_replay_loads_when_checksum_and_families_match(tmp_path: Path) -> None:
    events = [
        {
            "event_id": "e1",
            "product_family": "jordan_1_retro",
            "style_code": "555088-001",
            "shoe_size": "10",
            "highest_bid": "200",
            "lowest_ask": "250",
            "source_timestamp": TS,
        },
        {
            "event_id": "e2",
            "product_family": "nike_dunk_low",
            "style_code": "DD1391-100",
            "shoe_size": "9",
            "highest_bid": "100",
            "lowest_ask": "140",
            "source_timestamp": "2026-01-01T00:00:01+00:00",
        },
    ]
    checksum = _write_events(tmp_path / "events.jsonl", events)
    (tmp_path / "manifest.json").write_text(json.dumps(_manifest(checksum)), encoding="utf-8")

    replay = load_golden_historical_replay(tmp_path)
    assert replay.manifest.source_kind == "historical"
    assert replay.manifest.checksum_sha256 == checksum
    assert len(replay.events) == 2


def test_golden_replay_rejects_checksum_mismatch(tmp_path: Path) -> None:
    _write_events(
        tmp_path / "events.jsonl",
        [
            {
                "event_id": "e1",
                "product_family": "jordan_1_retro",
                "style_code": "555088-001",
                "shoe_size": "10",
                "highest_bid": "200",
                "lowest_ask": "250",
                "source_timestamp": TS,
            }
        ],
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(_manifest("0" * 64)),
        encoding="utf-8",
    )
    with pytest.raises(ReplayLoadError) as exc:
        load_golden_historical_replay(tmp_path)
    assert exc.value.code == "checksum_mismatch"


def test_golden_replay_rejects_non_allowlisted_family_in_events(tmp_path: Path) -> None:
    events = [
        {
            "event_id": "e1",
            "product_family": "yeezy",
            "style_code": "CP9654",
            "shoe_size": "10",
            "highest_bid": "200",
            "lowest_ask": "250",
            "source_timestamp": TS,
        }
    ]
    checksum = _write_events(tmp_path / "events.jsonl", events)
    (tmp_path / "manifest.json").write_text(json.dumps(_manifest(checksum)), encoding="utf-8")
    with pytest.raises(ReplayLoadError) as exc:
        load_golden_historical_replay(tmp_path)
    assert exc.value.code == "unsupported_product_family"


def test_golden_replay_rejects_non_historical_source_kind(tmp_path: Path) -> None:
    checksum = _write_events(
        tmp_path / "events.jsonl",
        [
            {
                "event_id": "e1",
                "product_family": "jordan_1_retro",
                "style_code": "555088-001",
                "shoe_size": "10",
                "highest_bid": "200",
                "lowest_ask": "250",
                "source_timestamp": TS,
            }
        ],
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(_manifest(checksum, source_kind="fixture")),
        encoding="utf-8",
    )
    with pytest.raises(ReplayLoadError) as exc:
        load_golden_historical_replay(tmp_path)
    assert exc.value.code == "invalid_source_kind"


def test_stockx_shaped_fixture_loads_without_being_golden(tmp_path: Path) -> None:
    events = [
        {
            "event_id": "f1",
            "product_family": "jordan_1_retro",
            "style_code": "555088-001",
            "shoe_size": "10",
            "highest_bid": "200",
            "lowest_ask": "250",
            "source_timestamp": TS,
        }
    ]
    checksum = _write_events(tmp_path / "events.jsonl", events)
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                **_manifest(checksum, source_kind="fixture"),
                "dataset_id": "local-fixture",
                "version": "0.0.1",
            }
        ),
        encoding="utf-8",
    )
    fixture = load_stockx_shaped_fixture(tmp_path)
    assert fixture.manifest.source_kind == "fixture"
    assert not fixture.is_golden_historical_replay


def test_bundled_golden_v1_dataset_loads() -> None:
    root = Path(__file__).resolve().parents[2] / "data" / "paper" / "golden_v1"
    replay = load_golden_historical_replay(root)
    assert replay.manifest.dataset_id == "golden-stockx-v1"
    assert replay.manifest.source_kind == "historical"
    assert {event.product_family for event in replay.events} <= {
        ProductFamily.JORDAN_1_RETRO,
        ProductFamily.NIKE_DUNK_LOW,
    }
