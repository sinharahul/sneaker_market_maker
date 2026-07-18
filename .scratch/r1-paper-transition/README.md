# R1 — Paper → transition plumbing

**Parent:** Track R / R1 in `docs/ROADMAP.md`  
**Spec:** `docs/superpowers/specs/2026-07-18-dual-track-roadmap.md`  
**Seams:** Paper Ops Control Plane + research transition repository  
**Status:** tickets ready-for-agent

## Tickets (dependency order)

| # | Title | Blocked by |
|---|--------|------------|
| 01 | Paper step effects capture | — |
| 02 | Fee-once paper reward projection | 01 |
| 03 | Paper→OfflineTransition assembler | 02 |
| 04 | Persist + export-from-run command | 03 |
| 05 | Acceptance: golden run → ≥1 trainable batch | 04 |

**Frontier:** start with **01**. Work one ticket at a time with `/implement`, clear context between tickets.

## Exit criteria (phase)

- Paper run emits append-only transition candidates with lineage to run/tick/fill ids  
- Invalid/incomplete rows quarantine fail-closed  
- Golden/paper acceptance: ≥1 trainable batch from a seeded paper run  
