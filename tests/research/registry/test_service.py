from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from sneaker_market_maker.research.registry.service import (
    LEGAL_TRANSITIONS,
    BenchmarkCriterion,
    BenchmarkPolicy,
    CompatibilityContract,
    InMemoryRegistryStore,
    RegistryService,
    RegistryState,
)

NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)
REPORT_ID = UUID(int=20)
HASH = "a" * 64
COMPATIBILITY = CompatibilityContract(
    state_schema_version="state-v1",
    action_schema_version="action-v1",
    encoder_version="encoder-v1",
    reward_version="reward-v1",
    architecture="iql-v1",
    environment_hash="b" * 64,
)
POLICY = BenchmarkPolicy(
    version="promotion-v1",
    criteria=(
        BenchmarkCriterion("artifact_verified", "required", True),
        BenchmarkCriterion("schema_compatible", "required", True),
        BenchmarkCriterion("finite_outputs", "required", True),
        BenchmarkCriterion("replay_passed", "required", True),
        BenchmarkCriterion("restart_passed", "required", True),
        BenchmarkCriterion("fold_return", "minimum", 0.01),
        BenchmarkCriterion("stress_drawdown", "maximum", 0.20),
        BenchmarkCriterion("support_coverage", "minimum", 0.95),
        BenchmarkCriterion("seed_dispersion", "maximum", 0.05),
        BenchmarkCriterion("shadow_latency_ms", "maximum", 50.0),
    ),
    frozen_at=NOW,
)
PASSING_REPORT = {
    "artifact_verified": True,
    "schema_compatible": True,
    "finite_outputs": True,
    "replay_passed": True,
    "restart_passed": True,
    "fold_return": 0.02,
    "stress_drawdown": 0.10,
    "support_coverage": 0.98,
    "seed_dispersion": 0.02,
    "shadow_latency_ms": 25.0,
}


def service(
    report: dict[str, float | bool] | None = None,
    *,
    policy: BenchmarkPolicy | None = POLICY,
    store: InMemoryRegistryStore | None = None,
) -> RegistryService:
    return RegistryService(
        store=store or InMemoryRegistryStore(),
        benchmark_policy=policy,
        benchmark_reports={REPORT_ID: report or PASSING_REPORT},
        clock=lambda: NOW,
        id_factory=lambda: UUID(int=19),
    )


def registered(registry: RegistryService | None = None):
    registry = registry or service()
    return registry, registry.register(HASH, COMPATIBILITY, REPORT_ID, "researcher")


def test_registration_is_immutable_and_grants_no_serving_status() -> None:
    _, model = registered()

    assert model.state is RegistryState.CANDIDATE
    assert model.state not in {RegistryState.SHADOW, RegistryState.ADVISORY_APPROVED}
    with pytest.raises(FrozenInstanceError):
        model.artifact_hash = "c" * 64  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        model.compatibility.state_schema_version = "state-v2"  # type: ignore[misc]


@pytest.mark.parametrize("artifact_hash", ["", "abc", "G" * 64, "a" * 63])
def test_registration_rejects_invalid_artifact_hash(artifact_hash: str) -> None:
    with pytest.raises(ValueError, match="artifact hash"):
        service().register(artifact_hash, COMPATIBILITY, REPORT_ID, "researcher")


@pytest.mark.parametrize(
    "field",
    [
        "state_schema_version",
        "action_schema_version",
        "encoder_version",
        "reward_version",
        "architecture",
        "environment_hash",
    ],
)
def test_registration_rejects_missing_compatibility_fields(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        service().register(HASH, replace(COMPATIBILITY, **{field: ""}), REPORT_ID, "researcher")


def test_all_and_only_declared_legal_transitions_succeed() -> None:
    for source, targets in LEGAL_TRANSITIONS.items():
        for target in targets:
            registry, model = registered()
            registry.store.models[model.model_id] = replace(model, state=source)
            transitioned = registry.transition(model.model_id, target, "reviewer", "evidence")
            assert transitioned.state is target


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (RegistryState.CANDIDATE, RegistryState.SHADOW),
        (RegistryState.VALIDATED, RegistryState.ADVISORY_APPROVED),
        (RegistryState.SHADOW, RegistryState.ADVISORY_APPROVED),
        (RegistryState.ROLLED_BACK, RegistryState.CANDIDATE),
        (RegistryState.REJECTED, RegistryState.CANDIDATE),
    ],
)
def test_illegal_skips_are_blocked(source: RegistryState, target: RegistryState) -> None:
    registry, model = registered()
    registry.store.models[model.model_id] = replace(model, state=source)

    with pytest.raises(ValueError, match="illegal registry transition"):
        registry.transition(model.model_id, target, "reviewer", "skip")

    assert registry.store.get(model.model_id).state is source


@pytest.mark.parametrize(
    ("criterion", "value"),
    [
        ("artifact_verified", False),
        ("schema_compatible", False),
        ("finite_outputs", False),
        ("replay_passed", False),
        ("restart_passed", False),
        ("fold_return", float("nan")),
        ("stress_drawdown", float("inf")),
        ("support_coverage", 0.90),
        ("seed_dispersion", 0.10),
        ("shadow_latency_ms", 75.0),
    ],
)
def test_artifact_schema_finite_replay_latency_restart_and_benchmarks_are_validated(
    criterion: str,
    value: float | bool,
) -> None:
    report = {**PASSING_REPORT, criterion: value}
    registry, model = registered(service(report))
    registry.store.models[model.model_id] = replace(model, state=RegistryState.SHADOW)

    with pytest.raises(ValueError, match=criterion):
        registry.transition(
            model.model_id,
            RegistryState.BENCHMARK_QUALIFIED,
            "reviewer",
            "qualify",
        )


def test_missing_fold_stress_support_seed_or_shadow_result_blocks() -> None:
    for name in (
        "fold_return",
        "stress_drawdown",
        "support_coverage",
        "seed_dispersion",
        "shadow_latency_ms",
    ):
        report = {key: value for key, value in PASSING_REPORT.items() if key != name}
        registry, model = registered(service(report))
        registry.store.models[model.model_id] = replace(model, state=RegistryState.SHADOW)
        with pytest.raises(ValueError, match=name):
            registry.transition(
                model.model_id,
                RegistryState.BENCHMARK_QUALIFIED,
                "reviewer",
                "qualify",
            )


def test_advisory_approval_is_blocked_without_explicit_policy() -> None:
    registry, model = registered(service(policy=None))
    registry.store.models[model.model_id] = replace(
        model,
        state=RegistryState.BENCHMARK_QUALIFIED,
    )
    with pytest.raises(ValueError, match="benchmark policy"):
        registry.transition(
            model.model_id,
            RegistryState.ADVISORY_APPROVED,
            "reviewer",
            "approve",
        )


def test_rollback_records_actor_and_reason_in_append_only_audit() -> None:
    registry, model = registered()
    registry.store.models[model.model_id] = replace(model, state=RegistryState.SHADOW)

    registry.transition(model.model_id, RegistryState.ROLLED_BACK, "operator", "drift")

    event = registry.store.audit[-1]
    assert (event.actor, event.reason) == ("operator", "drift")
    assert (event.source, event.target) == (RegistryState.SHADOW, RegistryState.ROLLED_BACK)
    with pytest.raises(AttributeError):
        registry.store.audit.append(event)  # type: ignore[attr-defined]


def test_transaction_failure_leaves_state_and_audit_unchanged() -> None:
    store = InMemoryRegistryStore()
    registry, model = registered(service(store=store))
    before_audit = registry.store.audit
    store.fail_next_transition = True

    with pytest.raises(RuntimeError, match="transaction failed"):
        registry.transition(model.model_id, RegistryState.VALIDATED, "reviewer", "valid")

    assert registry.store.get(model.model_id).state is RegistryState.CANDIDATE
    assert registry.store.audit == before_audit
