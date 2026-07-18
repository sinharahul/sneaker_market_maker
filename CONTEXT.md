# Sneaker Market Maker

Local-first paper trading and offline research for sneaker market making. Version 1 builds a continuous paper market-maker; live marketplace execution is out of scope.

## Language

**Continuous Paper Market-Maker**:
The Version 1 control-plane and simulation that keeps two-sided paper quotes alive under deterministic StockX historical replay (and StockX-shaped fixtures), revising, cancelling, or replacing paper orders as market and risk state change — without live execution.
_Avoid_: Live market maker, research demo, guided demo, shadow recommender (those are related but not this system)

**Product-Family Allowlist**:
The version-controlled set of product families the Continuous Paper Market-Maker may trade: Jordan 1 Retro and Nike Dunk Low only. Any other family fails validation.
_Avoid_: Open catalog, all sneakers, style-code free-for-all

**StockX Historical Replay**:
The authoritative Version 1 market-event source that drives the paper book for execution testing. For the first shippable slice this is a versioned, checksummed **Golden Historical Replay Dataset** for allowlisted products (historical-shaped, explicitly labeled); a larger real dump may replace that artifact later without changing the port. Distinct from StockX-Shaped Fixtures used only for casual local/dev.
_Avoid_: Live StockX feed, synthetic-as-proof, unlabeled fixture-as-benchmark

**Golden Historical Replay Dataset**:
The checked-in or loaded Version 1 replay artifact treated as StockX Historical Replay for Continuous Paper Market-Maker acceptance: versioned, checksummed, Product-Family Allowlist constrained, and swappable.
_Avoid_: Ad-hoc demo fixture, unlabeled synthetic path

**StockX-Shaped Fixture**:
A local-development market-event dataset that looks like StockX payloads but is not authoritative execution evidence.
_Avoid_: Historical replay, production benchmark

**Synthetic Scenario**:
Seeded GBM or shock paths used only for stress and model augmentation — never as authoritative evidence of paper-execution quality.
_Avoid_: Historical replay, execution benchmark

**Two-Sided Paper Quoting**:
The Version 1 quoting posture: maintain a deterministic desired bid when quoting is healthy, and an ask only when sellable inventory and risk allow (inventory-backed ask). Absence of an ask when flat is allowed; one-sided scalping as the strategy is not.
_Avoid_: Always-both-sides, bid-only strategy, ask-only strategy

**Deterministic Gate**:
The mandatory final authority on every paper place, revise, cancel, or replace. IQL may author or nudge Quote Intents under Strategy Mode, but never approves orders or overrides this gate.
_Avoid_: Model approval, soft risk check, optional gate

**Deterministic Strategy**:
The quote logic that produces desired bid/ask intents from market, inventory, capital, and fees without model influence. One of the operator-selectable Strategy Modes; always available as the fail-closed baseline.
_Avoid_: The only forever strategy, model-driven quoting (see Strategy Mode)

**Strategy Mode**:
The operator-selected quote brain for the Continuous Paper Market-Maker. Exactly one mode is active at a time: **deterministic** (Deterministic Strategy only), **advisory** (Deterministic Strategy base plus bounded IQL nudge), or **iql_primary** (IQL proposes intents). In every mode the Deterministic Gate remains the final authority on Paper Orders.
_Avoid_: Shadow-only observation as a Strategy Mode, stacking multiple quote brains on one tick, model override of the Gate

**Advisory Mode**:
Strategy Mode where the Deterministic Strategy proposes the base quote and a qualified IQL recommendation may apply a bounded skew/allocation nudge before the Deterministic Gate. If the recommendation is missing, late, or invalid, behavior falls back to the deterministic base.
_Avoid_: Unbounded model control, gate bypass, silent model authority

**IQL-Primary Mode**:
Strategy Mode where IQL proposes Quote Intents (mapped into the paper intent vocabulary) and the Deterministic Gate still accepts or rejects them. If IQL cannot produce a valid proposal (missing, late, or invalid), the StockX Historical Replay clock **pauses** until IQL is healthy again — quoting does not silently substitute Deterministic Strategy while the mode remains `iql_primary`.
_Avoid_: Ungated model execution, silent deterministic substitute while claiming IQL-primary, replacing the Gate

**First Shippable Slice**:
The Continuous Paper Market-Maker vertical that shipped first: Golden Historical Replay Dataset → Deterministic Strategy → Quote Intents → Deterministic Gate → Paper Orders → Fee-Aware Fills → Inventory Lots → Paper Capital/P&L → Authoritative Store → thin Ops Dashboard. Explicitly excluded model Strategy Modes, Discord/Slack alerts, Prometheus/Grafana, live marketplace adapters, and Synthetic Scenario as execution evidence.
_Avoid_: Treating First Shippable Slice as including IQL trading

**Model-Integrated Paper Slice**:
The vertical that wired Research/IQL into the paper quote loop under Strategy Mode (deterministic | advisory | iql_primary), still Deterministic-Gate-final, with Ops controls to select mode. **Shipped (R0).** Later dual-track work closed promote/bind with real artifacts (R3–R4). Entering **advisory** requires registry state `advisory_approved`; entering **iql_primary** requires at least `benchmark_qualified`. PFHedge is not a paper Strategy Mode (ADR-0005).
_Avoid_: Live marketplace orders, ungated model trading, PFHedge-authored paper quotes, research comparison page as a substitute for Ops mode control

**Research↔Paper Loop**:
The closed path from Continuous Paper Market-Maker experience to improved models: paper step effects → OfflineTransition export → mixed offline IQL retrain → registry register/promote → Ops `bind-model` of real weights. Track R (R1–R4) on `docs/ROADMAP.md`.
_Avoid_: Stub-only happy path as production proof, training on quarantined rows

**Read-Only Market Observation (L1)**:
Allowlisted StockX-shaped market snapshots from the observe port (`sneaker_market_maker.observe`) with no order credentials and no send client. Prep for live readiness; not paper capital mutation and not live-send.
_Avoid_: Live order adapter, treating observe as execution authority

**Model Qualification**:
The research registry progression that authorizes Strategy Modes which touch IQL: a model must reach `benchmark_qualified` before Ops may select `iql_primary`, and `advisory_approved` before Ops may select `advisory`. Deterministic mode needs no model qualification. Ops can advance legal edges via `promote-model` when a `RegistryService` is attached.
_Avoid_: Ad-hoc checkpoint without registry, operator override that skips qualification, a second parallel promotion system

**Action Translator**:
The versioned bridge from research `HybridAction` (category, ticks, allocation) to paper Quote Intents. For this slice: `QUOTE` maps touch ± (ticks × pinned tick_size) at quantity one; `CANCEL` cancels actives; `NO_OP` emits no new intents; allocation does not change size. Translator version and tick_size are pinned on the paper run.
_Avoid_: Multi-quantity paper from allocation, ad-hoc unversioned mapping, rewriting Paper Order semantics in this slice

**Paper Decision State**:
The research-compatible decision state built from the live paper book and current market event, then encoded with the registry-pinned encoder for IQL. Tests may inject a stub inference implementation behind the same port; they must not bypass Strategy Mode or the Deterministic Gate.
_Avoid_: Feeding raw Paper Order rows into the network, unversioned ad-hoc vectors, a second inference API that skips Mode Qualification

**Inference Latency Budget**:
The maximum wall-clock time allowed for IQL inference on a paper tick, pinned on the paper run (default 100ms, ceiling 250ms). Exceeding the budget counts as late/invalid: in `iql_primary` that pauses replay; in `advisory` that falls back to the deterministic base for that tick.
_Avoid_: Unlimited wait, unbounded operator-raised timeouts, treating slow success as healthy IQL-primary

**Paper Order**:
A simulated marketplace order for exactly one physical pair (quantity one). It is accepted, revised, cancelled, or replaced under the Deterministic Gate, and if it fills, it fills once in full — never partially.
_Avoid_: Live order, multi-quantity ticket, partial fill

**Paper Capital**:
Version 1 starting cash of $2,500.00. Aggregate principal reserved by open buy Paper Orders must not exceed 60% of that initial amount ($1,500.00); the reserve cap does not increase with paper profits. A buy must also fit available cash after existing reservations and expected buy-side fees and slippage.
_Avoid_: Unlimited capital, profit-scaling reserve cap, live funds

**Inventory Lot**:
One uniquely identified physical pair tracked through a lifecycle (at minimum purchase through availability and sale/settlement). Only lots in an available-for-sale state may back an ask. Not a fungible electronic position.
_Avoid_: Share count, virtual units, fungible position

**Ops Dashboard**:
The React control plane for the Continuous Paper Market-Maker: replay controls, Strategy Mode selection, and read models for Paper Capital, Paper Orders, fills, Inventory Lots, P&L, and (in the Model-Integrated Paper Slice) mode/audit of IQL influence. Distinct from the Guided Demo and research comparison pages.
_Avoid_: Guided demo, research comparison page as the paper control plane

**Quote Intent**:
An explicit place, revise, cancel, or replace instruction from the active Strategy Mode after comparing desired Two-Sided Paper Quoting with active Paper Orders. Continuous market-making means these intents keep firing under Deterministic Gate as market and risk state change — not a one-shot place.
_Avoid_: Set-and-forget quote, implicit book mutation without intent

**Authoritative Store**:
PostgreSQL as the durable system of record for Continuous Paper Market-Maker state — Paper Orders, Inventory Lots, fills, Paper Capital, and an append-only audit trail. The first shippable slice is not in-memory-only.
_Avoid_: Browser-only state, ephemeral process memory as source of truth

**Fee-Aware Fill**:
A Paper Order fill that records quoted price, execution price, slippage, fee-schedule version, and total fees, and updates Paper Capital / Inventory Lot cost basis / P&L accordingly. Required in the first shippable Continuous Paper Market-Maker slice.
_Avoid_: Gross-only fills, fee-free P&L
