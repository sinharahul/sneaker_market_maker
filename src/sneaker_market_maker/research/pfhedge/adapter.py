"""Independent PFHedge terminal direct-policy risk baseline.

This adapter optimizes terminal risk after the shared simulator has applied its
fee, slippage, and logistics cost path. PFHedge is not the Bellman/IQL engine:
it does not implement Bellman targets, IQL, categorical posture, replay
support, promotion decisions, or deterministic gates.
"""

from __future__ import annotations

import torch
from pfhedge.nn import EntropicRiskMeasure
from torch import Tensor, nn


class PFHedgeDirectPolicy(nn.Module):
    def __init__(self, feature_count: int, hidden: int = 64) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(feature_count, hidden),
            nn.Tanh(),
            nn.Linear(hidden, 3),
        )

    def forward(self, state: Tensor, bounds: Tensor) -> Tensor:
        raw = self.network(state)
        allocation = torch.sigmoid(raw[..., :1])
        offsets = torch.tanh(raw[..., 1:])
        low, high = bounds[..., 0, :], bounds[..., 1, :]
        mapped = low + (offsets + 1.0) * 0.5 * (high - low)
        return torch.cat((allocation, mapped), dim=-1)


class PFHedgeTrainer:
    def __init__(self, risk_aversion: float) -> None:
        self.criterion = EntropicRiskMeasure(a=risk_aversion)

    def loss(self, pnl: Tensor) -> Tensor:
        return self.criterion(pnl, target=torch.zeros_like(pnl))


__all__ = ["PFHedgeDirectPolicy", "PFHedgeTrainer"]
