"""Single policy evaluation path under frozen simulator assumptions."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Protocol

from sneaker_market_maker.research.contracts.action import (
    ActionCategory,
    RawHybridAction,
    canonicalize_action,
)
from sneaker_market_maker.research.encoding.schema import EncodedState
from sneaker_market_maker.research.episodes.builder import Episode
from sneaker_market_maker.research.evaluation.metrics import metric_intervals, seed_results
from sneaker_market_maker.research.ports import (
    EpisodeEvaluation,
    EvaluationPolicy,
    EvaluationReport,
    EvaluationSimulator,
    FrozenAssumptions,
)


class StateEncoderPort(Protocol):
    def encode(self, state: Mapping[str, object]) -> EncodedState:
        raise NotImplementedError


Encoder = StateEncoderPort | Callable[[Mapping[str, object]], EncodedState]


class EvaluationHarness:
    def __init__(
        self,
        simulator: EvaluationSimulator,
        encoder: Encoder | None = None,
        *,
        confidence: float = 0.95,
        bootstrap_samples: int = 1_000,
    ) -> None:
        self.simulator = simulator
        self.encoder = encoder
        self.confidence = confidence
        self.bootstrap_samples = bootstrap_samples

    def run(
        self,
        policy: EvaluationPolicy,
        episodes: Sequence[Episode],
        assumptions: FrozenAssumptions,
    ) -> EvaluationReport:
        if not episodes:
            raise ValueError("evaluation requires at least one episode")

        outcomes = tuple(
            self._run_episode(policy, episode, assumptions) for episode in episodes
        )
        metrics = metric_intervals(
            outcomes,
            confidence=self.confidence,
            bootstrap_samples=self.bootstrap_samples,
        )
        return EvaluationReport(
            policy_id=policy.policy_id,
            assumptions_hash=assumptions.content_hash,
            metrics=metrics,
            support_coverage=metrics["support_coverage"].point,
            numerical_failures=sum(row.numerical_failures for row in outcomes),
            seed_results=seed_results(outcomes),
            historical=self._historical(episodes),
        )

    def _run_episode(
        self,
        policy: EvaluationPolicy,
        episode: Episode,
        assumptions: FrozenAssumptions,
    ) -> EpisodeEvaluation:
        actions = []
        latencies: list[int] = []
        policy_failures = 0
        for decision in episode.decisions:
            if decision.action_mask is None or decision.action_bounds is None:
                raise ValueError("decision is missing action mask or bounds")
            state = self._encode(decision.state)
            output = policy.recommend(
                state,
                decision.action_mask,
                decision.action_bounds,
            )
            if output.policy_id != policy.policy_id:
                raise ValueError("policy output policy_id does not match evaluated policy")
            try:
                action = canonicalize_action(
                    output.action,
                    decision.action_bounds,
                    decision.action_mask,
                )
            except (TypeError, ValueError):
                if not decision.action_mask.no_op:
                    raise
                policy_failures += 1
                action = canonicalize_action(
                    RawHybridAction(ActionCategory.NO_OP, 0.0, 0.0, 0.0),
                    decision.action_bounds,
                    decision.action_mask,
                )
            actions.append(action)
            latencies.append(output.latency_ms)

        result = self.simulator.run_episode(episode, tuple(actions), assumptions)
        policy_latency = sum(latencies) / len(latencies) if latencies else 0.0
        return replace(
            result,
            numerical_failures=result.numerical_failures + policy_failures,
            latency_ms=result.latency_ms + policy_latency,
        )

    def _encode(self, state: Mapping[str, object]) -> EncodedState:
        if self.encoder is None:
            encoded = state.get("encoded_state")
            if not isinstance(encoded, EncodedState):
                raise ValueError("an encoder is required for raw decision state")
            return encoded
        if callable(self.encoder):
            return self.encoder(state)
        return self.encoder.encode(state)

    @staticmethod
    def _historical(episodes: Sequence[Episode]) -> bool:
        return all(
            provenance != "synthetic"
            for episode in episodes
            for decision in episode.decisions
            for provenance in decision.provenances
        )


__all__ = ["EvaluationHarness", "StateEncoderPort"]
