"""TDD: PaperOpsSession emits append-only paper.step_effects on tick."""

from __future__ import annotations

from sneaker_market_maker.paper.session import PaperOpsSession
from sneaker_market_maker.paper.step_effects import STEP_EFFECTS_EVENT


def test_golden_tick_emits_append_only_step_effects() -> None:
    session = PaperOpsSession()
    run_id = session.execute("load", {"seed": 7, "speed": 1}, "fx-load")
    session.execute("start", {}, "fx-start")
    session.execute("enable", {}, "fx-enable")

    for index in range(3):
        session.execute("tick", {}, f"fx-tick-{index}")

    effects_events = [
        event for event in session.after(0) if event.event_type == STEP_EFFECTS_EVENT
    ]
    assert len(effects_events) >= 1
    payloads = [event.payload for event in effects_events]
    assert all(payload["run_id"] == str(run_id) for payload in payloads)
    assert any(payload["fill_ids_added"] for payload in payloads)
    assert any(
        payload["cash_before"] != payload["cash_after"] for payload in payloads
    )

    sequences = [event.sequence for event in effects_events]
    assert sequences == sorted(sequences)
    assert len(sequences) == len(set(sequences))
    first_payload = dict(payloads[0])
    assert effects_events[0].payload == first_payload
