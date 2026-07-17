"""Adapters that expose all pre-Bellman baselines through one policy port."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import torch

from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    ActionMask,
    RawHybridAction,
)
from sneaker_market_maker.research.encoding.schema import EncodedState
from sneaker_market_maker.research.ports import PolicyOutput

Recommendation = Callable[
    [EncodedState, ActionMask, ActionBounds],
    RawHybridAction | PolicyOutput,
]


@dataclass(frozen=True)
class _CallablePolicyAdapter:
    recommender: Recommendation
    _policy_id: str

    @property
    def policy_id(self) -> str:
        return self._policy_id

    def recommend(
        self,
        state: EncodedState,
        mask: ActionMask,
        bounds: ActionBounds,
    ) -> PolicyOutput:
        recommendation = self.recommender(state, mask, bounds)
        if isinstance(recommendation, PolicyOutput):
            if recommendation.policy_id != self.policy_id:
                raise ValueError("adapter output policy_id does not match adapter")
            return recommendation
        return PolicyOutput(recommendation, None, self.policy_id, 0)


class DeterministicPolicyAdapter(_CallablePolicyAdapter):
    def __init__(
        self,
        recommender: Recommendation,
        policy_id: str = "deterministic",
    ) -> None:
        super().__init__(recommender, policy_id)


class HeuristicPolicyAdapter(_CallablePolicyAdapter):
    def __init__(
        self,
        recommender: Recommendation,
        policy_id: str = "heuristic",
    ) -> None:
        super().__init__(recommender, policy_id)


@dataclass(frozen=True)
class NoModelPolicy:
    policy_id: str = "no-model"

    def recommend(
        self,
        state: EncodedState,
        mask: ActionMask,
        bounds: ActionBounds,
    ) -> PolicyOutput:
        del state, bounds
        if not mask.no_op:
            raise ValueError("no-model baseline requires NO_OP to be available")
        action = RawHybridAction(ActionCategory.NO_OP, 0.0, 0.0, 0.0)
        return PolicyOutput(action, None, self.policy_id, 0)


NoModelPolicyAdapter = NoModelPolicy


class V1MLPPolicyAdapter:
    """Adapt the original sigmoid policy scorer without Bellman semantics."""

    def __init__(
        self,
        model: torch.nn.Module,
        policy_id: str = "v1-mlp",
    ) -> None:
        self.model = model
        self._policy_id = policy_id

    @property
    def policy_id(self) -> str:
        return self._policy_id

    def recommend(
        self,
        state: EncodedState,
        mask: ActionMask,
        bounds: ActionBounds,
    ) -> PolicyOutput:
        del bounds
        self.model.eval()
        with torch.no_grad():
            output = self.model(state.values)
        values = output.detach().to(dtype=torch.float64).reshape(-1)
        if values.numel() != 1 or not torch.isfinite(values).all():
            raise ValueError("v1 MLP must return one finite score")
        score = float(values.item())
        if not 0.0 <= score <= 1.0:
            raise ValueError("v1 MLP sigmoid score must be in [0, 1]")
        category = ActionCategory.QUOTE if mask.quote else ActionCategory.NO_OP
        action = RawHybridAction(category, score, 0.0, 0.0)
        return PolicyOutput(
            action=action,
            score=score,
            policy_id=self.policy_id,
            latency_ms=0,
        )


__all__ = [
    "DeterministicPolicyAdapter",
    "HeuristicPolicyAdapter",
    "NoModelPolicy",
    "NoModelPolicyAdapter",
    "V1MLPPolicyAdapter",
]
