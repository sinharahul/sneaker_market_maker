"""Tests for Paper Capital rules and Deterministic Gate."""

from __future__ import annotations

from decimal import Decimal

import pytest

from sneaker_market_maker.paper.capital import (
    INITIAL_PAPER_CAPITAL,
    OPEN_BUY_PRINCIPAL_CAP,
    PaperCapital,
)
from sneaker_market_maker.paper.gate import DeterministicGate, GateReason
from sneaker_market_maker.paper.intents import IntentKind, QuoteIntent, Side


@pytest.fixture
def gate() -> DeterministicGate:
    return DeterministicGate()


@pytest.fixture
def capital() -> PaperCapital:
    return PaperCapital.initial_state()


def test_initial_paper_capital_constants(capital: PaperCapital) -> None:
    assert capital.initial == INITIAL_PAPER_CAPITAL == Decimal("2500.00")
    assert capital.cash == Decimal("2500.00")
    assert capital.reserved_buy_principal == Decimal("0.00")
    assert capital.open_buy_principal_cap == OPEN_BUY_PRINCIPAL_CAP == Decimal("1500.00")


def test_open_buy_cap_does_not_grow_with_profits(gate: DeterministicGate) -> None:
    rich = PaperCapital(
        initial=INITIAL_PAPER_CAPITAL,
        cash=Decimal("5000.00"),
        reserved_buy_principal=Decimal("0.00"),
    )
    assert rich.open_buy_principal_cap == Decimal("1500.00")
    decision = gate.evaluate(
        QuoteIntent(
            kind=IntentKind.PLACE,
            side=Side.BUY,
            principal=Decimal("1500.01"),
            expected_fees_and_slippage=Decimal("0.00"),
            product_family="jordan_1_retro",
        ),
        rich,
    )
    assert decision.accepted is False
    assert decision.reason is GateReason.OPEN_BUY_CAP_EXCEEDED


def test_gate_rejects_buy_when_cash_after_reservations_insufficient(
    gate: DeterministicGate,
) -> None:
    capital = PaperCapital(
        initial=INITIAL_PAPER_CAPITAL,
        cash=Decimal("2500.00"),
        reserved_buy_principal=Decimal("1400.00"),
    )
    # available = 1100; need 1000 + 200 fees = 1200
    decision = gate.evaluate(
        QuoteIntent(
            kind=IntentKind.PLACE,
            side=Side.BUY,
            principal=Decimal("1000.00"),
            expected_fees_and_slippage=Decimal("200.00"),
            product_family="nike_dunk_low",
        ),
        capital,
    )
    assert decision.accepted is False
    assert decision.reason is GateReason.INSUFFICIENT_CASH
    assert capital.reserved_buy_principal == Decimal("1400.00")


def test_gate_accepts_buy_within_cap_and_cash_and_reserves_principal(
    gate: DeterministicGate, capital: PaperCapital
) -> None:
    decision = gate.evaluate(
        QuoteIntent(
            kind=IntentKind.PLACE,
            side=Side.BUY,
            principal=Decimal("1000.00"),
            expected_fees_and_slippage=Decimal("50.00"),
            product_family="jordan_1_retro",
        ),
        capital,
    )
    assert decision.accepted is True
    assert decision.reason is GateReason.ACCEPTED
    assert decision.capital_after is not None
    assert decision.capital_after.reserved_buy_principal == Decimal("1000.00")
    assert decision.capital_after.cash == Decimal("2500.00")
    assert capital.reserved_buy_principal == Decimal("0.00")


def test_replace_releases_old_and_reserves_new_atomically(gate: DeterministicGate) -> None:
    capital = PaperCapital(
        initial=INITIAL_PAPER_CAPITAL,
        cash=Decimal("2500.00"),
        reserved_buy_principal=Decimal("1200.00"),
    )
    decision = gate.evaluate(
        QuoteIntent(
            kind=IntentKind.REPLACE,
            side=Side.BUY,
            principal=Decimal("1300.00"),
            expected_fees_and_slippage=Decimal("10.00"),
            product_family="jordan_1_retro",
            replaces_reservation=Decimal("1200.00"),
        ),
        capital,
    )
    assert decision.accepted is True
    assert decision.capital_after is not None
    assert decision.capital_after.reserved_buy_principal == Decimal("1300.00")


def test_failed_replace_does_not_mutate_capital(gate: DeterministicGate) -> None:
    capital = PaperCapital(
        initial=INITIAL_PAPER_CAPITAL,
        cash=Decimal("2500.00"),
        reserved_buy_principal=Decimal("1200.00"),
    )
    decision = gate.evaluate(
        QuoteIntent(
            kind=IntentKind.REPLACE,
            side=Side.BUY,
            principal=Decimal("1600.00"),
            expected_fees_and_slippage=Decimal("0.00"),
            product_family="jordan_1_retro",
            replaces_reservation=Decimal("1200.00"),
        ),
        capital,
    )
    assert decision.accepted is False
    assert decision.reason is GateReason.OPEN_BUY_CAP_EXCEEDED
    assert capital.reserved_buy_principal == Decimal("1200.00")


def test_gate_rejects_unsupported_product_family(
    gate: DeterministicGate, capital: PaperCapital
) -> None:
    decision = gate.evaluate(
        QuoteIntent(
            kind=IntentKind.PLACE,
            side=Side.BUY,
            principal=Decimal("100.00"),
            expected_fees_and_slippage=Decimal("5.00"),
            product_family="yeezy",
        ),
        capital,
    )
    assert decision.accepted is False
    assert decision.reason is GateReason.UNSUPPORTED_PRODUCT_FAMILY


def test_cancel_releases_reservation(gate: DeterministicGate) -> None:
    capital = PaperCapital(
        initial=INITIAL_PAPER_CAPITAL,
        cash=Decimal("2500.00"),
        reserved_buy_principal=Decimal("500.00"),
    )
    decision = gate.evaluate(
        QuoteIntent(
            kind=IntentKind.CANCEL,
            side=Side.BUY,
            principal=Decimal("0.00"),
            expected_fees_and_slippage=Decimal("0.00"),
            product_family="jordan_1_retro",
            replaces_reservation=Decimal("500.00"),
        ),
        capital,
    )
    assert decision.accepted is True
    assert decision.capital_after is not None
    assert decision.capital_after.reserved_buy_principal == Decimal("0.00")
