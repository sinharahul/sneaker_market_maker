"""Framework-independent ports for policy evaluation."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Protocol

from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionMask,
    HybridAction,
    RawHybridAction,
)
from sneaker_market_maker.research.encoding.schema import EncodedState
from sneaker_market_maker.research.episodes.builder import Episode


@dataclass(frozen=True)
class PolicyOutput:
    action: RawHybridAction
    score: float | None
    policy_id: str
    latency_ms: int

    def __post_init__(self) -> None:
        if not self.policy_id or not self.policy_id.strip():
            raise ValueError("policy_id is required")
        if self.score is not None and not math.isfinite(self.score):
            raise ValueError("policy score must be finite")
        if self.latency_ms < 0:
            raise ValueError("policy latency_ms cannot be negative")


class EvaluationPolicy(Protocol):
    @property
    def policy_id(self) -> str:
        raise NotImplementedError

    def recommend(
        self,
        state: EncodedState,
        mask: ActionMask,
        bounds: ActionBounds,
    ) -> PolicyOutput:
        raise NotImplementedError


@dataclass(frozen=True)
class FrozenAssumptions:
    episode_hash: str
    fee_version: str
    slippage_version: str
    logistics_version: str
    terminal_policy_version: str
    gate_policy_version: str
    latency_ms: int

    def __post_init__(self) -> None:
        versions = (
            self.episode_hash,
            self.fee_version,
            self.slippage_version,
            self.logistics_version,
            self.terminal_policy_version,
            self.gate_policy_version,
        )
        if any(not value or not value.strip() for value in versions):
            raise ValueError("frozen assumption versions are required")
        if self.latency_ms < 0:
            raise ValueError("latency_ms cannot be negative")

    def to_bytes(self) -> bytes:
        return json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()


@dataclass(frozen=True)
class MetricInterval:
    point: float
    lower: float
    upper: float
    confidence: float

    def __post_init__(self) -> None:
        values = (self.point, self.lower, self.upper, self.confidence)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("metric interval values must be finite")
        if not 0.0 < self.confidence < 1.0:
            raise ValueError("metric confidence must be in (0, 1)")
        if self.lower > self.point or self.point > self.upper:
            raise ValueError("metric point must lie inside its interval")


@dataclass(frozen=True)
class EvaluationReport:
    policy_id: str
    assumptions_hash: str
    metrics: Mapping[str, MetricInterval]
    support_coverage: float
    numerical_failures: int
    seed_results: Mapping[int, Mapping[str, float]]
    historical: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        object.__setattr__(
            self,
            "seed_results",
            MappingProxyType(
                {
                    seed: MappingProxyType(dict(values))
                    for seed, values in self.seed_results.items()
                }
            ),
        )


@dataclass(frozen=True)
class EpisodeEvaluation:
    """Simulator-owned outcomes after all costs, terminal handling, and gates."""

    metrics: Mapping[str, float]
    support_coverage: float
    numerical_failures: int
    seed: int
    latency_ms: float

    def __post_init__(self) -> None:
        values = (*self.metrics.values(), self.support_coverage, self.latency_ms)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("episode evaluation values must be finite")
        if not 0.0 <= self.support_coverage <= 1.0:
            raise ValueError("support coverage must be in [0, 1]")
        if self.numerical_failures < 0 or self.latency_ms < 0:
            raise ValueError("evaluation counts and latency cannot be negative")
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))


class EvaluationSimulator(Protocol):
    def run_episode(
        self,
        episode: Episode,
        actions: tuple[HybridAction, ...],
        assumptions: FrozenAssumptions,
    ) -> EpisodeEvaluation:
        raise NotImplementedError


__all__ = [
    "EpisodeEvaluation",
    "EvaluationPolicy",
    "EvaluationReport",
    "EvaluationSimulator",
    "FrozenAssumptions",
    "MetricInterval",
    "PolicyOutput",
]
