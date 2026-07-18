"""Load Golden Historical Replay Datasets and StockX-shaped fixtures."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sneaker_market_maker.paper.allowlist import (
    ALLOWED_FAMILIES,
    ALLOWLIST_VERSION,
    ProductFamily,
    assert_family_allowed,
)
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.paper.replay.errors import ReplayLoadError
from sneaker_market_maker.paper.replay.manifest import ReplayManifest, SourceKind


@dataclass(frozen=True)
class MarketReplayEvent:
    event_id: str
    product_family: ProductFamily
    style_code: str
    shoe_size: Decimal
    highest_bid: Decimal
    lowest_ask: Decimal
    source_timestamp: datetime


@dataclass(frozen=True)
class LoadedReplay:
    manifest: ReplayManifest
    events: tuple[MarketReplayEvent, ...]

    @property
    def is_golden_historical_replay(self) -> bool:
        return self.manifest.source_kind == "historical"


def load_golden_historical_replay(directory: Path | str) -> LoadedReplay:
    """Load a checksummed historical-shaped Golden Historical Replay Dataset."""

    return _load(Path(directory), required_source_kind="historical")


def load_stockx_shaped_fixture(directory: Path | str) -> LoadedReplay:
    """Load a StockX-shaped fixture for local smoke — not execution evidence."""

    return _load(Path(directory), required_source_kind="fixture")


def _load(directory: Path, *, required_source_kind: SourceKind) -> LoadedReplay:
    manifest_path = directory / "manifest.json"
    events_path = directory / "events.jsonl"
    if not manifest_path.is_file() or not events_path.is_file():
        raise ReplayLoadError(
            "missing_replay_files",
            "replay directory must contain manifest.json and events.jsonl",
        )

    raw_manifest = _read_json_object(manifest_path)
    manifest = _parse_manifest(raw_manifest)
    if manifest.source_kind != required_source_kind:
        raise ReplayLoadError(
            "invalid_source_kind",
            f"expected source_kind={required_source_kind!r}, got {manifest.source_kind!r}",
        )
    if manifest.allowlist_version != ALLOWLIST_VERSION:
        raise ReplayLoadError(
            "allowlist_version_mismatch",
            f"manifest allowlist_version must be {ALLOWLIST_VERSION}",
        )
    if set(manifest.product_families) != ALLOWED_FAMILIES:
        raise ReplayLoadError(
            "allowlist_scope_mismatch",
            "manifest product_families must exactly match the Product-Family Allowlist",
        )

    body = events_path.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    if digest != manifest.checksum_sha256.casefold():
        raise ReplayLoadError(
            "checksum_mismatch",
            "events.jsonl sha256 does not match manifest checksum_sha256",
        )

    events = tuple(
        sorted(
            (_parse_event(line) for line in body.decode("utf-8").splitlines() if line.strip()),
            key=lambda event: (event.source_timestamp, event.event_id),
        )
    )
    if not events:
        raise ReplayLoadError("empty_replay", "events.jsonl must contain at least one event")
    return LoadedReplay(manifest=manifest, events=events)


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReplayLoadError("invalid_manifest", "manifest.json must be valid JSON") from error
    if not isinstance(payload, dict):
        raise ReplayLoadError("invalid_manifest", "manifest.json must be a JSON object")
    return payload


def _parse_manifest(raw: dict[str, Any]) -> ReplayManifest:
    try:
        source_kind = raw["source_kind"]
        if source_kind not in ("historical", "fixture"):
            raise ReplayLoadError(
                "invalid_source_kind",
                "source_kind must be historical or fixture",
            )
        families = raw["product_families"]
        if not isinstance(families, list) or not all(isinstance(item, str) for item in families):
            raise ReplayLoadError("invalid_manifest", "product_families must be a string list")
        return ReplayManifest(
            dataset_id=str(raw["dataset_id"]),
            version=str(raw["version"]),
            checksum_sha256=str(raw["checksum_sha256"]).casefold(),
            source_kind=source_kind,
            schema_version=str(raw["schema_version"]),
            allowlist_version=str(raw["allowlist_version"]),
            product_families=tuple(families),
        )
    except KeyError as error:
        raise ReplayLoadError(
            "invalid_manifest",
            f"manifest missing required field {error.args[0]!r}",
        ) from error


def _parse_event(line: str) -> MarketReplayEvent:
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as error:
        raise ReplayLoadError("invalid_event", "events.jsonl lines must be JSON objects") from error
    if not isinstance(raw, dict):
        raise ReplayLoadError("invalid_event", "each event must be a JSON object")
    try:
        family = assert_family_allowed(str(raw["product_family"]))
    except PaperError as error:
        raise ReplayLoadError(error.code, str(error)) from error
    try:
        timestamp = datetime.fromisoformat(str(raw["source_timestamp"]))
        if timestamp.tzinfo is None:
            raise ReplayLoadError(
                "invalid_event",
                "source_timestamp must be timezone-aware ISO-8601",
            )
        return MarketReplayEvent(
            event_id=str(raw["event_id"]),
            product_family=family,
            style_code=str(raw["style_code"]),
            shoe_size=Decimal(str(raw["shoe_size"])),
            highest_bid=Decimal(str(raw["highest_bid"])),
            lowest_ask=Decimal(str(raw["lowest_ask"])),
            source_timestamp=timestamp,
        )
    except ReplayLoadError:
        raise
    except (KeyError, ArithmeticError, ValueError, TypeError) as error:
        raise ReplayLoadError(
            "invalid_event",
            "event is missing required fields or has invalid timestamp/numerics",
        ) from error


__all__ = [
    "LoadedReplay",
    "MarketReplayEvent",
    "load_golden_historical_replay",
    "load_stockx_shaped_fixture",
]
