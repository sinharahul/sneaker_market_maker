"""R2 offline retrain package."""

from sneaker_market_maker.research.retrain.benchmark import (
    BenchmarkResult,
    CheckpointIqlPolicyAdapter,
    run_harness_benchmark,
)
from sneaker_market_maker.research.retrain.mixed_manifest import (
    MixedDatasetBundle,
    MixedDatasetManifest,
    MixedManifestError,
    MixedManifestRepository,
    build_mixed_dataset_manifest,
)
from sneaker_market_maker.research.retrain.ope_gate import OPEReport, gate_ope
from sneaker_market_maker.research.retrain.register_job import (
    RegisterResult,
    RegistryConflictError,
    register_trained_artifact,
)
from sneaker_market_maker.research.retrain.train_job import TrainJobResult, run_offline_iql_train

__all__ = [
    "BenchmarkResult",
    "CheckpointIqlPolicyAdapter",
    "MixedDatasetBundle",
    "MixedDatasetManifest",
    "MixedManifestError",
    "MixedManifestRepository",
    "OPEReport",
    "RegisterResult",
    "RegistryConflictError",
    "TrainJobResult",
    "build_mixed_dataset_manifest",
    "gate_ope",
    "register_trained_artifact",
    "run_harness_benchmark",
    "run_offline_iql_train",
]
