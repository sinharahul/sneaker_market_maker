# 01 — Ops promote / qualify command

**What to build:** An operator can advance a registry model along legal states (through `advisory_approved` where allowed) from the Paper Ops control plane, with actor and reason. Illegal transitions fail closed. Reuse `RegistryService` / `QualificationService` — do not invent a second promotion system.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Control-plane command promotes/qualifies along legal registry edges only
- [x] Actor and reason are required and recorded
- [x] Illegal or unqualified transitions fail closed (no silent state change)
- [x] Bound Ops session can reflect the new registry state for Model Qualification
- [x] Tests cover a legal promote path and at least one rejected illegal edge
