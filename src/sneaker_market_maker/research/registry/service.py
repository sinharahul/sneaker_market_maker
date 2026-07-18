"""Immutable model registration and fail-closed promotion governance."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4


class RegistryState(str, Enum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    SHADOW = "shadow"
    BENCHMARK_QUALIFIED = "benchmark_qualified"
    ADVISORY_APPROVED = "advisory_approved"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


LEGAL_TRANSITIONS = {
    RegistryState.CANDIDATE: {RegistryState.VALIDATED, RegistryState.REJECTED},
    RegistryState.VALIDATED: {RegistryState.SHADOW, RegistryState.REJECTED},
    RegistryState.SHADOW: {RegistryState.BENCHMARK_QUALIFIED, RegistryState.ROLLED_BACK},
    RegistryState.BENCHMARK_QUALIFIED: {
        RegistryState.ADVISORY_APPROVED,
        RegistryState.ROLLED_BACK,
    },
    RegistryState.ADVISORY_APPROVED: {RegistryState.ROLLED_BACK},
    RegistryState.ROLLED_BACK: set(),
    RegistryState.REJECTED: set(),
}


@dataclass(frozen=True)
class CompatibilityContract:
    state_schema_version: str
    action_schema_version: str
    encoder_version: str
    reward_version: str
    architecture: str
    environment_hash: str


@dataclass(frozen=True)
class BenchmarkCriterion:
    name: str
    comparison: Literal["minimum", "maximum", "required"]
    threshold: float | bool


@dataclass(frozen=True)
class BenchmarkPolicy:
    version: str
    criteria: tuple[BenchmarkCriterion, ...]
    frozen_at: datetime


@dataclass(frozen=True)
class RegistryModel:
    model_id: UUID
    artifact_hash: str
    compatibility: CompatibilityContract
    benchmark_report_id: UUID
    state: RegistryState
    created_at: datetime


@dataclass(frozen=True)
class RegistryAuditEvent:
    model_id: UUID
    source: RegistryState | None
    target: RegistryState
    actor: str
    reason: str
    occurred_at: datetime


class InMemoryRegistryStore:
    """Small atomic store for tests and local research workflows."""

    def __init__(self) -> None:
        self.models: dict[UUID, RegistryModel] = {}
        self._audit: tuple[RegistryAuditEvent, ...] = ()
        self.fail_next_transition = False

    @property
    def audit(self) -> tuple[RegistryAuditEvent, ...]:
        return self._audit

    def add(self, model: RegistryModel, event: RegistryAuditEvent) -> None:
        if model.model_id in self.models:
            raise ValueError(f"model already registered: {model.model_id}")
        if any(existing.artifact_hash == model.artifact_hash for existing in self.models.values()):
            raise ValueError(f"artifact hash already registered: {model.artifact_hash}")
        self.models[model.model_id] = model
        self._audit = (*self._audit, event)

    def get(self, model_id: UUID) -> RegistryModel:
        try:
            return self.models[model_id]
        except KeyError as exc:
            raise KeyError(f"unknown registry model: {model_id}") from exc

    def transition(
        self,
        model: RegistryModel,
        expected_state: RegistryState,
        event: RegistryAuditEvent,
    ) -> None:
        current = self.get(model.model_id)
        if current.state is not expected_state:
            raise RuntimeError("registry state changed during transition")
        if self.fail_next_transition:
            self.fail_next_transition = False
            raise RuntimeError("registry transaction failed")
        self.models[model.model_id] = model
        self._audit = (*self._audit, event)


class RegistryService:
    def __init__(
        self,
        store: InMemoryRegistryStore,
        benchmark_policy: BenchmarkPolicy | None = None,
        benchmark_reports: Mapping[UUID, Mapping[str, float | bool]] | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self.store = store
        self.benchmark_policy = benchmark_policy
        self._benchmark_reports = {
            report_id: dict(results)
            for report_id, results in (benchmark_reports or {}).items()
        }
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or uuid4
        self._validate_policy()

    def register(
        self,
        artifact_hash: str,
        compatibility: CompatibilityContract,
        benchmark_report_id: UUID,
        actor: str,
    ) -> RegistryModel:
        """Register immutable identity metadata without granting serving status."""
        self._validate_sha256(artifact_hash, "artifact hash")
        self._validate_compatibility(compatibility)
        self._require_text(actor, "actor")
        now = self._clock()
        model = RegistryModel(
            model_id=self._id_factory(),
            artifact_hash=artifact_hash,
            compatibility=compatibility,
            benchmark_report_id=benchmark_report_id,
            state=RegistryState.CANDIDATE,
            created_at=now,
        )
        event = RegistryAuditEvent(
            model.model_id,
            None,
            RegistryState.CANDIDATE,
            actor,
            "registered",
            now,
        )
        self.store.add(model, event)
        return model

    def transition(
        self,
        model_id: UUID,
        target: RegistryState,
        actor: str,
        reason: str,
    ) -> RegistryModel:
        """Apply one legal state edge and atomically append its audit event."""
        self._require_text(actor, "actor")
        self._require_text(reason, "reason")
        current = self.store.get(model_id)
        if target not in LEGAL_TRANSITIONS[current.state]:
            raise ValueError(
                f"illegal registry transition: {current.state.value} -> {target.value}"
            )
        if target in {
            RegistryState.BENCHMARK_QUALIFIED,
            RegistryState.ADVISORY_APPROVED,
        }:
            self._evaluate_benchmarks(current)

        updated = replace(current, state=target)
        event = RegistryAuditEvent(
            model_id=model_id,
            source=current.state,
            target=target,
            actor=actor,
            reason=reason,
            occurred_at=self._clock(),
        )
        self.store.transition(updated, current.state, event)
        return updated

    def _evaluate_benchmarks(self, model: RegistryModel) -> None:
        policy = self.benchmark_policy
        if policy is None:
            raise ValueError("benchmark policy is required for promotion")
        try:
            results = self._benchmark_reports[model.benchmark_report_id]
        except KeyError as exc:
            raise ValueError(f"benchmark report not found: {model.benchmark_report_id}") from exc

        for criterion in policy.criteria:
            if criterion.name not in results:
                raise ValueError(f"benchmark criterion is missing: {criterion.name}")
            result = results[criterion.name]
            if isinstance(result, float) and not math.isfinite(result):
                raise ValueError(f"benchmark criterion is not finite: {criterion.name}")
            if criterion.comparison == "required":
                passed = isinstance(result, bool) and result is criterion.threshold
            elif isinstance(result, bool):
                passed = False
            elif criterion.comparison == "minimum":
                passed = result >= criterion.threshold
            else:
                passed = result <= criterion.threshold
            if not passed:
                raise ValueError(f"benchmark criterion failed: {criterion.name}")

    def _validate_policy(self) -> None:
        policy = self.benchmark_policy
        if policy is None:
            return
        self._require_text(policy.version, "benchmark policy version")
        if not policy.criteria:
            raise ValueError("benchmark policy must contain criteria")
        names: set[str] = set()
        for criterion in policy.criteria:
            self._require_text(criterion.name, "benchmark criterion name")
            if criterion.name in names:
                raise ValueError(f"duplicate benchmark criterion: {criterion.name}")
            names.add(criterion.name)
            if criterion.comparison not in {"minimum", "maximum", "required"}:
                raise ValueError(f"invalid benchmark comparison: {criterion.comparison}")
            if isinstance(criterion.threshold, float) and not math.isfinite(criterion.threshold):
                raise ValueError(f"benchmark threshold is not finite: {criterion.name}")

    @classmethod
    def _validate_compatibility(cls, contract: CompatibilityContract) -> None:
        for field in (
            "state_schema_version",
            "action_schema_version",
            "encoder_version",
            "reward_version",
            "architecture",
        ):
            cls._require_text(getattr(contract, field), field)
        cls._validate_sha256(contract.environment_hash, "environment_hash")

    @staticmethod
    def _validate_sha256(value: str, name: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"{name} must be a lowercase SHA-256 digest")

    @staticmethod
    def _require_text(value: str, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be non-empty")


__all__ = [
    "LEGAL_TRANSITIONS",
    "BenchmarkCriterion",
    "BenchmarkPolicy",
    "CompatibilityContract",
    "InMemoryRegistryStore",
    "RegistryAuditEvent",
    "RegistryModel",
    "RegistryService",
    "RegistryState",
]
