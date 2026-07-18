"""R3 acceptance: golden replay + CI-pinned real IQL artifact (no stub)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sneaker_market_maker.api.app import create_app
from sneaker_market_maker.api.paper_routes import PaperServices
from sneaker_market_maker.api.research_routes import ResearchServices
from sneaker_market_maker.paper.artifact_bind import (
    bind_checkpoint_to_session,
    write_ci_pinned_checkpoint,
)
from sneaker_market_maker.paper.session import PaperOpsSession
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


def _bound_session(tmp_path: Path) -> PaperOpsSession:
    session = PaperOpsSession()
    artifact = write_ci_pinned_checkpoint(tmp_path / "ckpt")
    bind_checkpoint_to_session(
        session,
        model_id="ci-iql-v1",
        registry_state=RegistryState.ADVISORY_APPROVED,
        artifact=artifact,
    )
    return session


def test_bind_model_command_and_projection(tmp_path: Path) -> None:
    artifact = write_ci_pinned_checkpoint(tmp_path / "ckpt")
    session = PaperOpsSession()
    client = _client(session)
    response = _post(
        client,
        "bind-model",
        "bind-1",
        {
            "model_id": "bound-via-rest",
            "registry_state": "advisory_approved",
            "checkpoint_dir": str(artifact.checkpoint_dir),
        },
    )
    assert response.status_code == 202
    status = client.get("/api/paper/status").json()
    assert status["registry"]["model_id"] == "bound-via-rest"
    assert status["registry"]["encoder_version"] == "paper-decision-encoder-v1"
    assert status["registry"]["action_translator_version"] == "action-translator-v1"
    assert status["registry"]["artifact_hash"] == artifact.artifact_hash


def test_advisory_with_real_artifact_nudges_under_gate(tmp_path: Path) -> None:
    session = _bound_session(tmp_path)
    client = _client(session)
    assert _post(client, "set-mode", "adv", {"mode": "advisory"}).status_code == 202
    _boot(client, "real-adv")
    assert _post(client, "tick", "real-adv-t0").status_code == 202

    status = client.get("/api/paper/status").json()
    assert status["strategy_mode"] == "advisory"
    assert status["pause_reason"] is None
    assert status["registry"]["encoder_version"] == "paper-decision-encoder-v1"
    assert status["last_iql_action"] is not None
    assert status["last_iql_action"]["category"] == "QUOTE"
    assert status["last_iql_action"]["source"] == "advisory"
    # Gate remains final: qty stays one on open/filled buys
    orders = client.get("/api/paper/orders").json()["orders"]
    buys = [o for o in orders if o["side"] == "buy"]
    assert buys
    assert all(o["quantity"] == 1 for o in buys)


def test_iql_primary_pause_on_budget_timeout_with_real_port(tmp_path: Path) -> None:
    session = _bound_session(tmp_path)
    client = _client(session)
    assert _post(client, "set-budget", "bud", {"limit_ms": 1}).status_code == 202
    from sneaker_market_maker.paper.artifact_bind import CheckpointIqlInference
    from sneaker_market_maker.paper.decision_state import PaperDecisionState

    lineage = session._bound_lineage
    assert lineage is not None
    real = session._inference
    assert isinstance(real, CheckpointIqlInference)

    class SlowPort:
        def infer(self, state: PaperDecisionState):
            action, _ = real.infer(state)
            return action, 50.0

    session.apply_bound_artifact(lineage=lineage, port=SlowPort())  # type: ignore[arg-type]
    assert _post(client, "set-mode", "pri", {"mode": "iql_primary"}).status_code == 202
    _boot(client, "real-pri")
    assert _post(client, "tick", "real-pri-t0").status_code == 202
    status = client.get("/api/paper/status").json()
    assert status["strategy_mode"] == "iql_primary"
    assert status["pause_reason"] == "iql_unavailable"
    pause_payloads = [
        e.payload for e in session.after(0) if e.event_type == "replay.paused_iql"
    ]
    assert pause_payloads
    assert any(p.get("reason") == "timeout" for p in pause_payloads)


def test_unqualified_mode_still_rejected_with_bound_artifact(tmp_path: Path) -> None:
    session = PaperOpsSession()
    artifact = write_ci_pinned_checkpoint(tmp_path / "ckpt")
    bind_checkpoint_to_session(
        session,
        model_id="candidate-only",
        registry_state=RegistryState.CANDIDATE,
        artifact=artifact,
    )
    client = _client(session)
    response = _post(client, "set-mode", "bad", {"mode": "advisory"})
    assert response.status_code == 400
    assert client.get("/api/paper/status").json()["strategy_mode"] == "deterministic"


def test_deterministic_available_without_qualification(tmp_path: Path) -> None:
    session = _bound_session(tmp_path)
    client = _client(session)
    assert _post(client, "set-mode", "det", {"mode": "deterministic"}).status_code == 202
    _boot(client, "det")
    assert _post(client, "tick", "det-t0").status_code == 202
    status = client.get("/api/paper/status").json()
    assert status["strategy_mode"] == "deterministic"
    assert status["last_iql_action"] is None
