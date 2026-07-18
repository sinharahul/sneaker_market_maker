"""Control-plane tests for set-mode and set-budget (ticket 07)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sneaker_market_maker.api.app import create_app
from sneaker_market_maker.api.paper_routes import PaperServices
from sneaker_market_maker.api.research_routes import ResearchServices
from sneaker_market_maker.paper.session import PaperOpsSession
from sneaker_market_maker.research.registry.service import RegistryState
from tests.api.test_research_api import Events, Queries, TransactionalCommands


def _client() -> tuple[TestClient, PaperOpsSession]:
    session = PaperOpsSession()
    queries = Queries()
    research = ResearchServices(queries, TransactionalCommands(), Events())
    app = create_app(
        research,
        paper_services=PaperServices(
            query_service=session,
            command_service=session,
            event_service=session,
        ),
    )
    return TestClient(app), session


def _post(client: TestClient, command: str, key: str, payload: dict | None = None):
    return client.post(
        f"/api/paper/commands/{command}",
        headers={"Idempotency-Key": key},
        json=payload or {},
    )


def test_status_defaults_to_deterministic_and_default_budget() -> None:
    client, _ = _client()
    status = client.get("/api/paper/status").json()
    assert status["strategy_mode"] == "deterministic"
    assert status["inference_latency_budget_ms"] == 100
    assert status["registry"] == {"model_id": None, "state": None}


def test_set_budget_is_idempotent_and_rejects_above_ceiling() -> None:
    client, _ = _client()

    first = _post(client, "set-budget", "budget-1", {"limit_ms": 150})
    assert first.status_code == 202
    command_id = first.json()["command_id"]
    retry = _post(client, "set-budget", "budget-1", {"limit_ms": 150})
    assert retry.status_code == 202
    assert retry.json()["command_id"] == command_id
    assert client.get("/api/paper/status").json()["inference_latency_budget_ms"] == 150

    conflict = _post(client, "set-budget", "budget-1", {"limit_ms": 200})
    assert conflict.status_code == 409

    rejected = _post(client, "set-budget", "budget-2", {"limit_ms": 251})
    assert rejected.status_code == 400
    assert client.get("/api/paper/status").json()["inference_latency_budget_ms"] == 150


def test_set_mode_idempotent_and_unqualified_refused() -> None:
    client, session = _client()

    session.bind_active_model(
        model_id="iql-bench-1",
        registry_state=RegistryState.BENCHMARK_QUALIFIED,
    )
    status = client.get("/api/paper/status").json()
    assert status["registry"] == {
        "model_id": "iql-bench-1",
        "state": "benchmark_qualified",
    }

    refused = _post(client, "set-mode", "mode-adv", {"mode": "advisory"})
    assert refused.status_code == 400
    assert client.get("/api/paper/status").json()["strategy_mode"] == "deterministic"

    first = _post(client, "set-mode", "mode-iql", {"mode": "iql_primary"})
    assert first.status_code == 202
    command_id = first.json()["command_id"]
    retry = _post(client, "set-mode", "mode-iql", {"mode": "iql_primary"})
    assert retry.status_code == 202
    assert retry.json()["command_id"] == command_id
    assert client.get("/api/paper/status").json()["strategy_mode"] == "iql_primary"

    session.bind_active_model(
        model_id="iql-adv-1",
        registry_state=RegistryState.ADVISORY_APPROVED,
    )
    assert _post(client, "set-mode", "mode-adv-ok", {"mode": "advisory"}).status_code == 202
    assert client.get("/api/paper/status").json()["strategy_mode"] == "advisory"

    assert _post(client, "set-mode", "mode-det", {"mode": "deterministic"}).status_code == 202
    assert client.get("/api/paper/status").json()["strategy_mode"] == "deterministic"
