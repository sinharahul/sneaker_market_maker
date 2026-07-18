# R2 — Offline retrain on paper + historical mix

**Parent:** Track R / R2 in `docs/ROADMAP.md`  
**Spec:** `docs/superpowers/specs/2026-07-18-dual-track-roadmap.md`  
**Depends on:** R1 paper→transition export (done)  
**Status:** tickets ready-for-agent

## Tickets (dependency order)

| # | Title | Blocked by |
|---|--------|------------|
| 01 | Mixed dataset manifest | — |
| 02 | Offline IQL train job | 01 |
| 03 | Walk-forward harness benchmark | 02 |
| 04 | OPE validity gate | 03 |
| 05 | Registry register artifact | 03 |

**04** and **05** may run in parallel after **03**.

**Frontier:** start with **01**. Work one ticket at a time with `/implement`.

## Exit criteria (phase)

- Train job consumes R1 artifacts + pinned historical mix  
- EvaluationHarness report + registry `register` of new artifact  
- Walk-forward / leakage controls unchanged (train-fold scaler, etc.)  
