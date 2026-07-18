# 13 — Mode/inference audit + status projections

**What to build:** Paper Ops projections and append-only audit expose Strategy Mode, latency budget, fallback/pause reason, and last IQL action summary so clients do not invent authority.

**Blocked by:** 07 — set-mode; 10 — advisory fallback; 12 — iql_primary pause

**Status:** done

- [x] Status/projections include mode, budget, pause-for-IQL vs operator pause, last action summary
- [x] Audit records mode changes, inference outcomes, and fallback/pause events
- [x] Control-plane tests read these fields after advisory fallback and iql pause
