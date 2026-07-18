"""Local loopback research API with demo fixtures and Swagger UI.

Run::

    uvicorn sneaker_market_maker.api.local_demo:app --host 127.0.0.1 --port 8000

Then open http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from sneaker_market_maker.api.app import create_app
from sneaker_market_maker.api.paper_routes import PaperServices
from sneaker_market_maker.api.research_events import ResearchEventEnvelope
from sneaker_market_maker.api.research_routes import JsonValue, ResearchServices
from sneaker_market_maker.paper.session import PaperOpsSession

_QUOTE = {
    "category": "QUOTE",
    "allocation": 0.4,
    "bid_offset_ticks": -1,
    "ask_offset_ticks": 2,
}

COMPARISONS_FIXTURE: dict[str, JsonValue] = {
    "assumptions": {
        "episode_hash": "demo-episodes-sha256",
        "fee_version": "fees-v3",
        "slippage_version": "slippage-v2",
        "logistics_version": "logistics-v4",
        "terminal_policy_version": "terminal-v2",
        "gate_policy_version": "gates-v5",
        "latency_ms": 25,
    },
    "tracks": [
        {
            "id": "deterministic",
            "kind": "deterministic",
            "name": "Deterministic",
            "provenance": "historical",
            "ope": {"valid": True, "summary": "Supported historical evaluation"},
            "netReturn": {"point": 0.12, "lower": 0.08, "upper": 0.16},
        },
        {
            "id": "pfhedge",
            "kind": "pfhedge",
            "name": "PFHedge",
            "provenance": "synthetic",
            "ope": {"valid": False, "summary": "Missing trustworthy propensities"},
            "netReturn": {"point": 0.1, "lower": 0.04, "upper": 0.14},
        },
        {
            "id": "iql",
            "kind": "iql",
            "name": "IQL",
            "provenance": "historical",
            "ope": {"valid": True, "summary": "WIS supported"},
            "netReturn": {"point": 0.14, "lower": 0.09, "upper": 0.18},
        },
    ],
    "registry": {
        "model_id": "00000000-0000-0000-0000-000000000019",
        "artifact_hash": "a" * 64,
        "compatibility": {
            "state_schema_version": "state-v1",
            "action_schema_version": "action-v1",
            "encoder_version": "encoder-v1",
            "reward_version": "reward-v1",
            "architecture": "distributional_iql_v1",
            "environment_hash": "b" * 64,
        },
        "benchmark_report_id": "00000000-0000-0000-0000-000000000020",
        "state": "shadow",
        "created_at": "2026-07-17T12:00:00Z",
    },
    "trace": {
        "request_id": "00000000-0000-0000-0000-000000000022",
        "deterministic_action": {**_QUOTE, "allocation": 0.4},
        "pfhedge_action": {**_QUOTE, "allocation": 0.6},
        "iql_action": _QUOTE,
        "canonical_action": _QUOTE,
        "gate_results": [["schema", True], ["capital", True]],
        "final_action": {
            "category": "NO_OP",
            "allocation": 0,
            "bid_offset_ticks": 0,
            "ask_offset_ticks": 0,
        },
        "fallback_reason": None,
    },
}


class DemoQueryService:
    """Serves fixture read models for local Swagger / research UI demos."""

    def get(self, resource: str, resource_id: UUID | None) -> JsonValue:
        if resource == "comparisons":
            return deepcopy(COMPARISONS_FIXTURE)
        if resource == "registry":
            return deepcopy(COMPARISONS_FIXTURE["registry"])
        if resource == "recommendations":
            return deepcopy(COMPARISONS_FIXTURE["trace"])
        payload: dict[str, JsonValue] = {
            "resource": resource,
            "demo": True,
            "message": "Local demo fixture — not live marketplace data",
        }
        if resource_id is not None:
            payload["resource_id"] = str(resource_id)
        return payload


class DemoCommandService:
    def __init__(self) -> None:
        self._results: dict[str, tuple[str, UUID]] = {}
        self.audit: list[dict[str, object]] = []

    def execute(
        self,
        command: str,
        payload: Mapping[str, JsonValue],
        idempotency_key: str,
    ) -> UUID:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        previous = self._results.get(idempotency_key)
        if previous is not None:
            if previous[0] != normalized:
                raise HTTPException(status_code=409, detail="idempotency key reused")
            return previous[1]
        result = uuid4()
        self._results[idempotency_key] = (normalized, result)
        self.audit.append(
            {"command": command, "idempotency_key": idempotency_key, "id": str(result)}
        )
        return result


class DemoEventService:
    def __init__(self) -> None:
        now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
        self._events: tuple[ResearchEventEnvelope, ...] = (
            ResearchEventEnvelope(
                sequence=1,
                event_id=UUID(int=1),
                event_type="health.changed",
                simulation_time=None,
                wall_time=now,
                correlation_id=UUID(int=99),
                payload={"healthy": True},
            ),
            ResearchEventEnvelope(
                sequence=2,
                event_id=UUID(int=2),
                event_type="shadow.compared",
                simulation_time=None,
                wall_time=now,
                correlation_id=UUID(int=99),
                payload={"registry_state": "shadow"},
            ),
        )

    def after(self, sequence: int) -> Sequence[ResearchEventEnvelope]:
        return tuple(event for event in self._events if event.sequence > sequence)


def build_demo_services() -> ResearchServices:
    return ResearchServices(
        query_service=DemoQueryService(),
        command_service=DemoCommandService(),
        event_service=DemoEventService(),
    )


def create_demo_app():
    """FastAPI app factory for uvicorn `--factory` with Swagger at `/docs`."""

    paper = PaperOpsSession()
    application = create_app(
        build_demo_services(),
        paper_services=PaperServices(
            query_service=paper,
            command_service=paper,
            event_service=paper,
        ),
        bind_host="127.0.0.1",
    )
    application.title = "Sneaker Market Maker Local Control Plane"
    application.description = (
        "Loopback demo: research comparisons plus Paper Ops Control Plane. "
        "Guided React demo is fixture-only; `/?view=research` loads research; "
        "`/?view=ops` drives `/api/paper`."
    )

    @application.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    return application


app = create_demo_app()

__all__ = [
    "COMPARISONS_FIXTURE",
    "DemoCommandService",
    "DemoEventService",
    "DemoQueryService",
    "app",
    "build_demo_services",
    "create_demo_app",
]
