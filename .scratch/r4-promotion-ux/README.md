# R4 — Promotion UX + optional PFHedge

**Parent:** Track R / R4 in `docs/ROADMAP.md`  
**Spec:** `docs/superpowers/specs/2026-07-18-dual-track-roadmap.md`  
**Depends on:** R3 Ops bind (done)  
**Status:** done

## Tickets (dependency order)

| # | Title | Blocked by |
|---|--------|------------|
| 01 | Ops promote / qualify command | — |
| 02 | Promote path on Ops projections | 01 |
| 03 | PFHedge paper mode decision | — |
| 04 | Gate / qty-one regression after promote | 01, 02 |

**03** may run in parallel with **01**.

**Frontier:** start with **01** (and optionally **03**). Work with `/implement`.

## Exit criteria (phase)

- Operator can see promote/qualify path without only using research comparison  
- PFHedge paper mode either explicitly deferred with reason or shipped behind ADR + Gate-final  
