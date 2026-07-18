"""Ops control-plane promote/qualify over RegistryService."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.paper.strategy_mode import StrategyMode, mode_is_qualified
from sneaker_market_maker.research.registry.service import (
    RegistryModel,
    RegistryService,
    RegistryState,
)


class PromoteError(PaperError):
    """Fail-closed promote / qualify error."""


@dataclass(frozen=True)
class PromoteResult:
    model: RegistryModel
    source: RegistryState | None
    target: RegistryState
    actor: str
    reason: str


@dataclass(frozen=True)
class LastPromoteProjection:
    model_id: str
    actor: str
    reason: str
    source: str | None
    target: str


def unlocked_modes_for(state: RegistryState | None) -> tuple[str, ...]:
    """Strategy Modes the current registry state authorizes."""

    return tuple(
        mode.value
        for mode in StrategyMode
        if mode_is_qualified(mode, state)
    )


def promote_registry_model(
    registry: RegistryService,
    *,
    model_id: UUID | str,
    target: RegistryState | str,
    actor: str,
    reason: str,
) -> PromoteResult:
    """Apply one legal registry edge; reuse RegistryService (no second promotor)."""

    if not str(actor).strip():
        raise PromoteError("missing_actor", "actor is required")
    if not str(reason).strip():
        raise PromoteError("missing_reason", "reason is required")
    try:
        mid = model_id if isinstance(model_id, UUID) else UUID(str(model_id))
    except ValueError as error:
        raise PromoteError("invalid_model_id", f"invalid model_id: {model_id!r}") from error
    try:
        target_state = target if isinstance(target, RegistryState) else RegistryState(str(target))
    except ValueError as error:
        raise PromoteError("invalid_target", f"unknown registry target: {target!r}") from error

    try:
        current = registry.store.get(mid)
    except KeyError as error:
        raise PromoteError("unknown_model", f"unknown registry model: {mid}") from error
    source = current.state
    try:
        updated = registry.transition(mid, target_state, actor.strip(), reason.strip())
    except ValueError as error:
        raise PromoteError("illegal_transition", str(error)) from error
    return PromoteResult(
        model=updated,
        source=source,
        target=updated.state,
        actor=actor.strip(),
        reason=reason.strip(),
    )


__all__ = [
    "LastPromoteProjection",
    "PromoteError",
    "PromoteResult",
    "promote_registry_model",
    "unlocked_modes_for",
]
