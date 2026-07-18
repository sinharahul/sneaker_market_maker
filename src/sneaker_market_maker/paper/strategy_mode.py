"""Strategy Mode state machine for Model-Integrated Paper Slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StrategyMode(str, Enum):
    DETERMINISTIC = "deterministic"
    ADVISORY = "advisory"
    IQL_PRIMARY = "iql_primary"


@dataclass(frozen=True)
class StrategyModeAuditEntry:
    from_mode: StrategyMode
    to_mode: StrategyMode


@dataclass
class StrategyModeMachine:
    """Holds exactly one Strategy Mode; mode changes are append-only audited."""

    _mode: StrategyMode = StrategyMode.DETERMINISTIC
    _audit: list[StrategyModeAuditEntry] = field(default_factory=list)

    @property
    def mode(self) -> StrategyMode:
        return self._mode

    @property
    def audit(self) -> tuple[StrategyModeAuditEntry, ...]:
        return tuple(self._audit)

    def set_mode(self, mode: StrategyMode) -> bool:
        """Switch mode. Returns False when unchanged (no audit entry)."""

        if mode is self._mode:
            return False
        self._audit.append(StrategyModeAuditEntry(from_mode=self._mode, to_mode=mode))
        self._mode = mode
        return True
