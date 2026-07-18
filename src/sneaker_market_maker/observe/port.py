"""Read-only StockX-shaped market observation port (Track L1 — no order send)."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

from sneaker_market_maker.paper.allowlist import (
    ALLOWLIST_VERSION,
    ProductFamily,
    assert_family_allowed,
)
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.paper.replay.loader import MarketReplayEvent


class ObserveError(PaperError):
    """Fail-closed read-only observe / ingest error."""


@dataclass(frozen=True)
class ObserveSnapshot:
    """Normalized allowlisted observation (compatible with MarketReplayEvent fields)."""

    event_id: str
    product_family: ProductFamily
    style_code: str
    shoe_size: Decimal
    highest_bid: Decimal
    lowest_ask: Decimal
    observed_at: datetime

    def as_market_event(self) -> MarketReplayEvent:
        return MarketReplayEvent(
            event_id=self.event_id,
            product_family=self.product_family,
            style_code=self.style_code,
            shoe_size=self.shoe_size,
            highest_bid=self.highest_bid,
            lowest_ask=self.lowest_ask,
            source_timestamp=self.observed_at,
        )


class ReadOnlyMarketPort(Protocol):
    """Observe-only port: never places orders; never accepts order credentials."""

    def poll(self) -> tuple[ObserveSnapshot, ...]:
        """Return the latest allowlisted observations or raise ObserveError."""


def _finite_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ObserveError("corrupt_payload", f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ObserveError("corrupt_payload", f"{field} must be numeric") from error
    if not result.is_finite():
        raise ObserveError("corrupt_payload", f"{field} must be finite")
    return result


def normalize_stockx_shaped_payload(raw: Mapping[str, Any]) -> ObserveSnapshot:
    """Normalize one StockX-shaped observation; fail closed on corrupt input."""

    required = (
        "event_id",
        "product_family",
        "style_code",
        "shoe_size",
        "highest_bid",
        "lowest_ask",
        "observed_at",
    )
    for key in required:
        if key not in raw or raw[key] is None:
            raise ObserveError("corrupt_payload", f"missing required field {key!r}")

    try:
        family = assert_family_allowed(str(raw["product_family"]))
    except PaperError as error:
        raise ObserveError(error.code, str(error)) from error

    try:
        observed_at = datetime.fromisoformat(str(raw["observed_at"]))
    except ValueError as error:
        raise ObserveError(
            "corrupt_payload",
            "observed_at must be timezone-aware ISO-8601",
        ) from error
    if observed_at.tzinfo is None:
        raise ObserveError(
            "corrupt_payload",
            "observed_at must be timezone-aware ISO-8601",
        )

    highest_bid = _finite_decimal(raw["highest_bid"], "highest_bid")
    lowest_ask = _finite_decimal(raw["lowest_ask"], "lowest_ask")
    shoe_size = _finite_decimal(raw["shoe_size"], "shoe_size")
    if highest_bid <= 0 or lowest_ask <= 0:
        raise ObserveError("corrupt_payload", "bid and ask must be positive")
    if lowest_ask < highest_bid:
        raise ObserveError("corrupt_payload", "lowest_ask must be >= highest_bid")
    if shoe_size <= 0:
        raise ObserveError("corrupt_payload", "shoe_size must be positive")

    for label in ("highest_bid", "lowest_ask"):
        value = raw[label]
        if isinstance(value, float) and not math.isfinite(value):
            raise ObserveError("corrupt_payload", f"{label} must be finite")

    return ObserveSnapshot(
        event_id=str(raw["event_id"]),
        product_family=family,
        style_code=str(raw["style_code"]),
        shoe_size=shoe_size,
        highest_bid=highest_bid,
        lowest_ask=lowest_ask,
        observed_at=observed_at,
    )


@dataclass(frozen=True)
class RecordedReadOnlyMarketPort:
    """Read-only port backed by recorded JSON — no HTTP, no order credentials."""

    path: Path
    allowlist_version: str = ALLOWLIST_VERSION

    def poll(self) -> tuple[ObserveSnapshot, ...]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ObserveError(
                "corrupt_payload",
                "observe fixture must be valid JSON",
            ) from error
        if not isinstance(payload, dict):
            raise ObserveError("corrupt_payload", "observe fixture must be a JSON object")
        version = payload.get("allowlist_version")
        if version != self.allowlist_version:
            raise ObserveError(
                "allowlist_version_mismatch",
                f"allowlist_version must be {self.allowlist_version}",
            )
        observations = payload.get("observations")
        if not isinstance(observations, list) or not observations:
            raise ObserveError("corrupt_payload", "observations must be a non-empty list")
        out: list[ObserveSnapshot] = []
        for item in observations:
            if not isinstance(item, Mapping):
                raise ObserveError(
                    "corrupt_payload",
                    "each observation must be a JSON object",
                )
            out.append(normalize_stockx_shaped_payload(item))
        return tuple(out)


def default_observe_fixture_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "data"
        / "observe"
        / "fixtures"
        / "allowlisted_v1"
        / "observations.json"
    )


__all__ = [
    "ObserveError",
    "ObserveSnapshot",
    "ReadOnlyMarketPort",
    "RecordedReadOnlyMarketPort",
    "default_observe_fixture_path",
    "normalize_stockx_shaped_payload",
]
