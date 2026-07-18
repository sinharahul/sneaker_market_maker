"""Paper Ops Control Plane REST routes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from sneaker_market_maker.api.research_routes import JsonValue, validate_payload

COMMANDS = frozenset(
    {
        "load",
        "start",
        "pause",
        "resume",
        "stop",
        "enable",
        "disable",
        "cancel",
        "tick",
        "set-mode",
        "set-budget",
    }
)
READ_RESOURCES = frozenset(
    {"status", "capital", "orders", "fills", "lots", "pnl", "replay"}
)


class PaperCommandService(Protocol):
    def execute(
        self,
        command: str,
        payload: Mapping[str, JsonValue],
        idempotency_key: str,
    ) -> UUID: ...


class PaperQueryService(Protocol):
    def get(self, resource: str) -> JsonValue: ...


class PaperEventService(Protocol):
    def after(self, sequence: int) -> object: ...


@dataclass(frozen=True)
class PaperServices:
    query_service: PaperQueryService
    command_service: PaperCommandService
    event_service: PaperEventService


async def _payload_from(request: Request) -> dict[str, JsonValue]:
    body = await request.body()
    if len(body) > 64 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    import json

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


def create_paper_router(services: PaperServices) -> APIRouter:
    router = APIRouter(prefix="/api/paper", tags=["paper-ops"])

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
        try:
            result_id = services.command_service.execute(command, payload, idempotency_key)
        except ValueError as error:
            if "idempotency" in str(error).casefold():
                raise HTTPException(status_code=409, detail="idempotency key reused") from error
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        body: dict[str, JsonValue] = {"id": str(result_id), "command_id": str(result_id)}
        if command == "load":
            body["run_id"] = str(result_id)
        return JSONResponse(body, status_code=status.HTTP_202_ACCEPTED)

    @router.get("/{resource}")
    def read_resource(resource: str) -> JsonValue:
        if resource not in READ_RESOURCES:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        try:
            return services.query_service.get(resource)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error

    return router


__all__ = [
    "COMMANDS",
    "PaperCommandService",
    "PaperEventService",
    "PaperQueryService",
    "PaperServices",
    "READ_RESOURCES",
    "create_paper_router",
]
