"""Ordered, bounded research event envelopes and WebSocket delivery."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, WebSocket
from pydantic import BaseModel, ConfigDict, field_validator

from sneaker_market_maker.api.research_routes import (
    JsonValue,
    ResearchEventService,
    validate_payload,
)


class ResearchEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    event_id: UUID
    event_type: Literal[
        "run.progress",
        "evaluation.completed",
        "registry.changed",
        "shadow.compared",
        "recommendation.fallback",
        "health.changed",
    ]
    simulation_time: datetime | None
    wall_time: datetime
    correlation_id: UUID
    payload: dict[str, JsonValue]

    @field_validator("sequence")
    @classmethod
    def sequence_is_nonnegative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("sequence must be nonnegative")
        return value

    @field_validator("payload")
    @classmethod
    def payload_is_governed(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        validate_payload(value)
        return value


def create_event_router(event_service: ResearchEventService) -> APIRouter:
    router = APIRouter(prefix="/api/research", tags=["research-events"])

    @router.websocket("/events")
    async def events(websocket: WebSocket, after: int = 0) -> None:
        await websocket.accept()
        envelopes = sorted(event_service.after(after), key=lambda item: item.sequence)
        for envelope in envelopes:
            if envelope.sequence > after:
                await websocket.send_json(envelope.model_dump(mode="json"))
        await websocket.close()

    return router


__all__ = ["ResearchEventEnvelope", "create_event_router"]
