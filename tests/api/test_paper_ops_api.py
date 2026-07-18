"""Acceptance tests at the Paper Ops Control Plane seam."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sneaker_market_maker.api.app import create_app
from sneaker_market_maker.api.paper_routes import PaperServices
from sneaker_market_maker.api.research_routes import ResearchServices
from sneaker_market_maker.paper.session import PaperOpsSession
from tests.api.test_research_api import Events, Queries, TransactionalCommands


def _client() -> tuple[TestClient, PaperOpsSession]:
    session = PaperOpsSession()
    research, _, _, _ = _research_services()
    app = create_app(
        research,
        paper_services=PaperServices(
            query_service=session,
            command_service=session,
            event_service=session,
        ),
    )
    return TestClient(app), session


def _research_services() -> tuple[ResearchServices, Queries, TransactionalCommands, Events]:
    queries = Queries()
    commands = TransactionalCommands()
    events = Events()
    return ResearchServices(queries, commands, events), queries, commands, events


def _post(client: TestClient, command: str, key: str, payload: dict | None = None):
    return client.post(
        f"/api/paper/commands/{command}",
        headers={"Idempotency-Key": key},
        json=payload or {},
    )


def test_idempotent_load_start_enable_tick_produces_book_projections() -> None:
    client, _session = _client()

    first = _post(client, "load", "load-1", {"seed": 7, "speed": 1})
    assert first.status_code == 202
    run_id = first.json()["run_id"]
    retry = _post(client, "load", "load-1", {"seed": 7, "speed": 1})
    assert retry.status_code == 202
    assert retry.json()["run_id"] == run_id

    conflict = _post(client, "load", "load-1", {"seed": 8, "speed": 1})
    assert conflict.status_code == 409

    assert _post(client, "start", "start-1").status_code == 202
    assert _post(client, "enable", "enable-1").status_code == 202
    # Three ticks drain golden_v1 (speed=1): place → fill → dunk quote
    for index in range(3):
        assert _post(client, "tick", f"tick-{index}").status_code == 202

    status = client.get("/api/paper/status").json()
    assert status["run_id"] == run_id
    assert status["strategy_enabled"] is True
    assert status["fills"] >= 1
    assert status["lots"] >= 1
    assert status["replay"]["dataset_id"] == "golden-stockx-v1"

    capital = client.get("/api/paper/capital").json()
    assert capital["initial"] == "2500.00"
    assert capital["cash"] != "2500.00"

    orders = client.get("/api/paper/orders").json()["orders"]
    assert any(order["status"] == "filled" for order in orders)

    fills = client.get("/api/paper/fills").json()["fills"]
    assert len(fills) >= 1
    assert fills[0]["quantity"] == 1

    lots = client.get("/api/paper/lots").json()["lots"]
    assert len(lots) >= 1
    assert lots[0]["state"] == "available"

    pnl = client.get("/api/paper/pnl").json()
    assert "pnl" in pnl and "equity" in pnl

    with client.websocket_connect("/api/paper/events?after=0") as websocket:
        events = []
        while True:
            try:
                events.append(websocket.receive_json())
            except Exception:
                break
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert any(event["event_type"] == "replay.ticked" for event in events)


def test_paper_commands_require_idempotency_key() -> None:
    client, _ = _client()
    response = client.post("/api/paper/commands/load", json={})
    assert response.status_code == 400


def test_research_routes_remain_available_beside_paper_ops() -> None:
    client, _ = _client()
    assert client.get("/api/research/comparisons").status_code == 200
    assert client.get("/api/paper/status").status_code == 200
