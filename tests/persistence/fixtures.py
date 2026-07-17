"""Shared transition and lineage fixtures for persistence tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import insert
from sqlalchemy.orm import sessionmaker

from sneaker_market_maker.persistence.research_tables import (
    action_schemas,
    decision_points,
    episode_manifests,
    mdp_state_schemas,
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


def evidence(version: str) -> dict[str, object]:
    return {
        "id": uuid4(),
        "version": version,
        "content_hash": f"{version}-hash",
        "provenance": {"fixture": True},
        "payload": {"version": version},
    }


def transition() -> OfflineTransition:
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


def seed_lineage(
    session_factory: sessionmaker,
    item: OfflineTransition,
) -> None:
    now = datetime.now(UTC)
    with session_factory.begin() as session:
        for table, version in (
            (mdp_state_schemas, item.state_schema_version),
            (action_schemas, item.action_schema_version),
            (reward_schemas, item.reward_schema_version),
        ):
            session.execute(insert(table).values(evidence(version)))
        session.execute(
            insert(episode_manifests).values(
                id=item.episode_id,
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
                episode_id=item.episode_id,
                decision_index=item.decision_index,
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
