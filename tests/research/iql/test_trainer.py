from __future__ import annotations

import copy

import pytest
import torch
from torch import Tensor, nn

from sneaker_market_maker.research.iql.math import pairwise_quantile_huber_loss
from sneaker_market_maker.research.iql.trainer import (
    IQLConfig,
    IQLTrainer,
    TransitionBatch,
)


class ConstantValue(nn.Module):
    def __init__(self, quantiles: tuple[float, ...]) -> None:
        super().__init__()
        self.quantiles = nn.Parameter(torch.tensor(quantiles))
        self.grad_modes: list[bool] = []

    def forward(self, state: Tensor) -> Tensor:
        self.grad_modes.append(torch.is_grad_enabled())
        return self.quantiles.expand(state.shape[0], -1)


class ConstantQ(nn.Module):
    def __init__(self, quantiles: tuple[float, ...]) -> None:
        super().__init__()
        self.quantiles = nn.Parameter(torch.tensor(quantiles))
        self.actions: list[Tensor] = []

    def forward(self, state: Tensor, action: Tensor) -> Tensor:
        self.actions.append(action.detach().clone())
        return self.quantiles.expand(state.shape[0], -1)


class LoggedActor(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.bias = nn.Parameter(torch.tensor(0.0))
        self.received: tuple[Tensor, ...] | None = None
        self.return_nan = False

    def log_prob(
        self,
        state: Tensor,
        mask: Tensor,
        bounds: Tensor,
        category: Tensor,
        continuous: Tensor,
        active_dimensions: Tensor,
    ) -> Tensor:
        self.received = (state, mask, bounds, category, continuous, active_dimensions)
        result = self.bias.expand(state.shape[0])
        return result * torch.tensor(float("nan")) if self.return_nan else result


class RecordingSGD(torch.optim.SGD):
    def __init__(
        self, parameters: object, name: str, events: list[str], lr: float = 0.01
    ) -> None:
        super().__init__(parameters, lr=lr)  # type: ignore[arg-type]
        self.name = name
        self.events = events

    def step(self, closure: object = None) -> object:
        self.events.append(self.name)
        return super().step(closure)  # type: ignore[arg-type]


class RecordingTrainer(IQLTrainer):
    def __init__(self, *args: object, events: list[str], **kwargs: object) -> None:
        self.events = events
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def _polyak_update(self) -> None:
        self.events.append("targets")
        super()._polyak_update()


def config(*, cadence: int = 1, tau: float = 0.5) -> IQLConfig:
    return IQLConfig(
        eta=0.0,
        expectile=0.7,
        kappa=1.0,
        lambda_ce=0.1,
        lambda_cross=0.1,
        beta=2.0,
        exp_clip=5.0,
        max_weight=100.0,
        max_grad_norm=10.0,
        target_tau=tau,
        target_cadence=cadence,
    )


def batch(*, done: bool = False) -> TransitionBatch:
    return TransitionBatch(
        state=torch.tensor([[1.0, 2.0]]),
        action=torch.tensor([[0.4, -0.2, 0.3]]),
        reward=torch.tensor([2.0]),
        next_state=torch.tensor([[3.0, 4.0]]),
        done=torch.tensor([done]),
        discount=torch.tensor([0.95]),
        category_mask=torch.tensor([[True, True, False]]),
        bounds=torch.tensor([[[-1.0, -1.0], [1.0, 1.0]]]),
        logged_category=torch.tensor([1]),
        active_dimensions=torch.tensor([[True, True, True]]),
    )


def make_trainer(
    *,
    trainer_config: IQLConfig | None = None,
) -> tuple[IQLTrainer, ConstantValue, ConstantQ, ConstantQ, LoggedActor, list[str]]:
    events: list[str] = []
    value = ConstantValue((0.0, 0.0))
    q1 = ConstantQ((0.0, 0.0))
    q2 = ConstantQ((1.0, 1.0))
    actor = LoggedActor()
    trainer = RecordingTrainer(
        value=value,
        q1=q1,
        q2=q2,
        actor=actor,
        value_optimizer=RecordingSGD(value.parameters(), "value", events),
        q1_optimizer=RecordingSGD(q1.parameters(), "q1", events),
        q2_optimizer=RecordingSGD(q2.parameters(), "q2", events),
        actor_optimizer=RecordingSGD(actor.parameters(), "actor", events),
        fractions=torch.tensor([0.25, 0.75]),
        config=trainer_config or config(),
        events=events,
    )
    return trainer, value, q1, q2, actor, events


def test_step_orders_updates_and_uses_logged_actor_inputs() -> None:
    trainer, _, _, _, actor, events = make_trainer()
    transition = batch()

    metrics = trainer.step(transition)

    assert events == ["value", "q1", "q2", "actor", "targets"]
    assert metrics.target_updated
    assert actor.received is not None
    for received, expected in zip(
        actor.received,
        (
            transition.state,
            transition.category_mask,
            transition.bounds,
            transition.logged_category,
            transition.action,
            transition.active_dimensions,
        ),
        strict=True,
    ):
        assert received is expected


def test_value_and_actor_targets_are_detached_and_use_logged_action() -> None:
    trainer, value, _, _, _, _ = make_trainer()
    transition = batch()

    trainer.step(transition)

    assert value.grad_modes == [True, False]
    assert all(not parameter.requires_grad for parameter in trainer.target_value.parameters())
    assert all(not parameter.requires_grad for parameter in trainer.target_q1.parameters())
    assert all(not parameter.requires_grad for parameter in trainer.target_q2.parameters())
    assert all(parameter.grad is None for parameter in trainer.target_value.parameters())
    assert all(parameter.grad is None for parameter in trainer.target_q1.parameters())
    assert all(parameter.grad is None for parameter in trainer.target_q2.parameters())
    assert len(trainer.target_q1.actions) == 2
    assert len(trainer.target_q2.actions) == 2
    for recorded in trainer.target_q1.actions + trainer.target_q2.actions:
        torch.testing.assert_close(recorded, transition.action)


def test_terminal_transition_has_no_value_bootstrap() -> None:
    trainer, _, _, _, _, _ = make_trainer(trainer_config=config(cadence=10))
    with torch.no_grad():
        trainer.target_value.quantiles.fill_(100.0)
    transition = batch(done=True)
    expected = pairwise_quantile_huber_loss(
        torch.zeros(1, 2),
        transition.reward.unsqueeze(-1),
        trainer.fractions,
        config().kappa,
    )

    metrics = trainer.step(transition)

    assert metrics.q1_loss == pytest.approx(expected.item())


def test_polyak_updates_only_on_configured_successful_steps() -> None:
    trainer, _, q1, _, _, events = make_trainer(
        trainer_config=config(cadence=2, tau=0.25)
    )
    initial_target = trainer.target_q1.quantiles.detach().clone()

    first = trainer.step(batch())
    online_after_first = q1.quantiles.detach().clone()
    second = trainer.step(batch())

    assert not first.target_updated
    assert second.target_updated
    assert events.count("targets") == 1
    torch.testing.assert_close(
        trainer.target_q1.quantiles,
        0.25 * q1.quantiles.detach() + 0.75 * initial_target,
    )
    assert not torch.equal(online_after_first, q1.quantiles.detach())


def test_non_finite_input_aborts_before_optimizers_and_targets() -> None:
    trainer, _, _, _, _, events = make_trainer()
    transition = batch()
    transition = TransitionBatch(
        **{**transition.__dict__, "reward": torch.tensor([float("nan")])}
    )
    targets_before = copy.deepcopy(trainer.target_q1.state_dict())

    with pytest.raises(FloatingPointError, match="reward"):
        trainer.step(transition)

    assert events == []
    for name, parameter in trainer.target_q1.state_dict().items():
        torch.testing.assert_close(parameter, targets_before[name])


def test_non_finite_late_loss_never_updates_targets_or_success_counter() -> None:
    trainer, _, _, _, actor, events = make_trainer(
        trainer_config=config(cadence=1)
    )
    actor.return_nan = True
    target_before = trainer.target_q1.quantiles.detach().clone()

    with pytest.raises(FloatingPointError, match="actor loss"):
        trainer.step(batch())

    assert "targets" not in events
    torch.testing.assert_close(trainer.target_q1.quantiles, target_before)
    actor.return_nan = False
    metrics = trainer.step(batch())
    assert metrics.target_updated


def test_gradient_norm_is_finite_and_clipped() -> None:
    trainer, _, _, _, _, _ = make_trainer()

    metrics = trainer.step(batch())

    assert torch.isfinite(torch.tensor(metrics.gradient_norm))
    assert metrics.gradient_norm >= 0.0
