# 01 — Paper step effects capture

**What to build:** On each paper decision/tick, capture an append-only record of step effects (capital, lot, fill, and quote deltas) with stable lineage to paper run id, tick/simulation time, and related fill/order ids — without yet assembling OfflineTransitions or computing RL rewards.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Each quoting/decision tick that changes paper book state can emit a step-effects record
- [x] Record includes Decimal-honest money fields and lineage ids (run, tick, order/fill as applicable)
- [x] Capture is append-only / auditable (no silent overwrite of prior tick effects)
- [x] Unit or Paper Ops tests prove effects appear for a seeded golden tick path
- [x] Incomplete market/book snapshots fail closed rather than inventing zeros for missing money
