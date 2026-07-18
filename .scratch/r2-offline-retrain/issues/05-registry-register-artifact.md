# 05 — Registry register artifact

**What to build:** Register the trained checkpoint and lineage (FrozenAssumptions hash, mixed-dataset manifest id, harness metrics summary) into RegistryService as a candidate artifact. Same identity + content hash is idempotent; identity mismatch conflicts fail-closed.

**Blocked by:** 03 — Walk-forward harness benchmark

**Status:** done

- [x] RegistryService.register accepts the new IQL artifact with immutable lineage fields
- [x] Assumptions hash, manifest id, and metrics summary are stored on the registry record
- [x] Re-register of identical identity+hash returns existing / idempotent success
- [x] Conflicting hash for same identity raises a conflict (no silent overwrite)
- [x] Test proves register after a tiny train+harness fixture without promoting past candidate unless separately qualified
