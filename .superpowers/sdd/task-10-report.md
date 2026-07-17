# Task 10 Report

## Result

Implemented deterministic leakage-safe walk-forward fold generation.

## Delivered

- Added immutable `EpisodeManifest`, `WalkForwardConfig`, and `Fold` contracts.
- Validated all walk-forward counts as positive.
- Sorted manifests chronologically before creating fixed-width rolling windows.
- Rejected duplicate episode IDs, duplicate source events, and overlapping episodes.
- Rejected product/size lineage crossing train, validation, and test partitions in a fold.
- Restricted synthetic augmentation to effective training or explicitly declared validation stress.
- Rejected synthetic episodes from every historical test holdout.
- Generated canonical SHA-256 hashes from complete immutable holdout manifests.
- Preserved historical and synthetic provenance labels without mutation.
- Exposed scaler-fitting inputs only through each fold's training episode IDs.
- Kept all Task 10 source and test files below 300 lines and added no network or marketplace code.

## TDD Evidence

- Red phase:
  `.venv/bin/python -m pytest tests/research/evaluation/test_splits.py -q`
  failed during collection because the experiment contract module did not exist.
- Focused tests:
  `.venv/bin/python -m pytest tests/research/evaluation/test_splits.py -q`
  passed with `19 passed in 0.50s`.
- Affected research tests:
  `.venv/bin/python -m pytest tests/research -q`
  passed with `92 passed in 2.15s`.
- Focused Ruff:
  `.venv/bin/python -m ruff check src/sneaker_market_maker/research/contracts/experiment.py src/sneaker_market_maker/research/evaluation/splits.py tests/research/evaluation/test_splits.py`
  passed.
- `git diff --check` passed.

## Self-Review

- Safety checks run synchronously before any fold tuple is returned, so invalid data cannot reach
  downstream scaler fitting.
- Overlap and lineage errors identify both implicated episode IDs.
- Holdout hashes include episode identity, time boundaries, split, lineage, source IDs, provenance,
  and checksum in canonical serialization.
- Rolling windows remain deterministic for unsorted input and preserve chronology within every
  partition.

## Concern

- Repository-wide Ruff still reports the pre-existing `UP038` violation in
  `src/sneaker_market_maker/pipeline.py:59`; all Task 10 files pass focused Ruff.
