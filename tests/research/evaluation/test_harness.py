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
from sneaker_market_maker.research.evaluation.harness import (
    EvaluationHarness,
    serialize_episode,
)
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
        collection_mask=torch.tensor([True]),
        missingness=torch.tensor([False]),
        schema_version="state-v1",
        scaler_version="scaler-v1",
    )


def episode(index: int, provenance: str | None = "historical") -> Episode:
    episode_id = UUID(int=index + 1)
    source_ids = (f"source-{index}",) if provenance is not None else ()
    provenances = (provenance,) if provenance is not None else ()
    decision = DecisionPoint(
        index=0,
        simulation_time=NOW + timedelta(days=index),
        elapsed_seconds=60,
        reasons=(EventKind.BOOK,),
        source_ids=source_ids,
        provenances=provenances,
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
                serialize_episode(item),
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
    expected_episode_bytes = [serialize_episode(item) for item in items]

    report = EvaluationHarness(simulator).run(policy, items, assumptions())

    assert [call[0] for call in simulator.calls] == expected_episode_bytes
    assert [call[1] for call in simulator.calls] == [assumptions().to_bytes()] * 2
    assert report.assumptions_hash == assumptions().content_hash
    assert report.historical is True
    assert report.support_coverage == pytest.approx(0.75)


def test_episode_serialization_is_complete_and_canonical() -> None:
    payload = json.loads(serialize_episode(episode(0)))
    decision = payload["decisions"][0]
    encoded_state = decision["state"]["encoded_state"]

    assert decision["action_mask"] == {"cancel": True, "no_op": True, "quote": True}
    assert decision["action_bounds"] == {
        "ask_high": 3,
        "ask_low": -3,
        "bid_high": 2,
        "bid_low": -2,
    }
    assert decision["reasons"] == ["book"]
    assert decision["discount"] == 1.0
    assert encoded_state["missingness"]["values"] == [False]
    assert encoded_state["collection_mask"]["values"] == [True]
    assert encoded_state["schema_version"] == "state-v1"
    assert encoded_state["scaler_version"] == "scaler-v1"


def test_policy_receives_detached_clones_and_cannot_mutate_episode() -> None:
    item = episode(0)
    before = serialize_episode(item)
    simulator = SimulatorSpy()

    def mutate(state: EncodedState, _: ActionMask, __: ActionBounds) -> RawHybridAction:
        state.values.add_(100)
        state.collection_mask.fill_(False)
        state.missingness.fill_(True)
        return quote_policy(state, MASK, BOUNDS)

    EvaluationHarness(simulator).run(
        DeterministicPolicyAdapter(mutate),
        (item,),
        assumptions(),
    )

    assert serialize_episode(item) == before
    assert simulator.calls[0][0] == before


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


def test_empty_provenance_is_not_reported_as_historical() -> None:
    report = EvaluationHarness(SimulatorSpy()).run(
        NoModelPolicy(),
        (episode(0, None),),
        assumptions(),
    )

    assert report.historical is False
