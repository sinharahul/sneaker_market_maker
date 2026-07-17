"""Fee-once reward construction over exact accounting projections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import Decimal

from sneaker_market_maker.research.contracts.transition import RewardRecord

_ZERO = Decimal("0")
_COST_FIELDS = (
    "seller_fees",
    "processor_fees",
    "shipping",
    "authentication",
    "slippage",
)
_PENALTY_FIELDS = (
    "age",
    "capital",
    "turnover",
    "drawdown",
    "stale",
    "liquidation",
)


def _validate_decimals(instance: object, names: tuple[str, ...], label: str) -> None:
    values = tuple(getattr(instance, name) for name in names)
    if not all(isinstance(value, Decimal) for value in values):
        raise TypeError(f"{label} must be Decimal")
    if not all(value.is_finite() for value in values):
        raise ValueError(f"{label} must be finite")


def _validate_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")
    if any(not value or not value.strip() for value in values):
        raise ValueError(f"{label} must be nonempty")


@dataclass(frozen=True)
class AccountingProjection:
    nav: Decimal
    ledger_entry_ids: tuple[str, ...]
    seller_fees: Decimal
    processor_fees: Decimal
    shipping: Decimal
    authentication: Decimal
    slippage: Decimal
    open_reservations: tuple[str, ...]
    physical_lots: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_decimals(self, ("nav", *_COST_FIELDS), "accounting values")
        _validate_unique(self.ledger_entry_ids, "ledger IDs")
        _validate_unique(self.open_reservations, "reservation IDs")
        _validate_unique(self.physical_lots, "physical lot IDs")
        if any(getattr(self, name) < _ZERO for name in _COST_FIELDS):
            raise ValueError("explanatory costs must be nonnegative")
        object.__setattr__(self, "ledger_entry_ids", tuple(self.ledger_entry_ids))
        object.__setattr__(self, "open_reservations", tuple(self.open_reservations))
        object.__setattr__(self, "physical_lots", tuple(self.physical_lots))


@dataclass(frozen=True)
class PenaltyStatistics:
    age: Decimal
    capital: Decimal
    turnover: Decimal
    drawdown: Decimal
    stale: Decimal
    liquidation: Decimal

    def __post_init__(self) -> None:
        _validate_decimals(self, _PENALTY_FIELDS, "penalty statistics")
        if any(getattr(self, name) < _ZERO for name in _PENALTY_FIELDS):
            raise ValueError("penalty statistics must be nonnegative")


@dataclass(frozen=True)
class RewardConfig:
    version: str
    initial_nav: Decimal
    lambda_age: Decimal
    lambda_capital: Decimal
    lambda_turnover: Decimal
    lambda_drawdown: Decimal
    lambda_stale: Decimal
    lambda_terminal: Decimal
    tolerance: Decimal

    def __post_init__(self) -> None:
        decimal_names = tuple(field.name for field in fields(self) if field.name != "version")
        _validate_decimals(self, decimal_names, "reward configuration values")
        if not self.version or not self.version.strip():
            raise ValueError("reward version is required")
        if self.initial_nav <= _ZERO:
            raise ValueError("initial_nav must be positive")
        coefficients = (
            self.lambda_age,
            self.lambda_capital,
            self.lambda_turnover,
            self.lambda_drawdown,
            self.lambda_stale,
            self.lambda_terminal,
        )
        if any(value < _ZERO for value in coefficients):
            raise ValueError("penalty coefficients must be nonnegative")
        if self.tolerance < _ZERO:
            raise ValueError("tolerance must be nonnegative")


class RewardBuilder:
    def __init__(
        self,
        config: RewardConfig,
        accrual_entry_ids: Mapping[str, str] | None = None,
    ) -> None:
        self.config = config
        self.accrual_entry_ids = dict(accrual_entry_ids or {})
        unknown = set(self.accrual_entry_ids) - set(_COST_FIELDS)
        if unknown:
            raise ValueError(f"unknown accrual cost: {sorted(unknown)[0]}")
        _validate_unique(tuple(self.accrual_entry_ids.values()), "accrual ledger IDs")

    def build(
        self,
        before: AccountingProjection,
        after: AccountingProjection,
        penalties: PenaltyStatistics,
        terminal: bool,
    ) -> RewardRecord:
        """Build and reconcile one dimensionless transition reward."""
        if not isinstance(terminal, bool):
            raise TypeError("terminal must be bool")
        if terminal and (after.open_reservations or after.physical_lots):
            raise ValueError("terminal projection must close reservations and physical lots")

        explanatory_costs = {
            name: getattr(after, name) - getattr(before, name) for name in _COST_FIELDS
        }
        if any(value < _ZERO for value in explanatory_costs.values()):
            raise ValueError("cumulative explanatory costs cannot decrease")
        ledger_entry_ids = self._reconcile_cost_entries(before, after, explanatory_costs)

        weighted_penalties = {
            "age": self.config.lambda_age * penalties.age,
            "capital": self.config.lambda_capital * penalties.capital,
            "turnover": self.config.lambda_turnover * penalties.turnover,
            "drawdown": self.config.lambda_drawdown * penalties.drawdown,
            "stale": self.config.lambda_stale * penalties.stale,
            "liquidation": (
                self.config.lambda_terminal * penalties.liquidation if terminal else _ZERO
            ),
        }
        nav_delta = (after.nav - before.nav) / self.config.initial_nav
        penalty_total = sum(weighted_penalties.values(), start=_ZERO)
        total = nav_delta - penalty_total
        reconciled_total = nav_delta - sum(weighted_penalties.values(), start=_ZERO)
        if abs(total - reconciled_total) > self.config.tolerance:
            raise ValueError("reward components do not reconcile")

        return RewardRecord(
            version=self.config.version,
            total=total,
            nav_delta=nav_delta,
            penalties=weighted_penalties,
            explanatory_costs=explanatory_costs,
            ledger_entry_ids=ledger_entry_ids,
            reconciled=True,
        )

    def _reconcile_cost_entries(
        self,
        before: AccountingProjection,
        after: AccountingProjection,
        explanatory_costs: Mapping[str, Decimal],
    ) -> tuple[str, ...]:
        before_ids = set(before.ledger_entry_ids)
        new_ids = [entry_id for entry_id in after.ledger_entry_ids if entry_id not in before_ids]
        unused_ids = list(new_ids)
        reconciled_ids = list(new_ids)

        for name, amount in explanatory_costs.items():
            if amount == _ZERO:
                continue
            matching_id = next((entry_id for entry_id in unused_ids if name in entry_id), None)
            if matching_id is None and unused_ids:
                matching_id = unused_ids[0]
            if matching_id is not None:
                unused_ids.remove(matching_id)
                continue
            accrual_id = self.accrual_entry_ids.get(name)
            if accrual_id is None:
                raise ValueError(f"missing ledger entry for explanatory cost {name}")
            if accrual_id in before_ids or accrual_id in reconciled_ids:
                raise ValueError(f"duplicate ledger ID: {accrual_id}")
            reconciled_ids.append(accrual_id)

        return tuple(reconciled_ids)
