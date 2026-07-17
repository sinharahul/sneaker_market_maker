import os
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, inspect, select
from sqlalchemy.exc import IntegrityError

from alembic import command
from alembic.config import Config
from sneaker_market_maker.persistence.database import (
    create_database_engine,
    create_session_factory,
)
from sneaker_market_maker.persistence.research_repository import (
    AddResult,
    ResearchRepository,
    TransitionConflict,
)
from sneaker_market_maker.persistence.research_tables import (
    action_schemas,
    behavior_policies,
    decision_points,
    episode_manifests,
    mdp_state_schemas,
    offline_transitions,
    reward_schemas,
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
    StepEffects,
)

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL is required"),
]
ROOT = Path(__file__).parents[2]


def _alembic_config() -> Config:
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    return config


@pytest.fixture(scope="module")
def engine():
    database_engine = create_database_engine(DATABASE_URL)
    command.upgrade(_alembic_config(), "head")
    yield database_engine
    database_engine.dispose()


@pytest.fixture()
def session_factory(engine):
    with engine.begin() as connection:
        for table in (
            offline_transitions,
            behavior_policies,
            decision_points,
            episode_manifests,
            reward_schemas,
            action_schemas,
            mdp_state_schemas,
        ):
            connection.execute(delete(table))
    return create_session_factory(engine)


def _evidence(version: str) -> dict[str, object]:
    return {
        "id": uuid4(),
        "version": version,
        "content_hash": f"{version}-hash",
        "provenance": {"fixture": True},
        "payload": {"version": version},
    }


def _transition() -> OfflineTransition:
    action = HybridAction(ActionCategory.QUOTE, 0.5, -1, 1)
    return OfflineTransition(
        transition_id=uuid4(),
        episode_id=uuid4(),
        decision_index=0,
        state={"inventory": 0.0},
        proposed_action=action,
        post_gate_action=action,
        reward=RewardRecord(
            version="reward-v1",
            total=Decimal("1.25"),
            nav_delta=Decimal("1.50"),
            penalties={"inventory": Decimal("0.25")},
            explanatory_costs={"fees": Decimal("0.50")},
            ledger_entry_ids=("ledger-1",),
            reconciled=True,
        ),
        next_state={"inventory": 0.5},
        done=False,
        terminal_reason=None,
        elapsed_seconds=60,
        discount=0.99,
        action_mask=ActionMask(True, True, True),
        action_bounds=ActionBounds(-5, 5, -5, 5),
        behavior=BehaviorPolicy(
            version="behavior-v1",
            collection_mode="stochastic",
            categorical_propensity=0.5,
            active_continuous_log_density=-0.25,
            joint_log_propensity=-0.9431471805599453,
            deterministic=False,
            support_method="bounded-gaussian",
            support_version="support-v1",
            missingness_reason=None,
        ),
        state_schema_version="state-v1",
        action_schema_version="action-v1",
        reward_schema_version="reward-v1",
        source_record_ids=("source-sha256",),
        provenance_label="historical",
        dataset_version="dataset-v1",
        scenario_version="scenario-v1",
        simulator_version="simulator-v1",
        gate_policy_version="gate-v1",
        code_revision="abc123",
        random_seed=7,
        content_hash="content-sha256",
        effects=StepEffects(
            order_ids=("order-1",),
            fill_ids=("fill-1",),
            fee_ledger_ids=("fee-1",),
            inventory_transition_ids=("inventory-1",),
            logistics_transition_ids=("logistics-1",),
            settlement_ids=(),
        ),
        trainability_status="trainable",
        non_trainable_reason=None,
    )


def _seed_lineage(session_factory, transition: OfflineTransition) -> None:
    now = datetime.now(UTC)
    with session_factory.begin() as session:
        for table, version in (
            (mdp_state_schemas, transition.state_schema_version),
            (action_schemas, transition.action_schema_version),
            (reward_schemas, transition.reward_schema_version),
        ):
            session.execute(insert(table).values(_evidence(version)))
        session.execute(
            insert(episode_manifests).values(
                id=transition.episode_id,
                dataset_version="dataset-v1",
                scenario_version="scenario-v1",
                simulator_version="simulator-v1",
                source_window={},
                split="train",
                fold="fold-1",
                random_seed=7,
                checksum="episode-hash",
                provenance_label="historical",
                version="episode-v1",
                content_hash="episode-hash",
                provenance={"fixture": True},
            )
        )
        session.execute(
            insert(decision_points).values(
                id=uuid4(),
                episode_id=transition.episode_id,
                decision_index=transition.decision_index,
                event_reason="BOOK",
                maintenance_coalesced=False,
                source_time=now,
                simulation_time=now,
                wall_time=now,
                elapsed_seconds=60,
                version="decision-v1",
                content_hash="decision-hash",
                provenance={"fixture": True},
            )
        )


def test_migration_upgrade_downgrade_upgrade(engine) -> None:
    command.downgrade(_alembic_config(), "base")
    assert "offline_transitions" not in inspect(engine).get_table_names()
    command.upgrade(_alembic_config(), "head")
    assert "offline_transitions" in inspect(engine).get_table_names()


def test_foreign_key_rejection(session_factory) -> None:
    with pytest.raises(IntegrityError):
        ResearchRepository(session_factory).add_transition(_transition())


def test_reward_failure_rolls_back_behavior_insert(session_factory, monkeypatch) -> None:
    item = _transition()
    _seed_lineage(session_factory, item)
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
    item = _transition()
    _seed_lineage(session_factory, item)
    repository = ResearchRepository(session_factory)
    assert repository.add_transition(item) is AddResult.CREATED
    assert repository.add_transition(item) is AddResult.EXISTING
    assert repository.get_transition(item.transition_id) == item


def test_correction_supersedes_without_mutating_original(session_factory) -> None:
    original = _transition()
    _seed_lineage(session_factory, original)
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
        session.execute(insert(reward_schemas).values(_evidence("reward-v2")))

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
    original = _transition()
    other_original = replace(
        _transition(),
        state_schema_version="state-other-v1",
        action_schema_version="action-other-v1",
        reward_schema_version="reward-other-v1",
        reward=replace(_transition().reward, version="reward-other-v1"),
    )
    _seed_lineage(session_factory, original)
    _seed_lineage(session_factory, other_original)
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
        session.execute(insert(reward_schemas).values(_evidence("reward-v2")))
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
