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
The mandatory final authority on every paper place, revise, cancel, or replace. Model output may be compared in shadow or proposed as advisory later, but never approves orders or overrides this gate.
_Avoid_: Model approval, soft risk check, optional gate

**Deterministic Strategy**:
The Version 1 quote logic that produces desired bid/ask intents from market, inventory, capital, and fees without model influence. The first Continuous Paper Market-Maker shippable slice runs on this alone.
_Avoid_: Advisory strategy, model-driven quoting (later slices only)

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
The Version 1 React control plane for the Continuous Paper Market-Maker: load/start/pause/resume/stop StockX Historical Replay, enable/disable the Deterministic Strategy, and inspect Paper Capital, Paper Orders, fills, Inventory Lots, and P&L. Distinct from the Guided Demo and research comparison pages; model-research and advisory-promotion UI are later slices.
_Avoid_: Guided demo, research comparison page, full design §11 surface on day one

**Quote Intent**:
An explicit place, revise, cancel, or replace instruction from the quote engine after comparing desired Two-Sided Paper Quoting with active Paper Orders. Continuous market-making means these intents keep firing under Deterministic Gate as market and risk state change — not a one-shot place.
_Avoid_: Set-and-forget quote, implicit book mutation without intent

**Authoritative Store**:
PostgreSQL as the durable system of record for Continuous Paper Market-Maker state — Paper Orders, Inventory Lots, fills, Paper Capital, and an append-only audit trail. The first shippable slice is not in-memory-only.
_Avoid_: Browser-only state, ephemeral process memory as source of truth

**Fee-Aware Fill**:
A Paper Order fill that records quoted price, execution price, slippage, fee-schedule version, and total fees, and updates Paper Capital / Inventory Lot cost basis / P&L accordingly. Required in the first shippable Continuous Paper Market-Maker slice.
_Avoid_: Gross-only fills, fee-free P&L

**First Shippable Slice**:
The Continuous Paper Market-Maker vertical that ships first: Golden Historical Replay Dataset → Deterministic Strategy → Quote Intents → Deterministic Gate → Paper Orders → Fee-Aware Fills → Inventory Lots → Paper Capital/P&L → Authoritative Store → thin Ops Dashboard. Explicitly excludes model shadow/advisory in the quote loop, model-research/promotion UI, Discord/Slack alerts, Prometheus/Grafana, live marketplace adapters, and Synthetic Scenario as execution evidence.
_Avoid_: Full design §11 on day one, research-only demo as substitute
