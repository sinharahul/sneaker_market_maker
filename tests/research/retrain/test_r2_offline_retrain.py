"""R2 offline retrain: manifest → train → harness → OPE → registry."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
import torch

from sneaker_market_maker.research.evaluation.ope import SupportDiagnostics
from sneaker_market_maker.research.registry.service import (
    InMemoryRegistryStore,
    RegistryService,
    RegistryState,
)
from sneaker_market_maker.research.retrain import (
    MixedManifestError,
    build_mixed_dataset_manifest,
    gate_ope,
    register_trained_artifact,
    run_harness_benchmark,
    run_offline_iql_train,
)
from tests.persistence.fixtures import transition
from tests.research.evaluation.test_harness import SimulatorSpy, assumptions, episode
from tests.research.evaluation.test_ope import behavior


def _fixed_rows(*, include_quarantined: bool = False):
    paper = transition()
    historical = replace(transition(), transition_id=uuid4(), episode_id=uuid4())
    extra: tuple = ()
    if include_quarantined:
        quarantined = replace(
            paper,
            transition_id=uuid4(),
            trainability_status="quarantined",
            non_trainable_reason="manual quarantine",
        )
        extra = (quarantined,)
    return paper, historical, extra


def _mix(*, include_quarantined: bool = False):
    paper, historical, extra = _fixed_rows(include_quarantined=include_quarantined)
    return build_mixed_dataset_manifest(
        manifest_id="mix-v1",
        version="1",
        paper_transitions=(paper, *extra),
        historical_transitions=(historical,),
    )


def test_mixed_manifest_hashes_stably_and_excludes_quarantined() -> None:
    paper, historical, extra = _fixed_rows(include_quarantined=True)
    first = build_mixed_dataset_manifest(
        manifest_id="mix-v1",
        version="1",
        paper_transitions=(paper, *extra),
        historical_transitions=(historical,),
    )
    second = build_mixed_dataset_manifest(
        manifest_id="mix-v1",
        version="1",
        paper_transitions=(paper, *extra),
        historical_transitions=(historical,),
    )
    assert first.manifest.content_hash == second.manifest.content_hash
    assert len(first.trainable) == 2
    assert first.manifest.quarantined_ids
    assert all(row.trainability_status == "trainable" for row in first.trainable)


def test_mixed_manifest_fails_closed_without_historical() -> None:
    with pytest.raises(MixedManifestError, match="historical"):
        build_mixed_dataset_manifest(
            manifest_id="mix-v1",
            version="1",
            paper_transitions=(transition(),),
            historical_transitions=(),
        )


def test_offline_train_writes_safetensors_checkpoint(tmp_path: Path) -> None:
    bundle = _mix()
    frozen = assumptions()
    result = run_offline_iql_train(
        bundle=bundle,
        assumptions=frozen,
        output_dir=tmp_path / "ckpt",
        steps=2,
        seed=0,
    )
    assert result.steps == 2
    assert (result.checkpoint_dir / "weights.safetensors").exists()
    assert (result.checkpoint_dir / "manifest.json").exists()
    assert result.assumptions_hash == frozen.content_hash
    assert result.manifest_content_hash == bundle.manifest.content_hash
    assert "value_loss" in result.final_metrics


def test_harness_benchmark_compares_deterministic_and_iql(tmp_path: Path) -> None:
    bundle = _mix()
    frozen = assumptions()
    train = run_offline_iql_train(
        bundle=bundle,
        assumptions=frozen,
        output_dir=tmp_path / "ckpt",
        steps=1,
        seed=1,
    )
    bench = run_harness_benchmark(
        train_result=train,
        episodes=(episode(0), episode(1)),
        assumptions=frozen,
        simulator=SimulatorSpy(),
        state_dim=1,
        bootstrap_samples=5,
    )
    assert bench.deterministic.policy_id == "deterministic"
    assert bench.iql.policy_id == "iql-retrain"
    assert bench.assumptions_hash == frozen.content_hash


def test_ope_gate_invalid_has_no_estimate() -> None:
    report = gate_ope(
        behavior=(behavior(deterministic=True),),
        support=SupportDiagnostics(1.0, 10.0, True),
        nuisance_model_hash="n" * 64,
    )
    assert report.validity.status == "OPE_NOT_VALID"
    assert report.estimate is None


def test_ope_gate_valid_returns_wis() -> None:
    report = gate_ope(
        behavior=(behavior(),),
        support=SupportDiagnostics(1.0, 10.0, True),
        nuisance_model_hash="n" * 64,
        returns=torch.tensor([1.0, 2.0]),
        evaluation_log_prob=torch.tensor([-0.2, -0.3]),
        behavior_log_prob=torch.tensor([-0.5, -0.4]),
    )
    assert report.validity.valid is True
    assert report.estimate is not None
    assert report.estimate.method == "WIS"


def test_registry_register_idempotent(tmp_path: Path) -> None:
    bundle = _mix()
    frozen = assumptions()
    train = run_offline_iql_train(
        bundle=bundle,
        assumptions=frozen,
        output_dir=tmp_path / "ckpt",
        steps=1,
        seed=2,
    )
    registry = RegistryService(store=InMemoryRegistryStore())
    report_id = uuid4()
    first = register_trained_artifact(
        registry=registry,
        train_result=train,
        benchmark_report_id=report_id,
    )
    second = register_trained_artifact(
        registry=registry,
        train_result=train,
        benchmark_report_id=report_id,
    )
    assert first.status == "created"
    assert first.model.state is RegistryState.CANDIDATE
    assert second.status == "existing"
    assert second.model.model_id == first.model.model_id
    assert first.lineage_hash == second.lineage_hash


def test_registry_conflict_on_lineage_mismatch(tmp_path: Path) -> None:
    from sneaker_market_maker.research.retrain.register_job import RegistryConflictError
    from sneaker_market_maker.research.retrain.train_job import TrainJobResult

    bundle = _mix()
    frozen = assumptions()
    train = run_offline_iql_train(
        bundle=bundle,
        assumptions=frozen,
        output_dir=tmp_path / "ckpt",
        steps=1,
        seed=3,
    )
    registry = RegistryService(store=InMemoryRegistryStore())
    register_trained_artifact(
        registry=registry,
        train_result=train,
        benchmark_report_id=uuid4(),
    )
    conflicting = TrainJobResult(
        checkpoint_dir=train.checkpoint_dir,
        tensor_hash=train.tensor_hash,
        assumptions_hash="0" * 64,
        manifest_id=train.manifest_id,
        manifest_content_hash=train.manifest_content_hash,
        steps=train.steps,
        final_metrics=train.final_metrics,
    )
    with pytest.raises(RegistryConflictError, match="lineage"):
        register_trained_artifact(
            registry=registry,
            train_result=conflicting,
            benchmark_report_id=uuid4(),
        )
