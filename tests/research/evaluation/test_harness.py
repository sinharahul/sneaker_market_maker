import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
import torch

from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    ActionMask,
    HybridAction,
    RawHybridAction,
)
from sneaker_market_maker.research.encoding.schema import EncodedState
from sneaker_market_maker.research.episodes.builder import Episode
from sneaker_market_maker.research.episodes.events import DecisionPoint, EventKind
from sneaker_market_maker.research.evaluation.harness import EvaluationHarness
from sneaker_market_maker.research.policies.baselines import (
    DeterministicPolicyAdapter,
    HeuristicPolicyAdapter,
    NoModelPolicy,
    V1MLPPolicyAdapter,
)
from sneaker_market_maker.research.ports import (
    EpisodeEvaluation,
    FrozenAssumptions,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
MASK = ActionMask(no_op=True, quote=True, cancel=True)
BOUNDS = ActionBounds(-2, 2, -3, 3)


def encoded(value: float = 1.0) -> EncodedState:
    return EncodedState(
        values=torch.tensor([value]),
        collection_mask=torch.tensor([], dtype=torch.bool),
        missingness=torch.tensor([False]),
        schema_version="state-v1",
        scaler_version="scaler-v1",
    )


def episode(index: int, provenance: str = "historical") -> Episode:
    episode_id = UUID(int=index + 1)
    decision = DecisionPoint(
        index=0,
        simulation_time=NOW + timedelta(days=index),
        elapsed_seconds=60,
        reasons=(EventKind.BOOK,),
        source_ids=(f"source-{index}",),
        provenances=(provenance,),
        discount=1.0,
        episode_id=episode_id,
        state={"encoded_state": encoded(float(index + 1))},
        action_mask=MASK,
        action_bounds=BOUNDS,
        terminal_reason="replay_exhausted",
    )
    return Episode(
        episode_id=episode_id,
        start=decision.simulation_time - timedelta(minutes=1),
        end=decision.simulation_time,
        decisions=(decision,),
        terminal_reason="replay_exhausted",
    )


def assumptions() -> FrozenAssumptions:
    return FrozenAssumptions(
        episode_hash="episodes-v1",
        fee_version="fees-v2",
        slippage_version="slippage-v1",
        logistics_version="logistics-v3",
        terminal_policy_version="terminal-v1",
        gate_policy_version="gates-v4",
        latency_ms=25,
    )


def episode_bytes(item: Episode) -> bytes:
    payload = {
        "episode_id": str(item.episode_id),
        "start": item.start.isoformat(),
        "end": item.end.isoformat(),
        "terminal_reason": item.terminal_reason,
        "decisions": [
            {
                "index": decision.index,
                "simulation_time": decision.simulation_time.isoformat(),
                "source_ids": decision.source_ids,
                "provenances": decision.provenances,
                "state_values": decision.state["encoded_state"].values.tolist(),
            }
            for decision in item.decisions
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


class SimulatorSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, bytes, tuple[HybridAction, ...]]] = []

    def run_episode(
        self,
        item: Episode,
        actions: tuple[HybridAction, ...],
        frozen: FrozenAssumptions,
    ) -> EpisodeEvaluation:
        self.calls.append(
            (
                episode_bytes(item),
                frozen.to_bytes(),
                actions,
            )
        )
        value = float(item.episode_id.int)
        return EpisodeEvaluation(
            metrics={
                "net_return": value / 100,
                "max_drawdown": value / 200,
                "inventory_age": value,
                "stranded_inventory": 0.0,
                "capital_utilization": 0.5,
                "reservation_time": 10.0,
                "turnover_rate": 0.2,
                "cancel_rate": 0.1,
                "fill_rate": 0.4,
                "gate_rejection_rate": 0.0,
            },
            support_coverage=0.75,
            numerical_failures=0,
            seed=index_from_uuid(item.episode_id),
            latency_ms=7.0,
        )


def index_from_uuid(value: UUID) -> int:
    return value.int - 1


def quote_policy(_: EncodedState, __: ActionMask, ___: ActionBounds) -> RawHybridAction:
    return RawHybridAction(ActionCategory.QUOTE, 2.0, 9.2, -9.2)


class TinyMLP(torch.nn.Module):
    def forward(self, values: torch.Tensor) -> torch.Tensor:
        return torch.tensor([0.5])


@pytest.mark.parametrize(
    "policy",
    [
        DeterministicPolicyAdapter(quote_policy),
        NoModelPolicy(),
        HeuristicPolicyAdapter(quote_policy),
        V1MLPPolicyAdapter(TinyMLP()),
    ],
)
def test_every_baseline_uses_identical_inputs_and_shared_simulator(policy: object) -> None:
    items = (episode(0), episode(1))
    simulator = SimulatorSpy()

    report = EvaluationHarness(simulator).run(policy, items, assumptions())

    expected_episode_bytes = [episode_bytes(item) for item in items]
    assert [call[0] for call in simulator.calls] == expected_episode_bytes
    assert [call[1] for call in simulator.calls] == [assumptions().to_bytes()] * 2
    assert report.assumptions_hash == assumptions().content_hash
    assert report.historical is True
    assert report.support_coverage == pytest.approx(0.75)


def test_canonicalizes_policy_actions_before_shared_simulation() -> None:
    simulator = SimulatorSpy()

    EvaluationHarness(simulator).run(
        DeterministicPolicyAdapter(quote_policy),
        (episode(0),),
        assumptions(),
    )

    assert simulator.calls[0][2] == (
        HybridAction(ActionCategory.QUOTE, 1.0, 2, -3),
    )


def test_report_contains_required_metrics_intervals_and_seed_results() -> None:
    report = EvaluationHarness(SimulatorSpy()).run(
        NoModelPolicy(),
        (episode(0), episode(1)),
        assumptions(),
    )

    required = {
        "net_return",
        "certainty_equivalent",
        "mean_return",
        "median_return",
        "var_95",
        "cvar_95",
        "worst_block",
        "max_drawdown",
        "inventory_age",
        "stranded_inventory",
        "capital_utilization",
        "reservation_time",
        "turnover_rate",
        "cancel_rate",
        "fill_rate",
        "gate_rejection_rate",
        "support_coverage",
        "latency_ms",
        "numerical_failures",
        "seed_dispersion",
    }
    assert required <= report.metrics.keys()
    assert all(metric.lower <= metric.point <= metric.upper for metric in report.metrics.values())
    assert report.seed_results.keys() == {0, 1}


def test_mixed_provenance_is_not_reported_as_historical() -> None:
    report = EvaluationHarness(SimulatorSpy()).run(
        NoModelPolicy(),
        (episode(0), episode(1, "synthetic")),
        assumptions(),
    )

    assert report.historical is False
