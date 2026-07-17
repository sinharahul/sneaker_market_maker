"""Compatibility adapters for the original five-feature pipeline."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import ClassVar

from sneaker_market_maker.core import MarketSnapshot
from sneaker_market_maker.pipeline import SneakerDataPipeline
from sneaker_market_maker.research.contracts.state import StateValidationError


class LegacyFiveVectorAdapter:
    """Encode the frozen legacy feature order at a validated float boundary."""

    feature_names: ClassVar[tuple[str, ...]] = SneakerDataPipeline.FEATURE_NAMES

    def encode(
        self,
        snapshot: MarketSnapshot,
        fee_rate: Decimal,
    ) -> tuple[float, float, float, float, float]:
        values = (
            float(snapshot.highest_bid),
            float(snapshot.lowest_ask),
            float(snapshot.days_since_release),
            float(snapshot.volatility_48h),
            float(fee_rate),
        )
        if not all(math.isfinite(value) for value in values):
            raise StateValidationError("legacy five-vector values must be finite")
        return values
