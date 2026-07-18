"""Paper Capital for Continuous Paper Market-Maker."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

MONEY = Decimal("0.01")
INITIAL_PAPER_CAPITAL = Decimal("2500.00")
OPEN_BUY_PRINCIPAL_CAP = Decimal("1500.00")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PaperCapital:
    initial: Decimal
    cash: Decimal
    reserved_buy_principal: Decimal

    @classmethod
    def initial_state(cls) -> PaperCapital:
        return cls(
            initial=INITIAL_PAPER_CAPITAL,
            cash=INITIAL_PAPER_CAPITAL,
            reserved_buy_principal=Decimal("0.00"),
        )
    @property
    def open_buy_principal_cap(self) -> Decimal:
        """Cap is fixed to initial capital policy — does not grow with profits."""

        return OPEN_BUY_PRINCIPAL_CAP

    @property
    def available_cash(self) -> Decimal:
        return _money(self.cash - self.reserved_buy_principal)

    def with_reservation(self, reserved_buy_principal: Decimal) -> PaperCapital:
        return PaperCapital(
            initial=self.initial,
            cash=self.cash,
            reserved_buy_principal=_money(reserved_buy_principal),
        )

    def apply_buy_fill(
        self,
        *,
        principal_released: Decimal,
        total_cost: Decimal,
    ) -> PaperCapital:
        if principal_released > self.reserved_buy_principal:
            raise ValueError("cannot release more than reserved buy principal")
        if total_cost > self.cash:
            raise ValueError("insufficient cash for buy fill")
        return PaperCapital(
            initial=self.initial,
            cash=_money(self.cash - total_cost),
            reserved_buy_principal=_money(self.reserved_buy_principal - principal_released),
        )

    def apply_sell_fill(self, *, proceeds: Decimal) -> PaperCapital:
        if proceeds < 0:
            raise ValueError("sell proceeds cannot be negative")
        return PaperCapital(
            initial=self.initial,
            cash=_money(self.cash + proceeds),
            reserved_buy_principal=self.reserved_buy_principal,
        )
