# 04 — Quote engine → Quote Intents (continuous)

**What to build:** While Deterministic Strategy is enabled and replay is running, the quote engine compares desired Two-Sided Paper Quoting with active Paper Orders and emits continuous place/revise/cancel/replace Quote Intents (bid when healthy; ask only when inventory-backed), with churn thresholds, all submitted through the Deterministic Gate.

**Blocked by:** 02 — Simulation clock + replay controls; 03 — Paper Capital + Deterministic Gate

**Status:** ready-for-agent

- [ ] Desired vs active quotes diverge into explicit Quote Intents (not silent book edits)
- [ ] Ask intents are withheld when no available Inventory Lot can back them (inventory may be stubbed until ticket 06 if needed, but the rule is enforced)
- [ ] Price/age thresholds prevent quote thrash
- [ ] Strategy disable stops maintaining quotes per agreed policy
- [ ] Tests show continuous revise/cancel/replace under changing replay events
