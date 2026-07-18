# 05 — Acceptance: golden run → ≥1 trainable batch

**What to build:** End-to-end acceptance at the Paper Ops Control Plane + transition repository seams: a seeded golden historical replay paper run yields at least one trainable OfflineTransition batch with lineage; invalid paths remain quarantined; Decimal and Gate-final paper behavior unchanged.

**Blocked by:** 04 — Persist + export-from-run command

**Status:** ready-for-agent

- [ ] Seeded golden load → start → tick path produces ≥1 trainable transition after export
- [ ] Lineage fields tie transitions back to the paper run (and tick/fill where applicable)
- [ ] Induced incomplete path still quarantines (no silent train)
- [ ] Existing Strategy Mode / Gate acceptance tests remain green
- [ ] Acceptance does not rely on Ops Vitest or Guided Demo as sole proof
