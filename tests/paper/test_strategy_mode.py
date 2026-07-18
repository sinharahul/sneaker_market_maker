"""Strategy Mode state machine (ticket 05)."""

from __future__ import annotations

from sneaker_market_maker.paper.strategy_mode import StrategyMode, StrategyModeMachine


def test_default_mode_is_deterministic() -> None:
    machine = StrategyModeMachine()
    assert machine.mode is StrategyMode.DETERMINISTIC


def test_exactly_one_mode_active_and_audited_on_change() -> None:
    machine = StrategyModeMachine()
    assert machine.set_mode(StrategyMode.ADVISORY) is True
    assert machine.mode is StrategyMode.ADVISORY
    assert machine.set_mode(StrategyMode.IQL_PRIMARY) is True
    assert machine.mode is StrategyMode.IQL_PRIMARY
    assert [entry.to_mode for entry in machine.audit] == [
        StrategyMode.ADVISORY,
        StrategyMode.IQL_PRIMARY,
    ]
    assert [entry.from_mode for entry in machine.audit] == [
        StrategyMode.DETERMINISTIC,
        StrategyMode.ADVISORY,
    ]


def test_same_mode_is_noop_without_audit() -> None:
    machine = StrategyModeMachine()
    assert machine.set_mode(StrategyMode.DETERMINISTIC) is False
    assert machine.audit == ()


def test_modes_are_exclusive_enum_values() -> None:
    assert {mode.value for mode in StrategyMode} == {
        "deterministic",
        "advisory",
        "iql_primary",
    }
