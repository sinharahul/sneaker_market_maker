# 10 — Advisory fallback on invalid/late IQL

**What to build:** In `advisory`, missing/late/invalid IQL falls back to the deterministic base for that tick (audited). Replay does not pause.

**Blocked by:** 09 — Advisory Mode nudge path

**Status:** done

- [x] Timeout/invalid IQL yields deterministic-base quoting for that tick
- [x] Replay status remains running (not paused for IQL)
- [x] Fallback is visible in audit/projections
- [x] Tests cover timeout and invalid stub outcomes
