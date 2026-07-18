# 02 — Fail-closed corrupt payload ingest

**What to build:** Corrupt, partial, non-finite, or structurally invalid live-shaped payloads fail closed on the read-only port — no invented liquidity. Same spirit as `SneakerDataPipeline` / paper replay fail-closed ingest.

**Blocked by:** 01 — Read-only observation port + allowlist

**Status:** done

- [x] Missing required fields fail closed
- [x] Non-finite or crossed book prices fail closed
- [x] Corrupt JSON / malformed payloads fail closed
- [x] No silent defaulting that invents bid/ask liquidity
- [x] Tests cover at least three distinct corrupt-payload cases
