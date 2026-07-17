import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

import pytest

from sneaker_market_maker.research.contracts.experiment import (
    EpisodeManifest,
    WalkForwardConfig,
)
from sneaker_market_maker.research.evaluation.splits import WalkForwardSplitter

BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def manifest(
    index: float,
    *,
    episode_id: UUID | None = None,
    lineage: str | None = None,
    source_ids: tuple[str, ...] | None = None,
    provenance: Literal["historical", "synthetic"] = "historical",
    declared_split: Literal["train", "validation", "test"] = "train",
    checksum: str | None = None,
) -> EpisodeManifest:
    start = BASE_TIME + timedelta(days=index)
    return EpisodeManifest(
        episode_id=episode_id or uuid4(),
        start=start,
        end=start + timedelta(hours=12),
        split=declared_split,
        product_size_lineage=lineage or f"sku-{index}/size-10",
        source_record_ids=source_ids or (f"source-{index}",),
        provenance=provenance,
        checksum=checksum or f"checksum-{index}",
    )


def config(**overrides: int) -> WalkForwardConfig:
    values = {
        "train_episodes": 2,
        "validation_episodes": 1,
        "test_episodes": 1,
        "step_episodes": 2,
    }
    values.update(overrides)
    return WalkForwardConfig(**values)


class ScalerSpy:
    def __init__(self) -> None:
        self.fit_calls: list[tuple[UUID, ...]] = []

    def fit(self, episode_ids: tuple[UUID, ...]) -> None:
        self.fit_calls.append(episode_ids)


class EvaluationAdapter:
    def __init__(self, scaler: ScalerSpy) -> None:
        self.scaler = scaler

    def prepare(
        self,
        manifests: tuple[EpisodeManifest, ...],
        split_config: WalkForwardConfig,
    ) -> None:
        folds = WalkForwardSplitter().split(manifests, split_config)
        for fold in folds:
            self.scaler.fit(fold.train_episode_ids)


def export_round_trip(
    manifests: tuple[EpisodeManifest, ...],
) -> tuple[EpisodeManifest, ...]:
    exported = json.dumps([asdict(item) for item in manifests], default=str)
    rows = json.loads(exported)
    return tuple(
        EpisodeManifest(
            episode_id=UUID(row["episode_id"]),
            start=datetime.fromisoformat(row["start"]),
            end=datetime.fromisoformat(row["end"]),
            split=row["split"],
            product_size_lineage=row["product_size_lineage"],
            source_record_ids=tuple(row["source_record_ids"]),
            provenance=row["provenance"],
            checksum=row["checksum"],
        )
        for row in rows
    )


@pytest.mark.parametrize(
    "field",
    ["train_episodes", "validation_episodes", "test_episodes", "step_episodes"],
)
@pytest.mark.parametrize("value", [0, -1])
def test_config_requires_positive_counts(field: str, value: int) -> None:
    with pytest.raises(ValueError, match=field):
        config(**{field: value})


def test_builds_chronological_rolling_folds_from_unsorted_manifests() -> None:
    manifests = tuple(manifest(index) for index in range(6))

    folds = WalkForwardSplitter().split(tuple(reversed(manifests)), config())

    assert len(folds) == 2
    assert folds[0].train_episode_ids == tuple(item.episode_id for item in manifests[0:2])
    assert folds[0].validation_episode_ids == (manifests[2].episode_id,)
    assert folds[0].test_episode_ids == (manifests[3].episode_id,)
    assert folds[1].train_episode_ids == tuple(item.episode_id for item in manifests[2:4])
    assert folds[1].validation_episode_ids == (manifests[4].episode_id,)
    assert folds[1].test_episode_ids == (manifests[5].episode_id,)


def test_rejects_duplicate_source_events_and_names_both_episodes() -> None:
    first = manifest(0, source_ids=("shared",))
    second = manifest(1, source_ids=("shared",))

    with pytest.raises(ValueError) as exc_info:
        WalkForwardSplitter().split((first, second), config(train_episodes=1))

    message = str(exc_info.value)
    assert str(first.episode_id) in message
    assert str(second.episode_id) in message


def test_rejects_overlap_and_names_both_episodes() -> None:
    first = manifest(0)
    second = EpisodeManifest(
        episode_id=uuid4(),
        start=first.end - timedelta(minutes=1),
        end=first.end + timedelta(hours=1),
        split="train",
        product_size_lineage="other/size-10",
        source_record_ids=("other-source",),
        provenance="historical",
        checksum="other-checksum",
    )

    with pytest.raises(ValueError) as exc_info:
        WalkForwardSplitter().split((second, first), config(train_episodes=1))

    message = str(exc_info.value)
    assert str(first.episode_id) in message
    assert str(second.episode_id) in message


def test_rejects_lineage_crossing_fold_partitions_and_names_episodes() -> None:
    first = manifest(0, lineage="shared/size-10")
    crossing = manifest(2, lineage="shared/size-10")
    manifests = (first, manifest(1), crossing, manifest(3))

    with pytest.raises(ValueError) as exc_info:
        WalkForwardSplitter().split(manifests, config())

    message = str(exc_info.value)
    assert str(first.episode_id) in message
    assert str(crossing.episode_id) in message


def test_scaler_adapter_receives_only_fold_training_ids() -> None:
    manifests = tuple(manifest(index) for index in range(4))
    expected = WalkForwardSplitter().split(manifests, config())[0].train_episode_ids
    scaler = ScalerSpy()

    EvaluationAdapter(scaler).prepare(manifests, config())

    assert scaler.fit_calls == [expected]


def test_safety_validation_fails_before_scaler_invocation() -> None:
    scaler = ScalerSpy()
    first = manifest(0, source_ids=("duplicate",))
    duplicate = manifest(1, source_ids=("duplicate",))

    with pytest.raises(ValueError):
        EvaluationAdapter(scaler).prepare(
            (first, duplicate, manifest(2), manifest(3)),
            config(),
        )

    assert scaler.fit_calls == []


def test_augmentation_does_not_shift_historical_windows_or_holdout_hashes() -> None:
    historical = tuple(manifest(index) for index in (0, 2, 4, 6, 8, 10))
    train_stress = manifest(1, provenance="synthetic", declared_split="train")
    validation_stress = manifest(
        3,
        provenance="synthetic",
        declared_split="validation",
    )
    splitter = WalkForwardSplitter()

    baseline = splitter.split(historical, config())
    augmented = splitter.split(
        (*historical, train_stress, validation_stress),
        config(),
    )

    assert len(augmented) == len(baseline) == 2
    assert tuple(fold.test_episode_ids for fold in augmented) == tuple(
        fold.test_episode_ids for fold in baseline
    )
    assert tuple(fold.frozen_holdout_hash for fold in augmented) == tuple(
        fold.frozen_holdout_hash for fold in baseline
    )
    assert augmented[0].train_episode_ids == (
        historical[0].episode_id,
        train_stress.episode_id,
        historical[1].episode_id,
    )
    assert augmented[0].validation_episode_ids == (
        validation_stress.episode_id,
        historical[2].episode_id,
    )


def test_rejects_synthetic_test_augmentation() -> None:
    historical = tuple(manifest(index) for index in (0, 2, 4, 6))
    synthetic_test = manifest(5, provenance="synthetic", declared_split="test")

    with pytest.raises(ValueError, match="synthetic"):
        WalkForwardSplitter().split((*historical, synthetic_test), config())


def test_holdout_hash_is_frozen_and_sensitive_to_test_checksum() -> None:
    manifests = tuple(manifest(index) for index in range(4))
    splitter = WalkForwardSplitter()

    first = splitter.split(manifests, config())[0]
    repeated = splitter.split(tuple(reversed(manifests)), config())[0]
    changed = (*manifests[:3], manifest(3, checksum="changed"))

    assert first.frozen_holdout_hash == repeated.frozen_holdout_hash
    assert first.frozen_holdout_hash != splitter.split(changed, config())[0].frozen_holdout_hash
    assert len(first.frozen_holdout_hash) == 64


def test_historical_provenance_survives_mixed_json_export_round_trip() -> None:
    historical_train = manifest(0, provenance="historical")
    synthetic_train = manifest(1, provenance="synthetic", declared_split="train")
    historical_train_two = manifest(2, provenance="historical")
    historical_validation = manifest(4, provenance="historical")
    historical_test = manifest(6, provenance="historical")
    manifests = (
        historical_train,
        synthetic_train,
        historical_train_two,
        historical_validation,
        historical_test,
    )

    restored = export_round_trip(manifests)

    assert [item.provenance for item in restored] == [
        "historical",
        "synthetic",
        "historical",
        "historical",
        "historical",
    ]
    assert WalkForwardSplitter().split(restored, config())[0].test_episode_ids == (
        historical_test.episode_id,
    )
