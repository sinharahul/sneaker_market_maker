"""Ordered Paper Ops event envelopes and WebSocket delivery."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket
from pydantic import BaseModel, ConfigDict, field_validator

from sneaker_market_maker.api.paper_routes import PaperEventService
from sneaker_market_maker.api.research_routes import JsonValue, validate_payload


class PaperEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    event_id: UUID
    event_type: str
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


def _as_envelope(item: Any) -> PaperEventEnvelope:
    if isinstance(item, PaperEventEnvelope):
        return item
    return PaperEventEnvelope(
        sequence=item.sequence,
        event_id=item.event_id,
        event_type=item.event_type,
        simulation_time=item.simulation_time,
        wall_time=item.wall_time,
        correlation_id=item.correlation_id,
        payload=dict(item.payload),
    )


def create_paper_event_router(event_service: PaperEventService) -> APIRouter:
    router = APIRouter(prefix="/api/paper", tags=["paper-events"])

    @router.websocket("/events")
    async def events(websocket: WebSocket, after: int = 0) -> None:
        await websocket.accept()
        envelopes = sorted(
            (_as_envelope(item) for item in event_service.after(after)),
            key=lambda item: item.sequence,
        )
        for envelope in envelopes:
            if envelope.sequence > after:
                await websocket.send_json(envelope.model_dump(mode="json"))
        await websocket.close()

    return router


__all__ = ["PaperEventEnvelope", "create_paper_event_router"]
