"""Normalize heterogeneous marketplace payloads without silent data corruption."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np

from .core import MarketSnapshot


class PayloadError(ValueError):
    """Raised when marketplace data cannot be safely normalized."""


class SneakerDataPipeline:
    """Convert marketplace JSON into validated snapshots and numeric features."""

    FEATURE_NAMES = (
        "highest_bid",
        "lowest_ask",
        "days_since_release",
        "volatility_48h",
        "fee_rate",
    )

    def __init__(self, default_fee_rate: Decimal = Decimal("0.13")) -> None:
        if not Decimal("0") <= default_fee_rate < Decimal("1"):
            raise ValueError("default_fee_rate must be in [0, 1)")
        self.default_fee_rate = default_fee_rate

    @staticmethod
    def _first(data: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return default

    @staticmethod
    def _decimal(value: Any, field: str) -> Decimal:
        if isinstance(value, bool):
            raise PayloadError(f"{field} must be numeric")
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PayloadError(f"{field} must be numeric") from exc
        if not result.is_finite():
            raise PayloadError(f"{field} must be finite")
        return result

    @classmethod
    def _sales_prices(cls, sales: Any) -> list[float]:
        if sales is None:
            return []
        if isinstance(sales, (str, bytes)) or not isinstance(sales, Sequence):
            raise PayloadError("recent sales must be a sequence")

        prices: list[float] = []
        for sale in sales:
            value = sale.get("price") if isinstance(sale, Mapping) else sale
            price = cls._decimal(value, "sale price")
            if price <= 0:
                raise PayloadError("sale price must be positive")
            prices.append(float(price))
        return prices

    @staticmethod
    def _days_since_release(value: Any) -> int:
        if isinstance(value, str) and "-" in value:
            try:
                released = date.fromisoformat(value)
            except ValueError as exc:
                raise PayloadError("release_date must be ISO-8601") from exc
            return max((datetime.now(timezone.utc).date() - released).days, 0)
        try:
            days = int(value)
        except (TypeError, ValueError) as exc:
            raise PayloadError("days_since_release must be an integer") from exc
        if days < 0:
            raise PayloadError("days_since_release cannot be negative")
        return days

    def parse_payload(
        self,
        raw_payload: str | bytes | Mapping[str, Any],
        *,
        platform: str | None = None,
    ) -> tuple[MarketSnapshot, Decimal]:
        if isinstance(raw_payload, Mapping):
            data = raw_payload
        else:
            try:
                data = json.loads(raw_payload)
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as exc:
                raise PayloadError("payload is not valid JSON") from exc
        if not isinstance(data, Mapping):
            raise PayloadError("payload root must be an object")

        bid = self._decimal(self._first(data, "highestBid", "highest_bid"), "highest_bid")
        ask = self._decimal(self._first(data, "lowestAsk", "lowest_ask"), "lowest_ask")
        size = self._decimal(self._first(data, "shoeSize", "shoe_size", "size"), "shoe_size")
        style_code = str(self._first(data, "styleCode", "style_code", default="")).strip()
        source = str(platform or self._first(data, "platform", "source", default="")).strip()
        days = self._days_since_release(
            self._first(
                data,
                "daysSinceRelease",
                "days_released",
                "days_since_release",
                "release_date",
                default=0,
            )
        )
        sales = self._sales_prices(
            self._first(data, "recentSales", "completed_sales", default=[])
        )
        if len(sales) >= 2:
            volatility = Decimal(str(float(np.std(sales, ddof=1))))
        else:
            volatility = self._decimal(
                self._first(data, "fallback_volatility", "volatility_48h", default=0),
                "fallback_volatility",
            )
        fee_rate = self._decimal(
            self._first(data, "fee_tier", "fee_rate", default=self.default_fee_rate),
            "fee_rate",
        )
        if not Decimal("0") <= fee_rate < Decimal("1"):
            raise PayloadError("fee_rate must be in [0, 1)")

        try:
            snapshot = MarketSnapshot(
                platform=source,
                style_code=style_code,
                shoe_size=size,
                highest_bid=bid,
                lowest_ask=ask,
                sales_48h=len(sales),
                volatility_48h=volatility,
                days_since_release=days,
            )
        except ValueError as exc:
            raise PayloadError(str(exc)) from exc
        return snapshot, fee_rate

    def to_numpy(
        self,
        payloads: Sequence[str | bytes | Mapping[str, Any]],
        *,
        platform: str | None = None,
    ) -> np.ndarray:
        rows: list[list[float]] = []
        for payload in payloads:
            snapshot, fee_rate = self.parse_payload(payload, platform=platform)
            rows.append(
                [
                    float(snapshot.highest_bid),
                    float(snapshot.lowest_ask),
                    float(snapshot.days_since_release),
                    float(snapshot.volatility_48h),
                    float(fee_rate),
                ]
            )
        return np.asarray(rows, dtype=np.float32).reshape((-1, len(self.FEATURE_NAMES)))
