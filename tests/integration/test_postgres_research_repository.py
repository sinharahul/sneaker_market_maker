from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, inspect, select
from sqlalchemy.exc import IntegrityError

from alembic import command
from sneaker_market_maker.persistence.research_repository import (
    AddResult,
    ResearchRepository,
    TransitionConflict,
)
from sneaker_market_maker.persistence.research_tables import (
    behavior_policies,
    offline_transitions,
    reward_schemas,
)
from tests.integration.postgres_fixtures import DATABASE_URL, alembic_config
from tests.persistence.fixtures import evidence, seed_lineage, transition

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL is required"),
]


def test_migration_upgrade_downgrade_upgrade(engine) -> None:
    command.downgrade(alembic_config(), "base")
    assert "offline_transitions" not in inspect(engine).get_table_names()
    command.upgrade(alembic_config(), "head")
    assert "offline_transitions" in inspect(engine).get_table_names()


def test_foreign_key_rejection(session_factory) -> None:
    with pytest.raises(IntegrityError):
        ResearchRepository(session_factory).add_transition(transition())


def test_reward_failure_rolls_back_behavior_insert(session_factory, monkeypatch) -> None:
    item = transition()
    seed_lineage(session_factory, item)
    repository = ResearchRepository(session_factory)

    def fail_reward(*_args) -> None:
        raise RuntimeError("injected reward failure")

    monkeypatch.setattr(repository, "_insert_reward", fail_reward)
    with pytest.raises(RuntimeError, match="injected reward failure"):
        repository.add_transition(item)
    with session_factory() as session:
        assert session.scalar(select(behavior_policies.c.id)) is None
        assert session.scalar(select(offline_transitions.c.id)) is None


def test_idempotent_retry(session_factory) -> None:
    item = transition()
    seed_lineage(session_factory, item)
    repository = ResearchRepository(session_factory)
    assert repository.add_transition(item) is AddResult.CREATED
    assert repository.add_transition(item) is AddResult.EXISTING
    assert repository.get_transition(item.transition_id) == item


def test_correction_supersedes_without_mutating_original(session_factory) -> None:
    original = transition()
    seed_lineage(session_factory, original)
    repository = ResearchRepository(session_factory)
    assert repository.add_transition(original) is AddResult.CREATED
    correction = replace(
        original,
        transition_id=uuid4(),
        reward_schema_version="reward-v2",
        reward=replace(original.reward, version="reward-v2", total=Decimal("1.20")),
        content_hash="corrected-content-sha256",
    )
    with session_factory.begin() as session:
        session.execute(insert(reward_schemas).values(evidence("reward-v2")))

    assert (
        repository.add_correction(correction, supersedes_transition_id=original.transition_id)
        is AddResult.CREATED
    )
    with session_factory() as session:
        rows = session.execute(
            select(
                offline_transitions.c.id,
                offline_transitions.c.content_hash,
                offline_transitions.c.supersedes_transition_id,
            ).order_by(offline_transitions.c.id)
        ).mappings().all()
    by_id = {UUID(str(row["id"])): row for row in rows}
    assert by_id[original.transition_id]["content_hash"] == original.content_hash
    assert by_id[original.transition_id]["supersedes_transition_id"] is None
    assert by_id[correction.transition_id]["supersedes_transition_id"] == original.transition_id


def test_correction_retry_rejects_different_superseded_transition(session_factory) -> None:
    original = transition()
    other_original = replace(
        transition(),
        state_schema_version="state-other-v1",
        action_schema_version="action-other-v1",
        reward_schema_version="reward-other-v1",
        reward=replace(transition().reward, version="reward-other-v1"),
    )
    seed_lineage(session_factory, original)
    seed_lineage(session_factory, other_original)
    repository = ResearchRepository(session_factory)
    assert repository.add_transition(original) is AddResult.CREATED
    assert repository.add_transition(other_original) is AddResult.CREATED
    correction = replace(
        original,
        transition_id=uuid4(),
        reward_schema_version="reward-v2",
        reward=replace(original.reward, version="reward-v2", total=Decimal("1.20")),
        content_hash="corrected-content-sha256",
    )
    with session_factory.begin() as session:
        session.execute(insert(reward_schemas).values(evidence("reward-v2")))
    assert (
        repository.add_correction(correction, supersedes_transition_id=original.transition_id)
        is AddResult.CREATED
    )
    assert (
        repository.add_correction(correction, supersedes_transition_id=original.transition_id)
        is AddResult.EXISTING
    )

    with pytest.raises(TransitionConflict, match="different transition"):
        repository.add_correction(
            correction,
            supersedes_transition_id=other_original.transition_id,
        )
