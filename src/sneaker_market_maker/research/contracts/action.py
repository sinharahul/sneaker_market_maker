"""Hybrid action contracts and deterministic canonicalization."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class ActionCategory(str, Enum):
    NO_OP = "NO_OP"
    QUOTE = "QUOTE"
    CANCEL = "CANCEL"


@dataclass(frozen=True)
class ActionMask:
    no_op: bool
    quote: bool
    cancel: bool


@dataclass(frozen=True)
class ActionBounds:
    bid_low: int
    bid_high: int
    ask_low: int
    ask_high: int


@dataclass(frozen=True)
class RawHybridAction:
    category: ActionCategory
    allocation: float
    bid_offset_ticks: float
    ask_offset_ticks: float


@dataclass(frozen=True)
class HybridAction:
    category: ActionCategory
    allocation: float
    bid_offset_ticks: int
    ask_offset_ticks: int


def canonicalize_action(
    action: RawHybridAction,
    bounds: ActionBounds,
    mask: ActionMask,
) -> HybridAction:
    """Apply action availability, neutralization, rounding, and bounds."""
    allowed = {
        ActionCategory.NO_OP: mask.no_op,
        ActionCategory.QUOTE: mask.quote,
        ActionCategory.CANCEL: mask.cancel,
    }
    if not allowed[action.category]:
        raise ValueError("masked action category")
    if action.category is not ActionCategory.QUOTE:
        return HybridAction(action.category, 0.0, 0, 0)

    values = (
        action.allocation,
        float(action.bid_offset_ticks),
        float(action.ask_offset_ticks),
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("action values must be finite")
    return HybridAction(
        action.category,
        min(1.0, max(0.0, action.allocation)),
        min(bounds.bid_high, max(bounds.bid_low, round(action.bid_offset_ticks))),
        min(bounds.ask_high, max(bounds.ask_low, round(action.ask_offset_ticks))),
    )
