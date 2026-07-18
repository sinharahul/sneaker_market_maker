from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn.functional as functional
from torch import Tensor, nn
from torch.distributions import Normal


@dataclass(frozen=True)
class ActorAction:
    category: Tensor
    continuous: Tensor
    categorical_log_probability: Tensor


def masked_log_softmax(logits: Tensor, mask: Tensor) -> Tensor:
    if not mask.any(dim=-1).all():
        raise ValueError("fully masked action row")
    safe_min = torch.finfo(logits.dtype).min
    return torch.log_softmax(logits.masked_fill(~mask, safe_min), dim=-1)


def squash_continuous(raw: Tensor, bounds: Tensor) -> Tensor:
    allocation = torch.sigmoid(raw[..., :1])
    unit_offsets = torch.tanh(raw[..., 1:])
    low, high = bounds[..., 0, :], bounds[..., 1, :]
    offsets = low + 0.5 * (unit_offsets + 1.0) * (high - low)
    return torch.cat((allocation, offsets), dim=-1)


def transformed_normal_log_prob(
    mean: Tensor,
    log_std: Tensor,
    continuous: Tensor,
    bounds: Tensor,
    active_dimensions: Tensor,
) -> Tensor:
    epsilon = torch.finfo(continuous.dtype).eps
    allocation = continuous[..., :1].clamp(epsilon, 1.0 - epsilon)
    allocation_raw = torch.logit(allocation)
    low, high = bounds[..., 0, :], bounds[..., 1, :]
    offset_active = active_dimensions[..., 1:]
    span = torch.where(offset_active, high - low, torch.ones_like(high))
    unit_offsets = (2.0 * (continuous[..., 1:] - low) / span - 1.0).clamp(
        -1.0 + epsilon, 1.0 - epsilon
    )
    unit_offsets = torch.where(
        offset_active, unit_offsets, torch.zeros_like(unit_offsets)
    )
    offset_raw = torch.atanh(unit_offsets)
    raw = torch.cat((allocation_raw, offset_raw), dim=-1)
    base = Normal(mean, log_std.clamp(-5.0, 2.0).exp()).log_prob(raw)
    allocation_log_jacobian = torch.log(allocation * (1.0 - allocation))
    offset_log_jacobian = torch.log1p(-unit_offsets.square()) + torch.log(
        span / 2.0
    )
    log_jacobian = torch.cat(
        (allocation_log_jacobian, offset_log_jacobian), dim=-1
    )
    return ((base - log_jacobian) * active_dimensions).sum(dim=-1)


def _head(input_dim: int, hidden_dim: int, output_dim: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(input_dim, hidden_dim),
        nn.SiLU(),
        nn.Linear(hidden_dim, hidden_dim),
        nn.SiLU(),
        nn.Linear(hidden_dim, output_dim),
    )


class HybridActor(nn.Module):
    def __init__(self, state_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.category_head = _head(state_dim, hidden_dim, 3)
        conditioned_dim = state_dim + 3
        self.mean_head = _head(conditioned_dim, hidden_dim, 3)
        self.log_std_head = _head(conditioned_dim, hidden_dim, 3)

    def _continuous_parameters(
        self, state: Tensor, category: Tensor
    ) -> tuple[Tensor, Tensor]:
        one_hot = functional.one_hot(category, num_classes=3).to(state.dtype)
        conditioned = torch.cat((state, one_hot), dim=-1)
        return self.mean_head(conditioned), self.log_std_head(conditioned)

    def deterministic(
        self, state: Tensor, mask: Tensor, bounds: Tensor
    ) -> ActorAction:
        category_log_probabilities = masked_log_softmax(
            self.category_head(state), mask
        )
        category = category_log_probabilities.argmax(dim=-1)
        mean, _ = self._continuous_parameters(state, category)
        continuous = squash_continuous(mean, bounds)
        categorical_log_probability = category_log_probabilities.gather(
            1, category[:, None]
        ).squeeze(1)
        return ActorAction(category, continuous, categorical_log_probability)

    def log_prob(
        self,
        state: Tensor,
        mask: Tensor,
        bounds: Tensor,
        category: Tensor,
        continuous: Tensor,
        active_dimensions: Tensor,
    ) -> Tensor:
        category_log_probability = masked_log_softmax(
            self.category_head(state), mask
        ).gather(1, category[:, None]).squeeze(1)
        mean, log_std = self._continuous_parameters(state, category)
        continuous_log_probability = transformed_normal_log_prob(
            mean,
            log_std,
            continuous,
            bounds,
            active_dimensions,
        )
        return category_log_probability + continuous_log_probability


__all__ = [
    "ActorAction",
    "HybridActor",
    "masked_log_softmax",
    "squash_continuous",
    "transformed_normal_log_prob",
]
