# 03 — Walk-forward harness benchmark

**What to build:** Evaluate the new IQL checkpoint against deterministic (and optionally a prior IQL baseline) under EvaluationHarness on frozen walk-forward folds. Scalers fit on train folds only; leakage controls must remain unchanged.

**Blocked by:** 02 — Offline IQL train job

**Status:** done

- [x] Harness loads the new checkpoint as an EvaluationPolicy adapter
- [x] Report compares at least deterministic vs new IQL under identical FrozenAssumptions
- [x] Walk-forward folds isolate chronology; train-fold-only scaler fit preserved
- [x] Synthetic/historical provenance rules unchanged (synthetic not claimed as historical holdout)
- [x] Test proves harness report is produced for a tiny trained checkpoint fixture
