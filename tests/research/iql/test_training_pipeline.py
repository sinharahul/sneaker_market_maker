from __future__ import annotations

import ast
import json
import sys
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
import torch

from sneaker_market_maker.research.iql.actor import HybridActor
from sneaker_market_maker.research.iql.checkpoint import (
    CheckpointError,
    CheckpointManifest,
    CheckpointStore,
)
from sneaker_market_maker.research.iql.dataset import TransitionDataset
from sneaker_market_maker.research.iql.networks import DistributionalQ, DistributionalValue
from sneaker_market_maker.research.iql.trainer import IQLConfig, IQLTrainer
from tests.persistence.fixtures import transition


class ManifestRepository:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def transitions_for_manifest(self, manifest_id: str) -> tuple[object, ...]:
        assert manifest_id == "run-1"
        return tuple(self.rows)


def test_dataset_excludes_non_trainable_rows_with_reason_counts() -> None:
    accepted = transition()
    quarantined = replace(
        transition(),
        trainability_status="quarantined",
        non_trainable_reason="manual quarantine",
    )
    unreconciled = transition()
    unreconciled = replace(
        unreconciled,
        reward=replace(unreconciled.reward, reconciled=False),
    )

    dataset, exclusions = TransitionDataset.from_repository(
        ManifestRepository([accepted, quarantined, unreconciled]), "run-1"
    )

    assert len(dataset) == 1
    assert exclusions.accepted == 1
    assert exclusions.rejected == 2
    assert exclusions.reasons == {
        "manual quarantine": 1,
        "reward is not reconciled": 1,
    }
    assert dataset.state.shape == (1, 1)
    assert dataset.action.shape == (1, 3)
    assert dataset.category_mask.shape == (1, 3)
    assert dataset.bounds.shape == (1, 2, 2)
    assert dataset.logged_category.tolist() == [1]
    assert dataset.active_dimensions.tolist() == [[True, True, True]]


def test_dataset_rejects_corrupt_non_finite_state() -> None:
    corrupt = replace(transition(), state={"inventory": float("nan")})

    with pytest.raises(ValueError, match="non-finite"):
        TransitionDataset.from_repository(ManifestRepository([corrupt]), "run-1")


def _trainer(seed: int) -> tuple[IQLTrainer, dict[str, torch.Tensor]]:
    torch.manual_seed(seed)
    value = DistributionalValue(1, hidden_dim=8, quantile_count=4)
    q1 = DistributionalQ(1, 3, hidden_dim=8, quantile_count=4)
    q2 = DistributionalQ(1, 3, hidden_dim=8, quantile_count=4)
    actor = HybridActor(1, hidden_dim=8)
    trainer = IQLTrainer(
        value=value,
        q1=q1,
        q2=q2,
        actor=actor,
        value_optimizer=torch.optim.Adam(value.parameters(), lr=0.01),
        q1_optimizer=torch.optim.Adam(q1.parameters(), lr=0.01),
        q2_optimizer=torch.optim.Adam(q2.parameters(), lr=0.01),
        actor_optimizer=torch.optim.Adam(actor.parameters(), lr=0.01),
        fractions=torch.tensor([0.125, 0.375, 0.625, 0.875]),
        config=IQLConfig(
            eta=0.0,
            expectile=0.7,
            kappa=1.0,
            lambda_ce=0.0,
            lambda_cross=0.0,
            beta=0.0,
            exp_clip=5.0,
            max_weight=100.0,
            max_grad_norm=10.0,
            target_tau=0.05,
            target_cadence=1,
        ),
    )
    tensors = {
        f"{label}.{name}": tensor.detach()
        for label, module in (("value", value), ("q1", q1), ("q2", q2), ("actor", actor))
        for name, tensor in module.state_dict().items()
    }
    return trainer, tensors


def _smoke_run(seed: int, checkpoint_path: Path) -> tuple[list[float], str, bool]:
    dataset, _ = TransitionDataset.from_repository(
        ManifestRepository([transition()]), "run-1"
    )
    trainer, initial = _trainer(seed)
    critics_distinct = any(
        not torch.equal(initial[f"q1.{name}"], initial[f"q2.{name}"])
        for name in trainer.q1.state_dict()
    )
    losses: list[list[float]] = []
    for _ in range(120):
        metrics = trainer.step(dataset.as_batch())
        losses.append(
            [
                metrics.value_loss,
                metrics.q1_loss + metrics.q2_loss,
                metrics.actor_loss,
            ]
        )
    tensors = {
        f"{label}.{name}": tensor
        for label, module in (
            ("value", trainer.value),
            ("q1", trainer.q1),
            ("q2", trainer.q2),
            ("actor", trainer.actor),
        )
        for name, tensor in module.state_dict().items()
    }
    manifest = CheckpointManifest(
        architecture="distributional_iql_v1",
        run_manifest_hash="run-hash",
        environment_hash="env-hash",
        step=120,
        tensor_hash="",
        complete=True,
    )
    tensor_hash = CheckpointStore().save(checkpoint_path, manifest, tensors)
    return [sum(item[index] for item in losses[:10]) for index in range(3)] + [
        sum(item[index] for item in losses[-10:]) for index in range(3)
    ], tensor_hash, critics_distinct


def test_seeded_tiny_fixture_overfits_reproducibly(tmp_path: Path) -> None:
    first_losses, first_hash, critics_distinct = _smoke_run(19, tmp_path / "first")
    second_losses, second_hash, _ = _smoke_run(19, tmp_path / "second")

    assert first_losses[3] < first_losses[0]
    assert first_losses[4] < first_losses[1]
    assert first_losses[5] < first_losses[2]
    assert first_hash == second_hash
    assert first_losses == second_losses
    assert critics_distinct


def test_checkpoint_rejects_incomplete_mismatched_and_corrupt_data(
    tmp_path: Path,
) -> None:
    store = CheckpointStore()
    manifest = CheckpointManifest(
        architecture="distributional_iql_v1",
        run_manifest_hash="run-hash",
        environment_hash="env-hash",
        step=2,
        tensor_hash="",
        complete=True,
    )
    checkpoint = tmp_path / "checkpoint"
    tensor_hash = store.save(checkpoint, manifest, {"weight": torch.ones(2)})
    assert tensor_hash == sha256((checkpoint / "weights.safetensors").read_bytes()).hexdigest()
    loaded_manifest, tensors = store.load(checkpoint, "run-hash", "env-hash")
    assert loaded_manifest.tensor_hash == tensor_hash
    torch.testing.assert_close(tensors["weight"], torch.ones(2))

    for field, value, message in (
        ("complete", False, "incomplete"),
        ("architecture", "unknown", "allowlisted"),
        ("run_manifest_hash", "other", "run manifest mismatch"),
        ("environment_hash", "other", "environment mismatch"),
    ):
        payload = json.loads((checkpoint / "manifest.json").read_text())
        payload[field] = value
        (checkpoint / "manifest.json").write_text(json.dumps(payload))
        with pytest.raises(CheckpointError, match=message):
            store.load(checkpoint, "run-hash", "env-hash")
        store.save(checkpoint, manifest, {"weight": torch.ones(2)})

    (checkpoint / "weights.safetensors").write_bytes(b"corrupt")
    with pytest.raises(CheckpointError, match="tensor hash mismatch"):
        store.load(checkpoint, "run-hash", "env-hash")


def test_loaded_iql_modules_do_not_reference_pfhedge() -> None:
    root = Path(__file__).parents[3] / "src/sneaker_market_maker/research/iql"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text())
        assert not any(
            isinstance(node, ast.Import | ast.ImportFrom)
            and (
                getattr(node, "module", "") or getattr(node, "names", [None])[0].name
            ).split(".")[0]
            == "pfhedge"
            for node in ast.walk(tree)
        )
    assert all(
        not any(
            getattr(value, "__name__", "").split(".")[0] == "pfhedge"
            for value in vars(module).values()
        )
        for name, module in sys.modules.items()
        if name.startswith("sneaker_market_maker.research.iql")
    )
