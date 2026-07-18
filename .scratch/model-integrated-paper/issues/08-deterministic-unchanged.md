# 08 — Deterministic path unchanged under Strategy Mode

**What to build:** With Strategy Mode `deterministic`, golden replay ticks produce the same Quote Intent / fill behavior as the First Shippable Slice (no IQL calls required).

**Blocked by:** 05 — Strategy Mode state machine; 07 — Paper Ops commands: set-mode + set-budget

**Status:** ready-for-agent

- [ ] Mode `deterministic` does not invoke IQL on tick
- [ ] Golden replay acceptance for deterministic quoting still passes
- [ ] Switching back to `deterministic` restores baseline quoting
