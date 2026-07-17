from dataclasses import replace
from decimal import Decimal

import pytest

from sneaker_market_maker.research.rewards.builder import (
    AccountingProjection,
    PenaltyStatistics,
    RewardBuilder,
    RewardConfig,
)


def config() -> RewardConfig:
    return RewardConfig(
        version="reward-v1",
        initial_nav=Decimal("1000"),
        lambda_age=Decimal("0.1"),
        lambda_capital=Decimal("0.2"),
        lambda_turnover=Decimal("0.3"),
        lambda_drawdown=Decimal("0.4"),
        lambda_stale=Decimal("0.5"),
        lambda_terminal=Decimal("0.6"),
        tolerance=Decimal("1e-12"),
    )


def projection(**changes: object) -> AccountingProjection:
    values: dict[str, object] = {
        "nav": Decimal("1000"),
        "ledger_entry_ids": (),
        "seller_fees": Decimal("0"),
        "processor_fees": Decimal("0"),
        "shipping": Decimal("0"),
        "authentication": Decimal("0"),
        "slippage": Decimal("0"),
        "open_reservations": (),
        "physical_lots": (),
    }
    values.update(changes)
    return AccountingProjection(**values)  # type: ignore[arg-type]


def penalties() -> PenaltyStatistics:
    return PenaltyStatistics(
        age=Decimal("0.01"),
        capital=Decimal("0.02"),
        turnover=Decimal("0.03"),
        drawdown=Decimal("0.04"),
        stale=Decimal("0.05"),
        liquidation=Decimal("0.06"),
    )


def test_build_uses_exact_formula_and_reconciles_components() -> None:
    before = projection(
        ledger_entry_ids=("opening",),
        open_reservations=("reservation-1",),
        physical_lots=("lot-1",),
    )
    after = projection(
        nav=Decimal("1050"),
        ledger_entry_ids=(
            "opening",
            "seller_fees:sale-1",
            "processor_fees:sale-1",
            "authentication:lot-1",
            "slippage:fill-1",
        ),
        seller_fees=Decimal("10"),
        processor_fees=Decimal("2"),
        authentication=Decimal("3"),
        slippage=Decimal("1"),
    )

    reward = RewardBuilder(config()).build(before, after, penalties(), terminal=True)

    expected_nav_delta = Decimal("0.05")
    expected_penalties = {
        "age": Decimal("0.001"),
        "capital": Decimal("0.004"),
        "turnover": Decimal("0.009"),
        "drawdown": Decimal("0.016"),
        "stale": Decimal("0.025"),
        "liquidation": Decimal("0.036"),
    }
    assert reward.nav_delta == expected_nav_delta
    assert dict(reward.penalties) == expected_penalties
    assert reward.total == expected_nav_delta - sum(
        expected_penalties.values(), start=Decimal("0")
    )
    assert abs(
        reward.total
        - (reward.nav_delta - sum(reward.penalties.values(), start=Decimal("0")))
    ) <= config().tolerance
    assert dict(reward.explanatory_costs) == {
        "seller_fees": Decimal("10"),
        "processor_fees": Decimal("2"),
        "shipping": Decimal("0"),
        "authentication": Decimal("3"),
        "slippage": Decimal("1"),
    }
    assert reward.reconciled


def test_explanatory_fees_are_not_subtracted_twice() -> None:
    before = projection(nav=Decimal("1000"))
    after = projection(
        nav=Decimal("990"),
        ledger_entry_ids=("seller_fees:sale-1",),
        seller_fees=Decimal("10"),
    )
    zero_penalties = replace(
        penalties(),
        age=Decimal("0"),
        capital=Decimal("0"),
        turnover=Decimal("0"),
        drawdown=Decimal("0"),
        stale=Decimal("0"),
        liquidation=Decimal("0"),
    )

    reward = RewardBuilder(config()).build(before, after, zero_penalties, terminal=False)

    assert reward.total == Decimal("-0.01")
    assert reward.explanatory_costs["seller_fees"] == Decimal("10")


def test_missing_cost_ledger_entry_gets_one_named_accrual() -> None:
    before = projection()
    after = projection(nav=Decimal("995"), shipping=Decimal("5"))
    builder = RewardBuilder(
        config(),
        accrual_entry_ids={"shipping": "accrual:shipping:step-1"},
    )

    reward = builder.build(before, after, penalties(), terminal=False)

    assert reward.ledger_entry_ids == ("accrual:shipping:step-1",)
    assert reward.ledger_entry_ids.count("accrual:shipping:step-1") == 1


def test_missing_cost_ledger_entry_without_accrual_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing ledger entry.*shipping"):
        RewardBuilder(config()).build(
            projection(),
            projection(nav=Decimal("995"), shipping=Decimal("5")),
            penalties(),
            terminal=False,
        )


def test_duplicate_ledger_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate ledger"):
        RewardBuilder(config()).build(
            projection(),
            projection(ledger_entry_ids=("fee-1", "fee-1")),
            penalties(),
            terminal=False,
        )


@pytest.mark.parametrize(
    "field",
    ["age", "capital", "turnover", "drawdown", "stale", "liquidation"],
)
def test_penalty_statistics_must_be_nonnegative(field: str) -> None:
    with pytest.raises(ValueError, match="penalty statistics must be nonnegative"):
        replace(penalties(), **{field: Decimal("-0.01")})


def test_nonterminal_reward_does_not_apply_liquidation_penalty() -> None:
    reward = RewardBuilder(config()).build(
        projection(),
        projection(),
        penalties(),
        terminal=False,
    )

    assert reward.penalties["liquidation"] == Decimal("0")


def test_terminal_closes_inventory_and_reservations() -> None:
    before = projection(
        open_reservations=("reservation-1",),
        physical_lots=("lot-1",),
    )

    RewardBuilder(config()).build(before, projection(), penalties(), terminal=True)

    with pytest.raises(ValueError, match="terminal projection must close"):
        RewardBuilder(config()).build(
            before,
            projection(open_reservations=("reservation-1",)),
            penalties(),
            terminal=True,
        )
