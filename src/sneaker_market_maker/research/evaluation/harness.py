"""Single policy evaluation path under frozen simulator assumptions."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol
from uuid import UUID

import torch

from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    ActionMask,
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


def _tensor_payload(value: torch.Tensor) -> dict[str, object]:
    detached = value.detach().cpu()
    return {
        "dtype": str(detached.dtype),
        "shape": list(detached.shape),
        "values": detached.tolist(),
    }


def _json_value(value: object) -> object:
    if isinstance(value, EncodedState):
        return {
            "values": _tensor_payload(value.values),
            "collection_mask": _tensor_payload(value.collection_mask),
            "missingness": _tensor_payload(value.missingness),
            "schema_version": value.schema_version,
            "scaler_version": value.scaler_version,
        }
    if isinstance(value, torch.Tensor):
        return _tensor_payload(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_json_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID | Decimal):
        return str(value)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"episode state contains unsupported value: {type(value).__name__}")


def _mask_payload(mask: ActionMask | None) -> object:
    if mask is None:
        return None
    return {"no_op": mask.no_op, "quote": mask.quote, "cancel": mask.cancel}


def _bounds_payload(bounds: ActionBounds | None) -> object:
    if bounds is None:
        return None
    return {
        "bid_low": bounds.bid_low,
        "bid_high": bounds.bid_high,
        "ask_low": bounds.ask_low,
        "ask_high": bounds.ask_high,
    }


def serialize_episode(episode: Episode) -> bytes:
    """Return complete deterministic bytes for evaluation input comparison."""
    payload = {
        "episode_id": str(episode.episode_id),
        "start": episode.start.isoformat(),
        "end": episode.end.isoformat(),
        "terminal_reason": episode.terminal_reason,
        "decisions": [
            {
                "index": decision.index,
                "simulation_time": decision.simulation_time.isoformat(),
                "elapsed_seconds": decision.elapsed_seconds,
                "reasons": [reason.value for reason in decision.reasons],
                "source_ids": list(decision.source_ids),
                "provenances": list(decision.provenances),
                "discount": decision.discount,
                "episode_id": (
                    str(decision.episode_id) if decision.episode_id is not None else None
                ),
                "state": _json_value(decision.state),
                "action_mask": _mask_payload(decision.action_mask),
                "action_bounds": _bounds_payload(decision.action_bounds),
                "terminal_reason": decision.terminal_reason,
            }
            for decision in episode.decisions
        ],
    }
    return json.dumps(
        payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _clone_encoded(state: EncodedState) -> EncodedState:
    return EncodedState(
        values=state.values.detach().clone(),
        collection_mask=state.collection_mask.detach().clone(),
        missingness=state.missingness.detach().clone(),
        schema_version=state.schema_version,
        scaler_version=state.scaler_version,
    )


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

        episode_snapshots = tuple(serialize_episode(episode) for episode in episodes)
        outcomes = tuple(
            self._run_episode(policy, episode, assumptions, snapshot)
            for episode, snapshot in zip(episodes, episode_snapshots, strict=True)
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
        episode_snapshot: bytes,
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

        if serialize_episode(episode) != episode_snapshot:
            raise RuntimeError("policy mutated frozen episode input")
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
            return _clone_encoded(encoded)
        if callable(self.encoder):
            return _clone_encoded(self.encoder(state))
        return _clone_encoded(self.encoder.encode(state))

    @staticmethod
    def _historical(episodes: Sequence[Episode]) -> bool:
        provenances = [
            provenance
            for episode in episodes
            for decision in episode.decisions
            for provenance in decision.provenances
        ]
        return bool(provenances) and all(
            provenance == "historical" for provenance in provenances
        )


__all__ = ["EvaluationHarness", "StateEncoderPort", "serialize_episode"]
