from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import torch
from pfhedge.nn import EntropicRiskMeasure

from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionMask,
    HybridAction,
)
from sneaker_market_maker.research.encoding.schema import EncodedState
from sneaker_market_maker.research.episodes.builder import Episode
from sneaker_market_maker.research.episodes.events import DecisionPoint, EventKind
from sneaker_market_maker.research.evaluation.harness import EvaluationHarness
from sneaker_market_maker.research.pfhedge.adapter import (
    PFHedgeDirectPolicy,
    PFHedgeTrainer,
)
from sneaker_market_maker.research.policies.baselines import NoModelPolicy
from sneaker_market_maker.research.ports import (
    EpisodeEvaluation,
    FrozenAssumptions,
)
from sneaker_market_maker.research.rewards.builder import (
    AccountingProjection,
    PenaltyStatistics,
    RewardBuilder,
    RewardConfig,
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


class RewardBackedSimulator:
    """Shared harness simulator fixture backed by the canonical reward path."""

    def __init__(self) -> None:
        zero = Decimal("0")
        self.reward_builder = RewardBuilder(
            RewardConfig(
                version="reward-v1",
                initial_nav=Decimal("1000"),
                lambda_age=zero,
                lambda_capital=zero,
                lambda_turnover=zero,
                lambda_drawdown=zero,
                lambda_stale=zero,
                lambda_terminal=zero,
                tolerance=Decimal("1e-12"),
            )
        )
        self.terminal_pnl: list[float] = []
        self.costs: list[dict[str, Decimal]] = []

    def run_episode(
        self,
        episode: Episode,
        actions: tuple[HybridAction, ...],
        assumptions: FrozenAssumptions,
    ) -> EpisodeEvaluation:
        assert actions
        assert assumptions.fee_version == "fees-v2"
        assert assumptions.slippage_version == "slippage-v1"
        assert assumptions.logistics_version == "logistics-v3"
        before = _projection(nav=Decimal("1000"))
        terminal_nav = Decimal("1050") if episode.episode_id.int == 1 else Decimal("950")
        after = _projection(
            nav=terminal_nav,
            ledger_entry_ids=(
                "seller_fees:sale-1",
                "processor_fees:sale-1",
                "shipping:shipment-1",
                "authentication:lot-1",
                "slippage:fill-1",
            ),
            seller_fees=Decimal("10"),
            processor_fees=Decimal("2"),
            shipping=Decimal("5"),
            authentication=Decimal("3"),
            slippage=Decimal("1"),
        )
        reward = self.reward_builder.build(
            before,
            after,
            _zero_penalties(),
            terminal=True,
        )
        pnl = float(reward.total)
        self.terminal_pnl.append(pnl)
        self.costs.append(dict(reward.explanatory_costs))
        return EpisodeEvaluation(
            metrics={
                "net_return": pnl,
                "max_drawdown": max(0.0, -pnl),
                "inventory_age": 0.0,
                "stranded_inventory": 0.0,
                "capital_utilization": 0.0,
                "reservation_time": 0.0,
                "turnover_rate": 0.0,
                "cancel_rate": 0.0,
                "fill_rate": 0.0,
                "gate_rejection_rate": 0.0,
            },
            support_coverage=1.0,
            numerical_failures=0,
            seed=episode.episode_id.int,
            latency_ms=0.0,
        )


def _projection(**changes: object) -> AccountingProjection:
    values: dict[str, object] = {
        "nav": Decimal("1000"),
        "ledger_entry_ids": (),
        "seller_fees": Decimal("0"),
        "processor_fees": Decimal("0"),
        "shipping": Decimal("0"),
        "authentication": Decimal("0"),
        "slippage": Decimal("0"),
        "open_reservations": (),
        "physical_lots": (),
    }
    values.update(changes)
    return AccountingProjection(**values)  # type: ignore[arg-type]


def _zero_penalties() -> PenaltyStatistics:
    zero = Decimal("0")
    return PenaltyStatistics(zero, zero, zero, zero, zero, zero)


def _evaluation_episode(index: int) -> Episode:
    simulation_time = datetime(2026, 1, index + 1, tzinfo=timezone.utc)
    episode_id = UUID(int=index + 1)
    encoded = EncodedState(
        values=torch.tensor([float(index)]),
        collection_mask=torch.tensor([True]),
        missingness=torch.tensor([False]),
        schema_version="state-v1",
        scaler_version="scaler-v1",
    )
    decision = DecisionPoint(
        index=0,
        simulation_time=simulation_time,
        elapsed_seconds=60,
        reasons=(EventKind.BOOK,),
        source_ids=(f"source-{index}",),
        provenances=("historical",),
        discount=1.0,
        episode_id=episode_id,
        state={"encoded_state": encoded},
        action_mask=ActionMask(no_op=True, quote=True, cancel=True),
        action_bounds=ActionBounds(-2, 2, -3, 3),
        terminal_reason="replay_exhausted",
    )
    return Episode(
        episode_id=episode_id,
        start=simulation_time - timedelta(minutes=1),
        end=simulation_time,
        decisions=(decision,),
        terminal_reason="replay_exhausted",
    )


def _frozen_assumptions() -> FrozenAssumptions:
    return FrozenAssumptions(
        episode_hash="episodes-v1",
        fee_version="fees-v2",
        slippage_version="slippage-v1",
        logistics_version="logistics-v3",
        terminal_policy_version="terminal-v1",
        gate_policy_version="gates-v4",
        latency_ms=0,
    )


def test_trainer_uses_public_entropic_risk_on_terminal_simulator_pnl() -> None:
    simulator = RewardBackedSimulator()
    EvaluationHarness(simulator, bootstrap_samples=20).run(
        NoModelPolicy(),
        (_evaluation_episode(0), _evaluation_episode(1)),
        _frozen_assumptions(),
    )
    terminal_pnl = torch.tensor(simulator.terminal_pnl, dtype=torch.float64)
    trainer = PFHedgeTrainer(risk_aversion=0.5)

    loss = trainer.loss(terminal_pnl)

    expected = EntropicRiskMeasure(a=0.5)(
        terminal_pnl,
        target=torch.zeros_like(terminal_pnl),
    )
    torch.testing.assert_close(loss, expected)
    assert trainer.criterion.__class__ is EntropicRiskMeasure
    assert simulator.costs == [
        {
            "seller_fees": Decimal("10"),
            "processor_fees": Decimal("2"),
            "shipping": Decimal("5"),
            "authentication": Decimal("3"),
            "slippage": Decimal("1"),
        }
    ] * 2


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
