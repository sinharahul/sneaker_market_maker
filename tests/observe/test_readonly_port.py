"""L1 read-only market observation port."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sneaker_market_maker.observe import (
    ObserveError,
    RecordedReadOnlyMarketPort,
    default_observe_fixture_path,
    normalize_stockx_shaped_payload,
)
from sneaker_market_maker.paper.allowlist import ProductFamily


def _valid(**overrides: object) -> dict:
    base = {
        "event_id": "obs-1",
        "product_family": "jordan_1_retro",
        "style_code": "555088-134",
        "shoe_size": "10",
        "highest_bid": "220.00",
        "lowest_ask": "275.00",
        "observed_at": "2026-07-18T12:00:00+00:00",
    }
    base.update(overrides)
    return base


def test_allowlisted_fixture_polls() -> None:
    port = RecordedReadOnlyMarketPort(default_observe_fixture_path())
    snaps = port.poll()
    assert len(snaps) == 2
    assert snaps[0].product_family is ProductFamily.JORDAN_1_RETRO
    assert snaps[1].product_family is ProductFamily.NIKE_DUNK_LOW
    event = snaps[0].as_market_event()
    assert event.event_id == "obs-1"


def test_off_allowlist_fails_closed() -> None:
    with pytest.raises(ObserveError) as exc:
        normalize_stockx_shaped_payload(_valid(product_family="yeezy_boost"))
    assert exc.value.code == "unsupported_product_family"


@pytest.mark.parametrize(
    "overrides",
    [
        {"highest_bid": None},
        {"lowest_ask": "nan"},
        {"highest_bid": "300", "lowest_ask": "200"},
        {"observed_at": "2026-07-18T12:00:00"},
    ],
)
def test_corrupt_payloads_fail_closed(overrides: dict) -> None:
    with pytest.raises(ObserveError) as exc:
        normalize_stockx_shaped_payload(_valid(**overrides))
    assert exc.value.code == "corrupt_payload"


def test_recorded_port_rejects_bad_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ObserveError) as exc:
        RecordedReadOnlyMarketPort(path).poll()
    assert exc.value.code == "corrupt_payload"


def test_recorded_port_rejects_off_allowlist_row(tmp_path: Path) -> None:
    path = tmp_path / "obs.json"
    path.write_text(
        json.dumps(
            {
                "allowlist_version": "product-families-v1",
                "observations": [_valid(product_family="air_force_1")],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ObserveError) as exc:
        RecordedReadOnlyMarketPort(path).poll()
    assert exc.value.code == "unsupported_product_family"
