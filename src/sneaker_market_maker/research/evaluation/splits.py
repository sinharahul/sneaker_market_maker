"""Leakage-safe walk-forward fold generation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from sneaker_market_maker.research.contracts.experiment import (
    EpisodeManifest,
    Fold,
    WalkForwardConfig,
)


class WalkForwardSplitter:
    def split(
        self,
        manifests: Sequence[EpisodeManifest],
        config: WalkForwardConfig,
    ) -> tuple[Fold, ...]:
        """Validate episode safety before returning chronological rolling folds."""
        ordered = tuple(sorted(manifests, key=lambda item: item.start))
        self._assert_unique_sources(ordered)
        self._assert_non_overlapping(ordered)
        folds = self._window(ordered, config)
        self._assert_lineage_isolated(folds, ordered)
        self._assert_augmentation_isolated(folds, ordered)
        return folds

    @staticmethod
    def _assert_unique_sources(manifests: Sequence[EpisodeManifest]) -> None:
        episodes: dict[object, EpisodeManifest] = {}
        sources: dict[str, EpisodeManifest] = {}
        for manifest in manifests:
            existing_episode = episodes.get(manifest.episode_id)
            if existing_episode is not None:
                raise ValueError(
                    "duplicate episode ID between "
                    f"{existing_episode.episode_id} and {manifest.episode_id}"
                )
            episodes[manifest.episode_id] = manifest
            for source_id in manifest.source_record_ids:
                existing_source = sources.get(source_id)
                if existing_source is not None:
                    raise ValueError(
                        f"source record {source_id!r} is duplicated between episodes "
                        f"{existing_source.episode_id} and {manifest.episode_id}"
                    )
                sources[source_id] = manifest

    @staticmethod
    def _assert_non_overlapping(manifests: Sequence[EpisodeManifest]) -> None:
        for previous, current in zip(manifests, manifests[1:], strict=False):
            if current.start < previous.end:
                raise ValueError(
                    f"episodes {previous.episode_id} and {current.episode_id} overlap"
                )

    def _window(
        self,
        manifests: Sequence[EpisodeManifest],
        config: WalkForwardConfig,
    ) -> tuple[Fold, ...]:
        width = (
            config.train_episodes
            + config.validation_episodes
            + config.test_episodes
        )
        folds: list[Fold] = []
        for offset in range(0, len(manifests) - width + 1, config.step_episodes):
            train_end = offset + config.train_episodes
            validation_end = train_end + config.validation_episodes
            fold_end = validation_end + config.test_episodes
            train = manifests[offset:train_end]
            validation = manifests[train_end:validation_end]
            test = manifests[validation_end:fold_end]
            folds.append(
                Fold(
                    fold_id=f"fold-{len(folds):04d}",
                    train_episode_ids=tuple(item.episode_id for item in train),
                    validation_episode_ids=tuple(item.episode_id for item in validation),
                    test_episode_ids=tuple(item.episode_id for item in test),
                    frozen_holdout_hash=self._holdout_hash(test),
                )
            )
        return tuple(folds)

    @staticmethod
    def _assert_lineage_isolated(
        folds: Sequence[Fold],
        manifests: Sequence[EpisodeManifest],
    ) -> None:
        by_id = {manifest.episode_id: manifest for manifest in manifests}
        for fold in folds:
            partitions = (
                fold.train_episode_ids,
                fold.validation_episode_ids,
                fold.test_episode_ids,
            )
            seen: dict[str, tuple[int, EpisodeManifest]] = {}
            for partition_index, episode_ids in enumerate(partitions):
                for episode_id in episode_ids:
                    manifest = by_id[episode_id]
                    existing = seen.get(manifest.product_size_lineage)
                    if existing is not None and existing[0] != partition_index:
                        other = existing[1]
                        raise ValueError(
                            f"lineage {manifest.product_size_lineage!r} crosses fold "
                            f"partitions in episodes {other.episode_id} and "
                            f"{manifest.episode_id}"
                        )
                    seen[manifest.product_size_lineage] = (
                        partition_index,
                        manifest,
                    )

    @staticmethod
    def _assert_augmentation_isolated(
        folds: Sequence[Fold],
        manifests: Sequence[EpisodeManifest],
    ) -> None:
        by_id = {manifest.episode_id: manifest for manifest in manifests}
        for fold in folds:
            for episode_id in fold.train_episode_ids:
                manifest = by_id[episode_id]
                if manifest.provenance == "synthetic" and manifest.split != "train":
                    raise ValueError(
                        f"synthetic episode {episode_id} is not declared for training"
                    )
            for episode_id in fold.validation_episode_ids:
                manifest = by_id[episode_id]
                if (
                    manifest.provenance == "synthetic"
                    and manifest.split != "validation"
                ):
                    raise ValueError(
                        f"synthetic episode {episode_id} is not declared validation stress"
                    )
            for episode_id in fold.test_episode_ids:
                if by_id[episode_id].provenance == "synthetic":
                    raise ValueError(
                        f"synthetic episode {episode_id} cannot enter historical holdout"
                    )

    @staticmethod
    def _holdout_hash(manifests: Sequence[EpisodeManifest]) -> str:
        payload = [
            {
                "episode_id": str(manifest.episode_id),
                "start": manifest.start.isoformat(),
                "end": manifest.end.isoformat(),
                "split": manifest.split,
                "product_size_lineage": manifest.product_size_lineage,
                "source_record_ids": list(manifest.source_record_ids),
                "provenance": manifest.provenance,
                "checksum": manifest.checksum,
            }
            for manifest in manifests
        ]
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(canonical).hexdigest()
