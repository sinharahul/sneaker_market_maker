"""Assembly and fail-closed persistence of complete offline transitions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from sneaker_market_maker.persistence.research_repository import AddResult, TransitionRepository
from sneaker_market_maker.research.contracts.action import HybridAction
from sneaker_market_maker.research.contracts.transition import (
    BehaviorPolicy,
    OfflineTransition,
    RewardRecord,
    StepEffects,
    TrainabilityError,
)
from sneaker_market_maker.research.episodes.events import DecisionPoint

__all__ = [
    "StepEffects",
    "TransitionAssembler",
    "TransitionInput",
    "TransitionLineage",
    "TransitionService",
]


@dataclass(frozen=True)
class TransitionLineage:
    state_schema_version: str
    action_schema_version: str
    reward_schema_version: str
    dataset_version: str
    scenario_version: str
    simulator_version: str
    gate_policy_version: str
    code_revision: str
    random_seed: int
    provenance_label: Literal["historical", "synthetic"]


@dataclass(frozen=True)
class TransitionInput:
    current: DecisionPoint
    next: DecisionPoint
    proposed_action: HybridAction
    post_gate_action: HybridAction
    behavior: BehaviorPolicy
    reward: RewardRecord
    effects: StepEffects
    lineage: TransitionLineage


def _canonical(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {str(key): _canonical(item) for key, item in value.items()}  # type: ignore[union-attr]
    if isinstance(value, tuple | list):
        return [_canonical(item) for item in value]
    return value


def _action_payload(action: HybridAction) -> dict[str, object]:
    return {
        "category": action.category.value,
        "allocation": action.allocation,
        "bid_offset_ticks": action.bid_offset_ticks,
        "ask_offset_ticks": action.ask_offset_ticks,
    }


def _payload(input: TransitionInput) -> dict[str, object]:
    reward = input.reward
    return {
        "episode_id": input.current.episode_id,
        "decision_index": input.current.index,
        "state": input.current.state,
        "proposed_action": _action_payload(input.proposed_action),
        "post_gate_action": _action_payload(input.post_gate_action),
        "behavior": vars(input.behavior),
        "reward": {
            "version": reward.version,
            "total": reward.total,
            "nav_delta": reward.nav_delta,
            "penalties": reward.penalties,
            "explanatory_costs": reward.explanatory_costs,
            "ledger_entry_ids": reward.ledger_entry_ids,
            "reconciled": reward.reconciled,
        },
        "next_state": input.next.state,
        "done": input.next.terminal_reason is not None,
        "terminal_reason": input.next.terminal_reason,
        "elapsed_seconds": input.next.elapsed_seconds,
        "discount": input.next.discount,
        "action_mask": vars(input.current.action_mask) if input.current.action_mask else None,
        "action_bounds": vars(input.current.action_bounds) if input.current.action_bounds else None,
        "effects": vars(input.effects),
        "lineage": vars(input.lineage),
        "source_record_ids": (
            *input.current.source_ids,
            *input.next.source_ids,
            *input.effects.all_ids,
        ),
    }


def _content_hash(input: TransitionInput) -> str:
    encoded = json.dumps(
        _canonical(_payload(input)),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class TransitionAssembler:
    def assemble(self, input: TransitionInput) -> OfflineTransition:
        current = input.current
        next_point = input.next
        if current.episode_id is None or next_point.episode_id is None:
            raise ValueError("decision point episode ID is required")
        if current.episode_id != next_point.episode_id:
            raise ValueError("decision points belong to different episodes")
        if next_point.index != current.index + 1:
            raise ValueError("decision points must be adjacent")
        if current.action_mask is None or current.action_bounds is None:
            raise ValueError("current decision action constraints are required")
        digest = _content_hash(input)
        identity = (
            f"{current.episode_id}:{current.index}:"
            f"{input.lineage.state_schema_version}:"
            f"{input.lineage.action_schema_version}:"
            f"{input.lineage.reward_schema_version}"
        )
        return OfflineTransition(
            transition_id=uuid5(NAMESPACE_URL, identity),
            episode_id=current.episode_id,
            decision_index=current.index,
            state=current.state,
            proposed_action=input.proposed_action,
            post_gate_action=input.post_gate_action,
            reward=input.reward,
            next_state=next_point.state,
            done=next_point.terminal_reason is not None,
            terminal_reason=next_point.terminal_reason,
            elapsed_seconds=next_point.elapsed_seconds,
            discount=next_point.discount,
            action_mask=current.action_mask,
            action_bounds=current.action_bounds,
            behavior=input.behavior,
            state_schema_version=input.lineage.state_schema_version,
            action_schema_version=input.lineage.action_schema_version,
            reward_schema_version=input.lineage.reward_schema_version,
            source_record_ids=(
                *current.source_ids,
                *next_point.source_ids,
                *input.effects.all_ids,
            ),
            provenance_label=input.lineage.provenance_label,
            dataset_version=input.lineage.dataset_version,
            scenario_version=input.lineage.scenario_version,
            simulator_version=input.lineage.simulator_version,
            gate_policy_version=input.lineage.gate_policy_version,
            code_revision=input.lineage.code_revision,
            random_seed=input.lineage.random_seed,
            content_hash=digest,
            effects=input.effects,
        )


class TransitionService:
    def __init__(
        self,
        repository: TransitionRepository,
        assembler: TransitionAssembler | None = None,
    ) -> None:
        self.repository = repository
        self.assembler = assembler or TransitionAssembler()

    def record(self, input: TransitionInput) -> AddResult:
        transition = self.assembler.assemble(input)
        try:
            transition.validate_trainable()
        except TrainabilityError as exc:
            transition = replace(
                transition,
                trainability_status="quarantined",
                non_trainable_reason=str(exc),
            )
        return self.repository.add_transition(transition)
