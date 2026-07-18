# 04 — Persist + export-from-run command

**What to build:** Persist quarantined vs trainable paper-derived transitions append-only, and expose an operator/API (or job) command to export transitions for paper run X into the research transition repository so a researcher can pull a run’s dataset by run id.

**Blocked by:** 03 — Paper→OfflineTransition assembler

**Status:** ready-for-agent

- [ ] Trainable rows persist append-only into the research transition store
- [ ] Quarantined rows are retained separately (or marked) and never silently promoted to trainable
- [ ] Export/from-run command is idempotent for the same run + content hash (conflict on identity mismatch)
- [ ] Lineage to paper run id remains queryable after export
- [ ] API or Paper Ops control-plane test proves export for a seeded run without UI-only proof
