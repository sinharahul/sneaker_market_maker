# 01 — Product-Family Allowlist + Golden Historical Replay Dataset

**What to build:** An operator (or acceptance test) can load a versioned, checksummed Golden Historical Replay Dataset limited to Jordan 1 Retro and Nike Dunk Low; any other product family fails validation. The artifact is explicitly labeled as StockX Historical Replay for V1 and is swappable later without changing the market-event port.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Golden Historical Replay Dataset has version, checksum, allowlist scope, and historical-shaped label in its manifest
- [ ] Loading rejects non-allowlisted families with a stable error
- [ ] StockX-Shaped Fixtures remain usable for local smoke without being treated as the Golden Historical Replay Dataset
- [ ] Tests prove allowlist enforcement and manifest checksum verification at the ingest boundary
