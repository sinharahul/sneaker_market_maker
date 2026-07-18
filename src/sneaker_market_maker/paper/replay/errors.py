"""Replay ingest errors."""

from __future__ import annotations

from sneaker_market_maker.paper.errors import PaperError


class ReplayLoadError(PaperError):
    """Raised when a replay dataset cannot be loaded safely."""
