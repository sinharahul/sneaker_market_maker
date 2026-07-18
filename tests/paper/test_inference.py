"""IQL inference port + Inference Latency Budget (ticket 04)."""

from __future__ import annotations

import pytest

from sneaker_market_maker.paper.decision_state import PaperDecisionState
from sneaker_market_maker.paper.inference import (
    DEFAULT_LATENCY_MS,
    MAX_LATENCY_MS,
    InferenceError,
    InferenceLatencyBudget,
    InferenceOutcome,
    StubIqlInference,
    TimedIqlInference,
)
from sneaker_market_maker.research.contracts.action import ActionCategory, HybridAction


def _state() -> PaperDecisionState:
    return PaperDecisionState(
        schema_version="paper-decision-v1",
        payload={
            "highest_bid": 220.0,
            "lowest_ask": 275.0,
            "spread": 55.0,
            "cash": 2500.0,
            "reserved_buy_principal": 0.0,
            "available_cash": 2500.0,
            "open_buy_count": 0.0,
            "open_sell_count": 0.0,
            "available_lot_count": 0.0,
            "inventory_landed_cost": 0.0,
            "shoe_size": 10.0,
        },
    )


def test_budget_defaults_and_rejects_above_ceiling() -> None:
    budget = InferenceLatencyBudget()
    assert budget.limit_ms == DEFAULT_LATENCY_MS
    assert budget.limit_ms == 100
    with pytest.raises(InferenceError) as exc:
        InferenceLatencyBudget(limit_ms=MAX_LATENCY_MS + 1)
    assert exc.value.code == "budget_ceiling"


def test_stub_inference_succeeds_within_budget() -> None:
    action = HybridAction(ActionCategory.QUOTE, 0.5, -1, 2)
    port = StubIqlInference(action=action, latency_ms=10.0)
    timed = TimedIqlInference(port, budget=InferenceLatencyBudget(limit_ms=100))
    outcome = timed.infer(_state())
    assert outcome.valid is True
    assert outcome.action == action
    assert outcome.latency_ms == 10.0
    assert outcome.reason is None


def test_timeout_yields_invalid_not_silent_success() -> None:
    action = HybridAction(ActionCategory.QUOTE, 0.5, 0, 0)
    port = StubIqlInference(action=action, latency_ms=150.0)
    timed = TimedIqlInference(port, budget=InferenceLatencyBudget(limit_ms=100))
    outcome = timed.infer(_state())
    assert outcome.valid is False
    assert outcome.action is None
    assert outcome.reason == "timeout"
    assert outcome.latency_ms == 150.0


def test_encode_failure_yields_invalid() -> None:
    port = StubIqlInference(fail_with="encode_failed")
    timed = TimedIqlInference(port, budget=InferenceLatencyBudget(limit_ms=100))
    outcome = timed.infer(_state())
    assert outcome == InferenceOutcome(
        valid=False,
        action=None,
        latency_ms=0.0,
        reason="encode_failed",
    )


def test_budget_is_pinable_per_run() -> None:
    budget = InferenceLatencyBudget(limit_ms=200)
    assert budget.limit_ms == 200
    port = StubIqlInference(
        action=HybridAction(ActionCategory.NO_OP, 0.0, 0, 0),
        latency_ms=180.0,
    )
    assert TimedIqlInference(port, budget=budget).infer(_state()).valid is True
