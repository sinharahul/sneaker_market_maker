# 06 — Model Qualification gates

**What to build:** Selecting `advisory` requires registry `advisory_approved`; selecting `iql_primary` requires at least `benchmark_qualified`. `deterministic` needs no qualification. Unqualified attempts leave the active mode unchanged and return a clear error.

**Blocked by:** 05 — Strategy Mode state machine (session)

**Status:** done

- [x] Unqualified `advisory` / `iql_primary` selection is refused without changing mode
- [x] `deterministic` is always selectable
- [x] Qualification uses research registry states (no parallel promotion store)
- [x] Tests cover refuse/accept matrices for registry states
