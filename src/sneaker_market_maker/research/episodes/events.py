"""Normalized replay events used to construct research episodes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from sneaker_market_maker.research.contracts.action import ActionBounds, ActionMask


class EventKind(str, Enum):
    BOOK = "book"
    FILL = "fill"
    QUOTE = "quote"
    INVENTORY = "inventory"
    LOGISTICS = "logistics"
    FEE = "fee"
    REGIME = "regime"
    RESTOCK = "restock"
    SETTLEMENT = "settlement"
    FRESHNESS = "freshness"
    RISK_LIMIT = "risk_limit"


@dataclass(frozen=True)
class DecisionPoint:
    index: int
    simulation_time: datetime
    elapsed_seconds: int
    reasons: tuple[EventKind, ...]
    source_ids: tuple[str, ...]
    provenances: tuple[Literal["historical", "synthetic"], ...]
    discount: float
    episode_id: UUID | None = None
    state: Mapping[str, object] = field(default_factory=dict)
    action_mask: ActionMask | None = None
    action_bounds: ActionBounds | None = None
    terminal_reason: str | None = None

    def __post_init__(self) -> None:
        if len(self.source_ids) != len(self.provenances):
            raise ValueError("source IDs and provenances must align")
        object.__setattr__(self, "state", MappingProxyType(dict(self.state)))


@dataclass(frozen=True)
class NormalizedEvent:
    source_id: str
    simulation_time: datetime
    stable_order: int
    kind: EventKind
    payload: Mapping[str, object]
    provenance: Literal["historical", "synthetic"]

    def __post_init__(self) -> None:
        if not self.source_id or not self.source_id.strip():
            raise ValueError("source_id is required")
        if self.provenance not in ("historical", "synthetic"):
            raise ValueError("invalid event provenance")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
