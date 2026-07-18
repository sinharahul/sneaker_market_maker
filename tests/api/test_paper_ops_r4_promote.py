"""R4 promote/qualify via Paper Ops control plane."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi.testclient import TestClient

from sneaker_market_maker.api.app import create_app
from sneaker_market_maker.api.paper_routes import PaperServices
from sneaker_market_maker.api.research_routes import ResearchServices
from sneaker_market_maker.paper.artifact_bind import (
    bind_checkpoint_to_session,
    write_ci_pinned_checkpoint,
)
from sneaker_market_maker.paper.session import PaperOpsSession
from sneaker_market_maker.research.registry.service import (
    BenchmarkCriterion,
    BenchmarkPolicy,
    CompatibilityContract,
    InMemoryRegistryStore,
    RegistryService,
    RegistryState,
)
from tests.api.test_research_api import Events, Queries, TransactionalCommands

NOW = datetime(2026, 7, 18, tzinfo=timezone.utc)
REPORT_ID = UUID(int=42)
POLICY = BenchmarkPolicy(
    version="promotion-v1",
    criteria=(BenchmarkCriterion("artifact_verified", "required", True),),
    frozen_at=NOW,
)
PASSING = {"artifact_verified": True}
COMPAT = CompatibilityContract(
    state_schema_version="paper-decision-v1",
    action_schema_version="action-translator-v1",
    encoder_version="paper-decision-encoder-v1",
    reward_version="paper-reward-v1",
    architecture="distributional_iql_v1",
    environment_hash="d" * 64,
)


def _registry() -> RegistryService:
    return RegistryService(
        store=InMemoryRegistryStore(),
        benchmark_policy=POLICY,
        benchmark_reports={REPORT_ID: PASSING},
        clock=lambda: NOW,
        id_factory=lambda: UUID(int=99),
    )


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


def test_promote_legal_path_and_projection() -> None:
    session = PaperOpsSession()
    registry = _registry()
    session.attach_registry(registry)
    model = registry.register("a" * 64, COMPAT, REPORT_ID, "researcher")
    client = _client(session)

    for i, target in enumerate(
        ("validated", "shadow", "benchmark_qualified", "advisory_approved")
    ):
        response = _post(
            client,
            "promote-model",
            f"promo-{i}",
            {
                "model_id": str(model.model_id),
                "target": target,
                "actor": "operator",
                "reason": f"promote to {target}",
            },
        )
        assert response.status_code == 202, response.text

    status = client.get("/api/paper/status").json()
    assert status["registry"]["state"] == "advisory_approved"
    assert status["registry"]["model_id"] == str(model.model_id)
    assert "advisory" in status["registry"]["unlocked_modes"]
    assert "iql_primary" in status["registry"]["unlocked_modes"]
    assert status["last_promote"]["actor"] == "operator"
    assert status["last_promote"]["target"] == "advisory_approved"
    assert status["last_promote"]["reason"] == "promote to advisory_approved"

    events = [e for e in session.after(0) if e.event_type == "strategy.model_promoted"]
    assert events
    assert events[-1].payload["actor"] == "operator"


def test_illegal_promote_fails_closed() -> None:
    session = PaperOpsSession()
    registry = _registry()
    session.attach_registry(registry)
    model = registry.register("b" * 64, COMPAT, REPORT_ID, "researcher")
    client = _client(session)
    response = _post(
        client,
        "promote-model",
        "bad",
        {
            "model_id": str(model.model_id),
            "target": "advisory_approved",
            "actor": "operator",
            "reason": "skip ahead",
        },
    )
    assert response.status_code == 400
    assert client.get("/api/paper/status").json()["registry"]["state"] is None
    rejected = [e for e in session.after(0) if e.event_type == "strategy.promote_rejected"]
    assert rejected


def test_promote_then_bind_gate_qty_one(tmp_path) -> None:
    session = PaperOpsSession()
    registry = _registry()
    session.attach_registry(registry)
    model = registry.register("c" * 64, COMPAT, REPORT_ID, "researcher")
    for target in ("validated", "shadow", "benchmark_qualified", "advisory_approved"):
        registry.transition(model.model_id, RegistryState(target), "ops", f"to {target}")

    artifact = write_ci_pinned_checkpoint(tmp_path / "ckpt")
    bind_checkpoint_to_session(
        session,
        model_id=str(model.model_id),
        registry_state=RegistryState.ADVISORY_APPROVED,
        artifact=artifact,
    )
    client = _client(session)
    assert _post(client, "set-mode", "m", {"mode": "advisory"}).status_code == 202
    assert _post(client, "load", "l", {"seed": 7, "speed": 1}).status_code == 202
    assert _post(client, "start", "s").status_code == 202
    assert _post(client, "enable", "e").status_code == 202
    assert _post(client, "tick", "t").status_code == 202
    status = client.get("/api/paper/status").json()
    assert status["strategy_mode"] == "advisory"
    orders = client.get("/api/paper/orders").json()["orders"]
    buys = [o for o in orders if o["side"] == "buy"]
    assert buys
    assert all(o["quantity"] == 1 for o in buys)
