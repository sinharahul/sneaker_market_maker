"""Quote Intent contracts for the Continuous Paper Market-Maker."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class IntentKind(str, Enum):
    PLACE = "place"
    REVISE = "revise"
    CANCEL = "cancel"
    REPLACE = "replace"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class QuoteIntent:
    kind: IntentKind
    side: Side
    principal: Decimal
    expected_fees_and_slippage: Decimal
    product_family: str
    replaces_reservation: Decimal | None = None
