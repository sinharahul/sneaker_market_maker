"""Core domain models and deterministic opportunity evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

MONEY_QUANTUM = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


class RejectionReason(str, Enum):
    INVALID_MARKET = "invalid_market"
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"
    EXCESSIVE_VOLATILITY = "excessive_volatility"
    INSUFFICIENT_PROFIT = "insufficient_profit"
    CAPITAL_LIMIT = "capital_limit"


@dataclass(frozen=True)
class FeeSchedule:
    """All costs incurred from purchasing through final sale."""

    seller_rate: Decimal
    processor_rate: Decimal
    inbound_shipping: Decimal = Decimal("0")
    outbound_shipping: Decimal = Decimal("0")
    fixed_seller_fee: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        for name in ("seller_rate", "processor_rate"):
            value = getattr(self, name)
            if not Decimal("0") <= value < Decimal("1"):
                raise ValueError(f"{name} must be in [0, 1)")
        if self.seller_rate + self.processor_rate >= Decimal("1"):
            raise ValueError("combined sale fee rate must be less than 1")
        for name in ("inbound_shipping", "outbound_shipping", "fixed_seller_fee"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")

    @property
    def sale_rate(self) -> Decimal:
        return self.seller_rate + self.processor_rate

    def sale_proceeds(self, sale_price: Decimal) -> Decimal:
        if sale_price <= 0:
            raise ValueError("sale_price must be positive")
        variable_fees = sale_price * self.sale_rate
        return _money(
            sale_price - variable_fees - self.fixed_seller_fee - self.outbound_shipping
        )

    def total_purchase_cost(self, purchase_price: Decimal) -> Decimal:
        if purchase_price <= 0:
            raise ValueError("purchase_price must be positive")
        return _money(purchase_price + self.inbound_shipping)

    def net_profit(self, purchase_price: Decimal, sale_price: Decimal) -> Decimal:
        return _money(self.sale_proceeds(sale_price) - self.total_purchase_cost(purchase_price))

    def breakeven_sale_price(self, purchase_price: Decimal) -> Decimal:
        denominator = Decimal("1") - self.sale_rate
        required = (
            purchase_price
            + self.inbound_shipping
            + self.outbound_shipping
            + self.fixed_seller_fee
        ) / denominator
        return _money(required)


@dataclass(frozen=True)
class MarketSnapshot:
    platform: str
    style_code: str
    shoe_size: Decimal
    highest_bid: Decimal
    lowest_ask: Decimal
    sales_48h: int
    volatility_48h: Decimal
    days_since_release: int

    def __post_init__(self) -> None:
        if not self.platform.strip() or not self.style_code.strip():
            raise ValueError("platform and style_code are required")
        if self.shoe_size <= 0:
            raise ValueError("shoe_size must be positive")
        if self.highest_bid <= 0 or self.lowest_ask <= 0:
            raise ValueError("bid and ask must be positive")
        if self.sales_48h < 0 or self.days_since_release < 0:
            raise ValueError("counts and elapsed days cannot be negative")
        if self.volatility_48h < 0:
            raise ValueError("volatility cannot be negative")

    @property
    def raw_spread(self) -> Decimal:
        return _money(self.lowest_ask - self.highest_bid)

    @property
    def volatility_ratio(self) -> Decimal:
        return self.volatility_48h / self.highest_bid


@dataclass(frozen=True)
class RiskLimits:
    min_sales_48h: int = 3
    max_volatility_ratio: Decimal = Decimal("0.15")
    min_profit: Decimal = Decimal("10")
    max_purchase_price: Decimal = Decimal("500")
    bid_increment: Decimal = Decimal("1")
    ask_decrement: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if self.min_sales_48h < 0:
            raise ValueError("min_sales_48h cannot be negative")
        for name in (
            "max_volatility_ratio",
            "min_profit",
            "max_purchase_price",
            "bid_increment",
            "ask_decrement",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True)
class Opportunity:
    accepted: bool
    target_buy_price: Decimal
    target_sell_price: Decimal
    expected_profit: Decimal
    breakeven_sale_price: Decimal
    reason: RejectionReason | None = None


class OpportunityEvaluator:
    def __init__(self, fees: FeeSchedule, limits: RiskLimits | None = None) -> None:
        self.fees = fees
        self.limits = limits or RiskLimits()

    def evaluate(self, snapshot: MarketSnapshot) -> Opportunity:
        buy = _money(snapshot.highest_bid + self.limits.bid_increment)
        sell = _money(snapshot.lowest_ask - self.limits.ask_decrement)
        breakeven = self.fees.breakeven_sale_price(buy)
        profit = self.fees.net_profit(buy, sell) if sell > 0 else Decimal("-Infinity")

        reason: RejectionReason | None = None
        if sell <= buy:
            reason = RejectionReason.INVALID_MARKET
        elif snapshot.sales_48h < self.limits.min_sales_48h:
            reason = RejectionReason.INSUFFICIENT_LIQUIDITY
        elif snapshot.volatility_ratio > self.limits.max_volatility_ratio:
            reason = RejectionReason.EXCESSIVE_VOLATILITY
        elif buy > self.limits.max_purchase_price:
            reason = RejectionReason.CAPITAL_LIMIT
        elif profit < self.limits.min_profit:
            reason = RejectionReason.INSUFFICIENT_PROFIT

        return Opportunity(
            accepted=reason is None,
            target_buy_price=buy,
            target_sell_price=sell,
            expected_profit=profit,
            breakeven_sale_price=breakeven,
            reason=reason,
        )
