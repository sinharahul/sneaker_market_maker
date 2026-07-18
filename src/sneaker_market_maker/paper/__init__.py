"""Continuous Paper Market-Maker domain package."""

from sneaker_market_maker.paper.allowlist import ALLOWLIST_VERSION, ProductFamily
from sneaker_market_maker.paper.capital import (
    INITIAL_PAPER_CAPITAL,
    OPEN_BUY_PRINCIPAL_CAP,
    PaperCapital,
)
from sneaker_market_maker.paper.gate import DeterministicGate, GateDecision, GateReason

__all__ = [
    "ALLOWLIST_VERSION",
    "DeterministicGate",
    "GateDecision",
    "GateReason",
    "INITIAL_PAPER_CAPITAL",
    "OPEN_BUY_PRINCIPAL_CAP",
    "PaperCapital",
    "ProductFamily",
]
