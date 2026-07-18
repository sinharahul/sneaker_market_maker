# 03 — Happy path: no stub on advisory / iql_primary

**What to build:** The default Ops/demo happy path for `advisory` and `iql_primary` uses the bound registry artifact — stubs are test-only. `deterministic` remains always available without Model Qualification so operators can fail closed during bind outages.

**Blocked by:** 01 — Registry artifact → inference bind

**Status:** done

- [x] Default `advisory` path uses bound registry artifact (not a stub policy)
- [x] Default `iql_primary` path uses bound registry artifact (not a stub policy)
- [x] Stub / fake inference remains injectable for tests only
- [x] `deterministic` mode stays available without qualification
- [x] Test proves Gate-final nudge (`advisory`) and pause (`iql_primary`) semantics with a real/CI-pinned small artifact
