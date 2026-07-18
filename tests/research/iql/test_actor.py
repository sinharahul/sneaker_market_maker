from __future__ import annotations

import math

import pytest
import torch
from hypothesis import given
from hypothesis import strategies as st
from torch.distributions import Normal

from sneaker_market_maker.research.iql.actor import (
    HybridActor,
    masked_log_softmax,
    squash_continuous,
    transformed_normal_log_prob,
)


def _actor() -> HybridActor:
    return HybridActor(state_dim=2, hidden_dim=4)


def _set_constant_outputs(
    actor: HybridActor,
    category_logits: list[float],
    mean: list[float],
    log_std: list[float],
) -> None:
    with torch.no_grad():
        for module in (actor.category_head, actor.mean_head, actor.log_std_head):
            for parameter in module.parameters():
                parameter.zero_()
        actor.category_head[-1].bias.copy_(torch.tensor(category_logits))
        actor.mean_head[-1].bias.copy_(torch.tensor(mean))
        actor.log_std_head[-1].bias.copy_(torch.tensor(log_std))


def test_masked_categories_have_zero_probability() -> None:
    logits = torch.tensor([[100.0, 1.0, 2.0], [3.0, 100.0, 1.0]])
    mask = torch.tensor([[False, True, True], [True, False, True]])

    probabilities = masked_log_softmax(logits, mask).exp()

    assert torch.equal(probabilities[~mask], torch.zeros(2))


def test_fully_masked_rows_raise() -> None:
    with pytest.raises(ValueError, match="fully masked action row"):
        masked_log_softmax(
            torch.zeros(2, 3),
            torch.tensor([[True, False, False], [False, False, False]]),
        )


@given(
    raw_values=st.lists(
        st.floats(
            min_value=-80.0,
            max_value=80.0,
            allow_nan=False,
            allow_infinity=False,
            width=32,
        ),
        min_size=3,
        max_size=3,
    )
)
def test_squashed_continuous_stays_bounded_for_finite_raw_values(
    raw_values: list[float],
) -> None:
    raw = torch.tensor([raw_values])
    bounds = torch.tensor([[[-2.0, 10.0], [4.0, 12.0]]])

    continuous = squash_continuous(raw, bounds)

    assert torch.isfinite(continuous).all()
    assert 0.0 <= continuous[0, 0] <= 1.0
    assert -2.0 <= continuous[0, 1] <= 4.0
    assert 10.0 <= continuous[0, 2] <= 12.0


def test_deterministic_uses_masked_argmax_and_transformed_means() -> None:
    actor = _actor()
    _set_constant_outputs(
        actor,
        category_logits=[100.0, 2.0, 3.0],
        mean=[0.0, 0.5, -0.5],
        log_std=[0.0, 0.0, 0.0],
    )
    state = torch.zeros(1, 2)
    mask = torch.tensor([[False, True, True]])
    bounds = torch.tensor([[[-2.0, 10.0], [4.0, 12.0]]])

    action = actor.deterministic(state, mask, bounds)

    assert action.category.tolist() == [2]
    torch.testing.assert_close(
        action.continuous,
        squash_continuous(torch.tensor([[0.0, 0.5, -0.5]]), bounds),
    )
    expected_log_probability = masked_log_softmax(
        torch.tensor([[100.0, 2.0, 3.0]]), mask
    )[0, 2]
    torch.testing.assert_close(
        action.categorical_log_probability,
        expected_log_probability.unsqueeze(0),
    )


def test_inactive_dimensions_contribute_zero_log_density() -> None:
    result = transformed_normal_log_prob(
        mean=torch.tensor([[10.0, -20.0, 30.0]]),
        log_std=torch.tensor([[2.0, -5.0, 1.0]]),
        continuous=torch.tensor([[0.2, -1.0, 12.0]]),
        bounds=torch.tensor([[[-2.0, 10.0], [4.0, 14.0]]]),
        active_dimensions=torch.tensor([[False, False, False]]),
    )

    torch.testing.assert_close(result, torch.zeros(1))


def test_active_dimensions_include_sigmoid_and_affine_tanh_jacobians() -> None:
    mean = torch.zeros(1, 3, dtype=torch.float64)
    log_std = torch.zeros_like(mean)
    continuous = torch.tensor([[0.25, 1.0, 13.0]], dtype=torch.float64)
    bounds = torch.tensor([[[-1.0, 10.0], [3.0, 14.0]]], dtype=torch.float64)
    active = torch.tensor([[True, True, True]])

    result = transformed_normal_log_prob(mean, log_std, continuous, bounds, active)

    unit = torch.tensor([[0.0, 0.5]], dtype=torch.float64)
    raw = torch.cat((torch.logit(continuous[:, :1]), torch.atanh(unit)), dim=-1)
    base = Normal(mean, torch.ones_like(mean)).log_prob(raw)
    allocation_jacobian = torch.log(continuous[:, :1] * (1.0 - continuous[:, :1]))
    offset_jacobian = torch.log1p(-unit.square()) + math.log(2.0)
    expected = (base - torch.cat((allocation_jacobian, offset_jacobian), dim=-1)).sum(-1)
    torch.testing.assert_close(result, expected)


def test_log_prob_adds_masked_category_and_conditioned_continuous_density() -> None:
    actor = _actor()
    _set_constant_outputs(
        actor,
        category_logits=[0.0, 2.0, 1.0],
        mean=[0.0, 0.0, 0.0],
        log_std=[0.0, 0.0, 0.0],
    )
    state = torch.zeros(1, 2)
    mask = torch.tensor([[True, True, False]])
    bounds = torch.tensor([[[-1.0, -2.0], [1.0, 2.0]]])
    category = torch.tensor([1])
    continuous = torch.tensor([[0.5, 0.0, 0.0]])
    active = torch.tensor([[True, True, True]])

    result = actor.log_prob(state, mask, bounds, category, continuous, active)

    categorical = masked_log_softmax(torch.tensor([[0.0, 2.0, 1.0]]), mask)[0, 1]
    transformed = transformed_normal_log_prob(
        torch.zeros(1, 3),
        torch.zeros(1, 3),
        continuous,
        bounds,
        active,
    )
    torch.testing.assert_close(result, categorical + transformed)


def test_non_quote_action_is_categorical_only() -> None:
    actor = _actor()
    _set_constant_outputs(actor, [2.0, 1.0, 0.0], [50.0] * 3, [2.0] * 3)
    mask = torch.ones(1, 3, dtype=torch.bool)

    result = actor.log_prob(
        torch.zeros(1, 2),
        mask,
        torch.tensor([[[-1.0, -1.0], [1.0, 1.0]]]),
        torch.tensor([0]),
        torch.tensor([[0.5, 0.0, 0.0]]),
        torch.zeros(1, 3, dtype=torch.bool),
    )

    expected = masked_log_softmax(torch.tensor([[2.0, 1.0, 0.0]]), mask)[0, 0]
    torch.testing.assert_close(result, expected.unsqueeze(0))
