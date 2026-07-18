# 02 — Ops projection of bound model

**What to build:** When a registry artifact is bound, Ops projections surface what is running: model id, registry state, encoder version, and Action Translator version so operators can see lineage without opening research tooling.

**Blocked by:** 01 — Registry artifact → inference bind

**Status:** done

- [x] Projection includes model id for the currently bound artifact
- [x] Projection includes registry state (e.g. candidate / qualified) for that model
- [x] Projection includes encoder version and Action Translator version
- [x] Unbound or deterministic-only path does not invent model lineage
- [x] Test proves projection fields update after a successful bind
