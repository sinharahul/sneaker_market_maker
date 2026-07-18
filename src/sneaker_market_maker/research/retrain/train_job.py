"""Offline IQL train job over a mixed dataset manifest (R2-02)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch

from sneaker_market_maker.research.iql.actor import HybridActor
from sneaker_market_maker.research.iql.checkpoint import CheckpointManifest, CheckpointStore
from sneaker_market_maker.research.iql.dataset import TransitionDataset
from sneaker_market_maker.research.iql.networks import DistributionalQ, DistributionalValue
from sneaker_market_maker.research.iql.trainer import IQLConfig, IQLTrainer
from sneaker_market_maker.research.ports import FrozenAssumptions
from sneaker_market_maker.research.retrain.mixed_manifest import (
    MixedDatasetBundle,
    MixedManifestError,
    MixedManifestRepository,
)


@dataclass(frozen=True)
class TrainJobResult:
    checkpoint_dir: Path
    tensor_hash: str
    assumptions_hash: str
    manifest_id: str
    manifest_content_hash: str
    steps: int
    final_metrics: dict[str, float]


def _tiny_trainer(state_dim: int, seed: int) -> IQLTrainer:
    torch.manual_seed(seed)
    value = DistributionalValue(state_dim, hidden_dim=8, quantile_count=4)
    q1 = DistributionalQ(state_dim, 3, hidden_dim=8, quantile_count=4)
    q2 = DistributionalQ(state_dim, 3, hidden_dim=8, quantile_count=4)
    actor = HybridActor(state_dim, hidden_dim=8)
    return IQLTrainer(
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


def run_offline_iql_train(
    *,
    bundle: MixedDatasetBundle,
    assumptions: FrozenAssumptions,
    output_dir: Path,
    steps: int = 2,
    seed: int = 0,
) -> TrainJobResult:
    """Train distributional IQL on the mixed manifest and write a safetensors checkpoint."""

    if steps < 1:
        raise MixedManifestError("train steps must be positive")
    repo = MixedManifestRepository(bundle)
    dataset, exclusions = TransitionDataset.from_repository(
        repo, bundle.manifest.manifest_id
    )
    if len(dataset) == 0:
        raise MixedManifestError(
            f"no accepted rows after exclusions: {dict(exclusions.reasons)}"
        )
    state_dim = int(dataset.state.shape[-1])
    trainer = _tiny_trainer(state_dim, seed)
    batch = dataset.as_batch()
    metrics: dict[str, float] = {}
    for _ in range(steps):
        step_metrics = trainer.step(batch)
        metrics = {
            "value_loss": float(step_metrics.value_loss),
            "q_loss": float(step_metrics.q1_loss + step_metrics.q2_loss),
            "actor_loss": float(step_metrics.actor_loss),
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    assumptions_hash = assumptions.content_hash
    tensors = {
        f"{label}.{name}": tensor.detach().cpu()
        for label, module in (
            ("value", trainer.value),
            ("q1", trainer.q1),
            ("q2", trainer.q2),
            ("actor", trainer.actor),
        )
        for name, tensor in module.state_dict().items()
    }
    tensor_hash = CheckpointStore().save(
        output_dir,
        CheckpointManifest(
            architecture="distributional_iql_v1",
            run_manifest_hash=bundle.manifest.content_hash,
            environment_hash=assumptions_hash,
            step=steps,
            tensor_hash="",
            complete=True,
        ),
        tensors,
    )
    return TrainJobResult(
        checkpoint_dir=output_dir,
        tensor_hash=tensor_hash,
        assumptions_hash=assumptions_hash,
        manifest_id=bundle.manifest.manifest_id,
        manifest_content_hash=bundle.manifest.content_hash,
        steps=steps,
        final_metrics=metrics,
    )
