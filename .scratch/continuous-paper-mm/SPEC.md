# Continuous Paper Market-Maker — First Shippable Slice

**Date:** 2026-07-17  
**Status:** ready-for-agent  
**Glossary:** `CONTEXT.md`  
**ADRs:** `docs/adr/0001-golden-historical-replay-for-v1.md`, `docs/adr/0002-deterministic-first-paper-mm.md`  
**Parent design:** `docs/superpowers/specs/2026-07-17-market-maker-dashboard-design.md` (scoped to First Shippable Slice)

## Problem Statement

The approved dashboard design describes a Continuous Paper Market-Maker, but the repo today only delivers offline research (Guided Demo, research comparison, shadow recommender). An operator cannot load StockX Historical Replay, run a Deterministic Strategy that continuously place/revise/cancel/replaces Paper Orders, or observe Paper Capital, Inventory Lots, Fee-Aware Fills, and P&L in an Ops Dashboard. Without that control plane and simulation, strategy and risk remain unverifiable before any future marketplace adapter.

## Solution

Build the First Shippable Slice of the Continuous Paper Market-Maker: a Golden Historical Replay Dataset drives a deterministic simulation clock; the Deterministic Strategy emits Quote Intents; the Deterministic Gate is final; Paper Orders are quantity-one and fill at most once with fees and slippage; Inventory Lots back asks; PostgreSQL is the Authoritative Store; a thin Ops Dashboard starts/stops replay and shows capital, orders, fills, lots, and P&L. Model shadow, alerts, metrics, and live adapters stay out.

## User Stories

1. As an operator, I want to load a Golden Historical Replay Dataset, so that the paper book is driven by a versioned authoritative replay artifact.
2. As an operator, I want the dataset checksum and version shown, so that I know which replay I am running.
3. As an operator, I want non-allowlisted product families rejected at load, so that only Jordan 1 Retro and Nike Dunk Low enter the sim.
4. As an operator, I want to start, pause, resume, and stop replay, so that I control simulation time.
5. As an operator, I want replay speed and seed controls, so that runs are reproducible.
6. As an operator, I want the simulation clock visible, so that I can correlate events with decisions.
7. As an operator, I want to enable and disable the Deterministic Strategy, so that quoting can be stopped without unloading replay.
8. As an operator, I want desired bid and ask shown separately from active Paper Orders, so that I can see Quote Intent pressure.
9. As an operator, I want asks only when Inventory Lots are available, so that Two-Sided Paper Quoting stays inventory-backed.
10. As an operator, I want continuous place/revise/cancel/replace, so that quotes track the market instead of set-and-forget.
11. As an operator, I want quote churn limited by price/age thresholds, so that the book does not thrash.
12. As an operator, I want every Quote Intent gated, so that illegal orders never hit the paper book.
13. As an operator, I want stable rejection reason codes, so that risk failures are auditable.
14. As an operator, I want Paper Capital to start at $2,500.00, so that economics match the approved design.
15. As an operator, I want open buy principal capped at $1,500.00 of initial capital, so that reserve risk is bounded.
16. As an operator, I want that buy reserve cap not to grow with profits, so that risk does not silently expand.
17. As an operator, I want buys to fit available cash after reservations and expected buy-side fees/slippage, so that cash cannot go unbacked.
18. As an operator, I want Paper Orders to be quantity one, so that each order maps to one physical pair.
19. As an operator, I want fills to be all-or-nothing, so that partial fills never exist.
20. As an operator, I want Fee-Aware Fills recording quote price, execution price, slippage, fee version, and fees, so that P&L is honest.
21. As an operator, I want buy fills to create Inventory Lots, so that physical lifecycle begins.
22. As an operator, I want lot states through purchase, transit, auth, available, reserved, sold, settled (and exceptions), so that asks only use sellable stock.
23. As an operator, I want reserved lots unable to back another ask, so that double-selling is impossible.
24. As an operator, I want realized and unrealized P&L separated, so that mark policy is visible.
25. As an operator, I want fees and slippage visible in P&L, so that gross spread is not mistaken for profit.
26. As an operator, I want Postgres to survive restart, so that paper state is not lost with the process.
27. As an operator, I want an append-only audit trail, so that intents, gates, fills, and lot transitions are reconstructible.
28. As an operator, I want a thin Ops Dashboard distinct from Guided Demo, so that I operate the real paper loop.
29. As an operator, I want WebSocket or ordered projections for live updates, so that the UI does not invent authoritative state.
30. As an operator, I want REST commands with idempotency, so that double-clicks do not double-apply controls.
31. As an operator, I want loopback-only default binding, so that the control plane is not accidentally exposed.
32. As a developer, I want StockX-Shaped Fixtures for local smoke tests, so that I can develop without claiming execution benchmarks.
33. As a developer, I want Synthetic Scenario labeled and barred from execution evidence, so that stress paths cannot fake replay quality.
34. As a developer, I want seeded replay to reproduce ordered decisions and fills, so that regressions are golden-testable.
35. As a developer, I want Product-Family Allowlist versioned, so that allowlist changes are explicit.
36. As a researcher, I want this slice free of model authority, so that Deterministic Gate remains the only path to the paper book.
37. As a researcher, I want existing research UI untouched as the primary path, so that Guided Demo and research comparison keep working.
38. As an auditor, I want money as exact decimals, so that floating point never invents cash.
39. As an auditor, I want replacement to release and re-reserve capital atomically, so that failed replace cannot double-reserve.
40. As an operator, I want manual paper cancel from the Ops Dashboard, so that I can clear a stuck quote under gate rules.
41. As an operator, I want data-quality / stale failures to fail closed, so that bad market data does not quote.
42. As an operator, I want fill linkage to the source replay event, so that each fill is explainable.
43. As an operator, I want inventory age and landed cost on lots, so that holding cost is inspectable.
44. As an operator, I want strategy-off to cancel or stop maintaining quotes per policy, so that disable is meaningful.
45. As a developer, I want acceptance tests at the Paper Ops Control Plane seam, so that the slice is proven end-to-end without UI flakiness as the only proof.

## Implementation Decisions

- **Test seam (approved):** Paper Ops Control Plane — REST operator commands plus ordered projections/WebSocket. Domain internals (gate, matching, lots) are unit/property-tested in support of that seam, not as separate public products.
- **Glossary and ADRs govern naming:** Continuous Paper Market-Maker, Golden Historical Replay Dataset, Deterministic Strategy, Deterministic Gate, Quote Intent, Paper Order, Paper Capital, Inventory Lot, Fee-Aware Fill, Ops Dashboard, Authoritative Store, First Shippable Slice.
- **ADR-0001:** V1 authoritative replay is a versioned, checksummed Golden Historical Replay Dataset (swappable later).
- **ADR-0002:** First slice is deterministic-only; no model shadow in the quote loop.
- **Product-Family Allowlist:** Jordan 1 Retro and Nike Dunk Low only; others fail validation at ingest and gate.
- **Architecture:** Modular event-driven monolith behind FastAPI: simulator → normalize → Deterministic Strategy / quote engine → Deterministic Gate → paper execution → inventory/accounting → projections; Postgres authoritative.
- **Paper Capital:** $2,500.00 initial; $1,500.00 open-buy principal cap on initial capital (not profit-scaling); buys must fit cash after reservations and expected buy-side fees/slippage; replace reservations atomic.
- **Paper Order:** quantity one; full fill once; explicit place/revise/cancel/replace Quote Intents.
- **Two-Sided Paper Quoting:** desired bid when healthy; ask only with available Inventory Lot.
- **Fee-Aware Fill:** quote vs execution, slippage, fee schedule version, total fees into capital/lots/P&L.
- **Inventory Lot:** physical lifecycle; only available lots back asks; reserved lots exclusive.
- **Authoritative Store:** Postgres tables for runs, orders, fills, lots, capital snapshots, append-only audit events; Alembic migrations additive.
- **Ops Dashboard:** thin React control plane for replay controls, strategy toggle, capital, orders, fills, lots, P&L; not Guided Demo; not full design §11 research/promotion surface.
- **Reuse:** existing `FeeSchedule` / decimal money patterns; research API patterns for idempotent commands and loopback binding; do not route paper execution through the research shadow recommender in this slice.
- **Money:** Decimal / integer cents in Python and Postgres; no float in accounting paths.

## Testing Decisions

- Good tests assert **external behavior** at the Paper Ops Control Plane (commands + resulting projections/audit), not private function call graphs.
- Prefer highest seam: FastAPI TestClient (and WS where needed) with Postgres testcontainer for acceptance; unit tests for Deterministic Gate, matching rules, lot transitions, capital reservation.
- Prior art: `tests/api/test_research_api.py`, `tests/api/test_local_demo_swagger.py`, research integration Postgres tests, safety offline-boundary tests, frontend Vitest for research UI (mirror for Ops Dashboard).
- Golden replay: same seed + dataset checksum ⇒ same ordered Quote Intents, fills, and lot transitions.
- Fail-closed cases: non-allowlisted family, stale/invalid market data, reserve/cash breach, ask without available lot, partial-fill attempts rejected by construction.
- Frontend: Ops Dashboard controls and read models; keep Guided Demo tests green and separate.

## Out of Scope

- Model shadow/advisory in the quote loop
- Model-research and advisory promotion/rollback UI
- Discord / Slack alerts
- Prometheus / Grafana
- Live marketplace adapters or credentials
- Synthetic Scenario as execution evidence
- Products outside Jordan 1 Retro and Nike Dunk Low
- Multi-quantity or partial-fill Paper Orders
- In-memory-only “done” without Authoritative Store
- Replacing or removing the existing research Guided Demo / research API

## Further Notes

- Work tickets under `.scratch/continuous-paper-mm/issues/` in dependency order; frontier is tickets with all blockers done.
- Existing research subsystem remains; this slice adds the paper MM control plane beside it.
- When a larger real StockX dump arrives, swap the Golden Historical Replay Dataset artifact without changing the market-event port (ADR-0001).
