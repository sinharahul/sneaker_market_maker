from decimal import Decimal

import pytest

from sneaker_market_maker.core import (
    FeeSchedule,
    MarketSnapshot,
    OpportunityEvaluator,
    RejectionReason,
    RiskLimits,
)


def snapshot(**overrides: object) -> MarketSnapshot:
    values: dict[str, object] = {
        "platform": "stockx",
        "style_code": "DD1391-100",
        "shoe_size": Decimal("10"),
        "highest_bid": Decimal("100"),
        "lowest_ask": Decimal("150"),
        "sales_48h": 8,
        "volatility_48h": Decimal("5"),
        "days_since_release": 100,
    }
    values.update(overrides)
    return MarketSnapshot(**values)  # type: ignore[arg-type]


@pytest.fixture
def fees() -> FeeSchedule:
    return FeeSchedule(
        seller_rate=Decimal("0.10"),
        processor_rate=Decimal("0.03"),
        inbound_shipping=Decimal("8"),
        outbound_shipping=Decimal("2"),
    )


def test_fee_schedule_calculates_proceeds_profit_and_breakeven(
    fees: FeeSchedule,
) -> None:
    assert fees.sale_proceeds(Decimal("150")) == Decimal("128.50")
    assert fees.total_purchase_cost(Decimal("100")) == Decimal("108.00")
    assert fees.net_profit(Decimal("100"), Decimal("150")) == Decimal("20.50")
    assert fees.breakeven_sale_price(Decimal("100")) == Decimal("126.44")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seller_rate", Decimal("-0.01")),
        ("processor_rate", Decimal("1")),
        ("inbound_shipping", Decimal("-1")),
    ],
)
def test_fee_schedule_rejects_invalid_values(field: str, value: Decimal) -> None:
    values = {
        "seller_rate": Decimal("0.1"),
        "processor_rate": Decimal("0.03"),
        "inbound_shipping": Decimal("0"),
    }
    values[field] = value
    with pytest.raises(ValueError):
        FeeSchedule(**values)


def test_fee_schedule_rejects_combined_rate_of_one() -> None:
    with pytest.raises(ValueError, match="combined"):
        FeeSchedule(Decimal("0.6"), Decimal("0.4"))


def test_profitable_liquid_market_is_accepted(fees: FeeSchedule) -> None:
    result = OpportunityEvaluator(fees).evaluate(snapshot())

    assert result.accepted
    assert result.reason is None
    assert result.target_buy_price == Decimal("101.00")
    assert result.target_sell_price == Decimal("149.00")
    assert result.expected_profit == Decimal("18.63")


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"lowest_ask": Decimal("101")}, RejectionReason.INVALID_MARKET),
        ({"sales_48h": 2}, RejectionReason.INSUFFICIENT_LIQUIDITY),
        ({"volatility_48h": Decimal("16")}, RejectionReason.EXCESSIVE_VOLATILITY),
        (
            {"highest_bid": Decimal("501"), "lowest_ask": Decimal("650")},
            RejectionReason.CAPITAL_LIMIT,
        ),
        ({"lowest_ask": Decimal("130")}, RejectionReason.INSUFFICIENT_PROFIT),
    ],
)
def test_risk_rejections(
    fees: FeeSchedule,
    changes: dict[str, object],
    reason: RejectionReason,
) -> None:
    result = OpportunityEvaluator(fees).evaluate(snapshot(**changes))
    assert not result.accepted
    assert result.reason is reason


def test_rejection_priority_is_deterministic(fees: FeeSchedule) -> None:
    risky = snapshot(sales_48h=0, volatility_48h=Decimal("80"))
    result = OpportunityEvaluator(fees).evaluate(risky)
    assert result.reason is RejectionReason.INSUFFICIENT_LIQUIDITY


def test_custom_limits_change_quote_prices(fees: FeeSchedule) -> None:
    limits = RiskLimits(
        min_profit=Decimal("0"),
        bid_increment=Decimal("0.50"),
        ask_decrement=Decimal("2"),
    )
    result = OpportunityEvaluator(fees, limits).evaluate(snapshot())
    assert result.target_buy_price == Decimal("100.50")
    assert result.target_sell_price == Decimal("148.00")
