"""TDD: fee-once reward projection from paper accounting slices (R1-02)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.paper.reward_projection import (
    ZERO_PENALTIES,
    default_paper_reward_config,
    project_paper_reward,
)
from sneaker_market_maker.research.rewards.builder import AccountingProjection


def _proj(
    *,
    nav: Decimal,
    ledger: tuple[str, ...] = ("opening",),
    shipping: Decimal = Decimal("0"),
    seller_fees: Decimal = Decimal("0"),
    lots: tuple[str, ...] = (),
) -> AccountingProjection:
    return AccountingProjection(
        nav=nav,
        ledger_entry_ids=ledger,
        seller_fees=seller_fees,
        processor_fees=Decimal("0"),
        shipping=shipping,
        authentication=Decimal("0"),
        slippage=Decimal("0"),
        open_reservations=(),
        physical_lots=lots,
    )


def test_profitable_step_projects_fee_once_reward() -> None:
    before = _proj(nav=Decimal("2500.00"))
    after = _proj(
        nav=Decimal("2520.50"),
        ledger=("opening", "seller_fees:fill-1"),
        seller_fees=Decimal("15.00"),
    )
    reward = project_paper_reward(before=before, after=after, terminal=False)
    assert reward.reconciled is True
    assert reward.nav_delta == Decimal("0.0082")
    assert reward.explanatory_costs["seller_fees"] == Decimal("15.00")
    assert "seller_fees:fill-1" in reward.ledger_entry_ids


def test_fee_heavy_buy_attributes_shipping_ledger() -> None:
    before = _proj(nav=Decimal("2500.00"))
    after = _proj(
        nav=Decimal("2284.00"),
        ledger=("opening", "shipping:fill-buy"),
        shipping=Decimal("5.00"),
        lots=("lot-1",),
    )
    reward = project_paper_reward(before=before, after=after, terminal=False)
    assert reward.nav_delta < 0
    assert reward.explanatory_costs["shipping"] == Decimal("5.00")
    assert reward.ledger_entry_ids == ("shipping:fill-buy",)


def test_incomplete_ledger_quarantines() -> None:
    before = _proj(nav=Decimal("2500.00"))
    after = _proj(
        nav=Decimal("2490.00"),
        ledger=("opening",),  # fee rose without ledger id
        shipping=Decimal("10.00"),
    )
    with pytest.raises(PaperError, match="quarantine"):
        project_paper_reward(before=before, after=after, terminal=False)


def test_default_config_uses_initial_paper_capital() -> None:
    config = default_paper_reward_config()
    assert config.initial_nav == Decimal("2500.00")
    assert ZERO_PENALTIES.age == Decimal("0")
