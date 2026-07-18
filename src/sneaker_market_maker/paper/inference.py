"""Injectable IQL inference with pinned Inference Latency Budget."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sneaker_market_maker.paper.decision_state import PaperDecisionState
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.research.contracts.action import HybridAction

DEFAULT_LATENCY_MS = 100
MAX_LATENCY_MS = 250


class InferenceError(PaperError):
    """Fail-closed inference / budget configuration error."""


@dataclass(frozen=True)
class InferenceLatencyBudget:
    """Wall-clock budget for one paper-tick IQL call (milliseconds)."""

    limit_ms: int = DEFAULT_LATENCY_MS

    def __post_init__(self) -> None:
        if self.limit_ms <= 0:
            raise InferenceError("invalid_budget", "latency budget must be positive")
        if self.limit_ms > MAX_LATENCY_MS:
            raise InferenceError(
                "budget_ceiling",
                f"latency budget cannot exceed {MAX_LATENCY_MS}ms",
            )


@dataclass(frozen=True)
class InferenceOutcome:
    valid: bool
    action: HybridAction | None
    latency_ms: float
    reason: str | None


class IqlInferencePort(Protocol):
    """Production binds a real model; tests inject stubs behind this port."""

    def infer(self, state: PaperDecisionState) -> tuple[HybridAction, float]:
        """Return (action, observed_latency_ms). Raise InferenceError on hard failure."""


@dataclass
class StubIqlInference:
    """Deterministic test double — no Torch weights required."""

    action: HybridAction | None = None
    latency_ms: float = 0.0
    fail_with: str | None = None

    def infer(self, state: PaperDecisionState) -> tuple[HybridAction, float]:
        _ = state
        if self.fail_with is not None:
            raise InferenceError(self.fail_with, self.fail_with)
        if self.action is None:
            raise InferenceError("no_action", "stub IQL has no action configured")
        return self.action, self.latency_ms


@dataclass(frozen=True)
class TimedIqlInference:
    """Enforce Inference Latency Budget around an IqlInferencePort."""

    port: IqlInferencePort
    budget: InferenceLatencyBudget

    def infer(self, state: PaperDecisionState) -> InferenceOutcome:
        try:
            action, latency_ms = self.port.infer(state)
        except InferenceError as error:
            return InferenceOutcome(
                valid=False,
                action=None,
                latency_ms=0.0,
                reason=error.code,
            )
        if latency_ms > self.budget.limit_ms:
            return InferenceOutcome(
                valid=False,
                action=None,
                latency_ms=float(latency_ms),
                reason="timeout",
            )
        return InferenceOutcome(
            valid=True,
            action=action,
            latency_ms=float(latency_ms),
            reason=None,
        )
