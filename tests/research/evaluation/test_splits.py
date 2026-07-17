from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from sneaker_market_maker.research.contracts.experiment import (
    EpisodeManifest,
    WalkForwardConfig,
)
from sneaker_market_maker.research.evaluation.splits import WalkForwardSplitter

BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def manifest(
    index: int,
    *,
    episode_id: UUID | None = None,
    lineage: str | None = None,
    source_ids: tuple[str, ...] | None = None,
    provenance: str = "historical",
    declared_split: str = "train",
    checksum: str | None = None,
) -> EpisodeManifest:
    start = BASE_TIME + timedelta(days=index)
    return EpisodeManifest(
        episode_id=episode_id or uuid4(),
        start=start,
        end=start + timedelta(hours=12),
        split=declared_split,  # type: ignore[arg-type]
        product_size_lineage=lineage or f"sku-{index}/size-10",
        source_record_ids=source_ids or (f"source-{index}",),
        provenance=provenance,  # type: ignore[arg-type]
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


def test_safety_validation_fails_before_scaler_fitting() -> None:
    fit_calls: list[tuple[UUID, ...]] = []
    first = manifest(0, source_ids=("duplicate",))
    duplicate = manifest(1, source_ids=("duplicate",))

    with pytest.raises(ValueError):
        folds = WalkForwardSplitter().split(
            (first, duplicate, manifest(2), manifest(3)),
            config(),
        )
        fit_calls.append(folds[0].train_episode_ids)

    assert fit_calls == []


def test_fold_exposes_only_training_ids_for_scaler_fit() -> None:
    manifests = tuple(manifest(index) for index in range(4))
    fold = WalkForwardSplitter().split(manifests, config())[0]
    fitted_episode_ids: list[UUID] = []

    fitted_episode_ids.extend(fold.train_episode_ids)

    assert tuple(fitted_episode_ids) == tuple(item.episode_id for item in manifests[:2])
    assert not set(fitted_episode_ids) & set(fold.validation_episode_ids)
    assert not set(fitted_episode_ids) & set(fold.test_episode_ids)


def test_allows_train_and_declared_validation_stress_augmentation() -> None:
    train_stress = manifest(0, provenance="synthetic", declared_split="train")
    validation_stress = manifest(
        2,
        provenance="synthetic",
        declared_split="validation",
    )

    folds = WalkForwardSplitter().split(
        (train_stress, manifest(1), validation_stress, manifest(3)),
        config(),
    )

    assert folds[0].train_episode_ids[0] == train_stress.episode_id
    assert folds[0].validation_episode_ids == (validation_stress.episode_id,)


@pytest.mark.parametrize(
    ("synthetic_index", "declared_split"),
    [(2, "train"), (3, "test")],
)
def test_rejects_undeclared_validation_or_test_augmentation(
    synthetic_index: int,
    declared_split: str,
) -> None:
    manifests = [
        manifest(
            index,
            provenance="synthetic" if index == synthetic_index else "historical",
            declared_split=declared_split if index == synthetic_index else "train",
        )
        for index in range(4)
    ]

    with pytest.raises(ValueError, match="synthetic"):
        WalkForwardSplitter().split(manifests, config())


def test_holdout_hash_is_frozen_and_sensitive_to_test_checksum() -> None:
    manifests = tuple(manifest(index) for index in range(4))
    splitter = WalkForwardSplitter()

    first = splitter.split(manifests, config())[0]
    repeated = splitter.split(tuple(reversed(manifests)), config())[0]
    changed = (*manifests[:3], manifest(3, checksum="changed"))

    assert first.frozen_holdout_hash == repeated.frozen_holdout_hash
    assert first.frozen_holdout_hash != splitter.split(changed, config())[0].frozen_holdout_hash
    assert len(first.frozen_holdout_hash) == 64


def test_historical_labels_survive_mixed_exports() -> None:
    historical_train = manifest(0, provenance="historical")
    synthetic_train = manifest(1, provenance="synthetic", declared_split="train")
    historical_validation = manifest(2, provenance="historical")
    historical_test = manifest(3, provenance="historical")
    manifests = (
        historical_train,
        synthetic_train,
        historical_validation,
        historical_test,
    )

    fold = WalkForwardSplitter().split(manifests, config())[0]

    assert historical_train.provenance == "historical"
    assert historical_validation.provenance == "historical"
    assert historical_test.provenance == "historical"
    assert fold.test_episode_ids == (historical_test.episode_id,)
