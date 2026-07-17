# Task 9 Report

## Result

Implemented complete, deterministic offline-transition assembly and persistence through
`TransitionService`.

## Delivered

- Added the exact `TransitionInput`, `StepEffects`, and `TransitionLineage` fields.
- Linked adjacent decision-point state, next state, elapsed time, discount, terminal status,
  action constraints, actions, behavior policy, reward, categorized effects, and lineage.
- Added canonical sorted-key SHA-256 hashing with `Decimal` values encoded as strings.
- Derived stable transition IDs from immutable transition identity for idempotent retries.
- Added `TrainabilityError` and persisted only those failures as quarantined transitions with
  stable reasons.
- Preserved absent legacy propensity and logistics values instead of fabricating them.
- Persisted categorized effects and trainability metadata in repository serialization and schema.
- Kept repository failures and non-trainability programming/data errors uncaught.

## Verification

- Red phase confirmed: the focused test initially failed during import.
- Focused/affected tests: `39 passed`.
- Focused Ruff: all checks passed.
- `git diff --check`: passed.
- Relevant implementation and test files remain below 300 lines.

## Concerns

- The full suite cannot collect in the current environment because `pfhedge` and the Alembic
  Python package are unavailable.
- Repository-wide Ruff reaches one pre-existing `UP038` violation in
  `src/sneaker_market_maker/pipeline.py`; all Task 9 affected files pass Ruff.

## Fix

- Added recursive JSON-boundary conversion so `Decimal` values in state, next state, and nested
  JSON payloads persist as strings.
- Removed synthesized `OfflineTransition` effects and trainability defaults. Deserialization now
  requires the persisted effects, every categorized effect key, status, and reason fields.
- Added status/reason consistency checks so incomplete or contradictory records cannot appear
  trainable.
- Added regression coverage for nested Decimal state serialization, strict missing-field failure,
  distinct proposed/post-gate actions, and terminal next-state linkage.

Exact evidence:

- Red test:
  `python -m pytest tests/persistence/test_research_repository_unit.py tests/research/transitions/test_service.py -q`
  → `3 failed, 11 passed` before the fixes.
- Focused affected tests:
  `python -m pytest tests/research/transitions/test_service.py tests/research/contracts/test_transition.py tests/research/episodes/test_builder.py tests/persistence/test_research_repository_unit.py tests/persistence/test_research_tables.py -q`
  → `44 passed in 0.68s`.
- Focused Ruff over the modified source and test files → `All checks passed!`.
- `git diff --check` → passed.
