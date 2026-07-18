# R3 — Bind production artifacts in Ops

**Parent:** Track R / R3 in `docs/ROADMAP.md`  
**Spec:** `docs/superpowers/specs/2026-07-18-dual-track-roadmap.md`  
**Depends on:** R2 offline retrain + registry register (done)  
**Status:** done

## Tickets (dependency order)

| # | Title | Blocked by |
|---|--------|------------|
| 01 | Registry artifact → inference bind | — |
| 02 | Ops projection of bound model | 01 |
| 03 | Happy path: no stub on advisory / iql_primary | 01 |
| 04 | Qualification + latency on real infer | 01 |
| 05 | Golden acceptance + bind/qualify runbook | 02, 03, 04 |

**02**, **03**, and **04** may run in parallel after **01**.

**Frontier:** start with **01**. Work one ticket at a time with `/implement`.

## Exit criteria (phase)

- `advisory` / `iql_primary` happy path uses real registry artifact  
- Encoder/schema mismatch fail-closed  
- Acceptance: golden replay + real (or CI-pinned small) artifact proves nudge/pause under Gate  
