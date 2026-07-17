"""Fail-closed repositories for immutable offline transitions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from sneaker_market_maker.persistence.research_tables import (
    behavior_policies,
    offline_transitions,
)
from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    ActionMask,
    HybridAction,
)
from sneaker_market_maker.research.contracts.transition import (
    BehaviorPolicy,
    OfflineTransition,
    RewardRecord,
)


class AddResult(str, Enum):
    CREATED = "created"
    EXISTING = "existing"


class TransitionConflict(RuntimeError):
    pass


class TransitionRepository(Protocol):
    def add_transition(self, transition: OfflineTransition) -> AddResult:
        raise NotImplementedError

    def get_transition(self, transition_id: UUID) -> OfflineTransition | None:
        raise NotImplementedError


Identity = tuple[UUID, int, str, str, str]


def _identity(transition: OfflineTransition) -> Identity:
    return (
        transition.episode_id,
        transition.decision_index,
        transition.state_schema_version,
        transition.action_schema_version,
        transition.reward_schema_version,
    )


def _resolve_existing(existing: OfflineTransition, incoming: OfflineTransition) -> AddResult:
    if _identity(existing) != _identity(incoming):
        raise TransitionConflict("transition id is bound to a different immutable identity")
    if existing.content_hash != incoming.content_hash:
        raise TransitionConflict("immutable transition identity has different content hash")
    return AddResult.EXISTING


class InMemoryResearchRepository:
    def __init__(self) -> None:
        self._by_id: dict[UUID, OfflineTransition] = {}
        self._by_identity: dict[Identity, OfflineTransition] = {}

    def add_transition(self, transition: OfflineTransition) -> AddResult:
        by_id = self._by_id.get(transition.transition_id)
        by_identity = self._by_identity.get(_identity(transition))
        if by_id is not None:
            return _resolve_existing(by_id, transition)
        if by_identity is not None:
            return _resolve_existing(by_identity, transition)
        self._by_id[transition.transition_id] = transition
        self._by_identity[_identity(transition)] = transition
        return AddResult.CREATED

    def get_transition(self, transition_id: UUID) -> OfflineTransition | None:
        return self._by_id.get(transition_id)


class ResearchRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add_transition(self, transition: OfflineTransition) -> AddResult:
        try:
            with self._session_factory.begin() as session:
                row = session.execute(_existing_query(transition)).mappings().first()
                if row is not None:
                    return _resolve_existing(_transition_from_row(row), transition)
                policy_id = uuid4()
                session.execute(
                    insert(behavior_policies).values(_policy_values(policy_id, transition))
                )
                session.execute(
                    insert(offline_transitions).values(_transition_values(policy_id, transition))
                )
        except IntegrityError:
            return self._resolve_after_race(transition)
        return AddResult.CREATED

    def _resolve_after_race(self, transition: OfflineTransition) -> AddResult:
        with self._session_factory() as session:
            row = session.execute(_existing_query(transition)).mappings().first()
        if row is None:
            raise TransitionConflict("transition insert conflicted without an immutable match")
        return _resolve_existing(_transition_from_row(row), transition)

    def get_transition(self, transition_id: UUID) -> OfflineTransition | None:
        query = _joined_select().where(offline_transitions.c.id == transition_id)
        with self._session_factory() as session:
            row = session.execute(query).mappings().first()
        return None if row is None else _transition_from_row(row)


def _joined_select():
    return select(
        offline_transitions,
        *(
            column.label(f"behavior_{column.name}")
            for column in behavior_policies.c
            if column.name != "id"
        ),
    ).join(behavior_policies)


def _existing_query(transition: OfflineTransition):
    identity = _identity(transition)
    return _joined_select().where(
        or_(
            offline_transitions.c.id == transition.transition_id,
            (
                (offline_transitions.c.episode_id == identity[0])
                & (offline_transitions.c.decision_index == identity[1])
                & (offline_transitions.c.state_schema_version == identity[2])
                & (offline_transitions.c.action_schema_version == identity[3])
                & (offline_transitions.c.reward_schema_version == identity[4])
            ),
        )
    )


def _action_payload(action: HybridAction) -> dict[str, object]:
    return {
        "category": action.category.value,
        "allocation": action.allocation,
        "bid_offset_ticks": action.bid_offset_ticks,
        "ask_offset_ticks": action.ask_offset_ticks,
    }


def _money_payload(values: Mapping[str, Decimal]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items()}


def _policy_values(policy_id: UUID, transition: OfflineTransition) -> dict[str, object]:
    policy = transition.behavior
    payload = {
        "version": policy.version,
        "collection_mode": policy.collection_mode,
        "categorical_propensity": policy.categorical_propensity,
        "active_continuous_log_density": policy.active_continuous_log_density,
        "joint_log_propensity": policy.joint_log_propensity,
        "deterministic": policy.deterministic,
        "support_method": policy.support_method,
        "support_version": policy.support_version,
        "missingness_reason": policy.missingness_reason,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return {
        "id": policy_id,
        **payload,
        "content_hash": digest,
        "provenance": {"transition_id": str(transition.transition_id)},
    }


def _transition_values(policy_id: UUID, transition: OfflineTransition) -> dict[str, object]:
    reward = transition.reward
    return {
        "id": transition.transition_id,
        "episode_id": transition.episode_id,
        "decision_index": transition.decision_index,
        "behavior_policy_id": policy_id,
        "state": dict(transition.state),
        "proposed_action": _action_payload(transition.proposed_action),
        "post_gate_action": _action_payload(transition.post_gate_action),
        "reward": {
            "version": reward.version,
            "total": str(reward.total),
            "nav_delta": str(reward.nav_delta),
            "penalties": _money_payload(reward.penalties),
            "explanatory_costs": _money_payload(reward.explanatory_costs),
            "ledger_entry_ids": list(reward.ledger_entry_ids),
            "reconciled": reward.reconciled,
        },
        "reward_total": reward.total,
        "nav_delta": reward.nav_delta,
        "next_state": dict(transition.next_state),
        "done": transition.done,
        "terminal_reason": transition.terminal_reason,
        "elapsed_seconds": transition.elapsed_seconds,
        "discount": transition.discount,
        "action_mask": vars(transition.action_mask),
        "action_bounds": vars(transition.action_bounds),
        "state_schema_version": transition.state_schema_version,
        "action_schema_version": transition.action_schema_version,
        "reward_schema_version": transition.reward_schema_version,
        "source_record_ids": list(transition.source_record_ids),
        "provenance_label": transition.provenance_label,
        "dataset_version": transition.dataset_version,
        "scenario_version": transition.scenario_version,
        "simulator_version": transition.simulator_version,
        "gate_policy_version": transition.gate_policy_version,
        "code_revision": transition.code_revision,
        "random_seed": transition.random_seed,
        "content_hash": transition.content_hash,
    }


def _action_from_payload(payload: Mapping[str, object]) -> HybridAction:
    return HybridAction(
        ActionCategory(str(payload["category"])),
        float(payload["allocation"]),
        int(payload["bid_offset_ticks"]),
        int(payload["ask_offset_ticks"]),
    )


def _transition_from_row(row: Mapping[str, object]) -> OfflineTransition:
    reward = row["reward"]
    assert isinstance(reward, Mapping)
    return OfflineTransition(
        transition_id=UUID(str(row["id"])),
        episode_id=UUID(str(row["episode_id"])),
        decision_index=int(row["decision_index"]),
        state=dict(row["state"]),  # type: ignore[arg-type]
        proposed_action=_action_from_payload(row["proposed_action"]),  # type: ignore[arg-type]
        post_gate_action=_action_from_payload(row["post_gate_action"]),  # type: ignore[arg-type]
        reward=RewardRecord(
            version=str(reward["version"]),
            total=Decimal(str(reward["total"])),
            nav_delta=Decimal(str(reward["nav_delta"])),
            penalties={key: Decimal(str(value)) for key, value in reward["penalties"].items()},  # type: ignore[union-attr]
            explanatory_costs={
                key: Decimal(str(value))
                for key, value in reward["explanatory_costs"].items()  # type: ignore[union-attr]
            },
            ledger_entry_ids=tuple(reward["ledger_entry_ids"]),  # type: ignore[arg-type]
            reconciled=bool(reward["reconciled"]),
        ),
        next_state=dict(row["next_state"]),  # type: ignore[arg-type]
        done=bool(row["done"]),
        terminal_reason=None if row["terminal_reason"] is None else str(row["terminal_reason"]),
        elapsed_seconds=int(row["elapsed_seconds"]),
        discount=float(row["discount"]),
        action_mask=ActionMask(**row["action_mask"]),  # type: ignore[arg-type]
        action_bounds=ActionBounds(**row["action_bounds"]),  # type: ignore[arg-type]
        behavior=BehaviorPolicy(
            version=str(row["behavior_version"]),
            collection_mode=str(row["behavior_collection_mode"]),
            categorical_propensity=row["behavior_categorical_propensity"],  # type: ignore[arg-type]
            active_continuous_log_density=row["behavior_active_continuous_log_density"],  # type: ignore[arg-type]
            joint_log_propensity=row["behavior_joint_log_propensity"],  # type: ignore[arg-type]
            deterministic=bool(row["behavior_deterministic"]),
            support_method=str(row["behavior_support_method"]),
            support_version=str(row["behavior_support_version"]),
            missingness_reason=(
                None
                if row["behavior_missingness_reason"] is None
                else str(row["behavior_missingness_reason"])
            ),
        ),
        state_schema_version=str(row["state_schema_version"]),
        action_schema_version=str(row["action_schema_version"]),
        reward_schema_version=str(row["reward_schema_version"]),
        source_record_ids=tuple(row["source_record_ids"]),  # type: ignore[arg-type]
        provenance_label=str(row["provenance_label"]),  # type: ignore[arg-type]
        dataset_version=str(row["dataset_version"]),
        scenario_version=str(row["scenario_version"]),
        simulator_version=str(row["simulator_version"]),
        gate_policy_version=str(row["gate_policy_version"]),
        code_revision=str(row["code_revision"]),
        random_seed=int(row["random_seed"]),
        content_hash=str(row["content_hash"]),
    )
