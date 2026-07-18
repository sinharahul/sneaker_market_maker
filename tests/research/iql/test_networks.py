from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest
import torch

from sneaker_market_maker.research.iql.math import certainty_equivalent
from sneaker_market_maker.research.iql.networks import (
    DistributionalQ,
    DistributionalValue,
    create_inference_target,
    select_conservative_quantiles,
)


def test_distributional_value_forward_shape() -> None:
    batch_size = 4
    state_dim = 6
    quantile_count = 7
    value = DistributionalValue(state_dim, hidden_dim=16, quantile_count=quantile_count)
    state = torch.randn(batch_size, state_dim)

    result = value(state)

    assert result.shape == (batch_size, quantile_count)


def test_distributional_q_forward_shape() -> None:
    batch_size = 3
    state_dim = 5
    action_dim = 2
    quantile_count = 9
    critic = DistributionalQ(
        state_dim, action_dim, hidden_dim=16, quantile_count=quantile_count
    )
    state = torch.randn(batch_size, state_dim)
    action = torch.randn(batch_size, action_dim)

    result = critic(state, action)

    assert result.shape == (batch_size, quantile_count)


def test_twin_critics_are_independently_initialized() -> None:
    q1 = DistributionalQ(4, 2, hidden_dim=8, quantile_count=5)
    q2 = DistributionalQ(4, 2, hidden_dim=8, quantile_count=5)

    for param1, param2 in zip(q1.parameters(), q2.parameters(), strict=True):
        assert not torch.equal(param1, param2)


def test_distributional_value_rejects_non_finite_output() -> None:
    value = DistributionalValue(2, hidden_dim=4, quantile_count=3)
    state = torch.zeros(1, 2)
    with torch.no_grad():
        for parameter in value.net.parameters():
            parameter.fill_(float("nan"))

    with pytest.raises(FloatingPointError, match="value output is non-finite"):
        value(state)


def test_distributional_q_rejects_non_finite_output() -> None:
    critic = DistributionalQ(2, 1, hidden_dim=4, quantile_count=3)
    state = torch.zeros(1, 2)
    action = torch.zeros(1, 1)
    with torch.no_grad():
        for parameter in critic.net.parameters():
            parameter.fill_(float("nan"))

    with pytest.raises(FloatingPointError, match="q output is non-finite"):
        critic(state, action)


def test_select_conservative_quantiles_chooses_lower_ce_per_row() -> None:
    q1 = torch.tensor([[0.0, 2.0, 4.0], [10.0, 10.0, 10.0]], dtype=torch.float64)
    q2 = torch.tensor([[4.0, 4.0, 4.0], [1.0, 2.0, 3.0]], dtype=torch.float64)
    eta = 0.0

    result = select_conservative_quantiles(q1, q2, eta)

    ce1 = certainty_equivalent(q1, eta)
    ce2 = certainty_equivalent(q2, eta)
    expected = torch.where(
        (ce1 <= ce2).unsqueeze(-1),
        q1,
        q2,
    )
    torch.testing.assert_close(result, expected)


def test_select_conservative_quantiles_breaks_ties_with_first_critic() -> None:
    q1 = torch.tensor([[1.0, 2.0, 3.0], [5.0, 5.0, 5.0]], dtype=torch.float64)
    q2 = torch.tensor([[2.0, 2.0, 2.0], [5.0, 5.0, 5.0]], dtype=torch.float64)
    eta = 0.0

    result = select_conservative_quantiles(q1, q2, eta)

    assert torch.equal(result[0], q1[0])
    assert torch.equal(result[1], q1[1])


def test_inference_target_is_deep_copy_without_gradients() -> None:
    critic = DistributionalQ(3, 2, hidden_dim=8, quantile_count=4)
    target = create_inference_target(critic)

    assert all(not parameter.requires_grad for parameter in target.parameters())
    assert target is not critic

    for online, copied in zip(critic.parameters(), target.parameters(), strict=True):
        torch.testing.assert_close(online, copied)
        assert online is not copied

    with torch.no_grad():
        for parameter in critic.parameters():
            parameter.add_(1.0)

    for online, copied in zip(critic.parameters(), target.parameters(), strict=True):
        assert not torch.equal(online, copied)


def test_distributional_q_concatenates_state_and_action() -> None:
    critic = DistributionalQ(2, 3, hidden_dim=4, quantile_count=2)
    state = torch.tensor([[1.0, 2.0]])
    action = torch.tensor([[3.0, 4.0, 5.0]])
    expected_input = torch.tensor([[1.0, 2.0, 3.0, 4.0, 5.0]])

    with patch.object(critic.net, "forward", wraps=critic.net.forward) as forward:
        critic(state, action)

    torch.testing.assert_close(forward.call_args.args[0], expected_input)


def test_iql_networks_have_no_pfhedge_imports() -> None:
    iql_root = (
        Path(__file__).parents[3] / "src/sneaker_market_maker/research/iql"
    )
    for module_path in iql_root.glob("**/*.py"):
        tree = ast.parse(module_path.read_text())
        imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            and (
                (
                    isinstance(node, ast.ImportFrom)
                    and (node.module or "").split(".")[0] == "pfhedge"
                )
                or (
                    isinstance(node, ast.Import)
                    and any(alias.name.split(".")[0] == "pfhedge" for alias in node.names)
                )
            )
        ]
        assert not imports, f"{module_path} must not import PFHedge"
