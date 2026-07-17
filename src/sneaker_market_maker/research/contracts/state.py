"""Versioned state schema validation contracts."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass


class StateValidationError(ValueError):
    """Raised when state cannot be safely encoded."""


@dataclass(frozen=True)
class StateSchema:
    version: str
    feature_names: tuple[str, ...]
    required_fields: tuple[str, ...]

    def validate(self, payload: Mapping[str, object]) -> None:
        """Require every declared field to exist and contain a finite number."""
        for field in self.required_fields:
            if field not in payload:
                raise StateValidationError(f"missing required state field: {field}")
            try:
                finite = math.isfinite(payload[field])  # type: ignore[arg-type]
            except (TypeError, ValueError, OverflowError) as exc:
                raise StateValidationError(
                    f"required state field must be finite: {field}"
                ) from exc
            if not finite:
                raise StateValidationError(f"required state field must be finite: {field}")
