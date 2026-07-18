# 04 — Persist + export-from-run command

**What to build:** Persist quarantined vs trainable paper-derived transitions append-only, and expose an operator/API (or job) command to export transitions for paper run X into the research transition repository so a researcher can pull a run’s dataset by run id.

**Blocked by:** 03 — Paper→OfflineTransition assembler

**Status:** done

- [x] Trainable rows persist append-only into the research transition store
- [x] Quarantined rows are retained separately (or marked) and never silently promoted to trainable
- [x] Export/from-run command is idempotent for the same run + content hash (conflict on identity mismatch)
- [x] Lineage to paper run id remains queryable after export
- [x] API or Paper Ops control-plane test proves export for a seeded run without UI-only proof
