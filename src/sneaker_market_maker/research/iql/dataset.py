"""Fail-closed conversion of immutable replay rows into IQL tensors."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Protocol

import torch
from torch import Tensor

from sneaker_market_maker.research.contracts.action import ActionCategory
from sneaker_market_maker.research.contracts.transition import (
    OfflineTransition,
    TrainabilityError,
)
from sneaker_market_maker.research.iql.trainer import TransitionBatch


class ManifestTransitionRepository(Protocol):
    """Minimal Task 18 boundary; the run registry is owned by Task 19."""

    def transitions_for_manifest(
        self, manifest_id: str
    ) -> Sequence[OfflineTransition]: ...


@dataclass(frozen=True)
class ExclusionCounts:
    reasons: Mapping[str, int]
    accepted: int
    rejected: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", MappingProxyType(dict(self.reasons)))


@dataclass(frozen=True)
class TransitionDataset:
    state: Tensor
    action: Tensor
    reward: Tensor
    next_state: Tensor
    done: Tensor
    discount: Tensor
    category_mask: Tensor
    bounds: Tensor
    logged_category: Tensor
    active_dimensions: Tensor

    def __len__(self) -> int:
        return self.state.shape[0]

    def as_batch(self) -> TransitionBatch:
        return TransitionBatch(**self.__dict__)

    @classmethod
    def from_repository(
        cls,
        repository: ManifestTransitionRepository,
        manifest_id: str,
    ) -> tuple[TransitionDataset, ExclusionCounts]:
        if not manifest_id.strip():
            raise ValueError("manifest_id must be nonempty")
        rows = repository.transitions_for_manifest(manifest_id)
        accepted: list[OfflineTransition] = []
        reasons: Counter[str] = Counter()
        for row in rows:
            if not isinstance(row, OfflineTransition):
                raise TypeError("repository returned a non-transition row")
            if row.trainability_status == "quarantined":
                reasons[row.non_trainable_reason or "quarantined"] += 1
                continue
            try:
                row.validate_trainable()
            except TrainabilityError as error:
                reasons[str(error)] += 1
                continue
            accepted.append(row)

        dataset = cls._from_rows(accepted)
        counts = ExclusionCounts(
            reasons=reasons,
            accepted=len(accepted),
            rejected=sum(reasons.values()),
        )
        return dataset, counts

    @classmethod
    def _from_rows(cls, rows: Sequence[OfflineTransition]) -> TransitionDataset:
        if not rows:
            return cls(
                state=torch.empty((0, 0)),
                action=torch.empty((0, 3)),
                reward=torch.empty(0),
                next_state=torch.empty((0, 0)),
                done=torch.empty(0, dtype=torch.bool),
                discount=torch.empty(0),
                category_mask=torch.empty((0, 3), dtype=torch.bool),
                bounds=torch.empty((0, 2, 2)),
                logged_category=torch.empty(0, dtype=torch.long),
                active_dimensions=torch.empty((0, 3), dtype=torch.bool),
            )

        state_keys = tuple(sorted(rows[0].state))
        if not state_keys:
            raise ValueError("state cannot be empty")
        states: list[list[float]] = []
        next_states: list[list[float]] = []
        actions: list[list[float]] = []
        rewards: list[float] = []
        discounts: list[float] = []
        masks: list[list[bool]] = []
        bounds: list[list[list[float]]] = []
        categories: list[int] = []
        active_dimensions: list[list[bool]] = []

        category_index = {
            ActionCategory.NO_OP: 0,
            ActionCategory.QUOTE: 1,
            ActionCategory.CANCEL: 2,
        }
        for row in rows:
            if tuple(sorted(row.state)) != state_keys or tuple(
                sorted(row.next_state)
            ) != state_keys:
                raise ValueError("state schema mismatch")
            states.append(_state_vector(row.state, state_keys))
            next_states.append(_state_vector(row.next_state, state_keys))
            action = row.post_gate_action
            actions.append(
                [
                    _finite_float(action.allocation, "action"),
                    _finite_float(action.bid_offset_ticks, "action"),
                    _finite_float(action.ask_offset_ticks, "action"),
                ]
            )
            rewards.append(_finite_float(row.reward.total, "reward"))
            discounts.append(_finite_float(row.discount, "discount"))
            mask = row.action_mask
            masks.append([mask.no_op, mask.quote, mask.cancel])
            if not any(masks[-1]):
                raise ValueError("category mask is fully masked")
            category = category_index[action.category]
            if not masks[-1][category]:
                raise ValueError("logged category is masked")
            categories.append(category)
            action_bounds = row.action_bounds
            if (
                action_bounds.bid_low > action_bounds.bid_high
                or action_bounds.ask_low > action_bounds.ask_high
            ):
                raise ValueError("action bounds are invalid")
            bounds.append(
                [
                    [float(action_bounds.bid_low), float(action_bounds.ask_low)],
                    [float(action_bounds.bid_high), float(action_bounds.ask_high)],
                ]
            )
            active_dimensions.append([True, True, True] if category == 1 else [False] * 3)

        return cls(
            state=torch.tensor(states, dtype=torch.float32),
            action=torch.tensor(actions, dtype=torch.float32),
            reward=torch.tensor(rewards, dtype=torch.float32),
            next_state=torch.tensor(next_states, dtype=torch.float32),
            done=torch.tensor([row.done for row in rows], dtype=torch.bool),
            discount=torch.tensor(discounts, dtype=torch.float32),
            category_mask=torch.tensor(masks, dtype=torch.bool),
            bounds=torch.tensor(bounds, dtype=torch.float32),
            logged_category=torch.tensor(categories, dtype=torch.long),
            active_dimensions=torch.tensor(active_dimensions, dtype=torch.bool),
        )


def _state_vector(state: Mapping[str, object], keys: tuple[str, ...]) -> list[float]:
    return [_finite_float(state[key], f"state field {key!r}") for key in keys]


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        raise TypeError(f"{label} must be numeric")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} contains non-finite data")
    return converted


__all__ = [
    "ExclusionCounts",
    "ManifestTransitionRepository",
    "TransitionDataset",
]
