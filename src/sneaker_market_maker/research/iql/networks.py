from __future__ import annotations

import copy

import torch
from torch import Tensor, nn

from sneaker_market_maker.research.iql.math import certainty_equivalent


class DistributionalValue(nn.Module):
    def __init__(self, state_dim: int, hidden_dim: int, quantile_count: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, quantile_count),
        )

    def forward(self, state: Tensor) -> Tensor:
        result = self.net(state)
        if not torch.isfinite(result).all():
            raise FloatingPointError("value output is non-finite")
        return result


class DistributionalQ(nn.Module):
    def __init__(
        self, state_dim: int, action_dim: int, hidden_dim: int, quantile_count: int
    ) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim + action_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, quantile_count),
        )

    def forward(self, state: Tensor, action: Tensor) -> Tensor:
        result = self.net(torch.cat((state, action), dim=-1))
        if not torch.isfinite(result).all():
            raise FloatingPointError("q output is non-finite")
        return result


def select_conservative_quantiles(q1: Tensor, q2: Tensor, eta: float) -> Tensor:
    choose_first = certainty_equivalent(q1, eta) <= certainty_equivalent(q2, eta)
    return torch.where(choose_first.unsqueeze(-1), q1, q2)


def create_inference_target(module: nn.Module) -> nn.Module:
    target = copy.deepcopy(module)
    for parameter in target.parameters():
        parameter.requires_grad_(False)
    return target


__all__ = [
    "DistributionalQ",
    "DistributionalValue",
    "create_inference_target",
    "select_conservative_quantiles",
]
