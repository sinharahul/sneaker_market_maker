"""TDD: Paper step effects capture (pure builder seam)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from sneaker_market_maker.paper.capital import PaperCapital
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.paper.intents import Side
from sneaker_market_maker.paper.inventory import LotState
from sneaker_market_maker.paper.orders import OrderStatus
from sneaker_market_maker.paper.step_effects import (
    PaperBookDeltaView,
    PaperStepEffects,
    capture_paper_step_effects,
)
from sneaker_market_maker.persistence.paper_models import (
    PaperBookSnapshot,
    PersistedFill,
    PersistedLot,
    PersistedOrder,
)


def _capital(
    *,
    cash: Decimal = Decimal("2500.00"),
    reserved: Decimal = Decimal("0.00"),
) -> PaperCapital:
    return PaperCapital(
        initial=Decimal("2500.00"),
        cash=cash,
        reserved_buy_principal=reserved,
    )


def _empty_book(run_id, capital: PaperCapital) -> PaperBookSnapshot:
    return PaperBookSnapshot(run_id=run_id, capital=capital, orders=(), fills=(), lots=())


def test_capture_records_cash_delta_fill_and_lot_lineage() -> None:
    run_id = uuid4()
    fill_id = uuid4()
    order_id = uuid4()
    lot_id = uuid4()
    before = _empty_book(run_id, _capital())
    after = PaperBookSnapshot(
        run_id=run_id,
        capital=_capital(cash=Decimal("2284.00"), reserved=Decimal("0.00")),
        orders=(
            PersistedOrder(
                order_id=order_id,
                side=Side.BUY,
                price=Decimal("220.00"),
                quantity=1,
                status=OrderStatus.FILLED,
                product_family="jordan_1_retro",
                style_code="555088-001",
                shoe_size=Decimal("10"),
                principal=Decimal("220.00"),
                replaced_order_id=None,
            ),
        ),
        fills=(
            PersistedFill(
                fill_id=fill_id,
                order_id=order_id,
                side=Side.BUY,
                quantity=1,
                quoted_price=Decimal("220.00"),
                execution_price=Decimal("220.00"),
                slippage=Decimal("0.00"),
                fee_schedule_version="fees-v1",
                slippage_version="slippage-v1",
                total_fees=Decimal("5.00"),
                source_event_id="g2",
                product_family="jordan_1_retro",
                style_code="555088-001",
                shoe_size=Decimal("10"),
                simulation_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            ),
        ),
        lots=(
            PersistedLot(
                lot_id=lot_id,
                product_family="jordan_1_retro",
                style_code="555088-001",
                shoe_size=Decimal("10"),
                landed_cost=Decimal("225.00"),
                state=LotState.AVAILABLE,
                source_fill_id=str(fill_id),
                created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            ),
        ),
    )

    effects = capture_paper_step_effects(
        run_id=run_id,
        simulation_time=datetime(2024, 1, 1, 12, tzinfo=timezone.utc),
        source_event_ids=("g2",),
        before=before,
        after=after,
    )

    assert isinstance(effects, PaperStepEffects)
    assert effects.run_id == run_id
    assert effects.cash_before == Decimal("2500.00")
    assert effects.cash_after == Decimal("2284.00")
    assert effects.fill_ids_added == (str(fill_id),)
    assert effects.order_ids_added == (str(order_id),)
    assert effects.lot_ids_added == (str(lot_id),)
    assert effects.source_event_ids == ("g2",)


def test_capture_fails_closed_when_money_missing() -> None:
    run_id = uuid4()
    before = PaperBookDeltaView(
        cash=None,
        reserved_buy_principal=Decimal("0.00"),
        order_ids=frozenset(),
        fill_ids=frozenset(),
        lot_ids=frozenset(),
    )
    after = PaperBookDeltaView(
        cash=Decimal("2500.00"),
        reserved_buy_principal=Decimal("0.00"),
        order_ids=frozenset(),
        fill_ids=frozenset(),
        lot_ids=frozenset(),
    )
    with pytest.raises(PaperError, match="incomplete money"):
        capture_paper_step_effects(
            run_id=run_id,
            simulation_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            source_event_ids=(),
            before=before,
            after=after,
        )
