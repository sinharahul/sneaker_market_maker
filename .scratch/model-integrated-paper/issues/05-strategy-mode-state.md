# 05 — Strategy Mode state machine (session)

**What to build:** PaperOpsSession (or equivalent) holds exactly one Strategy Mode at a time: `deterministic` | `advisory` | `iql_primary`. Mode changes are append-only audited.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Exactly one Strategy Mode is active at a time
- [ ] Mode transitions are audited
- [ ] Default mode is `deterministic`
- [ ] Tests prove single-active-mode invariant and audit on change
