"""R1-04/05: export-from-run and golden acceptance at Paper Ops seam."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sneaker_market_maker.api.app import create_app
from sneaker_market_maker.api.paper_routes import PaperServices
from sneaker_market_maker.api.research_routes import ResearchServices
from sneaker_market_maker.paper.session import PaperOpsSession
from sneaker_market_maker.persistence.research_repository import InMemoryResearchRepository
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


def test_export_from_run_persists_trainable_transitions_idempotently() -> None:
    session = PaperOpsSession()
    repo = InMemoryResearchRepository()
    session.bind_transition_repository(repo)
    client = _client(session)

    load = _post(client, "load", "exp-load", {"seed": 7, "speed": 1})
    assert load.status_code == 202
    run_id = load.json()["run_id"]
    assert _post(client, "start", "exp-start").status_code == 202
    assert _post(client, "enable", "exp-enable").status_code == 202
    for index in range(3):
        assert _post(client, "tick", f"exp-tick-{index}").status_code == 202

    first = _post(client, "export-from-run", "exp-export", {"run_id": run_id})
    assert first.status_code == 202
    body = client.get("/api/paper/transitions").json()
    assert body["trainable"] >= 1
    assert body["count"] >= 1
    assert any(
        str(run_id) in row.scenario_version for row in repo.transitions
    )
    trainable_before = body["trainable"]

    second = _post(client, "export-from-run", "exp-export-2", {"run_id": run_id})
    assert second.status_code == 202
    again = client.get("/api/paper/transitions").json()
    assert again["trainable"] == trainable_before
    assert again["count"] == body["count"]


def test_acceptance_golden_run_exports_trainable_batch_with_lineage() -> None:
    session = PaperOpsSession()
    repo = InMemoryResearchRepository()
    session.bind_transition_repository(repo)
    client = _client(session)

    load = _post(client, "load", "acc-load", {"seed": 7, "speed": 1})
    run_id = load.json()["run_id"]
    assert _post(client, "start", "acc-start").status_code == 202
    assert _post(client, "enable", "acc-enable").status_code == 202
    for index in range(3):
        assert _post(client, "tick", f"acc-tick-{index}").status_code == 202

    assert _post(client, "export-from-run", "acc-export", {"run_id": run_id}).status_code == 202

    trainable = [row for row in repo.transitions if row.trainability_status == "trainable"]
    assert len(trainable) >= 1
    assert all(row.episode_id.hex for row in trainable)
    assert all(f"paper-run:{run_id}" == row.scenario_version for row in trainable)
    assert all(row.reward.reconciled for row in trainable)
    assert client.get("/api/paper/capital").json()["initial"] == "2500.00"
