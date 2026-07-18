# L1 — Read-only market data port

**Parent:** Track L / L1 in `docs/ROADMAP.md`  
**Spec:** `docs/superpowers/specs/2026-07-18-dual-track-roadmap.md`  
**Depends on:** none (parallel with Track R; no live-send)  
**Status:** done

## Tickets (dependency order)

| # | Title | Blocked by |
|---|--------|------------|
| 01 | Read-only observation port + allowlist | — |
| 02 | Fail-closed corrupt payload ingest | 01 |
| 03 | Safety: no send client in port tree | 01 |
| 04 | L1 acceptance fixture + observe docs | 02, 03 |

**02** and **03** may run in parallel after **01**.

**Frontier:** start with **01**. Work with `/implement`.

## Exit criteria (phase)

- Port delivers allowlisted snapshots/events without credentials that can place orders  
- Fail-closed on corrupt payloads  
- Safety tests: no send client in tree for this port  

**Out of scope for L1:** shadow would-quote (L2), kill-switch/ADR-0004 (L3), live-send (L4).
