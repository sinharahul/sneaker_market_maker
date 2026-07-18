from __future__ import annotations

import math
from dataclasses import dataclass, fields

import torch
from torch import Tensor, nn
from torch.optim import Optimizer

from sneaker_market_maker.research.iql.math import (
    certainty_equivalent,
    pairwise_quantile_huber_loss,
    quantile_crossing_loss,
    smooth_huber,
)
from sneaker_market_maker.research.iql.networks import (
    create_inference_target,
    select_conservative_quantiles,
)


@dataclass(frozen=True)
class TransitionBatch:
    state: Tensor
    action: Tensor
    reward: Tensor
    next_state: Tensor
    done: Tensor
    discount: Tensor
    category_mask: Tensor
    bounds: Tensor
    logged_category: Tensor
    active_dimensions: Tensor


@dataclass(frozen=True)
class IQLConfig:
    eta: float
    expectile: float
    kappa: float
    lambda_ce: float
    lambda_cross: float
    beta: float
    exp_clip: float
    max_weight: float
    max_grad_norm: float
    target_tau: float
    target_cadence: int


@dataclass(frozen=True)
class StepMetrics:
    value_loss: float
    q1_loss: float
    q2_loss: float
    actor_loss: float
    gradient_norm: float
    target_updated: bool


class IQLTrainer:
    def __init__(
        self,
        *,
        value: nn.Module,
        q1: nn.Module,
        q2: nn.Module,
        actor: nn.Module,
        value_optimizer: Optimizer,
        q1_optimizer: Optimizer,
        q2_optimizer: Optimizer,
        actor_optimizer: Optimizer,
        fractions: Tensor,
        config: IQLConfig,
    ) -> None:
        self.value = value
        self.q1 = q1
        self.q2 = q2
        self.actor = actor
        self.target_value = create_inference_target(value)
        self.target_q1 = create_inference_target(q1)
        self.target_q2 = create_inference_target(q2)
        self.value_optimizer = value_optimizer
        self.q1_optimizer = q1_optimizer
        self.q2_optimizer = q2_optimizer
        self.actor_optimizer = actor_optimizer
        self.fractions = fractions
        self.config = config
        self._successful_steps = 0
        self._validate_configuration()

    def step(self, batch: TransitionBatch) -> StepMetrics:
        self._assert_finite_batch(batch)
        config = self.config

        with torch.no_grad():
            target_q = select_conservative_quantiles(
                self.target_q1(batch.state, batch.action),
                self.target_q2(batch.state, batch.action),
                config.eta,
            )
        value = self.value(batch.state)
        delta = certainty_equivalent(
            target_q, config.eta
        ) - certainty_equivalent(value, config.eta)
        expectile_weight = torch.where(
            delta >= 0, config.expectile, 1.0 - config.expectile
        )
        value_loss = (
            expectile_weight
            * (
                smooth_huber(value - target_q, config.kappa).mean(dim=-1)
                + config.lambda_ce * delta.square()
            )
        ).mean() + config.lambda_cross * quantile_crossing_loss(value)
        value_norm = self._optimize(
            self.value, self.value_optimizer, value_loss, "value loss"
        )

        with torch.no_grad():
            bellman_target = batch.reward.unsqueeze(-1) + (
                batch.discount * (~batch.done).to(batch.reward.dtype)
            ).unsqueeze(-1) * self.target_value(batch.next_state)
        q1_loss = pairwise_quantile_huber_loss(
            self.q1(batch.state, batch.action),
            bellman_target,
            self.fractions,
            config.kappa,
        )
        q1_norm = self._optimize(self.q1, self.q1_optimizer, q1_loss, "q1 loss")
        q2_loss = pairwise_quantile_huber_loss(
            self.q2(batch.state, batch.action),
            bellman_target,
            self.fractions,
            config.kappa,
        )
        q2_norm = self._optimize(self.q2, self.q2_optimizer, q2_loss, "q2 loss")

        with torch.no_grad():
            conservative_q = select_conservative_quantiles(
                self.target_q1(batch.state, batch.action),
                self.target_q2(batch.state, batch.action),
                config.eta,
            )
            advantage = certainty_equivalent(
                conservative_q, config.eta
            ) - certainty_equivalent(self.value(batch.state), config.eta)
            weight = torch.exp(
                torch.clamp(
                    config.beta * advantage, -config.exp_clip, config.exp_clip
                )
            )
            weight = torch.clamp(weight, max=config.max_weight)
        actor_loss = -(weight * self._log_prob_logged(batch)).mean()
        actor_norm = self._optimize(
            self.actor, self.actor_optimizer, actor_loss, "actor loss"
        )

        self._successful_steps += 1
        target_updated = self._successful_steps % config.target_cadence == 0
        if target_updated:
            self._polyak_update()

        return StepMetrics(
            value_loss=value_loss.detach().item(),
            q1_loss=q1_loss.detach().item(),
            q2_loss=q2_loss.detach().item(),
            actor_loss=actor_loss.detach().item(),
            gradient_norm=max(value_norm, q1_norm, q2_norm, actor_norm),
            target_updated=target_updated,
        )

    def _log_prob_logged(self, batch: TransitionBatch) -> Tensor:
        return self.actor.log_prob(
            batch.state,
            batch.category_mask,
            batch.bounds,
            batch.logged_category,
            batch.action,
            batch.active_dimensions,
        )

    def _optimize(
        self,
        module: nn.Module,
        optimizer: Optimizer,
        loss: Tensor,
        label: str,
    ) -> float:
        if not torch.isfinite(loss).all():
            raise FloatingPointError(f"{label} is non-finite")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        parameters = [parameter for parameter in module.parameters() if parameter.grad is not None]
        for parameter in parameters:
            if not torch.isfinite(parameter.grad).all():
                optimizer.zero_grad(set_to_none=True)
                raise FloatingPointError(f"{label} gradient is non-finite")
        norm = torch.nn.utils.clip_grad_norm_(
            parameters,
            self.config.max_grad_norm,
            error_if_nonfinite=True,
        )
        if not torch.isfinite(norm):
            optimizer.zero_grad(set_to_none=True)
            raise FloatingPointError(f"{label} gradient norm is non-finite")
        optimizer.step()
        return float(norm)

    def _polyak_update(self) -> None:
        tau = self.config.target_tau
        with torch.no_grad():
            for online, target in (
                (self.value, self.target_value),
                (self.q1, self.target_q1),
                (self.q2, self.target_q2),
            ):
                for online_parameter, target_parameter in zip(
                    online.parameters(), target.parameters(), strict=True
                ):
                    target_parameter.mul_(1.0 - tau).add_(
                        online_parameter, alpha=tau
                    )

    def _assert_finite_batch(self, batch: TransitionBatch) -> None:
        for field in fields(batch):
            tensor = getattr(batch, field.name)
            if not torch.isfinite(tensor).all():
                raise FloatingPointError(f"{field.name} contains non-finite values")

    def _validate_configuration(self) -> None:
        numeric = (
            self.config.eta,
            self.config.expectile,
            self.config.kappa,
            self.config.lambda_ce,
            self.config.lambda_cross,
            self.config.beta,
            self.config.exp_clip,
            self.config.max_weight,
            self.config.max_grad_norm,
            self.config.target_tau,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("IQL configuration must be finite")
        if self.config.target_cadence <= 0:
            raise ValueError("target_cadence must be positive")
        if not 0.0 <= self.config.target_tau <= 1.0:
            raise ValueError("target_tau must be between zero and one")
        if self.config.max_grad_norm <= 0.0:
            raise ValueError("max_grad_norm must be positive")
        if not torch.isfinite(self.fractions).all():
            raise ValueError("fractions must be finite")


__all__ = ["IQLConfig", "IQLTrainer", "StepMetrics", "TransitionBatch"]
