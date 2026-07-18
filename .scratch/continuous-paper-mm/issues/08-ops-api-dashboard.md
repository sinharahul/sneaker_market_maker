# 08 — Paper Ops API + thin Ops Dashboard

**What to build:** A loopback FastAPI Paper Ops Control Plane exposes REST commands (load/start/pause/resume/stop replay, enable/disable Deterministic Strategy, optional manual cancel) with idempotency, plus ordered projections/WebSocket for Paper Capital, Paper Orders, fills, Inventory Lots, and P&L. A thin React Ops Dashboard (not Guided Demo, not research comparison) drives those controls and displays those read models.

**Blocked by:** 02 — Simulation clock + replay controls; 07 — Authoritative Store (Postgres + audit)

**Status:** done

- [x] Operator can run First Shippable Slice end-to-end from the Ops Dashboard against Golden Historical Replay
- [x] UI does not treat optimistic local state as authoritative; projections/events do
- [x] Guided Demo and research comparison routes remain available and separately tested
- [x] Acceptance tests at the Paper Ops Control Plane seam prove a seeded replay produces observable capital, orders, fills, lots, and P&L
- [x] Default bind remains loopback-oriented; no live marketplace calls
