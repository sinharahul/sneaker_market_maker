from decimal import Decimal

import pytest

from sneaker_market_maker.research.contracts.action import ActionCategory
from sneaker_market_maker.research.demo.fixture import (
    DEMO_EVENTS,
    DEMO_SEED,
    FEE_KEYS,
    ZERO_FEES,
)
from sneaker_market_maker.research.demo.service import DemoService, DemoSnapshot

PINNED_ROWS = (
    (0, "healthy_spread", ActionCategory.NO_OP, Decimal("2500.00"), Decimal("2500.00")),
    (60, "deterministic_bid", ActionCategory.QUOTE, Decimal("2500.00"), Decimal("2500.00")),
    (120, "paper_buy_fill", ActionCategory.NO_OP, Decimal("2312.00"), Decimal("2498.00")),
    (180, "shipping_authenticated", ActionCategory.NO_OP, Decimal("2312.00"), Decimal("2502.00")),
    (240, "inventory_ask_sale", ActionCategory.QUOTE, Decimal("2524.50"), Decimal("2524.50")),
    (300, "risk_gate_rejection", ActionCategory.NO_OP, Decimal("2524.50"), Decimal("2524.50")),
)

EXPECTED_BEATS = (
    "healthy_spread",
    "deterministic_bid",
    "paper_buy_fill",
    "shipping_authenticated",
    "inventory_ask_sale",
    "risk_gate_rejection",
)


def test_demo_events_are_immutable_pinned_story() -> None:
    assert DEMO_SEED == 20260717
    assert len(DEMO_EVENTS) == 6
    assert DEMO_EVENTS[0].simulation_second == 0
    assert DEMO_EVENTS[-1].simulation_second == 300

    for event, pinned in zip(DEMO_EVENTS, PINNED_ROWS, strict=True):
        second, beat, category, cash, nav = pinned
        assert event.simulation_second == second
        assert event.beat == beat
        assert event.final_action.category is category
        assert event.cash == cash
        assert event.nav == nav


def test_sale_beat_itemizes_fees_and_realized_pnl() -> None:
    sale = DEMO_EVENTS[4]
    assert sale.beat == "inventory_ask_sale"
    assert sale.fees["seller_fee"] == Decimal("15.00")
    assert sale.fees["processor_fee"] == Decimal("4.50")
    assert sale.fees["inbound_shipping"] == Decimal("8.00")
    assert sale.fees["outbound_shipping"] == Decimal("2.00")
    assert sale.realized_pnl == Decimal("24.50")
    for key in FEE_KEYS:
        if key not in {
            "seller_fee",
            "processor_fee",
            "inbound_shipping",
            "outbound_shipping",
        }:
            assert sale.fees[key] == Decimal("0")


def test_non_sale_beats_use_zero_fee_components() -> None:
    for event in DEMO_EVENTS:
        if event.beat == "inventory_ask_sale":
            continue
        assert event.fees == ZERO_FEES


def test_step_advances_exactly_one_coalesced_decision() -> None:
    service = DemoService()
    for expected_index, expected_beat in enumerate(EXPECTED_BEATS):
        snapshot = service.snapshot()
        assert snapshot.index == expected_index
        assert snapshot.beat == expected_beat
        if expected_index < len(EXPECTED_BEATS) - 1:
            next_snapshot = service.step()
            assert next_snapshot.index == expected_index + 1
            assert next_snapshot.beat == EXPECTED_BEATS[expected_index + 1]

    terminal = service.step()
    assert terminal.index == len(EXPECTED_BEATS) - 1
    assert terminal.beat == "risk_gate_rejection"


def _snapshot_payload(snapshot: DemoSnapshot) -> dict[str, object]:
    return {
        "index": snapshot.index,
        "simulation_second": snapshot.simulation_second,
        "paused": snapshot.paused,
        "beat": snapshot.beat,
        "deterministic_action": snapshot.deterministic_action,
        "pfhedge_score": snapshot.pfhedge_score,
        "iql_shadow_action": snapshot.iql_shadow_action,
        "final_action": snapshot.final_action,
        "inventory_state": snapshot.inventory_state,
        "fees": dict(snapshot.fees),
        "cash": snapshot.cash,
        "nav": snapshot.nav,
        "realized_pnl": snapshot.realized_pnl,
        "unrealized_pnl": snapshot.unrealized_pnl,
    }


def test_restart_restores_initial_snapshot_byte_equivalence() -> None:
    service = DemoService()
    initial = service.snapshot()
    service.step()
    service.step()
    service.resume()

    restarted = service.restart()
    assert _snapshot_payload(restarted) == _snapshot_payload(initial)
    assert restarted.paused is True


def test_pause_and_resume_toggle_paused_flag_only() -> None:
    service = DemoService()
    initial = service.snapshot()
    paused = service.pause()
    assert paused.paused is True
    assert paused.index == initial.index
    assert paused.beat == initial.beat

    resumed = service.resume()
    assert resumed.paused is False
    assert resumed.index == initial.index
    assert resumed.beat == initial.beat


def test_snapshot_exposes_required_fields() -> None:
    snapshot = DemoService().snapshot()
    assert isinstance(snapshot, DemoSnapshot)
    assert snapshot.simulation_second == 0
    assert snapshot.beat == "healthy_spread"
    assert snapshot.deterministic_action.category is ActionCategory.NO_OP
    assert isinstance(snapshot.pfhedge_score, float)
    assert snapshot.iql_shadow_action.category is ActionCategory.NO_OP
    assert snapshot.final_action.category is ActionCategory.NO_OP
    assert snapshot.inventory_state
    assert snapshot.cash == Decimal("2500.00")
    assert snapshot.nav == Decimal("2500.00")


def test_demo_service_performs_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, ...]] = []

    def blocked_open(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("unexpected I/O")

    monkeypatch.setattr("builtins.open", blocked_open)
    service = DemoService()
    service.pause()
    service.resume()
    service.step()
    service.restart()
    service.snapshot()
    assert calls == []
