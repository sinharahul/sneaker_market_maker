# Sneaker Market Maker Dashboard Design

**Date:** 2026-07-17
**Status:** Validated for implementation planning

## 1. Purpose

Build a local-first paper-trading dashboard that continuously makes a simulated
market in sneakers. The system consumes StockX-shaped fixture data or
deterministic historical replays, generates genuine two-sided quoting decisions,
and continuously revises, cancels, or replaces paper orders as the market and
risk state change.

Version 1 is a control plane and simulation environment, not a live trading
integration. It must make the strategy, capital usage, inventory lifecycle,
fees, slippage, fills, and P&L observable and reproducible before any future
authorized marketplace adapter is considered.

## 2. Scope and Safety Boundaries

### In scope

- A React dashboard for control, status, and inspection.
- A Python/FastAPI backend implemented as a modular event-driven monolith.
- REST commands for user intent and a WebSocket stream for state and domain
  events.
- An in-process typed event bus connecting independently testable modules.
- StockX-shaped fixtures and historical market replay.
- A continuous quote/revise/cancel/replace paper market-making loop.
- Paper order matching, fills, physical inventory state, cash accounting, fees,
  slippage, realized P&L, and mark-to-market unrealized P&L.
- PostgreSQL as the authoritative store, including an append-only audit event
  log.
- Deterministic recovery, command idempotency, observability, and a complete
  automated test strategy.

### Explicitly out of scope for version 1

- Cloudflare bypass or circumvention of marketplace protections.
- Proxy-ban evasion, fingerprint rotation, CAPTCHA bypass, or related techniques.
- Undocumented or private marketplace API use.
- Scraping that violates marketplace terms or access controls.
- Live order submission, modification, cancellation, or account automation.
- Custody or movement of real funds.

The future integration seam accepts only a documented, authorized marketplace
adapter. Adding that adapter requires a separate design and safety review; it
does not change version 1 into a live trading system.

## 3. Success Criteria

The first release is successful when an operator can:

1. Start, pause, resume, and stop a deterministic historical replay.
2. Enable or disable the paper strategy without restarting the service.
3. Watch the engine issue and continuously maintain genuine paper quotes rather
   than merely display hypothetical opportunities.
4. See every quote decision, order transition, fill, inventory transition, fee,
   slippage charge, and P&L change reflected in the dashboard and audit log.
5. Confirm that total open buy-order exposure never exceeds 60% of the initial
   $2,500 paper capital, and that neither reserved nor spent capital can make
   available cash negative.
6. Restart the backend and recover to the same authoritative state without
   duplicated commands, orders, fills, accounting entries, or inventory.
7. Re-run a seeded replay and obtain the same ordered decisions, fills, and
   terminal portfolio state.

## 4. Architecture

The system is a modular event-driven monolith. One FastAPI process hosts the API,
strategy modules, simulator, paper execution engine, and typed event bus. This
keeps deployment and consistency simple while preserving module boundaries that
could later support separate workers if scale requires them.

```text
React control plane
  | REST commands                     ^ WebSocket events/snapshots
  v                                   |
FastAPI API layer --------------------+
  |
Application command handlers
  |
In-process typed event bus
  |---- Market simulator / replay
  |---- Quote engine
  |---- Risk engine
  |---- Paper execution
  |---- Inventory and accounting
  `---- Projection / WebSocket publisher
  |
PostgreSQL: authoritative state + append-only audit events
```

REST expresses operator intent and returns an accepted or completed command
result. WebSocket messages report ordered facts and projection updates. The
client never treats an optimistic local update as authoritative.

All money, prices, fees, and quantities use exact decimal or integer
representations in Python and PostgreSQL. Floating-point values are limited to
statistical calculations and are converted through explicit rounding rules
before reaching accounting or order logic.

## 5. Module Boundaries

### API and control plane

FastAPI validates REST commands, enforces idempotency keys, and maps domain
errors to stable error responses. It exposes read models and publishes ordered
events over WebSocket. It contains no quote, risk, fill, or accounting policy.
Version 1 binds to loopback by default and has no multi-user authentication;
deploying it beyond loopback requires an authenticated external access layer.

### Market simulator

The simulator loads versioned StockX-shaped fixtures or historical replay
datasets, validates and normalizes them, and emits timestamped market events
under a controllable simulation clock. Controls include load, start, pause,
resume, stop, replay speed, and seeded reset. Replay ordering is deterministic,
including events sharing a source timestamp.

The simulator is connected through a market-data port. A future documented,
authorized StockX adapter may implement the same port, but no network adapter or
credential flow is included in version 1.

### Quote engine

The quote engine consumes normalized market observations, current paper orders,
inventory, capital, fees, and risk decisions. It computes bid and ask intents
for each configured product and size. It compares desired quotes with active
paper orders and emits explicit place, revise, cancel, or replace intents.

A quote is genuine within the paper market: while enabled, the engine maintains
an actionable simulated order until it fills, becomes invalid, violates risk,
is superseded by a materially different quote, or the strategy stops. Quote
revision uses configurable price and age thresholds to prevent churn. An ask is
allowed only when sellable inventory exists and is not already reserved.

### Risk engine

The risk engine is the mandatory gate before every paper order placement or
replacement. It evaluates capital reservations, inventory availability, stale
market data, price sanity, fee-aware economics, duplicate exposure, and
configured per-product or portfolio limits. Rejections use stable,
machine-readable reason codes and fail closed.

Paper capital starts at **$2,500.00**. The aggregate principal reserved by all
open buy orders must be at most **60% of initial paper capital**, or
**$1,500.00**. This cap does not grow with paper profits. A proposed buy must
also fit within available cash after existing reservations and expected
buy-side fees and slippage. Replacements release the old reservation and reserve
the new amount atomically so a failure cannot create unbacked exposure.

### Paper execution engine

The paper execution engine owns the order state machine and matches active
paper orders against replayed market events using explicit, deterministic
rules. It supports no live marketplace calls. Version 1 paper orders represent
one physical pair, so each accepted order has quantity one and fills exactly
once in full. The engine records acceptance, revision, cancellation, replacement
linkage, fill, and rejection.

Execution prices incorporate the configured slippage model. Each fill records
the raw market reference, quoted price, execution price, slippage, fee schedule
version, and total fees so results can be audited and replayed.

### Inventory and accounting

The inventory module models physical units, not immediately fungible electronic
positions. A buy fill creates one or more uniquely identified inventory lots
and starts the physical lifecycle:

```text
PURCHASED -> IN_TRANSIT -> AUTHENTICATING -> AVAILABLE
AVAILABLE -> RESERVED_FOR_SALE -> SOLD -> SETTLED
```

Exceptional terminal or corrective states are `AUTH_FAILED`, `RETURNED`, and
`LOST`. Simulator events drive transit, authentication, return, sale, and
settlement transitions. Only `AVAILABLE` units may back an ask; reserved units
cannot back another ask. Every transition is validated and audited.

Accounting maintains initial capital, available cash, order reservations,
pending settlement, fees, inventory cost basis, realized P&L, and unrealized
P&L. Buy fills reduce cash and establish landed cost basis. Sale settlement
releases proceeds and realizes P&L net of all modeled fees, shipping, and
slippage. Unrealized P&L uses a named, timestamped mark policy and is displayed
separately from realized P&L.

### Projection and event streaming

Projection handlers build dashboard read models from committed domain changes.
The WebSocket publisher sends an initial snapshot followed by ordered,
versioned events. Every message carries an event identifier, aggregate version,
event type, schema version, occurrence time, and simulation time. A reconnecting
client supplies its last event identifier; the server replays retained events
or sends a fresh snapshot when the requested gap is unavailable.

## 6. Events and Data Flow

Typed events are immutable dataclasses or validated models with explicit schema
versions. Representative event families are:

- Simulation: `ReplayLoaded`, `ReplayStarted`, `ReplayPaused`,
  `ReplayResumed`, `ReplayStopped`, `SimulationClockAdvanced`.
- Market data: `MarketObservationReceived`, `MarketDataRejected`,
  `MarketDataBecameStale`.
- Strategy: `QuoteCalculated`, `QuoteSkipped`, `QuoteCancelRequested`,
  `QuoteReplaceRequested`.
- Risk: `OrderRiskApproved`, `OrderRiskRejected`, `CapitalReserved`,
  `CapitalReleased`.
- Execution: `PaperOrderAccepted`, `PaperOrderRevised`,
  `PaperOrderCancelled`, `PaperOrderReplaced`, `PaperOrderFilled`.
- Inventory: `InventoryPurchased`, `InventoryTransitioned`,
  `InventoryReserved`, `InventoryReleased`.
- Accounting: `FeeCharged`, `SettlementCompleted`, `PnLMarked`.
- Operations: `CommandAccepted`, `CommandRejected`, `ComponentDegraded`,
  `ComponentRecovered`.

The core loop is:

1. The simulator commits a normalized market observation.
2. The event bus delivers it to quote and projection handlers.
3. The quote engine computes desired bid and inventory-backed ask intents.
4. Risk approves or rejects each order-changing intent.
5. Paper execution atomically applies approved intents and capital or inventory
   reservations.
6. Later market or lifecycle events cause fills, cancellations, replacements,
   inventory transitions, settlements, and P&L updates.
7. Committed events update projections and are streamed to the dashboard.
8. The loop repeats on each relevant market event and on a configurable quote
   maintenance tick, enabling cancellation or replacement even when no trade
   occurs.

Handlers must not publish observable follow-up events until the database
transaction containing their state change and audit events commits. In-process
delivery failures are retried from the durable event log.

## 7. Persistence Model

PostgreSQL is authoritative. Core tables include:

- simulation runs, replay metadata, clock state, and strategy configuration;
- normalized market observations;
- quote decisions and risk decisions;
- paper orders, order revisions, replacement links, and fills;
- capital reservations, immutable accounting entries, and settlements;
- physical inventory lots and inventory transitions;
- current read projections; and
- append-only audit events.

The audit table contains globally ordered event IDs, event type and schema
version, aggregate ID and version, correlation and causation IDs, command
idempotency key where applicable, simulation and wall-clock timestamps, and a
JSON payload. Audit rows are never updated or deleted by normal application
flows.

Domain state and its corresponding audit rows are committed in one transaction.
Database constraints enforce unique fill identifiers, one active reservation
per order, legal aggregate versions, and command idempotency. Accounting uses
balanced, immutable entries rather than mutable totals; displayed totals are
projections that can be rebuilt.

## 8. Idempotency and Recovery

Every mutating REST request requires an `Idempotency-Key`. The server persists
the key, normalized request hash, status, and response. Retrying the same key and
payload returns the original result; reusing the key with a different payload
returns a conflict.

Market observations, replay records, order intents, fills, inventory
transitions, and settlements each have stable source or derived identities.
Consumers record the last processed event and use uniqueness constraints so
at-least-once internal delivery cannot duplicate side effects.

At startup, the service:

1. verifies database migrations and configuration;
2. reconstructs or validates projections from authoritative state;
3. identifies accepted commands or committed events with unfinished work;
4. resumes them idempotently;
5. reconciles cash, reservations, orders, fills, and inventory;
6. keeps strategy execution disabled if reconciliation fails; and
7. exposes recovery status and reason through REST, WebSocket, and health checks.

A paused or stopped run remains paused or stopped after restart. An active run
may resume only after successful reconciliation and according to an explicit
run-level `resume_on_restart` setting, which defaults to false.

## 9. Fees and Slippage

Fee schedules are versioned and effective-dated. They support percentage and
fixed components for purchase, sale, payment processing, shipping,
authentication, and other configured marketplace costs. The quote engine uses
the same fee calculator as accounting so displayed edge cannot differ from
settled P&L.

Slippage is an explicit versioned model, not a hidden adjustment. Version 1
supports deterministic fixed or basis-point slippage and a seeded stochastic
fixture model. Buy slippage can only worsen the execution price upward; sell
slippage can only worsen it downward. Rounding mode and currency precision are
centralized and tested at boundary values.

The dashboard shows gross spread, expected net edge, modeled fees, modeled
slippage, landed cost, proceeds, and net P&L as separate values.

## 10. API and WebSocket Contract

REST endpoints are organized around commands and read models:

- simulation load, start, pause, resume, stop, reset, speed, and seed;
- strategy enable, disable, and configuration;
- explicit paper-order cancellation for operator control;
- status, configuration, capital, active quotes, order history, fills,
  inventory, P&L, replay progress, and audit events;
- liveness, readiness, and detailed component health.

Commands return a command ID, status, correlation ID, and either the resulting
resource version or a stable error object. HTTP status codes distinguish
validation, idempotency conflict, invalid state transition, risk rejection,
not found, temporary unavailability, and internal failure.

The WebSocket protocol begins with subscription acknowledgement and an
authoritative snapshot. Subsequent messages use a versioned envelope and are
ordered by global audit event ID. The client detects gaps and requests recovery
instead of applying events out of order. Heartbeats make stalled connections
visible. Backpressure is bounded; a client that falls too far behind receives a
resync-required message rather than causing unbounded server memory growth.

## 11. React Dashboard

The dashboard is an operational control plane with these areas:

- **Controls:** load replay, set speed and seed, start/pause/resume/stop the
  simulator, enable/disable the strategy, and issue explicit paper cancels.
- **System status:** backend, database, event bus, simulator, strategy, recovery,
  WebSocket connection, simulation clock, replay progress, and stale-data state.
- **Capital and risk:** initial capital, available cash, reserved bid principal,
  expected fees/slippage reserve, pending settlement, the $1,500 open-bid cap,
  current utilization, and recent risk rejections.
- **Quotes and orders:** desired versus active bid/ask, quote age, revisions,
  cancellation/replacement reason, order state, and inventory backing for asks.
- **Fills:** side, product and size, quantity, quote and execution prices,
  slippage, fees, source event, and timestamp.
- **Physical inventory:** lot identity, product/size, lifecycle state, age,
  landed cost, reservation, expected arrival/settlement, and exception reason.
- **P&L:** realized, unrealized, gross spread, fees, slippage, inventory value,
  and a time series keyed to simulation time.
- **Simulator:** dataset metadata, seed, speed, current timestamp, event counts,
  and deterministic replay controls.
- **Audit/activity:** correlated operator commands, decisions, state
  transitions, errors, and recovery events.

Controls are disabled when their command is illegal in the current state, but
the backend remains the final authority. Destructive simulation reset requires
confirmation and creates an audit event. The UI visibly distinguishes wall time
from simulation time and realized P&L from unrealized P&L. Connection loss
freezes controls that require fresh state and triggers snapshot resynchronization
after reconnect.

## 12. Error Handling

- Fixture and market-data validation failures are quarantined with a reason;
  malformed values are never silently converted to zero.
- Stale, missing, crossed, or nonsensical markets fail closed for new quotes and
  trigger cancellation of unsafe active quotes.
- Risk rejections are expected domain outcomes, not server errors, and include
  stable codes and relevant limit/current/proposed values.
- Invalid order or inventory transitions are rejected atomically and audited.
- Database failure prevents acknowledgement of uncommitted commands. The
  strategy enters a degraded, no-new-orders state until authoritative state is
  available and reconciled.
- Event handler failures use bounded retries with structured diagnostics.
  Exhaustion marks the component degraded and prevents dependent strategy
  actions; events remain recoverable from the audit log.
- Unknown fee schedules, rounding failures, or accounting imbalance halt the
  affected flow and fail readiness rather than estimate.
- UI errors retain the command correlation ID, explain whether a retry is safe,
  and never imply success before server confirmation.

## 13. Observability

Structured logs include correlation ID, causation ID, command ID, event ID,
simulation run, aggregate, product/size where applicable, and wall and
simulation times. Sensitive configuration is redacted.

Metrics cover market-event throughput and lag, quote calculation and churn,
risk approvals and rejections by reason, bid-cap utilization, open orders,
fills, fees, slippage, inventory by lifecycle state, realized/unrealized P&L,
event-handler latency and retries, WebSocket clients and resyncs, database
latency, and reconciliation failures.

Health endpoints separate liveness from readiness. Readiness fails when the
database, migrations, reconciliation, accounting invariants, simulator, or
required event handlers cannot safely support commands. Traces follow a market
observation through quote, risk, execution, accounting, projection, and
WebSocket publication.

Operational invariants are continuously checked:

- available cash, reservations, and ledger balances reconcile;
- open buy principal is at most $1,500;
- each active ask has distinct sellable inventory backing;
- each fill maps to exactly one order and accounting effect;
- aggregate versions are contiguous; and
- projection positions do not exceed the committed audit-event position.

## 14. Test Strategy

### Unit tests

- Quote calculations, threshold-based revise/cancel/replace behavior, and
  inventory-backed ask rules.
- Risk limits, especially exact values below, at, and above the $1,500 bid cap.
- Fee, slippage, decimal rounding, capital reservation, cost-basis, settlement,
  and realized/unrealized P&L calculations.
- All order and inventory lifecycle transitions, including illegal transitions.
- Fixture normalization and rejection of malformed or stale observations.
- Event schemas, version handling, idempotency, and deterministic identifiers.

### Property and invariant tests

- Random command and event sequences never produce negative available cash,
  excess open-bid exposure, double-reserved inventory, duplicate fills, or an
  unbalanced ledger.
- Buy slippage never improves and sell slippage never improves execution.
- Replaying the same ordered events is idempotent.
- Rebuilt projections equal incrementally maintained projections.

### Integration tests

- FastAPI, event bus, and PostgreSQL transaction boundaries using a real test
  database.
- Duplicate and conflicting idempotency keys.
- Atomic order replacement and reservation transfer.
- Fill-to-inventory-to-sale-to-settlement accounting.
- Handler retry, database interruption, startup reconciliation, and projection
  rebuild.
- WebSocket snapshot, ordered updates, reconnect catch-up, gap detection,
  heartbeat, and slow-client resync.

### Deterministic simulation tests

- Golden StockX fixture and historical replay scenarios.
- Seeded replays produce identical decisions, fills, audit-event order, and
  terminal portfolio state.
- Replay speed changes wall-clock duration without changing simulation results.
- Pausing, restarting, and resuming preserves the simulation position and does
  not duplicate effects.

### Frontend tests

- Component tests for controls, status, capital/risk, quotes, fills, inventory,
  P&L, simulator, and error states.
- Reducer tests for snapshots, ordered events, duplicate events, gaps, and
  resynchronization.
- API contract tests generated from or checked against the FastAPI schema.
- Accessibility tests for keyboard operation, labels, status announcements,
  focus behavior, and non-color-only state indicators.
- End-to-end tests for the complete operator workflow, disconnection recovery,
  risk rejection visibility, inventory lifecycle, and deterministic replay.

### Safety and scope tests

- Static configuration and dependency checks verify that version 1 has no live
  order endpoint, marketplace credential flow, protection-bypass code, proxy
  evasion, or undocumented/private API integration.
- Adapter contract tests use only local fakes. A network-deny test ensures the
  default test and simulation paths require no marketplace network access.

## 15. Delivery Boundaries

The implementation plan should preserve independently reviewable slices:
domain types and persistence, simulator, risk and accounting, paper execution,
quote loop, API/event streaming, and React dashboard. Each slice must include
its tests and observable failure behavior.

Version 1 is complete only when the continuous paper loop, physical inventory
lifecycle, recovery guarantees, and dashboard are integrated end to end. A
future authorized data adapter is an extension point, not a version 1
deliverable. Live order submission remains excluded regardless of adapter
availability.
