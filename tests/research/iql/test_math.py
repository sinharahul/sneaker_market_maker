from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest
import torch

from sneaker_market_maker.research.iql.math import (
    certainty_equivalent,
    pairwise_quantile_huber_loss,
    quantile_crossing_loss,
    smooth_huber,
)


def test_certainty_equivalent_at_zero_eta_returns_mean() -> None:
    quantiles = torch.tensor([[1.0, 2.0, 3.0], [4.0, 6.0, 8.0]], dtype=torch.float64)
    result = certainty_equivalent(quantiles, eta=0.0)
    expected = torch.tensor([2.0, 6.0], dtype=torch.float64)
    torch.testing.assert_close(result, expected)


def test_certainty_equivalent_near_zero_eta_uses_variance_series() -> None:
    quantiles = torch.tensor([[0.0, 1.0, 2.0]], dtype=torch.float64)
    eta = 1e-7
    result = certainty_equivalent(quantiles, eta=eta, epsilon=1e-6)
    mean = quantiles.mean(dim=-1)
    variance = ((quantiles - mean.unsqueeze(-1)) ** 2).mean(dim=-1)
    expected = mean - 0.5 * eta * variance
    torch.testing.assert_close(result, expected)


@pytest.mark.parametrize("eta", [0.25, 0.5, 1.0])
def test_certainty_equivalent_uses_float64_logsumexp(eta: float) -> None:
    quantiles = torch.tensor([[0.0, 1.0, 2.0, 3.0]], dtype=torch.float32)
    result = certainty_equivalent(quantiles, eta=eta)
    z = quantiles.to(torch.float64)
    expected = -(torch.logsumexp(-eta * z, dim=-1) - math.log(z.shape[-1])) / eta
    torch.testing.assert_close(result, expected)
    assert result.dtype == torch.float64


def test_certainty_equivalent_rejects_non_finite_quantiles() -> None:
    quantiles = torch.tensor([[1.0, float("nan"), 3.0]], dtype=torch.float64)
    with pytest.raises(FloatingPointError, match="quantiles must be finite"):
        certainty_equivalent(quantiles, eta=0.5)


def test_certainty_equivalent_rejects_negative_eta() -> None:
    quantiles = torch.tensor([[1.0, 2.0, 3.0]], dtype=torch.float64)
    with pytest.raises(ValueError, match="eta must be non-negative"):
        certainty_equivalent(quantiles, eta=-0.1)


def test_certainty_equivalent_autograd() -> None:
    quantiles = torch.tensor([[0.5, 1.5, 2.5]], dtype=torch.float64, requires_grad=True)
    result = certainty_equivalent(quantiles, eta=0.5)
    result.sum().backward()
    assert quantiles.grad is not None
    assert torch.isfinite(quantiles.grad).all()


@pytest.mark.parametrize(
    ("error", "kappa", "expected"),
    [
        (torch.tensor(0.0), 1.0, torch.tensor(0.0)),
        (torch.tensor(0.5), 1.0, torch.tensor(0.125)),
        (torch.tensor(-0.5), 1.0, torch.tensor(0.125)),
        (torch.tensor(2.0), 1.0, torch.tensor(1.5)),
        (torch.tensor(-2.0), 1.0, torch.tensor(1.5)),
        (torch.tensor(3.0), 1.0, torch.tensor(2.5)),
        (torch.tensor(-3.0), 1.0, torch.tensor(2.5)),
    ],
)
def test_smooth_huber_branch_values(
    error: torch.Tensor, kappa: float, expected: torch.Tensor
) -> None:
    torch.testing.assert_close(smooth_huber(error, kappa), expected)


def test_smooth_huber_autograd() -> None:
    error = torch.tensor([0.5, 2.0], dtype=torch.float64, requires_grad=True)
    result = smooth_huber(error, kappa=1.0)
    result.sum().backward()
    assert error.grad is not None
    torch.testing.assert_close(
        error.grad, torch.tensor([0.5, 1.0], dtype=torch.float64)
    )


def test_pairwise_quantile_huber_loss_quantile_sign_and_weights() -> None:
    predicted = torch.tensor([[1.0, 3.0]], dtype=torch.float64, requires_grad=True)
    target = torch.tensor([[2.0, 2.0]], dtype=torch.float64)
    fractions = torch.tensor([0.25, 0.75], dtype=torch.float64)
    kappa = 1.0

    loss = pairwise_quantile_huber_loss(predicted, target, fractions, kappa)

    errors = target.unsqueeze(-2) - predicted.unsqueeze(-1)
    indicator = (errors < 0).to(predicted.dtype)
    weights = (fractions.view(1, -1, 1) - indicator).abs()
    expected = (weights * smooth_huber(errors, kappa)).mean()
    torch.testing.assert_close(loss, expected)


def test_pairwise_quantile_huber_loss_reduces_by_one_over_k_squared() -> None:
    predicted = torch.tensor([[1.0, 2.0, 3.0]], dtype=torch.float64)
    target = torch.tensor([[1.5, 2.5, 3.5]], dtype=torch.float64)
    fractions = torch.tensor([0.2, 0.5, 0.8], dtype=torch.float64)
    kappa = 0.5

    loss = pairwise_quantile_huber_loss(predicted, target, fractions, kappa)
    errors = target.unsqueeze(-2) - predicted.unsqueeze(-1)
    indicator = (errors < 0).to(predicted.dtype)
    weights = (fractions.view(1, -1, 1) - indicator).abs()
    total = (weights * smooth_huber(errors, kappa)).sum()
    expected = total / (predicted.shape[0] * predicted.shape[-1] ** 2)
    torch.testing.assert_close(loss, expected)


def test_pairwise_quantile_huber_loss_target_is_detached() -> None:
    predicted = torch.tensor([[1.0, 2.0]], dtype=torch.float64, requires_grad=True)
    target = torch.tensor([[1.5, 2.5]], dtype=torch.float64, requires_grad=True)
    fractions = torch.tensor([0.25, 0.75], dtype=torch.float64)

    loss = pairwise_quantile_huber_loss(predicted, target, fractions, kappa=1.0)
    loss.backward()

    assert predicted.grad is not None
    assert target.grad is None


def test_quantile_crossing_loss_penalizes_violations_only() -> None:
    ordered = torch.tensor([[1.0, 2.0, 3.0, 4.0]], dtype=torch.float64)
    crossing = torch.tensor([[1.0, 3.0, 2.0, 4.0]], dtype=torch.float64)

    assert quantile_crossing_loss(ordered) == 0.0
    torch.testing.assert_close(
        quantile_crossing_loss(crossing),
        torch.tensor(1.0 / 3.0, dtype=torch.float64),
    )


def test_quantile_crossing_loss_autograd() -> None:
    quantiles = torch.tensor([[1.0, 3.0, 2.0, 4.0]], dtype=torch.float64, requires_grad=True)
    loss = quantile_crossing_loss(quantiles)
    loss.backward()
    assert quantiles.grad is not None
    torch.testing.assert_close(
        quantiles.grad,
        torch.tensor([[0.0, 1.0, -1.0, 0.0]], dtype=torch.float64) / 3.0,
    )


def test_iql_package_has_no_pfhedge_imports() -> None:
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
