# 12 — IQL-Primary pause-on-failure

**What to build:** In `iql_primary`, missing/late/invalid IQL pauses StockX Historical Replay with a status distinct from operator pause. Recovery: healthy IQL again, or switch to `deterministic` then resume.

**Blocked by:** 11 — IQL-Primary Mode intent authorship

**Status:** ready-for-agent

- [ ] Invalid/late IQL pauses replay with an IQL-unavailability reason
- [ ] No silent deterministic substitute while mode remains `iql_primary`
- [ ] Switching to `deterministic` allows resume under baseline quoting
- [ ] Tests cover pause and both recovery paths
