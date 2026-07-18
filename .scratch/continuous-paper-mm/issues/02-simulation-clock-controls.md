# 02 — Simulation clock + replay controls

**What to build:** After a Golden Historical Replay Dataset is loaded, an operator can start, pause, resume, and stop replay under a deterministic simulation clock (with seed/speed), producing ordered normalized market events suitable for quoting.

**Blocked by:** 01 — Product-Family Allowlist + Golden Historical Replay Dataset

**Status:** ready-for-agent

- [ ] Load/start/pause/resume/stop behave deterministically for the same dataset + seed
- [ ] Simulation clock and replay progress are observable via projections
- [ ] Events sharing a source timestamp have stable ordering
- [ ] Acceptance coverage through Paper Ops Control Plane commands (or the seam available once API exists; until then, simulator port tests that the API will wrap)
