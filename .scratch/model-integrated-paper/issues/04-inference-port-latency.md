# 04 — IQL inference port + Inference Latency Budget

**What to build:** An injectable IQL inference port encodes Paper Decision State and returns a HybridAction (or failure) within a pinned Inference Latency Budget (default 100ms, ceiling 250ms). Exceeding the budget counts as invalid. Tests use a stub behind the same port.

**Blocked by:** 03 — Paper Decision State builder

**Status:** ready-for-agent

- [ ] Inference port is injectable; stub works in tests without Torch weights
- [ ] Latency budget defaults to 100ms with ceiling 250ms and is pinable per run
- [ ] Timeout or encode failure yields invalid inference (not a silent success)
- [ ] Unit tests cover success, timeout-as-invalid, and budget ceiling rejection
