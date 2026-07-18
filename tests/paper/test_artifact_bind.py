"""R3 artifact bind: registry checkpoint → Ops inference port."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from sneaker_market_maker.paper.artifact_bind import (
    OPS_ACTION_SCHEMA_VERSION,
    OPS_ENCODER_VERSION,
    OPS_STATE_SCHEMA_VERSION,
    ArtifactBindError,
    CheckpointIqlInference,
    assert_ops_compatible,
    bind_checkpoint_to_session,
    write_ci_pinned_checkpoint,
)
from sneaker_market_maker.paper.decision_state import PaperDecisionState
from sneaker_market_maker.paper.inference import InferenceLatencyBudget, TimedIqlInference
from sneaker_market_maker.paper.session import PaperOpsSession
from sneaker_market_maker.research.contracts.action import ActionCategory
from sneaker_market_maker.research.registry.service import RegistryState
from tests.paper.test_inference import _state


def test_compatible_checkpoint_binds_and_infers(tmp_path: Path) -> None:
    artifact = write_ci_pinned_checkpoint(tmp_path / "ckpt")
    assert_ops_compatible(artifact.compatibility)
    port = CheckpointIqlInference(
        checkpoint_dir=artifact.checkpoint_dir,
        run_manifest_hash=artifact.run_manifest_hash,
        environment_hash=artifact.environment_hash,
        state_dim=artifact.state_dim,
    )
    action, latency_ms = port.infer(_state())
    assert action.category is ActionCategory.QUOTE
    assert latency_ms >= 0.0


def test_schema_mismatch_fails_closed_at_bind(tmp_path: Path) -> None:
    artifact = write_ci_pinned_checkpoint(tmp_path / "ckpt")
    bad = replace(
        artifact.compatibility,
        state_schema_version="research-state-v9",
    )
    with pytest.raises(ArtifactBindError) as exc:
        assert_ops_compatible(bad)
    assert exc.value.code == "schema_mismatch"

    session = PaperOpsSession()
    with pytest.raises(ArtifactBindError):
        bind_checkpoint_to_session(
            session,
            model_id="bad",
            registry_state=RegistryState.ADVISORY_APPROVED,
            artifact=replace(artifact, compatibility=bad),
        )


def test_encoder_mismatch_fails_closed(tmp_path: Path) -> None:
    artifact = write_ci_pinned_checkpoint(tmp_path / "ckpt")
    bad = replace(artifact.compatibility, encoder_version="wrong-encoder")
    with pytest.raises(ArtifactBindError) as exc:
        assert_ops_compatible(bad)
    assert exc.value.code == "encoder_mismatch"


def test_session_bind_sets_lineage_on_status(tmp_path: Path) -> None:
    artifact = write_ci_pinned_checkpoint(tmp_path / "ckpt")
    session = PaperOpsSession()
    lineage = bind_checkpoint_to_session(
        session,
        model_id="ops-model-1",
        registry_state=RegistryState.ADVISORY_APPROVED,
        artifact=artifact,
    )
    status = session.get("status")
    registry = status["registry"]
    assert registry["model_id"] == "ops-model-1"
    assert registry["state"] == "advisory_approved"
    assert registry["artifact_hash"] == lineage.artifact_hash
    assert registry["encoder_version"] == OPS_ENCODER_VERSION
    assert registry["state_schema_version"] == OPS_STATE_SCHEMA_VERSION
    assert registry["action_translator_version"] == OPS_ACTION_SCHEMA_VERSION


def test_stub_bind_clears_lineage_versions(tmp_path: Path) -> None:
    from sneaker_market_maker.paper.inference import StubIqlInference
    from sneaker_market_maker.research.contracts.action import HybridAction

    artifact = write_ci_pinned_checkpoint(tmp_path / "ckpt")
    session = PaperOpsSession()
    bind_checkpoint_to_session(
        session,
        model_id="ops-model-1",
        registry_state=RegistryState.ADVISORY_APPROVED,
        artifact=artifact,
    )
    session.bind_inference(
        StubIqlInference(action=HybridAction(ActionCategory.NO_OP, 0.0, 0, 0))
    )
    registry = session.get("status")["registry"]
    assert registry["artifact_hash"] is None
    assert registry["encoder_version"] is None


def test_wall_clock_latency_can_timeout(tmp_path: Path) -> None:
    artifact = write_ci_pinned_checkpoint(tmp_path / "ckpt")
    port = CheckpointIqlInference(
        checkpoint_dir=artifact.checkpoint_dir,
        run_manifest_hash=artifact.run_manifest_hash,
        environment_hash=artifact.environment_hash,
        state_dim=artifact.state_dim,
    )

    class _Slow(CheckpointIqlInference):
        def infer(self, state: PaperDecisionState):
            action, _latency = port.infer(state)
            return action, 999.0

    timed = TimedIqlInference(
        _Slow(
            checkpoint_dir=artifact.checkpoint_dir,
            run_manifest_hash=artifact.run_manifest_hash,
            environment_hash=artifact.environment_hash,
            state_dim=artifact.state_dim,
        ),
        budget=InferenceLatencyBudget(limit_ms=100),
    )
    outcome = timed.infer(_state())
    assert outcome.valid is False
    assert outcome.reason == "timeout"
