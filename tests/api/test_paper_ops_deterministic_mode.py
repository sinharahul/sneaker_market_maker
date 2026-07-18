"""Deterministic Strategy Mode must not invoke IQL (ticket 08)."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from sneaker_market_maker.api.app import create_app
from sneaker_market_maker.api.paper_routes import PaperServices
from sneaker_market_maker.api.research_routes import ResearchServices
from sneaker_market_maker.paper.decision_state import PaperDecisionState
from sneaker_market_maker.paper.session import PaperOpsSession
from sneaker_market_maker.research.contracts.action import ActionCategory, HybridAction
from sneaker_market_maker.research.registry.service import RegistryState
from tests.api.test_research_api import Events, Queries, TransactionalCommands


@dataclass
class CountingIql:
    """Spy port — any call proves the quote path invoked IQL."""

    calls: list[PaperDecisionState] = field(default_factory=list)

    def infer(self, state: PaperDecisionState) -> tuple[HybridAction, float]:
        self.calls.append(state)
        return HybridAction(ActionCategory.QUOTE, 0.5, 5, -5), 1.0


def _client(session: PaperOpsSession | None = None) -> tuple[TestClient, PaperOpsSession]:
    paper = session or PaperOpsSession()
    research = ResearchServices(Queries(), TransactionalCommands(), Events())
    app = create_app(
        research,
        paper_services=PaperServices(
            query_service=paper,
            command_service=paper,
            event_service=paper,
        ),
    )
    return TestClient(app), paper


def _post(client: TestClient, command: str, key: str, payload: dict | None = None):
    return client.post(
        f"/api/paper/commands/{command}",
        headers={"Idempotency-Key": key},
        json=payload or {},
    )


def _run_golden(client: TestClient, *, key_prefix: str) -> dict:
    assert _post(client, "load", f"{key_prefix}-load", {"seed": 7, "speed": 1}).status_code == 202
    assert _post(client, "start", f"{key_prefix}-start").status_code == 202
    assert _post(client, "enable", f"{key_prefix}-enable").status_code == 202
    for index in range(3):
        assert _post(client, "tick", f"{key_prefix}-tick-{index}").status_code == 202
    return {
        "status": client.get("/api/paper/status").json(),
        "orders": client.get("/api/paper/orders").json()["orders"],
        "fills": client.get("/api/paper/fills").json()["fills"],
    }


def test_non_deterministic_mode_invokes_iql_on_tick() -> None:
    """Positive control: advisory/iql_primary must reach the inference port."""

    spy = CountingIql()
    session = PaperOpsSession()
    session.bind_inference(spy)
    session.bind_active_model(
        model_id="iql-bench-1",
        registry_state=RegistryState.BENCHMARK_QUALIFIED,
    )
    client, _ = _client(session)

    assert _post(client, "set-mode", "iql", {"mode": "iql_primary"}).status_code == 202
    assert _post(client, "load", "iql-load", {"seed": 7, "speed": 1}).status_code == 202
    assert _post(client, "start", "iql-start").status_code == 202
    assert _post(client, "enable", "iql-enable").status_code == 202
    assert _post(client, "tick", "iql-tick-0").status_code == 202
    assert len(spy.calls) >= 1


def test_deterministic_mode_never_invokes_iql_on_golden_ticks() -> None:
    spy = CountingIql()
    session = PaperOpsSession()
    session.bind_inference(spy)
    client, _ = _client(session)

    result = _run_golden(client, key_prefix="det")
    assert result["status"]["strategy_mode"] == "deterministic"
    assert result["status"]["fills"] >= 1
    assert spy.calls == []


def test_switch_back_to_deterministic_restores_baseline_without_iql() -> None:
    spy = CountingIql()
    session = PaperOpsSession()
    session.bind_inference(spy)
    session.bind_active_model(
        model_id="iql-bench-1",
        registry_state=RegistryState.BENCHMARK_QUALIFIED,
    )
    client, _ = _client(session)

    assert _post(client, "set-mode", "to-iql", {"mode": "iql_primary"}).status_code == 202
    assert client.get("/api/paper/status").json()["strategy_mode"] == "iql_primary"
    assert _post(client, "set-mode", "to-det", {"mode": "deterministic"}).status_code == 202
    assert client.get("/api/paper/status").json()["strategy_mode"] == "deterministic"

    result = _run_golden(client, key_prefix="restore")
    assert result["status"]["fills"] >= 1
    assert any(order["status"] == "filled" for order in result["orders"])
    assert spy.calls == []
