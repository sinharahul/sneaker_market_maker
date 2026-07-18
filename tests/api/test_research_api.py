import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from sneaker_market_maker.api.app import DEFAULT_BIND_HOST, create_app
from sneaker_market_maker.api.research_events import ResearchEventEnvelope
from sneaker_market_maker.api.research_routes import JsonValue, ResearchServices

RESOURCES = (
    "manifests",
    "quality",
    "runs",
    "checkpoints",
    "reports",
    "registry",
    "comparisons",
    "recommendations",
)
COMMANDS = ("create", "cancel", "validate", "register", "shadow", "advisory", "rollback")


class Queries:
    def __init__(self) -> None:
        self.calls: list[tuple[str, UUID | None]] = []

    def get(self, resource: str, resource_id: UUID | None) -> JsonValue:
        self.calls.append((resource, resource_id))
        return {"resource": resource, "resource_id": str(resource_id) if resource_id else None}


class TransactionalCommands:
    """In-memory double that commits state and audit records atomically."""

    def __init__(self) -> None:
        self.state: list[dict[str, object]] = []
        self.audit: list[dict[str, object]] = []
        self.results: dict[str, tuple[str, UUID]] = {}
        self.fail_after_state = False

    def execute(
        self,
        command: str,
        payload: Mapping[str, JsonValue],
        idempotency_key: str,
    ) -> UUID:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        previous = self.results.get(idempotency_key)
        if previous is not None:
            if previous[0] != normalized:
                raise HTTPException(status_code=409, detail="idempotency key reused")
            return previous[1]

        staged_state = deepcopy(self.state)
        staged_audit = deepcopy(self.audit)
        result = UUID(int=len(self.results) + 100)
        staged_state.append({"command": command, "payload": dict(payload), "id": result})
        if self.fail_after_state:
            raise RuntimeError("injected transaction failure")
        staged_audit.append({"command": command, "idempotency_key": idempotency_key})
        self.state, self.audit = staged_state, staged_audit
        self.results[idempotency_key] = (normalized, result)
        return result


class Events:
    def __init__(self, events: Sequence[ResearchEventEnvelope] = ()) -> None:
        self.events = tuple(events)
        self.calls: list[int] = []

    def after(self, sequence: int) -> Sequence[ResearchEventEnvelope]:
        self.calls.append(sequence)
        return tuple(event for event in self.events if event.sequence > sequence)


def services(
    events: Sequence[ResearchEventEnvelope] = (),
) -> tuple[ResearchServices, Queries, TransactionalCommands, Events]:
    queries = Queries()
    commands = TransactionalCommands()
    event_store = Events(events)
    return ResearchServices(queries, commands, event_store), queries, commands, event_store


def event(sequence: int) -> ResearchEventEnvelope:
    return ResearchEventEnvelope(
        sequence=sequence,
        event_id=UUID(int=sequence),
        event_type="run.progress",
        simulation_time=None,
        wall_time=datetime(2026, 7, 17, tzinfo=timezone.utc),
        correlation_id=UUID(int=99),
        payload={"progress": sequence / 10},
    )


def test_reads_are_limited_to_governed_resources() -> None:
    injected, queries, _, _ = services()
    client = TestClient(create_app(injected))
    resource_id = UUID(int=7)

    for resource in RESOURCES:
        assert client.get(f"/api/research/{resource}").status_code == 200
        response = client.get(f"/api/research/{resource}/{resource_id}")
        assert response.status_code == 200
        assert response.json()["resource_id"] == str(resource_id)

    assert len(queries.calls) == len(RESOURCES) * 2
    assert client.get("/api/research/secrets").status_code == 404


@pytest.mark.parametrize("command", COMMANDS)
def test_commands_require_idempotency_and_return_stable_durable_ids(command: str) -> None:
    injected, _, commands, _ = services()
    client = TestClient(create_app(injected), raise_server_exceptions=False)
    url = f"/api/research/commands/{command}"

    assert client.post(url, json={"run": "offline"}).status_code == 400
    first = client.post(url, json={"run": "offline"}, headers={"Idempotency-Key": command})
    retried = client.post(url, json={"run": "offline"}, headers={"Idempotency-Key": command})

    assert first.status_code == 202
    assert first.json() == retried.json()
    assert UUID(first.json()["id"]) == commands.state[-1]["id"]
    assert len(commands.state) == len(commands.audit) == 1


def test_command_double_rolls_back_state_and_audit_together() -> None:
    injected, _, commands, _ = services()
    commands.fail_after_state = True
    client = TestClient(create_app(injected), raise_server_exceptions=False)

    response = client.post(
        "/api/research/commands/create",
        json={"run": "offline"},
        headers={"Idempotency-Key": "failed"},
    )

    assert response.status_code == 500
    assert commands.state == []
    assert commands.audit == []


@pytest.mark.parametrize(
    "payload",
    [
        {"model_code": "print('unsafe')"},
        {"nested": {"tensor": [1.0, 2.0]}},
        {"artifact_blob": "AAAA"},
    ],
)
def test_commands_reject_code_tensor_and_blob_fields(payload: dict[str, object]) -> None:
    injected, _, commands, _ = services()
    client = TestClient(create_app(injected))

    response = client.post(
        "/api/research/commands/register",
        json=payload,
        headers={"Idempotency-Key": "unsafe"},
    )

    assert response.status_code == 422
    assert commands.state == []


def test_commands_reject_payloads_over_64_kib() -> None:
    injected, _, commands, _ = services()
    client = TestClient(create_app(injected))

    response = client.post(
        "/api/research/commands/create",
        content=json.dumps({"description": "x" * (64 * 1024)}),
        headers={"Content-Type": "application/json", "Idempotency-Key": "large"},
    )

    assert response.status_code == 413
    assert commands.state == []


def test_websocket_sends_events_in_sequence_order_after_cursor() -> None:
    injected, _, _, event_store = services((event(3), event(1), event(2)))
    client = TestClient(create_app(injected))

    with client.websocket_connect("/api/research/events?after=1") as websocket:
        received = [websocket.receive_json(), websocket.receive_json()]

    assert [item["sequence"] for item in received] == [2, 3]
    assert event_store.calls == [1]


def test_default_is_loopback_and_external_binding_requires_authentication() -> None:
    injected, _, _, _ = services()
    app = create_app(injected)
    assert DEFAULT_BIND_HOST == "127.0.0.1"
    assert app.state.bind_host == DEFAULT_BIND_HOST

    with pytest.raises(ValueError, match="authentication"):
        create_app(injected, bind_host="0.0.0.0")

    authenticated = create_app(injected, bind_host="0.0.0.0", authentication=lambda: None)
    assert TestClient(authenticated).get("/api/research/runs").status_code == 200
