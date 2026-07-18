"""Authoritative Paper Market-Maker persistence (Postgres + in-memory)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sneaker_market_maker.persistence.paper_models import (
    PaperAuditEvent,
    PaperBookSnapshot,
    PersistedFill,
    PersistedLot,
    PersistedOrder,
    json_safe,
)
from sneaker_market_maker.persistence.paper_sql_store import SqlAlchemyPaperStore

__all__ = [
    "InMemoryPaperStore",
    "PaperAuditEvent",
    "PaperBookSnapshot",
    "PersistedFill",
    "PersistedLot",
    "PersistedOrder",
    "SqlAlchemyPaperStore",
]


class InMemoryPaperStore:
    """Non-authoritative double for unit tests — production path is Postgres."""

    def __init__(self) -> None:
        self._runs: dict[UUID, dict[str, Any]] = {}
        self._books: dict[UUID, PaperBookSnapshot] = {}
        self._audit: dict[UUID, list[PaperAuditEvent]] = {}

    def create_run(
        self,
        *,
        dataset_id: str,
        dataset_version: str,
        checksum_sha256: str,
        seed: int,
        status: str = "loaded",
    ) -> UUID:
        run_id = uuid4()
        self._runs[run_id] = {
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "checksum_sha256": checksum_sha256,
            "seed": seed,
            "status": status,
        }
        self._audit[run_id] = []
        return run_id

    def save_book(self, snapshot: PaperBookSnapshot) -> None:
        if snapshot.run_id not in self._runs:
            raise KeyError("unknown paper run")
        self._books[snapshot.run_id] = snapshot

    def load_book(self, run_id: UUID) -> PaperBookSnapshot | None:
        return self._books.get(run_id)

    def append_audit(
        self,
        run_id: UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> int:
        events = self._audit.setdefault(run_id, [])
        sequence = len(events) + 1
        events.append(
            PaperAuditEvent(
                sequence=sequence,
                event_type=event_type,
                payload=json_safe(payload),
                created_at=datetime.now(timezone.utc),
            )
        )
        return sequence

    def list_audit(
        self, run_id: UUID, *, after_sequence: int = 0
    ) -> tuple[PaperAuditEvent, ...]:
        return tuple(e for e in self._audit.get(run_id, []) if e.sequence > after_sequence)
