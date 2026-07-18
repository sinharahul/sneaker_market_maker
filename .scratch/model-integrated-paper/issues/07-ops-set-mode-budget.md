# 07 — Paper Ops commands: set-mode + set-budget

**What to build:** Idempotent Paper Ops REST commands set Strategy Mode and Inference Latency Budget; projections expose mode, registry qualification state, and budget. Unqualified mode sets fail closed without mutation.

**Blocked by:** 05 — Strategy Mode state machine; 06 — Model Qualification gates

**Status:** ready-for-agent

- [ ] Idempotent set-mode and set-budget commands exist on the Paper Ops Control Plane
- [ ] Projections include mode, registry model/state, and latency budget
- [ ] Unqualified set-mode does not change active mode
- [ ] Control-plane tests cover idempotency and reject paths
