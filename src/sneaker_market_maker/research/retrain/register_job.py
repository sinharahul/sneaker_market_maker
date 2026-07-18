"""Register a trained IQL artifact into RegistryService (R2-05)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sneaker_market_maker.research.registry.service import (
    CompatibilityContract,
    InMemoryRegistryStore,
    RegistryModel,
    RegistryService,
)
from sneaker_market_maker.research.retrain.train_job import TrainJobResult


class RegistryConflictError(ValueError):
    """Same artifact identity registered with a conflicting lineage hash."""


@dataclass(frozen=True)
class RegisterResult:
    model: RegistryModel
    status: str  # created | existing
    lineage_hash: str


def _lineage_hash(
    *,
    assumptions_hash: str,
    manifest_id: str,
    manifest_content_hash: str,
    metrics: dict[str, float],
) -> str:
    payload = {
        "assumptions_hash": assumptions_hash,
        "manifest_id": manifest_id,
        "manifest_content_hash": manifest_content_hash,
        "metrics": {key: metrics[key] for key in sorted(metrics)},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def register_trained_artifact(
    *,
    registry: RegistryService,
    train_result: TrainJobResult,
    benchmark_report_id: UUID,
    actor: str = "retrain-job",
    state_schema_version: str = "paper-state-v1",
    action_schema_version: str = "paper-action-v1",
    encoder_version: str = "encoder-v1",
    reward_version: str = "paper-reward-v1",
) -> RegisterResult:
    """Register checkpoint as CANDIDATE; idempotent on artifact_hash + lineage."""

    lineage = _lineage_hash(
        assumptions_hash=train_result.assumptions_hash,
        manifest_id=train_result.manifest_id,
        manifest_content_hash=train_result.manifest_content_hash,
        metrics=train_result.final_metrics,
    )
    artifact_hash = train_result.tensor_hash
    compatibility = CompatibilityContract(
        state_schema_version=state_schema_version,
        action_schema_version=action_schema_version,
        encoder_version=encoder_version,
        reward_version=reward_version,
        architecture="distributional_iql_v1",
        environment_hash=lineage,
    )

    store: InMemoryRegistryStore = registry.store  # type: ignore[assignment]
    for existing in store.models.values():
        if existing.artifact_hash == artifact_hash:
            if existing.compatibility.environment_hash != lineage:
                raise RegistryConflictError(
                    "artifact hash already registered with different lineage"
                )
            return RegisterResult(model=existing, status="existing", lineage_hash=lineage)

    model = registry.register(
        artifact_hash,
        compatibility,
        benchmark_report_id,
        actor,
    )
    return RegisterResult(model=model, status="created", lineage_hash=lineage)
