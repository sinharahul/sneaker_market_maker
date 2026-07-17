"""Fail-closed repositories for immutable offline transitions."""

from __future__ import annotations

import json
from enum import Enum
from typing import Protocol
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.orm import Session, sessionmaker

from sneaker_market_maker.persistence.research_serialization import (
    policy_values,
    reward_payload,
    transition_from_row,
    transition_values,
)
from sneaker_market_maker.persistence.research_tables import (
    behavior_policies,
    offline_transitions,
)
from sneaker_market_maker.research.contracts.transition import OfflineTransition


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
        self.session_factory = session_factory

    def add_transition(self, transition: OfflineTransition) -> AddResult:
        identity = _identity(transition)
        with self.session_factory() as session, session.begin():
            existing = self._get_by_identity(session, identity)
            if existing is not None:
                if existing.content_hash != transition.content_hash:
                    raise TransitionConflict("transition identity has different content")
                return AddResult.EXISTING
            self._insert_behavior(session, transition)
            self._insert_reward(session, transition)
            self._insert_transition(session, transition)
        return AddResult.CREATED

    def add_correction(
        self,
        transition: OfflineTransition,
        *,
        supersedes_transition_id: UUID,
    ) -> AddResult:
        with self.session_factory() as session, session.begin():
            original = self._get_by_id(session, supersedes_transition_id)
            if original is None:
                raise TransitionConflict("superseded transition does not exist")
            existing = self._get_by_identity(session, _identity(transition))
            if existing is not None:
                if existing.content_hash != transition.content_hash:
                    raise TransitionConflict("transition identity has different content")
                persisted_supersedes_id = self._get_supersedes_id(
                    session,
                    existing.transition_id,
                )
                if persisted_supersedes_id != supersedes_transition_id:
                    raise TransitionConflict(
                        "correction identity supersedes a different transition"
                    )
                return AddResult.EXISTING
            self._insert_behavior(session, transition)
            self._insert_reward(session, transition)
            self._insert_transition(session, transition, supersedes_transition_id)
        return AddResult.CREATED

    def get_transition(self, transition_id: UUID) -> OfflineTransition | None:
        with self.session_factory() as session:
            return self._get_by_id(session, transition_id)

    def _get_by_id(self, session: Session, transition_id: UUID) -> OfflineTransition | None:
        row = session.execute(
            _joined_select().where(offline_transitions.c.id == transition_id)
        ).mappings().first()
        return None if row is None else transition_from_row(row)

    def _get_by_identity(
        self,
        session: Session,
        identity: Identity,
    ) -> OfflineTransition | None:
        row = session.execute(_identity_query(identity)).mappings().first()
        return None if row is None else transition_from_row(row)

    def _get_supersedes_id(self, session: Session, transition_id: UUID) -> UUID | None:
        return session.scalar(
            select(offline_transitions.c.supersedes_transition_id).where(
                offline_transitions.c.id == transition_id
            )
        )

    def _insert_behavior(self, session: Session, transition: OfflineTransition) -> None:
        session.execute(insert(behavior_policies).values(policy_values(transition)))

    def _insert_reward(self, _session: Session, transition: OfflineTransition) -> None:
        json.dumps(reward_payload(transition), sort_keys=True)

    def _insert_transition(
        self,
        session: Session,
        transition: OfflineTransition,
        supersedes_transition_id: UUID | None = None,
    ) -> OfflineTransition:
        row = session.execute(
            insert(offline_transitions)
            .values(transition_values(transition, supersedes_transition_id))
            .returning(*offline_transitions.c)
        ).mappings().one()
        return transition_from_row({**row, **_behavior_labels(transition)})


def _joined_select():
    return select(
        offline_transitions,
        *(
            column.label(f"behavior_{column.name}")
            for column in behavior_policies.c
            if column.name != "id"
        ),
    ).join(behavior_policies)


def _identity_query(identity: Identity):
    return _joined_select().where(
        (offline_transitions.c.episode_id == identity[0])
        & (offline_transitions.c.decision_index == identity[1])
        & (offline_transitions.c.state_schema_version == identity[2])
        & (offline_transitions.c.action_schema_version == identity[3])
        & (offline_transitions.c.reward_schema_version == identity[4])
    )


def _behavior_labels(transition: OfflineTransition) -> dict[str, object]:
    policy = transition.behavior
    return {
        "behavior_version": policy.version,
        "behavior_collection_mode": policy.collection_mode,
        "behavior_categorical_propensity": policy.categorical_propensity,
        "behavior_active_continuous_log_density": policy.active_continuous_log_density,
        "behavior_joint_log_propensity": policy.joint_log_propensity,
        "behavior_deterministic": policy.deterministic,
        "behavior_support_method": policy.support_method,
        "behavior_support_version": policy.support_version,
        "behavior_missingness_reason": policy.missingness_reason,
    }
