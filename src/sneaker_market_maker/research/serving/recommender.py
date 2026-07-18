"""Fail-closed shadow and bounded advisory recommendations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import monotonic
from typing import Protocol
from uuid import UUID

from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionMask,
    HybridAction,
    RawHybridAction,
    canonicalize_action,
)
from sneaker_market_maker.research.registry.service import RegistryState


@dataclass(frozen=True)
class GateResult:
    accepted: bool
    results: tuple[tuple[str, bool], ...]


@dataclass(frozen=True)
class RecommendationRequest:
    request_id: UUID
    deterministic_action: HybridAction
    pfhedge_action: RawHybridAction | None
    iql_action: RawHybridAction | None
    selected_model_action: RawHybridAction | None
    bounds: ActionBounds
    mask: ActionMask
    risk_state: Mapping[str, object]
    registry_state: RegistryState
    support_ok: bool
    healthy: bool
    drifted: bool
    lineage_compatible: bool


@dataclass(frozen=True)
class RecommendationRecord:
    request_id: UUID
    deterministic_action: HybridAction
    pfhedge_action: RawHybridAction | None
    iql_action: RawHybridAction | None
    canonical_action: HybridAction | None
    gate_results: tuple[tuple[str, bool], ...]
    final_action: HybridAction
    fallback_reason: str | None


class GatePort(Protocol):
    """Deterministic gates; intentionally has no execution capability."""

    def evaluate(
        self,
        action: HybridAction,
        risk_state: Mapping[str, object],
    ) -> GateResult:
        raise NotImplementedError


class ComparisonStore(Protocol):
    """Persistence boundary for recommendation comparisons only."""

    def save(self, record: RecommendationRecord) -> None:
        raise NotImplementedError


class RecommendationService:
    def __init__(
        self,
        gates: GatePort,
        comparisons: ComparisonStore,
        *,
        clock: Callable[[], float] = monotonic,
        timeout_seconds: float = 0.05,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.gates = gates
        self.comparisons = comparisons
        self._clock = clock
        self._timeout_seconds = timeout_seconds

    def recommend(self, request: RecommendationRequest) -> RecommendationRecord:
        candidate = (
            canonicalize_action(request.selected_model_action, request.bounds, request.mask)
            if request.selected_model_action is not None
            else None
        )
        gate_result = (
            self._evaluate_gates(candidate, request.risk_state)
            if candidate is not None
            else GateResult(False, (("model_output_present", False),))
        )
        gate_result = self._apply_runtime_checks(request, gate_result)

        if request.registry_state is RegistryState.SHADOW:
            final_action = request.deterministic_action
        elif (
            request.registry_state is RegistryState.ADVISORY_APPROVED
            and candidate is not None
            and gate_result.accepted
        ):
            final_action = candidate
        else:
            final_action = request.deterministic_action

        record = RecommendationRecord(
            request_id=request.request_id,
            deterministic_action=request.deterministic_action,
            pfhedge_action=request.pfhedge_action,
            iql_action=request.iql_action,
            canonical_action=candidate,
            gate_results=gate_result.results,
            final_action=final_action,
            fallback_reason=self._fallback_reason(request, gate_result),
        )
        self.comparisons.save(record)
        return record

    def _evaluate_gates(
        self,
        candidate: HybridAction,
        risk_state: Mapping[str, object],
    ) -> GateResult:
        started_at = self._clock()
        result = self.gates.evaluate(candidate, risk_state)
        if self._clock() - started_at > self._timeout_seconds:
            return GateResult(False, (*result.results, ("timeout", False)))
        return result

    @staticmethod
    def _apply_runtime_checks(
        request: RecommendationRequest,
        gate_result: GateResult,
    ) -> GateResult:
        runtime_ok = (
            request.support_ok
            and request.healthy
            and not request.drifted
            and request.lineage_compatible
        )
        return GateResult(gate_result.accepted and runtime_ok, gate_result.results)

    @staticmethod
    def _fallback_reason(
        request: RecommendationRequest,
        gate_result: GateResult,
    ) -> str | None:
        if not request.healthy:
            return "unhealthy_service"
        if not request.lineage_compatible:
            return "incompatible_lineage"
        if request.drifted:
            return "drift"
        if not request.support_ok:
            return "weak_support"
        if request.selected_model_action is None:
            return "missing_artifact"
        for name, passed in gate_result.results:
            if not passed:
                return "timeout" if name == "timeout" else f"gate_failed:{name}"
        if request.registry_state not in {
            RegistryState.SHADOW,
            RegistryState.ADVISORY_APPROVED,
        }:
            return "registry_not_serving"
        return None


__all__ = [
    "ComparisonStore",
    "GatePort",
    "GateResult",
    "RecommendationRecord",
    "RecommendationRequest",
    "RecommendationService",
]
