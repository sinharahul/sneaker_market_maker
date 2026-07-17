"""Honest offline-policy-evaluation diagnostics and weighted IS."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import torch

from sneaker_market_maker.research.contracts.transition import BehaviorPolicy


@dataclass(frozen=True)
class OPEValidity:
    valid: bool
    status: Literal["VALID", "OPE_NOT_VALID"]
    reason: str | None


@dataclass(frozen=True)
class SupportDiagnostics:
    supported_fraction: float
    effective_sample_size: float
    trustworthy_joint_propensities: bool

    def __post_init__(self) -> None:
        if not math.isfinite(self.supported_fraction) or not 0.0 <= self.supported_fraction <= 1.0:
            raise ValueError("supported fraction must be finite and in [0, 1]")
        if not math.isfinite(self.effective_sample_size) or self.effective_sample_size < 0.0:
            raise ValueError("effective sample size must be finite and nonnegative")


@dataclass(frozen=True)
class OPEEstimate:
    value: float
    effective_sample_size: float
    method: Literal["WIS"]


def _not_valid(reason: str) -> OPEValidity:
    return OPEValidity(False, "OPE_NOT_VALID", reason)


def assess_ope_validity(
    behavior: Sequence[BehaviorPolicy],
    support: SupportDiagnostics,
    nuisance_model_hash: str | None,
) -> OPEValidity:
    """Assess whether logged data supports propensity-based WIS.

    A nuisance-model hash is accepted for report lineage, but it does not make
    unsupported propensity regions valid. Fitted-Q and doubly-robust estimators
    are deliberately not exposed until nuisance-model validation is defined.
    """
    del nuisance_model_hash
    if not behavior:
        return _not_valid("behavior policy metadata is missing")
    if any(policy.deterministic for policy in behavior):
        return _not_valid("deterministic behavior policy has no valid propensity")
    if any(policy.joint_log_propensity is None for policy in behavior):
        return _not_valid("joint behavior propensity is missing")
    if not support.trustworthy_joint_propensities:
        return _not_valid("joint behavior propensities are not trustworthy")
    if support.supported_fraction == 0.0:
        return _not_valid("evaluation policy has no supported actions")
    return OPEValidity(True, "VALID", None)


def weighted_importance_sampling(
    returns: torch.Tensor,
    evaluation_log_prob: torch.Tensor,
    behavior_log_prob: torch.Tensor,
) -> OPEEstimate:
    log_weights = evaluation_log_prob - behavior_log_prob
    if not torch.isfinite(log_weights).all():
        raise ValueError("non-finite importance weight")
    weights = torch.softmax(log_weights, dim=0)
    estimate = torch.sum(weights * returns)
    ess = torch.reciprocal(torch.sum(weights.square()))
    return OPEEstimate(float(estimate), float(ess), "WIS")


__all__ = [
    "OPEEstimate",
    "OPEValidity",
    "SupportDiagnostics",
    "assess_ope_validity",
    "weighted_importance_sampling",
]
