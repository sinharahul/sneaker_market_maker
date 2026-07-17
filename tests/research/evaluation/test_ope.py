import pytest
import torch

from sneaker_market_maker.research.contracts.transition import BehaviorPolicy
from sneaker_market_maker.research.evaluation.ope import (
    SupportDiagnostics,
    assess_ope_validity,
    weighted_importance_sampling,
)


def behavior(
    *,
    deterministic: bool = False,
    missing: bool = False,
    zero_propensity: bool = False,
) -> BehaviorPolicy:
    no_propensities = deterministic or missing or zero_propensity
    propensities = (None, None, None) if no_propensities else (0.5, -0.2, -0.9)
    missingness_reason = None
    if zero_propensity:
        missingness_reason = "zero joint propensity"
    elif deterministic or missing:
        missingness_reason = "not logged"
    return BehaviorPolicy(
        version="behavior-v1",
        collection_mode="logged",
        categorical_propensity=propensities[0],
        active_continuous_log_density=propensities[1],
        joint_log_propensity=propensities[2],
        deterministic=deterministic,
        support_method="joint-density",
        support_version="support-v1",
        missingness_reason=missingness_reason,
    )


def support(*, trustworthy: bool = True, fraction: float = 1.0, ess: float = 20.0):
    return SupportDiagnostics(
        supported_fraction=fraction,
        effective_sample_size=ess,
        trustworthy_joint_propensities=trustworthy,
    )


def test_trustworthy_nonzero_joint_propensities_permit_wis() -> None:
    validity = assess_ope_validity((behavior(), behavior()), support(), None)

    assert validity.valid is True
    assert validity.status == "VALID"
    assert validity.reason is None


@pytest.mark.parametrize(
    ("policies", "diagnostics", "reason"),
    [
        (
            (behavior(deterministic=True),),
            support(),
            "deterministic behavior policy has no valid propensity",
        ),
        (
            (behavior(missing=True),),
            support(),
            "joint behavior propensity is missing",
        ),
        (
            (behavior(zero_propensity=True),),
            support(trustworthy=False),
            "joint behavior propensity is zero",
        ),
        (
            (behavior(),),
            support(trustworthy=False),
            "joint behavior propensities are not trustworthy",
        ),
        (
            (behavior(),),
            support(fraction=0.0),
            "evaluation policy has no supported actions",
        ),
        (
            (behavior(),),
            support(fraction=0.5),
            "evaluation policy lacks full action support",
        ),
    ],
)
def test_invalid_regions_have_stable_status(
    policies: tuple[BehaviorPolicy, ...],
    diagnostics: SupportDiagnostics,
    reason: str,
) -> None:
    first = assess_ope_validity(policies, diagnostics, None)
    second = assess_ope_validity(policies, diagnostics, "unused-nuisance-hash")

    assert first.status == second.status == "OPE_NOT_VALID"
    assert first.valid is second.valid is False
    assert first.reason == second.reason == reason


def test_wis_reports_weak_effective_sample_size() -> None:
    estimate = weighted_importance_sampling(
        returns=torch.tensor([1.0, 2.0, 10.0]),
        evaluation_log_prob=torch.tensor([0.0, -20.0, -20.0]),
        behavior_log_prob=torch.zeros(3),
    )

    assert estimate.method == "WIS"
    assert estimate.value == pytest.approx(1.0)
    assert estimate.effective_sample_size == pytest.approx(1.0)


def test_wis_rejects_nonfinite_importance_weights() -> None:
    with pytest.raises(ValueError, match="non-finite importance weight"):
        weighted_importance_sampling(
            returns=torch.tensor([1.0]),
            evaluation_log_prob=torch.tensor([float("-inf")]),
            behavior_log_prob=torch.tensor([0.0]),
        )


def test_nuisance_methods_are_not_claimed_without_validated_lineage() -> None:
    from sneaker_market_maker.research.evaluation import ope

    validity = assess_ope_validity((behavior(),), support(), None)

    assert validity.valid is True
    assert not hasattr(ope, "fitted_q_evaluation")
    assert not hasattr(ope, "doubly_robust")
