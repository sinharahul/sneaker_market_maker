"""Typed REST ports and routes for governed local research."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from typing_extensions import TypeAliasType

if TYPE_CHECKING:
    from sneaker_market_maker.api.research_events import ResearchEventEnvelope

JsonValue = TypeAliasType(
    "JsonValue",
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"],
)

MAX_PAYLOAD_BYTES = 64 * 1024
READ_RESOURCES = frozenset(
    {
        "manifests",
        "quality",
        "runs",
        "checkpoints",
        "reports",
        "registry",
        "comparisons",
        "recommendations",
    }
)
COMMANDS = frozenset(
    {"create", "cancel", "validate", "register", "shadow", "advisory", "rollback"}
)


class ResearchQueryService(Protocol):
    def get(self, resource: str, resource_id: UUID | None) -> JsonValue:
        """Return one governed research read model or a collection."""


class ResearchCommandService(Protocol):
    def execute(
        self,
        command: str,
        payload: Mapping[str, JsonValue],
        idempotency_key: str,
    ) -> UUID:
        """Atomically apply and audit an idempotent command."""


class ResearchEventService(Protocol):
    def after(self, sequence: int) -> Sequence[ResearchEventEnvelope]:
        """Return event envelopes strictly after a sequence cursor."""


@dataclass(frozen=True)
class ResearchServices:
    query_service: ResearchQueryService
    command_service: ResearchCommandService
    event_service: ResearchEventService


def validate_payload(payload: Mapping[str, JsonValue]) -> None:
    """Reject unbounded or executable/binary-shaped API payloads."""

    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError("payload exceeds 64 KiB")

    pending: list[Mapping[str, JsonValue]] = [payload]
    while pending:
        current = pending.pop()
        for key, value in current.items():
            normalized = key.casefold().replace("-", "_")
            if (
                "code" in normalized
                or "tensor" in normalized
                or "blob" in normalized
            ):
                raise ValueError(f"field '{key}' is not accepted")
            if isinstance(value, dict):
                pending.append(value)
            elif isinstance(value, list):
                pending.extend(item for item in value if isinstance(item, dict))


async def _payload_from(request: Request) -> dict[str, JsonValue]:
    body = await request.body()
    if len(body) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    try:
        payload = json.loads(body or b"{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="request body must be valid JSON",
        ) from error
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="command payload must be a JSON object",
        )
    try:
        validate_payload(payload)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    return payload


def create_research_router(services: ResearchServices) -> APIRouter:
    router = APIRouter(prefix="/api/research", tags=["research"])

    @router.post("/commands/{command}", status_code=status.HTTP_202_ACCEPTED)
    async def execute_command(
        command: str,
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> JSONResponse:
        if command not in COMMANDS:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        if idempotency_key is None or not idempotency_key.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Idempotency-Key is required",
            )
        payload = await _payload_from(request)
        result_id = services.command_service.execute(command, payload, idempotency_key)
        response = {"id": str(result_id), "command_id": str(result_id)}
        if command == "create":
            response["run_id"] = str(result_id)
        return JSONResponse(response, status_code=status.HTTP_202_ACCEPTED)

    @router.get("/{resource}")
    def read_collection(resource: str) -> JsonValue:
        if resource not in READ_RESOURCES:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return services.query_service.get(resource, None)

    @router.get("/{resource}/{resource_id}")
    def read_one(resource: str, resource_id: UUID) -> JsonValue:
        if resource not in READ_RESOURCES:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return services.query_service.get(resource, resource_id)

    return router


__all__ = [
    "JsonValue",
    "ResearchCommandService",
    "ResearchEventService",
    "ResearchQueryService",
    "ResearchServices",
    "create_research_router",
]
