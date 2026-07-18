"""Mixed paper + historical dataset manifest (R2-01)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from sneaker_market_maker.research.contracts.transition import OfflineTransition


class MixedManifestError(ValueError):
    """Fail-closed mixed dataset construction error."""


@dataclass(frozen=True)
class MixedDatasetManifest:
    manifest_id: str
    version: str
    paper_transition_ids: tuple[str, ...]
    historical_transition_ids: tuple[str, ...]
    quarantined_ids: tuple[str, ...]
    content_hash: str

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MixedDatasetBundle:
    manifest: MixedDatasetManifest
    trainable: tuple[OfflineTransition, ...]


def _hash_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_mixed_dataset_manifest(
    *,
    manifest_id: str,
    version: str,
    paper_transitions: Sequence[OfflineTransition],
    historical_transitions: Sequence[OfflineTransition],
) -> MixedDatasetBundle:
    """Join paper + historical transitions; exclude quarantined from trainable set."""

    if not manifest_id.strip() or not version.strip():
        raise MixedManifestError("manifest_id and version are required")
    if not paper_transitions:
        raise MixedManifestError("paper export is missing")
    if not historical_transitions:
        raise MixedManifestError("historical pin is missing")

    trainable: list[OfflineTransition] = []
    quarantined: list[str] = []
    paper_ids: list[str] = []
    historical_ids: list[str] = []

    paper_id_set = {str(row.transition_id) for row in paper_transitions}
    historical_id_set = {str(row.transition_id) for row in historical_transitions}

    for row in (*paper_transitions, *historical_transitions):
        tid = str(row.transition_id)
        if tid in paper_id_set and tid not in paper_ids:
            paper_ids.append(tid)
        if tid in historical_id_set and tid not in historical_ids:
            historical_ids.append(tid)
        if row.trainability_status != "trainable":
            quarantined.append(tid)
            continue
        try:
            row.validate_trainable()
        except Exception:
            quarantined.append(tid)
            continue
        trainable.append(row)

    if not trainable:
        raise MixedManifestError("no trainable transitions in mix")

    # Stable id lists (sorted) for hashing — membership uses original order lists
    payload = {
        "manifest_id": manifest_id,
        "version": version,
        "paper_transition_ids": sorted(set(paper_ids)),
        "historical_transition_ids": sorted(set(historical_ids)),
        "quarantined_ids": sorted(set(quarantined)),
        "trainable_content_hashes": sorted(row.content_hash for row in trainable),
    }
    manifest = MixedDatasetManifest(
        manifest_id=manifest_id,
        version=version,
        paper_transition_ids=tuple(paper_ids),
        historical_transition_ids=tuple(historical_ids),
        quarantined_ids=tuple(quarantined),
        content_hash=_hash_payload(payload),
    )
    return MixedDatasetBundle(manifest=manifest, trainable=tuple(trainable))


class MixedManifestRepository:
    """ManifestTransitionRepository backed by a MixedDatasetBundle."""

    def __init__(self, bundle: MixedDatasetBundle) -> None:
        self._bundle = bundle

    def transitions_for_manifest(self, manifest_id: str) -> Sequence[OfflineTransition]:
        if manifest_id != self._bundle.manifest.manifest_id:
            raise MixedManifestError(
                f"unknown mixed manifest: {manifest_id}"
            )
        return self._bundle.trainable
