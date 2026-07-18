"""OPE validity gate for R2 eval reports (R2-04)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import torch

from sneaker_market_maker.research.contracts.transition import BehaviorPolicy
from sneaker_market_maker.research.evaluation.ope import (
    OPEEstimate,
    OPEValidity,
    SupportDiagnostics,
    assess_ope_validity,
    weighted_importance_sampling,
)


@dataclass(frozen=True)
class OPEReport:
    validity: OPEValidity
    estimate: OPEEstimate | None


def gate_ope(
    *,
    behavior: Sequence[BehaviorPolicy],
    support: SupportDiagnostics,
    nuisance_model_hash: str | None,
    returns: torch.Tensor | None = None,
    evaluation_log_prob: torch.Tensor | None = None,
    behavior_log_prob: torch.Tensor | None = None,
) -> OPEReport:
    """Return WIS only when OPE is valid; otherwise OPE_NOT_VALID with no estimate."""

    validity = assess_ope_validity(behavior, support, nuisance_model_hash)
    if not validity.valid:
        return OPEReport(validity=validity, estimate=None)
    if returns is None or evaluation_log_prob is None or behavior_log_prob is None:
        return OPEReport(
            validity=OPEValidity(False, "OPE_NOT_VALID", "WIS inputs missing"),
            estimate=None,
        )
    estimate = weighted_importance_sampling(
        returns, evaluation_log_prob, behavior_log_prob
    )
    return OPEReport(validity=validity, estimate=estimate)
