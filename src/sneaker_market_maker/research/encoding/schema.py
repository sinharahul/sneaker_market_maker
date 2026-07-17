"""Validated tensor encoding and legal hybrid-action construction."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import torch

from sneaker_market_maker.research.contracts.action import ActionBounds, ActionMask
from sneaker_market_maker.research.contracts.state import StateValidationError

STANDARDIZED_CLIP = 10.0


def _finite_float(value: object, field: str) -> float:
    try:
        converted = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError) as exc:
        raise StateValidationError(f"state field must be finite: {field}") from exc
    if not math.isfinite(converted):
        raise StateValidationError(f"state field must be finite: {field}")
    return converted


@dataclass(frozen=True)
class EncodedState:
    values: torch.Tensor
    collection_mask: torch.Tensor
    missingness: torch.Tensor
    schema_version: str
    scaler_version: str


@dataclass(frozen=True)
class Scaler:
    version: str
    fold_hash: str
    means: Mapping[str, float]
    scales: Mapping[str, float]

    def __post_init__(self) -> None:
        if not self.version or not self.fold_hash:
            raise ValueError("scaler version and fold_hash are required")
        means = {name: _finite_float(value, name) for name, value in self.means.items()}
        scales = {name: _finite_float(value, name) for name, value in self.scales.items()}
        if means.keys() != scales.keys():
            raise ValueError("scaler means and scales must name the same features")
        if any(scale <= 0 for scale in scales.values()):
            raise ValueError("scaler scales must be positive")
        object.__setattr__(self, "means", means)
        object.__setattr__(self, "scales", scales)

    def transform(self, name: str, value: float) -> float:
        if name not in self.means:
            raise StateValidationError(f"scaler has no feature: {name}")
        finite = _finite_float(value, name)
        standardized = (finite - self.means[name]) / self.scales[name]
        return min(STANDARDIZED_CLIP, max(-STANDARDIZED_CLIP, standardized))

    @classmethod
    def fit(
        cls,
        rows: Sequence[Mapping[str, object]],
        split: str,
        *,
        version: str,
        fold_hash: str,
    ) -> Scaler:
        if split != "train":
            raise ValueError("scaler may only be fit on the train split")
        if not rows:
            raise ValueError("cannot fit scaler on empty rows")
        names = tuple(rows[0])
        if not names:
            raise ValueError("cannot fit scaler without features")
        columns: dict[str, list[float]] = {name: [] for name in names}
        for row in rows:
            if set(row) != set(names):
                raise StateValidationError("scaler rows must share the same features")
            for name in names:
                columns[name].append(_finite_float(row[name], name))
        means = {name: sum(values) / len(values) for name, values in columns.items()}
        scales = {
            name: math.sqrt(
                sum((value - means[name]) ** 2 for value in values) / len(values)
            )
            or 1.0
            for name, values in columns.items()
        }
        return cls(version=version, fold_hash=fold_hash, means=means, scales=scales)


@dataclass(frozen=True)
class StateSchema:
    version: str
    continuous: tuple[str, ...]
    required: tuple[str, ...]
    categorical_vocabularies: Mapping[str, tuple[str, ...]]
    collection_limits: Mapping[str, int]

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("schema version is required")
        declared = self.continuous + tuple(self.categorical_vocabularies) + tuple(
            self.collection_limits
        )
        if len(set(declared)) != len(declared):
            raise ValueError("state fields may only be declared once")
        if len(set(self.required)) != len(self.required):
            raise ValueError("required state fields must be unique")
        if not set(self.required).issubset(declared):
            raise ValueError("required state fields must be declared")
        if any(not vocabulary for vocabulary in self.categorical_vocabularies.values()):
            raise ValueError("categorical vocabularies cannot be empty")
        if any(limit < 0 for limit in self.collection_limits.values()):
            raise ValueError("collection limits cannot be negative")

    @property
    def field_order(self) -> tuple[str, ...]:
        return self.continuous + tuple(self.categorical_vocabularies) + tuple(
            self.collection_limits
        )

    def validate(self, state: Mapping[str, object]) -> None:
        for name in self.required:
            if name not in state or state[name] is None:
                raise StateValidationError(f"missing required state field: {name}")
        for name in self.continuous:
            if name not in state or state[name] is None:
                raise StateValidationError(f"missing continuous state field: {name}")
            _finite_float(state[name], name)
        for name, vocabulary in self.categorical_vocabularies.items():
            if name not in state or state[name] is None:
                continue
            value = state[name]
            if not isinstance(value, str) or value not in vocabulary:
                raise StateValidationError(f"invalid categorical state field: {name}")
        for name, limit in self.collection_limits.items():
            if name not in state or state[name] is None:
                continue
            value = state[name]
            if not isinstance(value, Sequence) or isinstance(value, str | bytes):
                raise StateValidationError(f"state collection must be a sequence: {name}")
            if len(value) > limit:
                raise StateValidationError(f"state collection exceeds limit: {name}")


class StateEncoder:
    def __init__(self, schema: StateSchema, scaler: Scaler) -> None:
        self.schema = schema
        self.scaler = scaler

    def encode(self, state: Mapping[str, object]) -> EncodedState:
        self.schema.validate(state)
        values = torch.tensor(
            [
                self.scaler.transform(name, float(state[name]))  # type: ignore[arg-type]
                for name in self.schema.continuous
            ],
            dtype=torch.float32,
        )
        if not torch.isfinite(values).all():
            raise StateValidationError("encoded state is non-finite")
        return EncodedState(
            values=values,
            collection_mask=self._collection_mask(state),
            missingness=torch.tensor(
                [name not in state or state[name] is None for name in self.schema.field_order],
                dtype=torch.bool,
            ),
            schema_version=self.schema.version,
            scaler_version=self.scaler.version,
        )

    def _collection_mask(self, state: Mapping[str, object]) -> torch.Tensor:
        mask: list[bool] = []
        for name, limit in self.schema.collection_limits.items():
            value = state.get(name)
            length = len(value) if isinstance(value, Sequence) else 0
            mask.extend(index < length for index in range(limit))
        return torch.tensor(mask, dtype=torch.bool)


class MaskBuilder:
    _BOUND_FIELDS = (
        "bid_offset_low",
        "bid_offset_high",
        "ask_offset_low",
        "ask_offset_high",
    )

    def build(self, state: Mapping[str, object]) -> tuple[ActionMask, ActionBounds]:
        bounds_values = tuple(self._integer_bound(state, name) for name in self._BOUND_FIELDS)
        bounds = ActionBounds(*bounds_values)
        if bounds.bid_low > bounds.bid_high or bounds.ask_low > bounds.ask_high:
            raise StateValidationError("action bounds have an invalid range")
        sellable = self._availability(state, "sellable_inventory")
        cancellable = self._availability(state, "cancellable_quote")
        return ActionMask(no_op=True, quote=sellable, cancel=cancellable), bounds

    @staticmethod
    def _availability(state: Mapping[str, object], name: str) -> bool:
        if name not in state or state[name] is None:
            raise StateValidationError(f"missing required state field: {name}")
        value = state[name]
        if isinstance(value, bool):
            return value
        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            return bool(value)
        return _finite_float(value, name) > 0

    @staticmethod
    def _integer_bound(state: Mapping[str, object], name: str) -> int:
        if name not in state or state[name] is None:
            raise StateValidationError(f"missing required state field: {name}")
        value = _finite_float(state[name], name)
        if not value.is_integer():
            raise StateValidationError(f"action bound must be an integer: {name}")
        return int(value)


__all__ = [
    "EncodedState",
    "MaskBuilder",
    "Scaler",
    "StateEncoder",
    "StateSchema",
    "StateValidationError",
]
