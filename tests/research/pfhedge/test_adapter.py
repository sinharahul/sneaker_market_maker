from __future__ import annotations

import ast
from pathlib import Path

import torch
from pfhedge.nn import EntropicRiskMeasure

from sneaker_market_maker.research.pfhedge.adapter import (
    PFHedgeDirectPolicy,
    PFHedgeTrainer,
)


def _scenario() -> tuple[torch.Tensor, torch.Tensor]:
    state = torch.tensor(
        [
            [[0.1, -0.2, 0.3, 0.4], [0.2, -0.1, 0.4, 0.5]],
            [[-0.3, 0.2, 0.1, -0.4], [-0.2, 0.3, 0.2, -0.5]],
        ],
        dtype=torch.float64,
    )
    low = torch.tensor([-0.25, -0.50], dtype=torch.float64)
    high = torch.tensor([0.75, 0.25], dtype=torch.float64)
    bounds = torch.stack((low, high)).expand(2, 2, -1, -1)
    return state, bounds


def _fit_seeded_policy(seed: int) -> tuple[torch.Tensor, torch.Tensor]:
    torch.manual_seed(seed)
    state, bounds = _scenario()
    policy = PFHedgeDirectPolicy(feature_count=4, hidden=8).to(dtype=torch.float64)
    optimizer = torch.optim.SGD(policy.parameters(), lr=0.05)
    trainer = PFHedgeTrainer(risk_aversion=0.5)

    for _ in range(3):
        optimizer.zero_grad()
        action = policy(state, bounds)
        terminal_pnl = (
            action[..., 0].sum(dim=1)
            - action[..., 1].square().sum(dim=1)
            - action[..., 2].abs().sum(dim=1)
        )
        trainer.loss(terminal_pnl).backward()
        optimizer.step()

    parameters = torch.cat([parameter.detach().flatten() for parameter in policy.parameters()])
    return policy(state, bounds).detach(), parameters


def test_direct_policy_returns_bounded_continuous_actions() -> None:
    state, bounds = _scenario()
    policy = PFHedgeDirectPolicy(feature_count=4, hidden=8).to(dtype=torch.float64)

    action = policy(state, bounds)

    assert action.shape == torch.Size([2, 2, 3])
    assert torch.all((action[..., 0] >= 0.0) & (action[..., 0] <= 1.0))
    assert torch.all(action[..., 1:] >= bounds[..., 0, :])
    assert torch.all(action[..., 1:] <= bounds[..., 1, :])


def test_seeded_fit_is_deterministic() -> None:
    first_action, first_parameters = _fit_seeded_policy(seed=173)
    second_action, second_parameters = _fit_seeded_policy(seed=173)

    torch.testing.assert_close(first_action, second_action, rtol=0.0, atol=0.0)
    torch.testing.assert_close(first_parameters, second_parameters, rtol=0.0, atol=0.0)


def test_trainer_uses_public_entropic_risk_on_terminal_simulator_pnl() -> None:
    gross_pnl = torch.tensor([2.0, -1.0], dtype=torch.float64)
    shared_simulator_costs = torch.tensor([0.5, 0.25], dtype=torch.float64)
    terminal_pnl = gross_pnl - shared_simulator_costs
    trainer = PFHedgeTrainer(risk_aversion=0.5)

    loss = trainer.loss(terminal_pnl)

    expected = EntropicRiskMeasure(a=0.5)(
        terminal_pnl,
        target=torch.zeros_like(terminal_pnl),
    )
    torch.testing.assert_close(loss, expected)
    assert trainer.criterion.__class__ is EntropicRiskMeasure


def test_iql_track_has_no_pfhedge_imports() -> None:
    research_root = Path(__file__).parents[3] / "src/sneaker_market_maker/research"
    iql_root = research_root / "iql"

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
