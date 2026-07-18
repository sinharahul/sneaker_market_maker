# 04 — L1 acceptance fixture + observe docs

**What to build:** Close L1 with a CI/fixture acceptance path for allowlisted read-only observe, plus a short operator note that this is observe-only (not L2 shadow, not live-send). Mark L1 exit criteria when acceptance + safety land.

**Blocked by:** 02 — Fail-closed corrupt payload ingest; 03 — Safety: no send client in port tree

**Status:** done

- [x] Fixture/acceptance proves allowlisted observe end-to-end at the port seam
- [x] Off-allowlist and corrupt paths remain fail-closed in acceptance
- [x] Short observe-only operator note linked from ROADMAP or paper-ops / live-readiness docs
- [x] Note explicitly defers shadow (L2) and live-send (L4 / ADR-0004)
- [x] L1 phase exit criteria marked complete when this lands
