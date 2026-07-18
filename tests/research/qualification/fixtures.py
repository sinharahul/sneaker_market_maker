from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

from sneaker_market_maker.research.ports import EvaluationReport, MetricInterval
from sneaker_market_maker.research.qualification.service import (
    QualificationBenchmarkPolicy,
    QualificationCriterion,
    QualificationInput,
)
from sneaker_market_maker.research.registry.service import (
    BenchmarkCriterion,
    BenchmarkPolicy,
    CompatibilityContract,
    InMemoryRegistryStore,
    RegistryService,
    RegistryState,
)

NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)
ARTIFACT_HASH = "a" * 64
POLICY_VERSION = "advisory-qualification-v1"
REPORT_ID = UUID(int=20)
COMPATIBILITY = CompatibilityContract(
    state_schema_version="state-v1",
    action_schema_version="action-v1",
    encoder_version="encoder-v1",
    reward_version="reward-v1",
    architecture="iql-v1",
    environment_hash="b" * 64,
)


def interval(point: float, *, spread: float = 0.01) -> MetricInterval:
    return MetricInterval(
        point=point,
        lower=point - spread,
        upper=point + spread,
        confidence=0.95,
    )


def evaluation_report(
    *,
    metrics: dict[str, MetricInterval] | None = None,
    support_coverage: float = 0.98,
    seed_results: dict[int, dict[str, float]] | None = None,
    historical: bool = True,
) -> EvaluationReport:
    return EvaluationReport(
        policy_id="candidate-iql",
        assumptions_hash="c" * 64,
        metrics=metrics
        or {
            "net_return": interval(0.03),
            "ce_vs_deterministic": interval(0.02),
            "ce_vs_heuristic": interval(0.02, spread=0.005),
            "cvar": interval(0.04, spread=0.005),
            "max_drawdown": interval(0.08, spread=0.01),
            "inventory_age": interval(12.0, spread=0.5),
            "stranded_inventory": interval(0.01, spread=0.002),
            "capital_utilization": interval(0.55, spread=0.02),
            "turnover_rate": interval(0.25, spread=0.01),
            "gate_rejection_rate": interval(0.02, spread=0.005),
        },
        support_coverage=support_coverage,
        numerical_failures=0,
        seed_results=seed_results
        or {
            1: {"net_return": 0.031, "max_drawdown": 0.079},
            2: {"net_return": 0.029, "max_drawdown": 0.081},
            3: {"net_return": 0.030, "max_drawdown": 0.080},
        },
        historical=historical,
    )


def benchmark_policy() -> QualificationBenchmarkPolicy:
    return QualificationBenchmarkPolicy(
        version=POLICY_VERSION,
        criteria=(
            QualificationCriterion(
                "required_folds",
                "historical",
                "required_folds",
                "minimum",
                3.0,
            ),
            QualificationCriterion(
                "net_return_lower_vs_deterministic",
                "historical",
                "net_return_lower",
                "minimum",
                0.01,
            ),
            QualificationCriterion(
                "ce_vs_heuristic_lower",
                "historical",
                "ce_vs_heuristic_lower",
                "minimum",
                0.004,
            ),
            QualificationCriterion("cvar_ceiling", "historical", "cvar_upper", "maximum", 0.05),
            QualificationCriterion(
                "drawdown_ceiling",
                "historical",
                "max_drawdown_upper",
                "maximum",
                0.12,
            ),
            QualificationCriterion(
                "inventory_age_ceiling",
                "historical",
                "inventory_age_upper",
                "maximum",
                14.0,
            ),
            QualificationCriterion(
                "stranded_inventory_ceiling",
                "historical",
                "stranded_inventory_upper",
                "maximum",
                0.02,
            ),
            QualificationCriterion(
                "capital_utilization_ceiling",
                "historical",
                "capital_utilization_upper",
                "maximum",
                0.70,
            ),
            QualificationCriterion(
                "turnover_floor",
                "historical",
                "turnover_rate_lower",
                "minimum",
                0.15,
            ),
            QualificationCriterion(
                "gate_rejection_ceiling",
                "historical",
                "gate_rejection_rate_upper",
                "maximum",
                0.05,
            ),
            QualificationCriterion(
                "support_coverage",
                "historical",
                "support_coverage",
                "minimum",
                0.95,
            ),
            QualificationCriterion(
                "seed_dispersion",
                "historical",
                "seed_dispersion:net_return",
                "maximum",
                0.01,
            ),
            QualificationCriterion(
                "stress_drawdown_ceiling",
                "stress",
                "max_drawdown_upper",
                "maximum",
                0.20,
            ),
            QualificationCriterion(
                "stress_cvar_ceiling",
                "stress",
                "cvar_upper",
                "maximum",
                0.08,
            ),
            QualificationCriterion(
                "shadow_observations",
                "shadow",
                "observations",
                "minimum",
                1000.0,
            ),
            QualificationCriterion(
                "paper_stream_equivalent",
                "shadow",
                "paper_stream_hash_match",
                "required",
                True,
            ),
            QualificationCriterion("restart_drill", "drill", "restart", "required", True),
            QualificationCriterion("rollback_drill", "drill", "rollback", "required", True),
            QualificationCriterion("drift_drill", "drill", "drift", "required", True),
            QualificationCriterion("artifact_drill", "drill", "artifact", "required", True),
        ),
    )


def qualification_input(**overrides: object) -> QualificationInput:
    values: dict[str, object] = {
        "benchmark_policy": benchmark_policy(),
        "artifact_hash": ARTIFACT_HASH,
        "historical_reports": (
            evaluation_report(),
            evaluation_report(),
            evaluation_report(),
        ),
        "stress_reports": (
            evaluation_report(
                metrics={
                    "max_drawdown": interval(0.15, spread=0.01),
                    "cvar": interval(0.06, spread=0.005),
                },
                historical=False,
            ),
            evaluation_report(
                metrics={
                    "max_drawdown": interval(0.18, spread=0.01),
                    "cvar": interval(0.07, spread=0.005),
                },
                historical=False,
            ),
        ),
        "shadow_observations": 1500,
        "shadow_stream_hash_match": True,
        "drill_results": {
            "restart": True,
            "rollback": True,
            "drift": True,
            "artifact": True,
        },
    }
    values.update(overrides)
    return QualificationInput(**values)  # type: ignore[arg-type]


def registry_service() -> RegistryService:
    return RegistryService(
        store=InMemoryRegistryStore(),
        benchmark_policy=BenchmarkPolicy(
            version=POLICY_VERSION,
            criteria=(BenchmarkCriterion("artifact_verified", "required", True),),
            frozen_at=NOW,
        ),
        benchmark_reports={REPORT_ID: {"artifact_verified": True}},
        clock=lambda: NOW,
        id_factory=lambda: UUID(int=19),
    )


def benchmark_qualified_model(registry: RegistryService):
    model = registry.register(ARTIFACT_HASH, COMPATIBILITY, REPORT_ID, "researcher")
    registry.store.models[model.model_id] = replace(model, state=RegistryState.VALIDATED)
    registry.transition(model.model_id, RegistryState.SHADOW, "reviewer", "shadow")
    registry.transition(
        model.model_id,
        RegistryState.BENCHMARK_QUALIFIED,
        "reviewer",
        "qualified",
    )
    return registry.store.get(model.model_id)


def historical_override(metric: str, interval_value: MetricInterval) -> dict[str, object]:
    failing = replace(
        evaluation_report(),
        metrics={**evaluation_report().metrics, metric: interval_value},
    )
    return {"historical_reports": (failing, evaluation_report(), evaluation_report())}
