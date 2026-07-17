"""Bellman-ready transition, provenance, and propensity contracts."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionMask,
    HybridAction,
)


class TrainabilityError(ValueError):
    """Raised when a transition must be quarantined from training."""


@dataclass(frozen=True)
class StepEffects:
    order_ids: tuple[str, ...]
    fill_ids: tuple[str, ...]
    fee_ledger_ids: tuple[str, ...]
    inventory_transition_ids: tuple[str, ...]
    logistics_transition_ids: tuple[str, ...]
    settlement_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for value in self.all_ids:
            if not value or not value.strip():
                raise ValueError("effect IDs must be nonempty")
        if len(self.all_ids) != len(set(self.all_ids)):
            raise ValueError("effect IDs must be unique")

    @property
    def all_ids(self) -> tuple[str, ...]:
        return (
            *self.order_ids,
            *self.fill_ids,
            *self.fee_ledger_ids,
            *self.inventory_transition_ids,
            *self.logistics_transition_ids,
            *self.settlement_ids,
        )


@dataclass(frozen=True)
class BehaviorPolicy:
    version: str
    collection_mode: str
    categorical_propensity: float | None
    active_continuous_log_density: float | None
    joint_log_propensity: float | None
    deterministic: bool
    support_method: str
    support_version: str
    missingness_reason: str | None

    def __post_init__(self) -> None:
        values = (
            self.categorical_propensity,
            self.active_continuous_log_density,
            self.joint_log_propensity,
        )
        if self.deterministic:
            if any(value is not None for value in values):
                raise ValueError("deterministic propensity values must be absent")
            if not self.missingness_reason or not self.missingness_reason.strip():
                raise ValueError("deterministic policy requires a missingness reason")
            return

        if any(value is None for value in values):
            if (
                all(value is None for value in values)
                and self.missingness_reason
                and self.missingness_reason.strip()
            ):
                return
            raise ValueError("stochastic propensity values are required together")
        categorical = self.categorical_propensity
        if (
            categorical is None
            or not math.isfinite(categorical)
            or not 0.0 < categorical <= 1.0
        ):
            raise ValueError("categorical propensity must be finite and in (0, 1]")
        if not all(math.isfinite(value) for value in values if value is not None):
            raise ValueError("propensity log densities must be finite")


@dataclass(frozen=True)
class RewardRecord:
    version: str
    total: Decimal
    nav_delta: Decimal
    penalties: Mapping[str, Decimal]
    explanatory_costs: Mapping[str, Decimal]
    ledger_entry_ids: tuple[str, ...]
    reconciled: bool

    def __post_init__(self) -> None:
        money = (self.total, self.nav_delta, *self.penalties.values())
        money += tuple(self.explanatory_costs.values())
        if not all(isinstance(value, Decimal) for value in money):
            raise TypeError("reward money values must be Decimal")
        if not all(value.is_finite() for value in money):
            raise ValueError("reward money values must be finite")
        object.__setattr__(self, "penalties", MappingProxyType(dict(self.penalties)))
        object.__setattr__(
            self,
            "explanatory_costs",
            MappingProxyType(dict(self.explanatory_costs)),
        )
        object.__setattr__(self, "ledger_entry_ids", tuple(self.ledger_entry_ids))


@dataclass(frozen=True)
class OfflineTransition:
    transition_id: UUID
    episode_id: UUID
    decision_index: int
    state: Mapping[str, object]
    proposed_action: HybridAction
    post_gate_action: HybridAction
    reward: RewardRecord
    next_state: Mapping[str, object]
    done: bool
    terminal_reason: str | None
    elapsed_seconds: int
    discount: float
    action_mask: ActionMask
    action_bounds: ActionBounds
    behavior: BehaviorPolicy
    state_schema_version: str
    action_schema_version: str
    reward_schema_version: str
    source_record_ids: tuple[str, ...]
    provenance_label: Literal["historical", "synthetic"]
    dataset_version: str
    scenario_version: str
    simulator_version: str
    gate_policy_version: str
    code_revision: str
    random_seed: int
    content_hash: str
    effects: StepEffects
    trainability_status: Literal["trainable", "quarantined"]
    non_trainable_reason: str | None

    def __post_init__(self) -> None:
        if self.trainability_status not in ("trainable", "quarantined"):
            raise ValueError("invalid trainability status")
        if self.trainability_status == "trainable" and self.non_trainable_reason is not None:
            raise ValueError("trainable transition cannot have a quarantine reason")
        if self.trainability_status == "quarantined" and (
            not self.non_trainable_reason or not self.non_trainable_reason.strip()
        ):
            raise ValueError("quarantined transition requires a reason")
        object.__setattr__(self, "state", MappingProxyType(dict(self.state)))
        object.__setattr__(self, "next_state", MappingProxyType(dict(self.next_state)))
        object.__setattr__(self, "source_record_ids", tuple(self.source_record_ids))

    def validate_trainable(self) -> None:
        if not self.reward.reconciled:
            raise TrainabilityError("reward is not reconciled")
        if not self.next_state:
            raise TrainabilityError("next state is required")
        if self.done != (self.terminal_reason is not None):
            raise TrainabilityError("terminal reason must match done")
        schema_versions = (
            self.state_schema_version,
            self.action_schema_version,
            self.reward_schema_version,
        )
        if any(not version or not version.strip() for version in schema_versions):
            raise TrainabilityError("schema versions are required")
        lineage_versions = (
            self.dataset_version,
            self.scenario_version,
            self.simulator_version,
            self.gate_policy_version,
            self.code_revision,
        )
        if any(not version or not version.strip() for version in lineage_versions):
            raise TrainabilityError("transition lineage is incomplete")
        if (
            not self.source_record_ids
            or any(not record_id or not record_id.strip() for record_id in self.source_record_ids)
            or not self.content_hash
            or not self.content_hash.strip()
        ):
            raise TrainabilityError("provenance is incomplete")
        propensities = (
            self.behavior.categorical_propensity,
            self.behavior.active_continuous_log_density,
            self.behavior.joint_log_propensity,
        )
        if not self.behavior.deterministic and any(value is None for value in propensities):
            raise TrainabilityError("behavior propensity is missing")
        if not self.effects.logistics_transition_ids:
            raise TrainabilityError("logistics outcomes are missing")
