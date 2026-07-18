"""Walk-forward harness benchmark for a trained IQL checkpoint (R2-03)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch

from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    ActionMask,
    RawHybridAction,
)
from sneaker_market_maker.research.encoding.schema import EncodedState
from sneaker_market_maker.research.episodes.builder import Episode
from sneaker_market_maker.research.evaluation.harness import EvaluationHarness
from sneaker_market_maker.research.iql.actor import HybridActor
from sneaker_market_maker.research.iql.checkpoint import CheckpointStore
from sneaker_market_maker.research.policies.baselines import DeterministicPolicyAdapter
from sneaker_market_maker.research.ports import (
    EvaluationReport,
    FrozenAssumptions,
    PolicyOutput,
)
from sneaker_market_maker.research.retrain.train_job import TrainJobResult

_CATEGORIES = (ActionCategory.NO_OP, ActionCategory.QUOTE, ActionCategory.CANCEL)


class CheckpointIqlPolicyAdapter:
    """EvaluationPolicy that loads HybridActor weights from an IQL checkpoint."""

    def __init__(
        self,
        *,
        checkpoint_dir: Path,
        run_manifest_hash: str,
        environment_hash: str,
        state_dim: int,
        policy_id: str = "iql-retrain",
    ) -> None:
        _manifest, tensors = CheckpointStore().load(
            checkpoint_dir,
            run_manifest_hash,
            environment_hash,
        )
        self._policy_id = policy_id
        self._actor = HybridActor(state_dim, hidden_dim=8)
        actor_state = {
            key.removeprefix("actor."): value
            for key, value in tensors.items()
            if key.startswith("actor.")
        }
        self._actor.load_state_dict(actor_state)
        self._actor.eval()
        self._state_dim = state_dim

    @property
    def policy_id(self) -> str:
        return self._policy_id

    def recommend(
        self,
        state: EncodedState,
        mask: ActionMask,
        bounds: ActionBounds,
    ) -> PolicyOutput:
        values = state.values.detach().float()
        if values.ndim == 1:
            values = values.unsqueeze(0)
        if values.shape[-1] < self._state_dim:
            pad = torch.zeros(values.shape[0], self._state_dim - values.shape[-1])
            values = torch.cat((values, pad), dim=-1)
        elif values.shape[-1] > self._state_dim:
            values = values[..., : self._state_dim]
        mask_t = torch.tensor(
            [[mask.no_op, mask.quote, mask.cancel]], dtype=torch.bool
        )
        bounds_t = torch.tensor(
            [
                [
                    [float(bounds.bid_low), float(bounds.ask_low)],
                    [float(bounds.bid_high), float(bounds.ask_high)],
                ]
            ],
            dtype=torch.float32,
        )
        with torch.no_grad():
            action = self._actor.deterministic(values, mask_t, bounds_t)
        category = _CATEGORIES[int(action.category.reshape(-1)[0].item())]
        continuous = action.continuous.detach().cpu().reshape(-1)
        raw = RawHybridAction(
            category,
            float(continuous[0].item()),
            float(continuous[1].item()),
            float(continuous[2].item()),
        )
        return PolicyOutput(action=raw, score=0.0, policy_id=self._policy_id, latency_ms=1)


@dataclass(frozen=True)
class BenchmarkResult:
    deterministic: EvaluationReport
    iql: EvaluationReport
    assumptions_hash: str


def run_harness_benchmark(
    *,
    train_result: TrainJobResult,
    episodes: tuple[Episode, ...],
    assumptions: FrozenAssumptions,
    simulator: object,
    state_dim: int,
    bootstrap_samples: int = 5,
) -> BenchmarkResult:
    """Compare deterministic baseline vs checkpoint IQL under one FrozenAssumptions."""

    harness = EvaluationHarness(
        simulator,  # type: ignore[arg-type]
        bootstrap_samples=bootstrap_samples,
    )

    def _noop(
        _state: EncodedState, _mask: ActionMask, _bounds: ActionBounds
    ) -> RawHybridAction:
        return RawHybridAction(ActionCategory.NO_OP, 0.0, 0.0, 0.0)

    deterministic = DeterministicPolicyAdapter(_noop)
    iql_policy = CheckpointIqlPolicyAdapter(
        checkpoint_dir=train_result.checkpoint_dir,
        run_manifest_hash=train_result.manifest_content_hash,
        environment_hash=train_result.assumptions_hash,
        state_dim=state_dim,
    )
    return BenchmarkResult(
        deterministic=harness.run(deterministic, episodes, assumptions),
        iql=harness.run(iql_policy, episodes, assumptions),
        assumptions_hash=assumptions.content_hash,
    )
