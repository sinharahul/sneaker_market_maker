"""Control-plane acceptance for advisory and iql_primary Strategy Modes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sneaker_market_maker.api.app import create_app
from sneaker_market_maker.api.paper_routes import PaperServices
from sneaker_market_maker.api.research_routes import ResearchServices
from sneaker_market_maker.paper.inference import StubIqlInference
from sneaker_market_maker.paper.session import PaperOpsSession
from sneaker_market_maker.research.contracts.action import ActionCategory, HybridAction
from sneaker_market_maker.research.registry.service import RegistryState
from tests.api.test_research_api import Events, Queries, TransactionalCommands


def _client(session: PaperOpsSession) -> TestClient:
    research = ResearchServices(Queries(), TransactionalCommands(), Events())
    app = create_app(
        research,
        paper_services=PaperServices(
            query_service=session,
            command_service=session,
            event_service=session,
        ),
    )
    return TestClient(app)


def _post(client: TestClient, command: str, key: str, payload: dict | None = None):
    return client.post(
        f"/api/paper/commands/{command}",
        headers={"Idempotency-Key": key},
        json=payload or {},
    )


def _boot(client: TestClient, prefix: str) -> None:
    assert _post(client, "load", f"{prefix}-load", {"seed": 7, "speed": 1}).status_code == 202
    assert _post(client, "start", f"{prefix}-start").status_code == 202
    assert _post(client, "enable", f"{prefix}-enable").status_code == 202


def test_advisory_nudge_changes_bid_relative_to_deterministic() -> None:
    session = PaperOpsSession()
    session.bind_active_model(
        model_id="iql-adv",
        registry_state=RegistryState.ADVISORY_APPROVED,
    )
    session.bind_inference(
        StubIqlInference(
            action=HybridAction(ActionCategory.QUOTE, 0.5, 2, -2),
            latency_ms=5.0,
        )
    )
    client = _client(session)
    assert _post(client, "set-mode", "adv", {"mode": "advisory"}).status_code == 202
    _boot(client, "adv-nudge")
    assert _post(client, "tick", "adv-nudge-t0").status_code == 202

    status = client.get("/api/paper/status").json()
    assert status["strategy_mode"] == "advisory"
    assert status["fallback_reason"] is None
    assert status["pause_reason"] is None
    assert status["replay"]["status"] == "running"
    assert status["last_iql_action"]["category"] == "QUOTE"
    assert status["last_iql_action"]["bid_offset_ticks"] == 2

    orders = client.get("/api/paper/orders").json()["orders"]
    open_or_filled = [o for o in orders if o["side"] == "buy"]
    assert open_or_filled
    # Deterministic base is 221; +2 tick nudge → 223
    assert open_or_filled[0]["price"] == "223.00"


def test_advisory_fallback_on_timeout_keeps_replay_running() -> None:
    session = PaperOpsSession()
    session.bind_active_model(
        model_id="iql-adv",
        registry_state=RegistryState.ADVISORY_APPROVED,
    )
    session.bind_inference(
        StubIqlInference(
            action=HybridAction(ActionCategory.QUOTE, 0.5, 2, -2),
            latency_ms=200.0,
        )
    )
    client = _client(session)
    assert _post(client, "set-budget", "budget", {"limit_ms": 100}).status_code == 202
    assert _post(client, "set-mode", "adv", {"mode": "advisory"}).status_code == 202
    _boot(client, "adv-fb")
    assert _post(client, "tick", "adv-fb-t0").status_code == 202

    status = client.get("/api/paper/status").json()
    assert status["fallback_reason"] == "timeout"
    assert status["pause_reason"] is None
    assert status["replay"]["status"] == "running"
    orders = client.get("/api/paper/orders").json()["orders"]
    buy = next(o for o in orders if o["side"] == "buy")
    assert buy["price"] == "221.00"  # deterministic base

    audit_types = [e.event_type for e in session.after(0)]
    assert "strategy.advisory_fallback" in audit_types


def test_advisory_qualification_refused_at_control_plane() -> None:
    session = PaperOpsSession()
    session.bind_active_model(
        model_id="iql-shadow",
        registry_state=RegistryState.SHADOW,
    )
    client = _client(session)
    refused = _post(client, "set-mode", "bad", {"mode": "advisory"})
    assert refused.status_code == 400
    assert client.get("/api/paper/status").json()["strategy_mode"] == "deterministic"


def test_iql_primary_authors_bid_from_market_touch() -> None:
    session = PaperOpsSession()
    session.bind_active_model(
        model_id="iql-prim",
        registry_state=RegistryState.BENCHMARK_QUALIFIED,
    )
    session.bind_inference(
        StubIqlInference(
            action=HybridAction(ActionCategory.QUOTE, 0.5, 3, -3),
            latency_ms=5.0,
        )
    )
    client = _client(session)
    assert _post(client, "set-mode", "prim", {"mode": "iql_primary"}).status_code == 202
    _boot(client, "prim-auth")
    assert _post(client, "tick", "prim-auth-t0").status_code == 202

    status = client.get("/api/paper/status").json()
    assert status["strategy_mode"] == "iql_primary"
    assert status["pause_reason"] is None
    assert status["last_iql_action"]["bid_offset_ticks"] == 3
    buy = next(o for o in client.get("/api/paper/orders").json()["orders"] if o["side"] == "buy")
    # Touch 220 + 3 ticks → 223 (not deterministic 221)
    assert buy["price"] == "223.00"


def test_iql_primary_pauses_on_invalid_and_recovers_via_deterministic() -> None:
    stub = StubIqlInference(fail_with="model_error")
    session = PaperOpsSession()
    session.bind_active_model(
        model_id="iql-prim",
        registry_state=RegistryState.BENCHMARK_QUALIFIED,
    )
    session.bind_inference(stub)
    client = _client(session)
    assert _post(client, "set-mode", "prim", {"mode": "iql_primary"}).status_code == 202
    _boot(client, "prim-pause")
    assert _post(client, "tick", "prim-pause-t0").status_code == 202

    status = client.get("/api/paper/status").json()
    assert status["replay"]["status"] == "paused"
    assert status["pause_reason"] == "iql_unavailable"
    assert status["open_orders"] == 0
    assert any(e.event_type == "replay.paused_iql" for e in session.after(0))

    blocked = _post(client, "resume", "prim-resume-blocked")
    assert blocked.status_code == 400

    assert _post(client, "set-mode", "to-det", {"mode": "deterministic"}).status_code == 202
    assert client.get("/api/paper/status").json()["pause_reason"] == "operator"
    assert _post(client, "resume", "prim-resume-ok").status_code == 202
    assert _post(client, "tick", "prim-det-t1").status_code == 202
    status = client.get("/api/paper/status").json()
    assert status["strategy_mode"] == "deterministic"
    assert status["pause_reason"] is None
    assert status["fills"] >= 0
    assert any(
        o["side"] == "buy" and o["price"] == "221.00"
        for o in client.get("/api/paper/orders").json()["orders"]
    )


def test_iql_primary_recovers_via_healthy_inference() -> None:
    stub = StubIqlInference(fail_with="model_error")
    session = PaperOpsSession()
    session.bind_active_model(
        model_id="iql-prim",
        registry_state=RegistryState.BENCHMARK_QUALIFIED,
    )
    session.bind_inference(stub)
    client = _client(session)
    assert _post(client, "set-mode", "prim", {"mode": "iql_primary"}).status_code == 202
    _boot(client, "prim-heal")
    assert _post(client, "tick", "prim-heal-t0").status_code == 202
    assert client.get("/api/paper/status").json()["pause_reason"] == "iql_unavailable"

    stub.fail_with = None
    stub.action = HybridAction(ActionCategory.QUOTE, 0.5, 0, 0)
    stub.latency_ms = 5.0
    assert _post(client, "resume", "prim-heal-resume").status_code == 202
    assert _post(client, "tick", "prim-heal-t1").status_code == 202
    status = client.get("/api/paper/status").json()
    assert status["pause_reason"] is None
    assert status["replay"]["status"] == "running"
    assert status["last_iql_action"]["bid_offset_ticks"] == 0
    buy = next(o for o in client.get("/api/paper/orders").json()["orders"] if o["side"] == "buy")
    assert buy["price"] == "220.00"
