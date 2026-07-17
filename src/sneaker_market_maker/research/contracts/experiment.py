"""Immutable contracts for leakage-safe research experiments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class Fold:
    fold_id: str
    train_episode_ids: tuple[UUID, ...]
    validation_episode_ids: tuple[UUID, ...]
    test_episode_ids: tuple[UUID, ...]
    frozen_holdout_hash: str


@dataclass(frozen=True)
class EpisodeManifest:
    episode_id: UUID
    start: datetime
    end: datetime
    split: Literal["train", "validation", "test"]
    product_size_lineage: str
    source_record_ids: tuple[str, ...]
    provenance: Literal["historical", "synthetic"]
    checksum: str

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("episode end must be after start")
        if self.split not in ("train", "validation", "test"):
            raise ValueError("invalid episode split")
        if self.provenance not in ("historical", "synthetic"):
            raise ValueError("invalid episode provenance")
        if not self.product_size_lineage or not self.product_size_lineage.strip():
            raise ValueError("product_size_lineage is required")
        if not self.source_record_ids:
            raise ValueError("source_record_ids are required")
        if any(not source_id or not source_id.strip() for source_id in self.source_record_ids):
            raise ValueError("source record IDs must be nonempty")
        if not self.checksum or not self.checksum.strip():
            raise ValueError("checksum is required")
        object.__setattr__(self, "source_record_ids", tuple(self.source_record_ids))


@dataclass(frozen=True)
class WalkForwardConfig:
    train_episodes: int
    validation_episodes: int
    test_episodes: int
    step_episodes: int

    def __post_init__(self) -> None:
        for field_name in (
            "train_episodes",
            "validation_episodes",
            "test_episodes",
            "step_episodes",
        ):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be positive")
