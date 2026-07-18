# Model-Integrated Paper Slice — Research/IQL in the quote loop

**Date:** 2026-07-18  
**Status:** shipped (R0 / Model-Integrated Paper Slice)  
**Glossary:** `CONTEXT.md`  
**ADRs:** `docs/adr/0001-golden-historical-replay-for-v1.md`, `docs/adr/0002-deterministic-first-paper-mm.md`, `docs/adr/0003-iql-strategy-modes-gate-final.md`  
**Depends on:** First Shippable Slice (Continuous Paper Market-Maker Ops + golden replay)  
**Follow-on:** Dual-track roadmap closes R1–R4 + L1 — see `docs/ROADMAP.md`  
**Parent design:** `docs/superpowers/specs/2026-07-17-market-maker-dashboard-design.md` (scoped to Strategy Modes + IQL; not full §11)

## Problem Statement

The First Shippable Slice runs a Continuous Paper Market-Maker on Deterministic Strategy alone. Research/IQL already exists (registry, encoder, recommender, HybridAction) but does not author or nudge Quote Intents in the paper loop. An operator cannot select Strategy Mode, cannot let a qualified IQL model actually influence paper trading under the Deterministic Gate, and cannot prove fail-closed behavior when inference is late or invalid. Without this Model-Integrated Paper Slice, IQL remains a research comparison artifact rather than a gated participant in paper market-making.

## Solution

Wire Research/IQL into the paper quote loop under operator Strategy Mode (`deterministic` | `advisory` | `iql_primary`). Exactly one mode is active. IQL sees Paper Decision State encoded with the registry-pinned encoder; HybridAction maps through a versioned Action Translator into quantity-one Quote Intents; the Deterministic Gate remains final. Model Qualification gates mode entry. Inference Latency Budget is pinned per run. In `iql_primary`, late/invalid IQL pauses StockX Historical Replay; in `advisory`, late/invalid falls back to the deterministic base for that tick. Ops Dashboard gains mode selection and mode/audit projections. PFHedge stays off the paper quote path. Shadow-only observation is not the primary outcome of this slice.

## User Stories

1. As an operator, I want to select Strategy Mode `deterministic`, so that quoting uses Deterministic Strategy alone.
2. As an operator, I want to select Strategy Mode `advisory`, so that Deterministic Strategy proposes the base quote and qualified IQL may nudge within bounds before the Deterministic Gate.
3. As an operator, I want to select Strategy Mode `iql_primary`, so that IQL proposes Quote Intents that still pass through the Deterministic Gate.
4. As an operator, I want exactly one Strategy Mode active at a time, so that quote authorship is unambiguous.
5. As an operator, I want mode changes audited, so that who changed mode and when is reconstructible.
6. As an operator, I want `advisory` refused unless the active model is `advisory_approved`, so that Model Qualification is enforced.
7. As an operator, I want `iql_primary` refused unless the active model is at least `benchmark_qualified`, so that unqualified models cannot author paper quotes.
8. As an operator, I want `deterministic` always available without Model Qualification, so that I can always fail closed to the baseline.
9. As an operator, I want the active registry model id and state visible on Ops projections, so that I know which IQL artifact is bound.
10. As an operator, I want Inference Latency Budget pinned on the paper run (default 100ms, ceiling 250ms), so that “late” is explicit and auditable.
11. As an operator, I want exceeding the latency budget treated as invalid inference, so that slow models cannot silently claim health.
12. As an operator, I want `advisory` to fall back to the deterministic base for that tick when IQL is missing, late, or invalid, so that quoting continues safely.
13. As an operator, I want `iql_primary` to pause StockX Historical Replay when IQL is missing, late, or invalid, so that the mode does not silently pretend to be IQL while using Deterministic Strategy.
14. As an operator, I want a clear projection that replay is paused for IQL unavailability, so that I can distinguish operator pause from model pause.
15. As an operator, I want to resume replay only after IQL is healthy again (or after switching mode), so that recovery is intentional.
16. As an operator, I want every Quote Intent—whether deterministic, nudged, or IQL-authored—to pass the Deterministic Gate, so that models never approve orders.
17. As an operator, I want gate rejections of IQL-authored intents recorded with stable reason codes, so that model vs risk failures are separable.
18. As an operator, I want Paper Orders to remain quantity one, so that Action Translator allocation never invents multi-qty tickets.
19. As an operator, I want `QUOTE` HybridActions mapped as touch ± (ticks × pinned tick_size), so that research ticks become paper prices consistently.
20. As an operator, I want `CANCEL` HybridActions to cancel actives under the gate, so that model cancel is real.
21. As an operator, I want `NO_OP` to emit no new intents, so that the model can sit out a tick without mutating the book.
22. As an operator, I want Action Translator version and tick_size pinned on the run, so that mappings are reproducible.
23. As an operator, I want Paper Decision State built from the live paper book and current market event, so that IQL sees the same world the gate will enforce.
24. As an operator, I want encoding to use the registry-pinned encoder version, so that lineage matches Model Qualification.
25. As an operator, I want encoder/schema mismatch to fail closed (invalid inference), so that incompatible models cannot trade.
26. As an operator, I want Ops Dashboard Strategy Mode controls, so that I can switch modes without using the research comparison page.
27. As an operator, I want projections for mode, latency, fallback/pause reason, and last IQL action summary, so that the UI does not invent authority.
28. As an operator, I want idempotent REST commands to set Strategy Mode and latency budget, so that double-clicks do not thrash mode.
29. As an operator, I want existing replay load/start/pause/resume/stop/tick and capital/orders/fills/lots/P&L projections to keep working, so that First Shippable Slice behavior is preserved.
30. As an operator, I want Guided Demo and research comparison routes unchanged as separate surfaces, so that research browsing is not conflated with paper control.
31. As a researcher, I want PFHedge excluded from paper Strategy Modes in this slice, so that IQL integration stays focused.
32. As a researcher, I want existing registry transition rules reused for Model Qualification, so that a second promotion system is not invented.
33. As a developer, I want a stubbable IQL inference port behind Paper Decision State, so that acceptance tests do not require a GPU or live Torch weights.
34. As a developer, I want unit tests for Action Translator edge cases (bounds, NO_OP, CANCEL, tick_size), so that mapping bugs are caught without full replay.
35. As a developer, I want unit tests for Paper Decision State construction, so that missing capital/lot fields fail closed.
36. As a developer, I want acceptance tests at the Paper Ops Control Plane proving `advisory` nudge and `iql_primary` pause, so that the slice is proven without UI-only proof.
37. As an auditor, I want append-only audit events for mode changes, inference outcomes, translator outputs, and gate decisions, so that IQL influence is reconstructible.
38. As an auditor, I want money paths to remain Decimal, so that IQL floats never enter accounting.
39. As an operator, I want inventory-backed ask rules preserved under all Strategy Modes, so that IQL cannot ask without an available Inventory Lot (gate/strategy still enforce).
40. As an operator, I want Paper Capital caps preserved under all Strategy Modes, so that IQL cannot bypass reserve/cash rules.
41. As an operator, I want switching from `iql_primary` to `deterministic` while paused to allow resume under deterministic quoting, so that I can recover without fixing IQL first.
42. As an operator, I want attempt to select an unqualified mode to return a clear error without changing the active mode, so that fail-closed is obvious.
43. As a developer, I want golden replay + stub IQL to produce deterministic ordered intents and fills for a fixed seed, so that regressions are golden-testable.
44. As an operator, I want loopback-oriented binding preserved, so that the control plane is not accidentally exposed.
45. As a researcher, I want this slice not to require shadow-only compare as a deliverable, so that effort goes to gated trading modes.

## Implementation Decisions

- **Test seam (approved):** Primary — Paper Ops Control Plane (REST commands + ordered projections/WebSocket). Supporting — Action Translator and Paper Decision State builder unit tests. Not primary — research UI, Ops Vitest alone, PFHedge paper path.
- **Glossary / ADR-0003:** Strategy Mode, Advisory Mode, IQL-Primary Mode, Model Qualification, Action Translator, Paper Decision State, Inference Latency Budget, Model-Integrated Paper Slice.
- **Architecture:** Extend PaperOpsSession quote path: on tick, if mode needs IQL → build Paper Decision State → encode → infer within latency budget → Action Translator → merge with Deterministic Strategy per mode → Deterministic Gate → existing execution/inventory/store.
- **Strategy Mode command:** idempotent paper command to set mode; reject unqualified transitions without mutating mode; audit success and rejection.
- **Inference port:** injectable interface for IQL inference; production binds registry artifact + encoder; tests inject stub returning HybridAction or failure/timeout.
- **Action Translator:** versioned; `QUOTE` → dollar offsets from ticks × tick_size at qty 1; ignore allocation for size; `CANCEL` / `NO_OP` as defined; pin translator version + tick_size on run.
- **Advisory:** deterministic base desired quotes; apply bounded tick nudge from IQL when valid; on invalid/late → deterministic base only for that tick (audited).
- **IQL-primary:** translator output is the desired quote author; on invalid/late → pause replay (status distinct from operator pause); no silent deterministic substitute while mode remains `iql_primary`.
- **Model Qualification:** reuse research registry states; do not invent a parallel promotion store for paper.
- **PFHedge:** out of paper Strategy Modes this slice.
- **Persistence:** extend append-only paper audit (and projections) for mode, inference latency, fallback/pause reasons, translator summary; no float money columns.
- **Ops Dashboard:** Strategy Mode selector + status for qualification, latency budget, pause-for-IQL; continue to treat projections as authoritative.
- **API:** extend `/api/paper` rather than routing paper execution through research shadow-only recommender paths; may reuse recommendation canonicalization helpers where they do not imply ungated authority.
- **Money:** Decimal in paper accounting; research float actions only enter via Action Translator into decimal prices.

## Testing Decisions

- Good tests assert **external behavior** at the Paper Ops Control Plane (commands → projections/audit/replay status), plus pure unit behavior of Action Translator and Paper Decision State builder.
- Acceptance: load golden replay, bind stub IQL + qualified registry double, set `advisory` / `iql_primary`, tick, assert orders/fills and fallback vs pause semantics.
- Unit: translator bounds, NO_OP/CANCEL/QUOTE, latency-exceeded treated as invalid, unqualified mode set rejected.
- Prior art: `tests/api/test_paper_ops_api.py`, `tests/api/test_research_api.py`, `tests/research/serving/test_recommender.py`, paper gate/execution unit tests, Ops Dashboard Vitest (mode controls only; not sole proof).
- Keep Guided Demo and research comparison tests green and separate.
- Fail-closed cases: unqualified mode, encoder mismatch, timeout, ask without lot, capital breach (unchanged gate).

## Out of Scope

- Shadow-only observation as the primary deliverable
- PFHedge as a paper Strategy Mode or advisory blend
- Multi-quantity Paper Orders driven by allocation
- Ungated model trading / model override of Deterministic Gate
- Live marketplace adapters
- Discord / Slack alerts, Prometheus / Grafana
- Full design §11 research promotion UI beyond what Ops needs for mode + qualification display
- Retraining IQL on paper transitions as a blocker for this slice
- Synthetic Scenario as execution evidence
- Products outside the Product-Family Allowlist

## Further Notes

- First Shippable Slice remains the deterministic baseline; this slice adds modes on top without removing deterministic-only operation.
- ADR-0002 deferred model influence for the first MM vertical; ADR-0003 authorizes this follow-on under Gate-final rules.
- Next after this slice (not here): paper→transition training plumbing, PFHedge paper mode, richer promotion UX.
