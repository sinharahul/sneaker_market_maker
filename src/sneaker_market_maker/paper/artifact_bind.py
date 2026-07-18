"""Bind registry-pinned IQL checkpoints into the paper Ops inference port."""

from __future__ import annotations

import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import torch

from sneaker_market_maker.paper.decision_state import (
    PAPER_DECISION_FEATURES,
    PaperDecisionState,
)
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.paper.inference import InferenceError
from sneaker_market_maker.paper.mode_path import DEFAULT_BOUNDS, DEFAULT_TRANSLATOR
from sneaker_market_maker.research.contracts.action import (
    ActionCategory,
    ActionMask,
    HybridAction,
    RawHybridAction,
    canonicalize_action,
)
from sneaker_market_maker.research.iql.actor import HybridActor
from sneaker_market_maker.research.iql.checkpoint import (
    CheckpointError,
    CheckpointManifest,
    CheckpointStore,
)
from sneaker_market_maker.research.registry.service import (
    CompatibilityContract,
    RegistryState,
)

OPS_STATE_SCHEMA_VERSION = "paper-decision-v1"
OPS_ACTION_SCHEMA_VERSION = "action-translator-v1"
OPS_ENCODER_VERSION = "paper-decision-encoder-v1"
OPS_ARCHITECTURE = "distributional_iql_v1"
CI_RUN_MANIFEST_HASH = "c" * 64
CI_ENVIRONMENT_HASH = "d" * 64
_CATEGORIES = (ActionCategory.NO_OP, ActionCategory.QUOTE, ActionCategory.CANCEL)
_FULL_MASK = ActionMask(True, True, True)


class ArtifactBindError(PaperError):
    """Fail-closed registry artifact bind / compatibility error."""


@dataclass(frozen=True)
class BoundModelLineage:
    """Lineage surfaced on Ops projections after a successful bind."""

    model_id: str
    registry_state: RegistryState
    artifact_hash: str
    state_schema_version: str
    action_translator_version: str
    encoder_version: str
    checkpoint_dir: str


@dataclass(frozen=True)
class CiPinnedArtifact:
    checkpoint_dir: Path
    artifact_hash: str
    run_manifest_hash: str
    environment_hash: str
    state_dim: int
    compatibility: CompatibilityContract


def assert_ops_compatible(compatibility: CompatibilityContract) -> None:
    """Reject checkpoints that cannot safely drive paper Strategy Modes."""

    if compatibility.architecture != OPS_ARCHITECTURE:
        raise ArtifactBindError(
            "incompatible_architecture",
            f"architecture {compatibility.architecture!r} is not allowlisted for Ops",
        )
    if compatibility.state_schema_version != OPS_STATE_SCHEMA_VERSION:
        raise ArtifactBindError(
            "schema_mismatch",
            f"state schema {compatibility.state_schema_version!r} != {OPS_STATE_SCHEMA_VERSION!r}",
        )
    if compatibility.action_schema_version != OPS_ACTION_SCHEMA_VERSION:
        raise ArtifactBindError(
            "schema_mismatch",
            f"action/translator schema {compatibility.action_schema_version!r} != "
            f"{OPS_ACTION_SCHEMA_VERSION!r}",
        )
    if compatibility.encoder_version != OPS_ENCODER_VERSION:
        raise ArtifactBindError(
            "encoder_mismatch",
            f"encoder {compatibility.encoder_version!r} != {OPS_ENCODER_VERSION!r}",
        )
    if compatibility.action_schema_version != DEFAULT_TRANSLATOR.version:
        raise ArtifactBindError(
            "translator_mismatch",
            "Action Translator version does not match registry action schema",
        )


def encode_paper_decision(state: PaperDecisionState) -> torch.Tensor:
    """Map PaperDecisionState into the fixed Ops encoder feature order."""

    if state.schema_version != OPS_STATE_SCHEMA_VERSION:
        raise InferenceError(
            "schema_mismatch",
            f"decision schema {state.schema_version!r} != {OPS_STATE_SCHEMA_VERSION!r}",
        )
    try:
        values = [float(state.payload[name]) for name in PAPER_DECISION_FEATURES]
    except KeyError as error:
        raise InferenceError(
            "encode_failed",
            f"missing decision feature {error.args[0]!r}",
        ) from error
    return torch.tensor([values], dtype=torch.float32)


class CheckpointIqlInference:
    """Production IqlInferencePort backed by a safetensors HybridActor checkpoint."""

    def __init__(
        self,
        *,
        checkpoint_dir: Path,
        run_manifest_hash: str,
        environment_hash: str,
        state_dim: int,
        bounds=DEFAULT_BOUNDS,
    ) -> None:
        try:
            _manifest, tensors = CheckpointStore().load(
                checkpoint_dir,
                run_manifest_hash,
                environment_hash,
            )
        except CheckpointError as error:
            raise ArtifactBindError("checkpoint_load_failed", str(error)) from error
        self._actor = HybridActor(state_dim, hidden_dim=8)
        actor_state = {
            key.removeprefix("actor."): value
            for key, value in tensors.items()
            if key.startswith("actor.")
        }
        if not actor_state:
            raise ArtifactBindError(
                "checkpoint_load_failed",
                "checkpoint has no actor.* tensors",
            )
        self._actor.load_state_dict(actor_state)
        self._actor.eval()
        self._state_dim = state_dim
        self._bounds = bounds

    def infer(self, state: PaperDecisionState) -> tuple[HybridAction, float]:
        started = time.perf_counter()
        values = encode_paper_decision(state)
        if values.shape[-1] != self._state_dim:
            raise InferenceError(
                "schema_mismatch",
                f"encoded dim {values.shape[-1]} != checkpoint state_dim {self._state_dim}",
            )
        mask_t = torch.tensor(
            [[_FULL_MASK.no_op, _FULL_MASK.quote, _FULL_MASK.cancel]],
            dtype=torch.bool,
        )
        bounds_t = torch.tensor(
            [
                [
                    [float(self._bounds.bid_low), float(self._bounds.ask_low)],
                    [float(self._bounds.bid_high), float(self._bounds.ask_high)],
                ]
            ],
            dtype=torch.float32,
        )
        with torch.no_grad():
            action = self._actor.deterministic(values, mask_t, bounds_t)
        category = _CATEGORIES[int(action.category.reshape(-1)[0].item())]
        continuous = action.continuous.detach().cpu().reshape(-1)
        raw = RawHybridAction(
            category,
            float(continuous[0].item()),
            float(continuous[1].item()),
            float(continuous[2].item()),
        )
        hybrid = canonicalize_action(raw, self._bounds, _FULL_MASK)
        latency_ms = (time.perf_counter() - started) * 1000.0
        return hybrid, latency_ms


def write_ci_pinned_checkpoint(output_dir: Path) -> CiPinnedArtifact:
    """Materialize a tiny deterministic Ops-compatible IQL actor checkpoint."""

    torch.manual_seed(0)
    state_dim = len(PAPER_DECISION_FEATURES)
    actor = HybridActor(state_dim, hidden_dim=8)
    with torch.no_grad():
        # Zero final category weights so large paper features cannot drown the QUOTE bias.
        actor.category_head[-1].weight.zero_()
        actor.category_head[-1].bias.copy_(torch.tensor([-20.0, 20.0, -20.0]))
        actor.mean_head[-1].weight.zero_()
        actor.mean_head[-1].bias.copy_(torch.tensor([0.0, 1.0, -1.0]))
    tensors = {
        f"actor.{name}": tensor.detach().cpu()
        for name, tensor in actor.state_dict().items()
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_hash = CheckpointStore().save(
        output_dir,
        CheckpointManifest(
            architecture=OPS_ARCHITECTURE,
            run_manifest_hash=CI_RUN_MANIFEST_HASH,
            environment_hash=CI_ENVIRONMENT_HASH,
            step=0,
            tensor_hash="",
            complete=True,
        ),
        tensors,
    )
    compatibility = CompatibilityContract(
        state_schema_version=OPS_STATE_SCHEMA_VERSION,
        action_schema_version=OPS_ACTION_SCHEMA_VERSION,
        encoder_version=OPS_ENCODER_VERSION,
        reward_version="paper-reward-v1",
        architecture=OPS_ARCHITECTURE,
        environment_hash=CI_ENVIRONMENT_HASH,
    )
    pinned = CiPinnedArtifact(
        checkpoint_dir=output_dir,
        artifact_hash=artifact_hash,
        run_manifest_hash=CI_RUN_MANIFEST_HASH,
        environment_hash=CI_ENVIRONMENT_HASH,
        state_dim=state_dim,
        compatibility=compatibility,
    )
    _write_ops_lineage(pinned)
    return pinned


def _write_ops_lineage(artifact: CiPinnedArtifact) -> None:
    """Sidecar for REST bind-model (avoids API keys that contain 'code'/'tensor')."""

    import json

    payload = {
        "artifact_hash": artifact.artifact_hash,
        "run_manifest_hash": artifact.run_manifest_hash,
        "environment_hash": artifact.environment_hash,
        "state_dim": artifact.state_dim,
        "state_schema_version": artifact.compatibility.state_schema_version,
        "action_schema_version": artifact.compatibility.action_schema_version,
        "feature_map_version": artifact.compatibility.encoder_version,
        "reward_version": artifact.compatibility.reward_version,
        "architecture": artifact.compatibility.architecture,
    }
    (artifact.checkpoint_dir / "ops_lineage.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n"
    )


def load_ops_lineage(checkpoint_dir: Path) -> CiPinnedArtifact:
    """Load CiPinnedArtifact metadata from an ops_lineage.json sidecar."""

    import json

    payload = json.loads((checkpoint_dir / "ops_lineage.json").read_text())
    compatibility = CompatibilityContract(
        state_schema_version=str(payload["state_schema_version"]),
        action_schema_version=str(payload["action_schema_version"]),
        encoder_version=str(payload["feature_map_version"]),
        reward_version=str(payload.get("reward_version", "paper-reward-v1")),
        architecture=str(payload.get("architecture", OPS_ARCHITECTURE)),
        environment_hash=str(payload["environment_hash"]),
    )
    return CiPinnedArtifact(
        checkpoint_dir=checkpoint_dir,
        artifact_hash=str(payload["artifact_hash"]),
        run_manifest_hash=str(payload["run_manifest_hash"]),
        environment_hash=str(payload["environment_hash"]),
        state_dim=int(payload["state_dim"]),
        compatibility=compatibility,
    )


def default_ci_artifact_dir() -> Path:
    """Repo-relative path for the CI/demo pinned Ops artifact."""

    return (
        Path(__file__).resolve().parents[3]
        / "data"
        / "paper"
        / "artifacts"
        / "iql_ci_v1"
    )


def ensure_ci_pinned_artifact(path: Path | None = None) -> CiPinnedArtifact:
    """Return the CI pin, writing it if the checkpoint is missing."""

    target = path or default_ci_artifact_dir()
    if (target / "weights.safetensors").exists() and (target / "manifest.json").exists():
        if (target / "ops_lineage.json").exists():
            return load_ops_lineage(target)
        artifact_hash = sha256((target / "weights.safetensors").read_bytes()).hexdigest()
        compatibility = CompatibilityContract(
            state_schema_version=OPS_STATE_SCHEMA_VERSION,
            action_schema_version=OPS_ACTION_SCHEMA_VERSION,
            encoder_version=OPS_ENCODER_VERSION,
            reward_version="paper-reward-v1",
            architecture=OPS_ARCHITECTURE,
            environment_hash=CI_ENVIRONMENT_HASH,
        )
        pinned = CiPinnedArtifact(
            checkpoint_dir=target,
            artifact_hash=artifact_hash,
            run_manifest_hash=CI_RUN_MANIFEST_HASH,
            environment_hash=CI_ENVIRONMENT_HASH,
            state_dim=len(PAPER_DECISION_FEATURES),
            compatibility=compatibility,
        )
        _write_ops_lineage(pinned)
        return pinned
    return write_ci_pinned_checkpoint(target)


def bind_checkpoint_to_session(
    session: object,
    *,
    model_id: str | UUID,
    registry_state: RegistryState,
    artifact: CiPinnedArtifact | None = None,
    checkpoint_dir: Path | None = None,
    run_manifest_hash: str | None = None,
    environment_hash: str | None = None,
    artifact_hash: str | None = None,
    compatibility: CompatibilityContract | None = None,
    state_dim: int | None = None,
) -> BoundModelLineage:
    """Fail-closed bind of a registry-compatible checkpoint into a PaperOpsSession."""

    pinned = artifact
    if pinned is None:
        if (
            checkpoint_dir is None
            or run_manifest_hash is None
            or environment_hash is None
            or artifact_hash is None
            or compatibility is None
            or state_dim is None
        ):
            raise ArtifactBindError(
                "incomplete_bind",
                "artifact pin or full checkpoint lineage is required",
            )
        pinned = CiPinnedArtifact(
            checkpoint_dir=checkpoint_dir,
            artifact_hash=artifact_hash,
            run_manifest_hash=run_manifest_hash,
            environment_hash=environment_hash,
            state_dim=state_dim,
            compatibility=compatibility,
        )

    assert_ops_compatible(pinned.compatibility)
    port = CheckpointIqlInference(
        checkpoint_dir=pinned.checkpoint_dir,
        run_manifest_hash=pinned.run_manifest_hash,
        environment_hash=pinned.environment_hash,
        state_dim=pinned.state_dim,
    )
    lineage = BoundModelLineage(
        model_id=str(model_id),
        registry_state=registry_state,
        artifact_hash=pinned.artifact_hash,
        state_schema_version=pinned.compatibility.state_schema_version,
        action_translator_version=pinned.compatibility.action_schema_version,
        encoder_version=pinned.compatibility.encoder_version,
        checkpoint_dir=str(pinned.checkpoint_dir),
    )
    binder = session.apply_bound_artifact
    binder(lineage=lineage, port=port)
    return lineage


__all__ = [
    "OPS_ACTION_SCHEMA_VERSION",
    "OPS_ARCHITECTURE",
    "OPS_ENCODER_VERSION",
    "OPS_STATE_SCHEMA_VERSION",
    "ArtifactBindError",
    "BoundModelLineage",
    "CheckpointIqlInference",
    "CiPinnedArtifact",
    "assert_ops_compatible",
    "bind_checkpoint_to_session",
    "default_ci_artifact_dir",
    "encode_paper_decision",
    "ensure_ci_pinned_artifact",
    "load_ops_lineage",
    "write_ci_pinned_checkpoint",
]
