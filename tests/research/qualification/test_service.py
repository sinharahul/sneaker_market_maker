from dataclasses import replace

import pytest

from sneaker_market_maker.research.qualification.service import (
    CriterionResult,
    QualificationReport,
    QualificationService,
)
from sneaker_market_maker.research.registry.service import RegistryState
from tests.research.qualification.failure_cases import APPROVAL_REJECTION_CASES, BLOCKING_CASES
from tests.research.qualification.fixtures import (
    ARTIFACT_HASH,
    COMPATIBILITY,
    POLICY_VERSION,
    REPORT_ID,
    benchmark_qualified_model,
    evaluation_report,
    interval,
    qualification_input,
    registry_service,
)


def test_evaluate_passes_when_every_preregistered_criterion_is_met() -> None:
    report = QualificationService().evaluate(qualification_input())

    assert isinstance(report, QualificationReport)
    assert report.benchmark_policy_version == POLICY_VERSION
    assert report.artifact_hash == ARTIFACT_HASH
    assert report.qualified is True
    assert all(isinstance(result, CriterionResult) and result.passed for result in report.criteria)


@pytest.mark.parametrize(("override", "criterion_name"), BLOCKING_CASES)
def test_any_missing_or_failing_criterion_blocks_qualification(
    override: dict[str, object],
    criterion_name: str,
) -> None:
    report = QualificationService().evaluate(qualification_input(**override))

    assert report.qualified is False
    failed = {result.name for result in report.criteria if not result.passed}
    assert criterion_name in failed


def test_missing_metric_in_report_blocks_qualification() -> None:
    report = QualificationService().evaluate(
        qualification_input(
            historical_reports=(
                replace(evaluation_report(), metrics={"net_return": interval(0.03)}),
            )
            * 3,
        )
    )

    assert report.qualified is False


def test_approve_transitions_to_advisory_only_with_explicit_confirmation() -> None:
    registry = registry_service()
    model = benchmark_qualified_model(registry)
    report = QualificationService().evaluate(qualification_input())
    confirmation = (
        f"I approve advisory use for artifact {ARTIFACT_HASH} "
        f"under benchmark policy {POLICY_VERSION}"
    )

    approved = QualificationService().approve(
        registry,
        model.model_id,
        report,
        "risk-committee",
        confirmation,
    )

    assert approved.state is RegistryState.ADVISORY_APPROVED
    assert registry.store.audit[-1].target is RegistryState.ADVISORY_APPROVED


@pytest.mark.parametrize(
    ("report_override", "confirmation"),
    APPROVAL_REJECTION_CASES,
)
def test_approve_rejects_unqualified_or_incomplete_confirmation(
    report_override: dict[str, object],
    confirmation: str,
) -> None:
    registry = registry_service()
    model = benchmark_qualified_model(registry)
    before = registry.store.get(model.model_id)
    report = QualificationService().evaluate(qualification_input(**report_override))

    with pytest.raises(ValueError):
        QualificationService().approve(
            registry,
            model.model_id,
            report,
            "risk-committee",
            confirmation,
        )

    assert registry.store.get(model.model_id).state is before.state


def test_approve_rejects_when_registry_is_not_benchmark_qualified() -> None:
    registry = registry_service()
    model = registry.register(ARTIFACT_HASH, COMPATIBILITY, REPORT_ID, "researcher")
    registry.store.models[model.model_id] = replace(model, state=RegistryState.SHADOW)
    before = registry.store.get(model.model_id)
    report = QualificationService().evaluate(qualification_input())
    confirmation = (
        f"I approve advisory use for artifact {ARTIFACT_HASH} "
        f"under benchmark policy {POLICY_VERSION}"
    )

    with pytest.raises(ValueError):
        QualificationService().approve(
            registry,
            model.model_id,
            report,
            "risk-committee",
            confirmation,
        )

    assert registry.store.get(model.model_id).state is before.state
