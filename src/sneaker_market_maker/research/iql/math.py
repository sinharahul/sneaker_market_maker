from __future__ import annotations

import math

import torch
from torch import Tensor


def certainty_equivalent(
    quantiles: Tensor, eta: float, epsilon: float = 1e-6
) -> Tensor:
    if eta < 0:
        raise ValueError("eta must be non-negative")
    if not torch.isfinite(quantiles).all():
        raise FloatingPointError("quantiles must be finite")
    z = quantiles.to(torch.float64)
    mean = z.mean(dim=-1)
    if eta == 0.0:
        return mean
    if abs(eta) < epsilon:
        variance = ((z - mean.unsqueeze(-1)) ** 2).mean(dim=-1)
        return mean - 0.5 * eta * variance
    return -(torch.logsumexp(-eta * z, dim=-1) - math.log(z.shape[-1])) / eta


def smooth_huber(error: Tensor, kappa: float) -> Tensor:
    absolute = error.abs()
    return torch.where(
        absolute <= kappa,
        0.5 * error.square(),
        kappa * (absolute - 0.5 * kappa),
    )


def pairwise_quantile_huber_loss(
    predicted: Tensor, target: Tensor, fractions: Tensor, kappa: float
) -> Tensor:
    error = target.detach().unsqueeze(-2) - predicted.unsqueeze(-1)
    indicator = (error < 0).to(predicted.dtype)
    weights = (fractions.view(1, -1, 1) - indicator).abs()
    return (weights * smooth_huber(error, kappa)).mean()


def quantile_crossing_loss(quantiles: Tensor) -> Tensor:
    return torch.relu(quantiles[..., :-1] - quantiles[..., 1:]).mean()


__all__ = [
    "certainty_equivalent",
    "pairwise_quantile_huber_loss",
    "quantile_crossing_loss",
    "smooth_huber",
]
