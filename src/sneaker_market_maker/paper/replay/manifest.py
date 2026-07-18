"""Golden Historical Replay and StockX-shaped fixture manifests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SourceKind = Literal["historical", "fixture"]


@dataclass(frozen=True)
class ReplayManifest:
    dataset_id: str
    version: str
    checksum_sha256: str
    source_kind: SourceKind
    schema_version: str
    allowlist_version: str
    product_families: tuple[str, ...]
