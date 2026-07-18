# 11 — IQL-Primary Mode intent authorship

**What to build:** In `iql_primary` with valid IQL within budget, the Action Translator output authors desired Quote Intents; Deterministic Gate remains final; Paper Orders/fills are observable on golden replay with a stub.

**Blocked by:** 01 — QUOTE mapping; 02 — CANCEL/NO_OP; 04 — inference port; 07 — set-mode; 08 — deterministic unchanged

**Status:** ready-for-agent

- [ ] Valid IQL authors intents (not merely nudging deterministic)
- [ ] Gate still rejects illegal intents
- [ ] Session/control-plane tests show IQL-authored orders under stub
