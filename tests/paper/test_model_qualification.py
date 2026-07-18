"""Model Qualification gates for Strategy Mode (ticket 06)."""

from __future__ import annotations

import pytest

from sneaker_market_maker.paper.strategy_mode import (
    QualificationError,
    StrategyMode,
    StrategyModeMachine,
    mode_is_qualified,
)
from sneaker_market_maker.research.registry.service import RegistryState


@pytest.mark.parametrize(
    ("mode", "state", "allowed"),
    [
        (StrategyMode.DETERMINISTIC, None, True),
        (StrategyMode.DETERMINISTIC, RegistryState.CANDIDATE, True),
        (StrategyMode.ADVISORY, RegistryState.ADVISORY_APPROVED, True),
        (StrategyMode.ADVISORY, RegistryState.BENCHMARK_QUALIFIED, False),
        (StrategyMode.ADVISORY, RegistryState.SHADOW, False),
        (StrategyMode.ADVISORY, None, False),
        (StrategyMode.IQL_PRIMARY, RegistryState.BENCHMARK_QUALIFIED, True),
        (StrategyMode.IQL_PRIMARY, RegistryState.ADVISORY_APPROVED, True),
        (StrategyMode.IQL_PRIMARY, RegistryState.SHADOW, False),
        (StrategyMode.IQL_PRIMARY, RegistryState.VALIDATED, False),
        (StrategyMode.IQL_PRIMARY, None, False),
    ],
)
def test_qualification_matrix(
    mode: StrategyMode,
    state: RegistryState | None,
    allowed: bool,
) -> None:
    assert mode_is_qualified(mode, state) is allowed


def test_unqualified_advisory_refused_without_mode_change() -> None:
    machine = StrategyModeMachine()
    with pytest.raises(QualificationError) as exc:
        machine.set_mode(
            StrategyMode.ADVISORY,
            registry_state=RegistryState.BENCHMARK_QUALIFIED,
        )
    assert exc.value.code == "not_qualified"
    assert machine.mode is StrategyMode.DETERMINISTIC
    assert machine.audit == ()


def test_unqualified_iql_primary_refused_without_mode_change() -> None:
    machine = StrategyModeMachine()
    with pytest.raises(QualificationError) as exc:
        machine.set_mode(StrategyMode.IQL_PRIMARY, registry_state=RegistryState.SHADOW)
    assert exc.value.code == "not_qualified"
    assert machine.mode is StrategyMode.DETERMINISTIC
    assert machine.audit == ()


def test_qualified_modes_are_accepted() -> None:
    machine = StrategyModeMachine()
    assert (
        machine.set_mode(
            StrategyMode.IQL_PRIMARY,
            registry_state=RegistryState.BENCHMARK_QUALIFIED,
        )
        is True
    )
    assert machine.mode is StrategyMode.IQL_PRIMARY
    assert (
        machine.set_mode(
            StrategyMode.ADVISORY,
            registry_state=RegistryState.ADVISORY_APPROVED,
        )
        is True
    )
    assert machine.mode is StrategyMode.ADVISORY


def test_deterministic_always_selectable_from_any_state() -> None:
    machine = StrategyModeMachine()
    machine.set_mode(
        StrategyMode.IQL_PRIMARY,
        registry_state=RegistryState.ADVISORY_APPROVED,
    )
    assert machine.set_mode(StrategyMode.DETERMINISTIC) is True
    assert machine.mode is StrategyMode.DETERMINISTIC
