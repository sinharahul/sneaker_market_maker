"""Strategy Mode state machine with Model Qualification gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.research.registry.service import RegistryState


class StrategyMode(str, Enum):
    DETERMINISTIC = "deterministic"
    ADVISORY = "advisory"
    IQL_PRIMARY = "iql_primary"


class QualificationError(PaperError):
    """Fail-closed Model Qualification refusal."""


@dataclass(frozen=True)
class StrategyModeAuditEntry:
    from_mode: StrategyMode
    to_mode: StrategyMode


def mode_is_qualified(
    mode: StrategyMode,
    registry_state: RegistryState | None,
) -> bool:
    """Whether registry state authorizes the Strategy Mode (research states only)."""

    if mode is StrategyMode.DETERMINISTIC:
        return True
    if mode is StrategyMode.ADVISORY:
        return registry_state is RegistryState.ADVISORY_APPROVED
    if mode is StrategyMode.IQL_PRIMARY:
        return registry_state in {
            RegistryState.BENCHMARK_QUALIFIED,
            RegistryState.ADVISORY_APPROVED,
        }
    return False


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

    def set_mode(
        self,
        mode: StrategyMode,
        *,
        registry_state: RegistryState | None = None,
    ) -> bool:
        """Switch mode when Model Qualification allows. Raises otherwise (no mutation)."""

        if not mode_is_qualified(mode, registry_state):
            raise QualificationError(
                "not_qualified",
                f"Strategy Mode {mode.value!r} is not allowed for registry state "
                f"{None if registry_state is None else registry_state.value!r}",
            )
        if mode is self._mode:
            return False
        self._audit.append(StrategyModeAuditEntry(from_mode=self._mode, to_mode=mode))
        self._mode = mode
        return True
