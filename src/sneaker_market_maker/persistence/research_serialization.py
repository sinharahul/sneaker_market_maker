"""Serialization helpers for immutable research transition rows."""

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from uuid import UUID

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


def action_payload(action: HybridAction) -> dict[str, object]:
    return {
        "category": action.category.value,
        "allocation": action.allocation,
        "bid_offset_ticks": action.bid_offset_ticks,
        "ask_offset_ticks": action.ask_offset_ticks,
    }


def reward_payload(transition: OfflineTransition) -> dict[str, object]:
    reward = transition.reward
    return {
        "version": reward.version,
        "total": str(reward.total),
        "nav_delta": str(reward.nav_delta),
        "penalties": {key: str(value) for key, value in reward.penalties.items()},
        "explanatory_costs": {
            key: str(value) for key, value in reward.explanatory_costs.items()
        },
        "ledger_entry_ids": list(reward.ledger_entry_ids),
        "reconciled": reward.reconciled,
    }


def policy_values(transition: OfflineTransition) -> dict[str, object]:
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
        "id": transition.transition_id,
        **payload,
        "content_hash": digest,
        "provenance": {"transition_id": str(transition.transition_id)},
    }


def transition_values(
    transition: OfflineTransition,
    supersedes_transition_id: UUID | None = None,
) -> dict[str, object]:
    reward = transition.reward
    return {
        "id": transition.transition_id,
        "episode_id": transition.episode_id,
        "decision_index": transition.decision_index,
        "behavior_policy_id": transition.transition_id,
        "supersedes_transition_id": supersedes_transition_id,
        "state": dict(transition.state),
        "proposed_action": action_payload(transition.proposed_action),
        "post_gate_action": action_payload(transition.post_gate_action),
        "reward": reward_payload(transition),
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


def transition_from_row(row: Mapping[str, object]) -> OfflineTransition:
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
            penalties={
                key: Decimal(str(value))
                for key, value in reward["penalties"].items()  # type: ignore[union-attr]
            },
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
