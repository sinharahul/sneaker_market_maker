"""Compact local fixtures for network-denied safety smoke tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import torch

from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    ActionMask,
    HybridAction,
    RawHybridAction,
)
from sneaker_market_maker.research.demo.service import DemoService
from sneaker_market_maker.research.encoding.schema import EncodedState
from sneaker_market_maker.research.episodes.builder import Episode, EpisodeBuilder, EpisodeConfig
from sneaker_market_maker.research.episodes.events import DecisionPoint, EventKind, NormalizedEvent
from sneaker_market_maker.research.evaluation.harness import EvaluationHarness
from sneaker_market_maker.research.iql.actor import HybridActor
from sneaker_market_maker.research.pfhedge.adapter import PFHedgeDirectPolicy
from sneaker_market_maker.research.policies.baselines import NoModelPolicy
from sneaker_market_maker.research.ports import EpisodeEvaluation, FrozenAssumptions
from sneaker_market_maker.research.registry.service import (
    CompatibilityContract,
    InMemoryRegistryStore,
    RegistryService,
    RegistryState,
)
from sneaker_market_maker.research.rewards.builder import (
    AccountingProjection,
    PenaltyStatistics,
    RewardBuilder,
    RewardConfig,
)
from sneaker_market_maker.research.serving.recommender import (
    GateResult,
    RecommendationRequest,
    RecommendationService,
)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
DETERMINISTIC = HybridAction(ActionCategory.NO_OP, 0.0, 0, 0)
RAW_QUOTE = RawHybridAction(ActionCategory.QUOTE, 1.0, -1.0, 1.0)
BOUNDS = ActionBounds(-3, 3, -4, 2)
MASK = ActionMask(True, True, True)


def build_episode() -> object:
    builder = EpisodeBuilder()
    events = [
        NormalizedEvent(
            source_id="book",
            simulation_time=START + timedelta(seconds=30),
            stable_order=1,
            kind=EventKind.BOOK,
            payload={},
            provenance="historical",
        ),
        NormalizedEvent(
            source_id="fill",
            simulation_time=START + timedelta(seconds=30),
            stable_order=2,
            kind=EventKind.FILL,
            payload={},
            provenance="historical",
        ),
    ]
    config = EpisodeConfig(
        episode_id=uuid4(),
        start=START,
        split_end=START + timedelta(days=30),
        discount_rate=0.01,
    )
    return builder.build(events, config)


def build_reward() -> Decimal:
    builder = RewardBuilder(
        RewardConfig(
            version="reward-v1",
            initial_nav=Decimal("1000"),
            lambda_age=Decimal("0"),
            lambda_capital=Decimal("0"),
            lambda_turnover=Decimal("0"),
            lambda_drawdown=Decimal("0"),
            lambda_stale=Decimal("0"),
            lambda_terminal=Decimal("0"),
            tolerance=Decimal("1e-12"),
        )
    )
    zero = Decimal("0")
    before = AccountingProjection(
        nav=Decimal("1000"),
        ledger_entry_ids=(),
        seller_fees=zero,
        processor_fees=zero,
        shipping=zero,
        authentication=zero,
        slippage=zero,
        open_reservations=(),
        physical_lots=(),
    )
    after = AccountingProjection(
        nav=Decimal("1010"),
        ledger_entry_ids=("seller_fees:ledger-1",),
        seller_fees=Decimal("1"),
        processor_fees=zero,
        shipping=zero,
        authentication=zero,
        slippage=zero,
        open_reservations=(),
        physical_lots=(),
    )
    penalties = PenaltyStatistics(zero, zero, zero, zero, zero, zero)
    return builder.build(before, after, penalties, terminal=False).total


class LocalSimulator:
    def run_episode(self, episode, actions, assumptions) -> EpisodeEvaluation:
        del actions, assumptions
        return EpisodeEvaluation(
            metrics={
                "net_return": float(episode.episode_id.int % 7),
                "max_drawdown": 0.0,
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


def evaluation_episode() -> Episode:
    episode_id = uuid4()
    simulation_time = START + timedelta(seconds=60)
    encoded = EncodedState(
        values=torch.tensor([1.0]),
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
        source_ids=("source-1",),
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


def run_evaluation() -> float:
    report = EvaluationHarness(LocalSimulator(), bootstrap_samples=5).run(
        NoModelPolicy(),
        (evaluation_episode(),),
        FrozenAssumptions(
            episode_hash="episodes-v1",
            fee_version="fees-v2",
            slippage_version="slippage-v1",
            logistics_version="logistics-v3",
            terminal_policy_version="terminal-v1",
            gate_policy_version="gates-v4",
            latency_ms=0,
        ),
    )
    return report.metrics["net_return"].point


def run_pfhedge_inference() -> int:
    state = torch.tensor([[[0.1, 0.2, 0.3, 0.4]]], dtype=torch.float64)
    bounds = torch.tensor([[[[-1.0, -2.0], [1.0, 2.0]]]], dtype=torch.float64)
    policy = PFHedgeDirectPolicy(feature_count=4, hidden=8).to(dtype=torch.float64)
    action = policy(state, bounds)
    return int(action.shape[-1])


def run_iql_inference() -> int:
    actor = HybridActor(state_dim=2, hidden_dim=4)
    with torch.no_grad():
        for module in (actor.category_head, actor.mean_head, actor.log_std_head):
            for parameter in module.parameters():
                parameter.zero_()
        actor.category_head[-1].bias.copy_(torch.tensor([0.0, 2.0, 3.0]))
    state = torch.zeros(1, 2)
    mask = torch.tensor([[False, True, True]])
    bounds = torch.tensor([[[-1.0, -2.0], [1.0, 2.0]]])
    action = actor.deterministic(state, mask, bounds)
    return int(action.category.item())


def register_candidate() -> RegistryState:
    store = InMemoryRegistryStore()
    registry = RegistryService(
        store=store,
        benchmark_policy=None,
        benchmark_reports={},
        clock=lambda: START,
        id_factory=lambda: UUID(int=1),
    )
    model = registry.register(
        "a" * 64,
        CompatibilityContract(
            state_schema_version="state-v1",
            action_schema_version="action-v1",
            encoder_version="encoder-v1",
            reward_version="reward-v1",
            architecture="iql-v1",
            environment_hash="b" * 64,
        ),
        UUID(int=2),
        "researcher",
    )
    return model.state


class Gates:
    def evaluate(self, action: HybridAction, risk_state: object) -> GateResult:
        del action, risk_state
        return GateResult(True, (("risk", True),))


class Store:
    def __init__(self) -> None:
        self.records: list[object] = []

    def save(self, record: object) -> None:
        self.records.append(record)


def shadow_recommendation() -> HybridAction:
    store = Store()
    record = RecommendationService(Gates(), store).recommend(
        RecommendationRequest(
            request_id=UUID(int=3),
            deterministic_action=DETERMINISTIC,
            pfhedge_action=RAW_QUOTE,
            iql_action=RAW_QUOTE,
            selected_model_action=RAW_QUOTE,
            bounds=BOUNDS,
            mask=MASK,
            risk_state={"deterministic_approved": True},
            registry_state=RegistryState.SHADOW,
            support_ok=True,
            healthy=True,
            drifted=False,
            lineage_compatible=True,
        )
    )
    assert len(store.records) == 1
    return record.final_action


def run_demo() -> tuple[str, ...]:
    service = DemoService()
    beats = [service.snapshot().beat]
    while service.snapshot().index < 5:
        beats.append(service.step().beat)
    return tuple(beats)
