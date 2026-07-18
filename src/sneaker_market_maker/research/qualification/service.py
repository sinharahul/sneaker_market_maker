"""Pre-registered advisory qualification without fabricated approval."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sneaker_market_maker.research.ports import EvaluationReport
from sneaker_market_maker.research.registry.service import (
    RegistryModel,
    RegistryService,
    RegistryState,
)


@dataclass(frozen=True)
class CriterionResult:
    name: str
    passed: bool


@dataclass(frozen=True)
class QualificationCriterion:
    name: str
    source: Literal["historical", "stress", "shadow", "drill"]
    metric: str
    comparison: Literal["minimum", "maximum", "required"]
    threshold: float | bool


@dataclass(frozen=True)
class QualificationBenchmarkPolicy:
    version: str
    criteria: tuple[QualificationCriterion, ...]


@dataclass(frozen=True)
class QualificationInput:
    benchmark_policy: QualificationBenchmarkPolicy
    artifact_hash: str
    historical_reports: tuple[EvaluationReport, ...]
    stress_reports: tuple[EvaluationReport, ...]
    shadow_observations: int
    shadow_stream_hash_match: bool
    drill_results: Mapping[str, bool]


@dataclass(frozen=True)
class QualificationReport:
    benchmark_policy_version: str
    artifact_hash: str
    criteria: tuple[CriterionResult, ...]
    qualified: bool


class QualificationService:
    """Evaluate frozen benchmark criteria; approval stays explicit and audited."""

    def evaluate(self, input: QualificationInput) -> QualificationReport:
        results = tuple(
            CriterionResult(
                name=criterion.name,
                passed=self._evaluate_criterion(criterion, input),
            )
            for criterion in input.benchmark_policy.criteria
        )
        return QualificationReport(
            benchmark_policy_version=input.benchmark_policy.version,
            artifact_hash=input.artifact_hash,
            criteria=results,
            qualified=all(result.passed for result in results),
        )

    def approve(
        self,
        registry: RegistryService,
        model_id: UUID,
        report: QualificationReport,
        actor: str,
        confirmation: str,
    ) -> RegistryModel:
        current = registry.store.get(model_id)
        if not report.qualified:
            raise ValueError("qualification report is not qualified")
        if current.state is not RegistryState.BENCHMARK_QUALIFIED:
            raise ValueError("advisory approval requires benchmark-qualified state")
        if report.artifact_hash != current.artifact_hash:
            raise ValueError("qualification artifact hash does not match registry model")
        if report.benchmark_policy_version not in confirmation:
            raise ValueError("confirmation must include benchmark policy version")
        if report.artifact_hash not in confirmation:
            raise ValueError("confirmation must include artifact hash")
        return registry.transition(
            model_id,
            RegistryState.ADVISORY_APPROVED,
            actor,
            confirmation.strip(),
        )

    def _evaluate_criterion(
        self,
        criterion: QualificationCriterion,
        input: QualificationInput,
    ) -> bool:
        if criterion.source == "historical":
            return self._evaluate_reports(criterion, input.historical_reports)
        if criterion.source == "stress":
            return self._evaluate_reports(criterion, input.stress_reports)
        if criterion.source == "shadow":
            return self._evaluate_shadow(criterion, input)
        if criterion.source == "drill":
            return self._evaluate_drill(criterion, input)
        return False

    def _evaluate_reports(
        self,
        criterion: QualificationCriterion,
        reports: tuple[EvaluationReport, ...],
    ) -> bool:
        if criterion.metric == "required_folds":
            return len(reports) >= int(criterion.threshold)
        if not reports:
            return False
        for report in reports:
            value = self._report_value(report, criterion.metric)
            if value is None or not self._compare(value, criterion.comparison, criterion.threshold):
                return False
        return True

    def _evaluate_shadow(
        self,
        criterion: QualificationCriterion,
        input: QualificationInput,
    ) -> bool:
        if criterion.metric == "observations":
            return input.shadow_observations >= criterion.threshold
        if criterion.metric == "paper_stream_hash_match":
            return self._compare(
                input.shadow_stream_hash_match,
                criterion.comparison,
                criterion.threshold,
            )
        return False

    def _evaluate_drill(
        self,
        criterion: QualificationCriterion,
        input: QualificationInput,
    ) -> bool:
        if criterion.metric not in input.drill_results:
            return False
        return self._compare(
            input.drill_results[criterion.metric],
            criterion.comparison,
            criterion.threshold,
        )

    def _report_value(self, report: EvaluationReport, metric: str) -> float | None:
        if metric == "support_coverage":
            return report.support_coverage
        if metric == "numerical_failures":
            return float(report.numerical_failures)
        if metric.startswith("seed_dispersion:"):
            return self._seed_dispersion(report, metric.split(":", maxsplit=1)[1])
        if metric.endswith("_lower"):
            return self._interval_component(report, metric[:-6], "lower")
        if metric.endswith("_upper"):
            return self._interval_component(report, metric[:-6], "upper")
        if metric.endswith("_point"):
            return self._interval_component(report, metric[:-6], "point")
        return self._interval_component(report, metric, "point")

    def _interval_component(
        self,
        report: EvaluationReport,
        metric: str,
        component: Literal["lower", "upper", "point"],
    ) -> float | None:
        interval = report.metrics.get(metric)
        if interval is None:
            return None
        return getattr(interval, component)

    def _seed_dispersion(self, report: EvaluationReport, metric: str) -> float | None:
        if not report.seed_results:
            return None
        values: list[float] = []
        for seed_metrics in report.seed_results.values():
            if metric not in seed_metrics:
                return None
            value = seed_metrics[metric]
            if not math.isfinite(value):
                return None
            values.append(value)
        if len(values) < 2:
            return 0.0
        return max(values) - min(values)

    @staticmethod
    def _compare(
        value: float | bool,
        comparison: Literal["minimum", "maximum", "required"],
        threshold: float | bool,
    ) -> bool:
        if comparison == "required":
            return isinstance(value, bool) and value is threshold
        if isinstance(value, bool) or isinstance(threshold, bool):
            return False
        if not math.isfinite(value) or not math.isfinite(threshold):
            return False
        if comparison == "minimum":
            return value >= threshold
        return value <= threshold


__all__ = [
    "CriterionResult",
    "QualificationBenchmarkPolicy",
    "QualificationCriterion",
    "QualificationInput",
    "QualificationReport",
    "QualificationService",
]
