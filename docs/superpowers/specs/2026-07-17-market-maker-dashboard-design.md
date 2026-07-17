# Sneaker Market Maker Dashboard Design

**Date:** 2026-07-17
**Status:** Validated for implementation planning

## 1. Purpose

Build a local-first paper-trading dashboard that continuously makes a simulated
market in **Jordan 1 Retro** and **Nike Dunk Low** products. Version 1 starts
with deterministic StockX historical replay and StockX-shaped fixtures,
generates genuine two-sided paper-quoting decisions, and continuously revises,
cancels, or replaces paper orders as the market and risk state change.

Version 1 is a control plane and simulation environment, not a live trading
integration. It must make the strategy, capital usage, inventory lifecycle,
fees, slippage, fills, and P&L observable and reproducible before any future
authorized marketplace adapter is considered. It also establishes a governed
quantitative research path: every valid market snapshot produces a versioned
five-feature vector, and a PyTorch `SneakerHedgingNet` is trained and evaluated
offline before running in shadow mode. The model cannot approve orders or
override deterministic controls.

## 2. Scope and Safety Boundaries

### In scope

- A React dashboard for control, status, and inspection.
- A Python/FastAPI backend implemented as a modular event-driven monolith.
- REST commands for user intent and a WebSocket stream for state and domain
  events.
- An in-process typed event bus connecting independently testable modules.
- StockX historical replay as the first and authoritative execution-testing
  source, plus versioned StockX-shaped fixtures for local development.
- Jordan 1 Retro and Nike Dunk Low only, identified by an explicit,
  version-controlled product-family allowlist; other products fail validation.
- A continuous quote/revise/cancel/replace paper market-making loop.
- Paper order matching, fills, physical inventory state, cash accounting, fees,
  slippage, realized P&L, and mark-to-market unrealized P&L.
- A richer validated domain snapshot plus a separately versioned five-feature
  model vector: `highest_bid`, `lowest_ask`, `days_since_release`,
  `volatility_48h`, and `fee_rate`.
- A PyTorch `SneakerHedgingNet`, entropic-risk research objective, reproducible
  training/evaluation pipeline, model registry, shadow inference, and benchmark
  approval workflow.
- Seeded GBM scenarios with explicit discrete restock and event shocks for
  stress testing and model training augmentation, never as authoritative
  evidence of execution quality.
- PostgreSQL as the authoritative store, including an append-only audit event
  log.
- Asynchronous Discord and Slack operational alerts with bounded timeout,
  retry, redaction, and durable delivery status.
- Prometheus metrics and optional operator-supplied Grafana dashboards.
- Deterministic recovery, command idempotency, observability, and a complete
  automated test strategy.

### Explicitly out of scope for version 1

- TLS fingerprinting, fingerprint rotation, Cloudflare bypass, CAPTCHA bypass,
  proxy rotation for ban evasion, or related circumvention techniques.
- Undocumented or private marketplace API use.
- Scraping that violates marketplace terms or access controls.
- Live order submission, modification, cancellation, or account automation.
- Custody or movement of real funds.
- Products outside Jordan 1 Retro and Nike Dunk Low.
- Model authority to approve orders, bypass gates, directly place orders, or
  control execution.
- Any claim that the version 1 sigmoid MLP and entropic loss constitute Deep
  Bellman Hedging or reinforcement learning.

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
8. Trace each valid domain snapshot to an immutable, schema-versioned five-
   feature vector; malformed or incomplete payloads are quarantined and never
   zero-filled.
9. Reproduce a `SneakerHedgingNet` training/evaluation run from its dataset,
   feature schema, code, configuration, seed, and artifact references.
10. Compare shadow-model outputs with deterministic decisions and approved
    baselines without permitting the model to alter orders.
11. Demonstrate that any later advisory mode can affect only allocation within
    already-approved limits and quote skew, and that fee, capital, liquidity,
    inventory, stale-data, price-sanity, and exposure gates remain authoritative.
12. Use StockX historical replay for execution benchmarks and separately report
    GBM/restock/event-shock stress results without conflating the two.
13. Observe Prometheus metrics and inspect redacted Discord/Slack alert delivery
    attempts, including timeout, retry, success, and terminal failure states.

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
  |---- StockX replay / scenario simulator
  |---- Snapshot normalization / feature extraction
  |---- Quote engine
  |---- Deterministic risk gates
  |---- Model inference / research orchestration
  |---- Paper execution
  |---- Inventory and accounting
  |---- Projection / WebSocket publisher
  `---- Alert dispatcher / metrics
  |
PostgreSQL: authoritative state + model lineage + delivery attempts
            + append-only audit events
```

REST expresses operator intent and returns an accepted or completed command
result. WebSocket messages report ordered facts and projection updates. The
client never treats an optimistic local update as authoritative.

All money, prices, fees, and quantities use exact decimal or integer
representations in Python and PostgreSQL. Floating-point values are limited to
statistical calculations and are converted through explicit rounding rules
before reaching accounting or order logic.

Historical replay and synthetic scenarios are deliberately separate data
sources behind the same normalized market-event port. StockX replay is
authoritative for execution testing because it preserves observed ordering and
market conditions. GBM with explicit restock and event shocks is used only for
stress analysis and training scenarios; scenario results are labeled synthetic
through storage, metrics, API responses, and dashboard views.

The model path is also separated from deterministic decision authority. Feature
extraction and inference may run asynchronously from committed observations,
but quote generation never waits indefinitely for a model result. In shadow
mode, inference is recorded and compared only. A benchmark-approved model may
later enter advisory mode and suggest bounded allocation weights or quote skew;
the quote and risk engines clamp those suggestions to configuration and apply
all deterministic gates afterward.

## 5. Module Boundaries

### API and control plane

FastAPI validates REST commands, enforces idempotency keys, and maps domain
errors to stable error responses. It exposes read models and publishes ordered
events over WebSocket. It contains no quote, risk, fill, or accounting policy.
Version 1 binds to loopback by default and has no multi-user authentication;
deploying it beyond loopback requires an authenticated external access layer.

### Market simulator

The simulator loads versioned StockX historical replay datasets first, with
StockX-shaped fixtures as a local-development fallback. It accepts only the
Jordan 1 Retro and Nike Dunk Low allowlisted families, validates and normalizes
records, and emits timestamped market events under a controllable simulation
clock. Controls include load, start, pause, resume, stop, replay speed, and
seeded reset. Replay ordering is deterministic, including events sharing a
source timestamp. Dataset manifests record source, collection window, product
family, schema, checksum, and whether data is historical or synthetic.

A distinct scenario generator produces seeded GBM paths with configurable
drift, volatility, horizon, and discrete restock or named event shocks. It emits
the same normalized event contract but carries `source_kind=synthetic` and a
scenario definition/version. Synthetic paths can expand stress and training
coverage but cannot pass an execution benchmark or replace a historical holdout.

The simulator is connected through a market-data port. A future documented,
authorized StockX adapter may implement the same port, but no network adapter or
credential flow is included in version 1.

### Snapshot normalization and feature extraction

The normalization module converts StockX-shaped records into a rich immutable
domain snapshot containing source identity, product family, style code, size,
bid/ask, recent sales and liquidity, volatility, release timing, source and
ingestion timestamps, fee-schedule reference, and data-quality metadata. It
validates required fields, numeric finiteness, positive prices and sizes,
timestamps, family allowlisting, and supported schema versions.

After snapshot validation, a pure feature extractor creates exactly this
version 1 ordered vector:

```text
[highest_bid, lowest_ask, days_since_release, volatility_48h, fee_rate]
```

The vector is a model input, not a replacement for the richer snapshot. Each
stored vector references its snapshot, feature-schema name and semantic version,
ordered feature names, raw values, transformation/scaler version, and creation
time. A missing, malformed, non-finite, or out-of-range required field rejects
the payload and emits a reason-coded data-quality event; no path silently
substitutes zero or another default.

### Quantitative research and model inference

The research module provides a PyTorch `SneakerHedgingNet`: a versioned MLP over
the five-feature vector with two 32-unit ReLU hidden layers and one sigmoid
output, plus an entropic-risk training/evaluation pipeline. The scalar output is
a normalized hedge/allocation score in `[0, 1]`, not an order directive. A
versioned deterministic interpreter may map that score to bounded allocation
weight and quote-skew suggestions only in advisory mode. Runs pin the
historical/synthetic dataset versions, split policy, feature and scaler
versions, model architecture, loss configuration, optimizer, hyperparameters,
code revision, random seeds, environment, and artifact hashes. Training data
may include labeled synthetic stress scenarios, but evaluation reports
historical replay holdouts separately and uses them for promotion.

The entropic-risk objective uses a declared risk-aversion parameter (default
`0.5`, configurable and persisted per run) and a numerically stable loss
`log(mean(exp(-risk_aversion * final_net_PnL))) / risk_aversion`, with the
zero-risk-aversion limit handled explicitly. `final_net_PnL` includes modeled
fees, processing charges, shipping, and slippage over the declared horizon.
Reports include the objective, ordinary P&L/error metrics, tail risk, drawdown,
turnover, inventory and capital utilization, gate rejection rates, calibration
where applicable, and uncertainty across seeds. A model version is immutable
after registration.

New models start in **shadow** mode. Inference records the input vector, model
and scaler versions, raw output, interpreted recommendation, latency, and any
error, but does not affect quote or execution behavior. Promotion to
**advisory** requires an explicit operator approval tied to a benchmark report
and audit event. Advisory output is limited to bounded allocation weighting
within deterministic capital/product limits and bounded bid/ask quote skew.
Timeout, unavailable model, unknown feature version, invalid output, or NaN/Inf
falls back to the deterministic strategy and records a failed-closed inference
decision. Advisory can be disabled or rolled back without restarting.

Fee, capital, liquidity, inventory, stale-data, price-sanity, and exposure gates
are always evaluated deterministically after advisory adjustments. The model
cannot turn a rejected opportunity into an approved order, reserve capital,
select unsupported products, create inventory, or call paper execution.

### Quote engine

The quote engine consumes normalized market observations, current paper orders,
inventory, capital, fees, deterministic strategy configuration, and optionally
a valid advisory recommendation. It computes bid and ask intents for each
configured allowlisted product and size. It compares desired quotes with active
paper orders and emits explicit place, revise, cancel, or replace intents.
Model influence, when enabled, is recorded as a bounded allocation or skew
adjustment on the quote decision so the deterministic base quote remains
auditable.

A quote is genuine within the paper market: while enabled, the engine maintains
an actionable simulated order until it fills, becomes invalid, violates risk,
is superseded by a materially different quote, or the strategy stops. Quote
revision uses configurable price and age thresholds to prevent churn. An ask is
allowed only when sellable inventory exists and is not already reserved.

### Risk engine

The risk engine is the mandatory and authoritative gate before every paper order
placement or replacement, including model-influenced intents. It evaluates fee-
aware economics, capital reservations, liquidity thresholds, inventory
availability, stale market data, price sanity, supported product family,
duplicate exposure, and configured per-product or portfolio limits. Rejections
use stable, machine-readable reason codes and fail closed. No model confidence,
score, or recommendation can bypass or weaken a gate.

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

### Alert delivery

An asynchronous alert dispatcher subscribes only to committed events such as
paper order acceptance/rejection/fill/cancel, settlement, degraded components,
invariant violations, prolonged stale data, model promotion/rollback, replay
failure, and terminal webhook delivery failure.
Discord and Slack are outbound webhook adapters behind one port; neither is in
the trading decision path.

Each destination has an explicit connect/read timeout, bounded exponential
backoff with jitter, maximum attempts, and a redaction policy applied before
persistence and transmission. Secrets, webhook URLs, authorization material,
raw payloads containing sensitive configuration, and unexpected user-provided
fields are never included. Every attempt records pending, in-flight, delivered,
retryable failure, or terminal failure status plus timestamps, HTTP status where
safe, a sanitized error code, and next-attempt time. A stable alert/destination
idempotency key prevents duplicate logical notifications. Delivery failure is
visible and auditable but cannot block event processing or paper execution.

### Deep Bellman Hedging / RL research boundary

The specified `SneakerHedgingNet` is a sigmoid MLP trained with an entropic-risk
loss. That is supervised or direct policy-scoring research, **not yet Deep
Bellman Hedging or reinforcement learning**. The project must not make either
claim based on the version 1 model.

Before such a claim, a separate approved design must define and implement:

- an MDP state containing at least time, product/size market state, open orders,
  physical inventory lifecycle, cash/reservations, fee state, stale-data state,
  and relevant exogenous event history;
- an action space for bounded quote offsets/skew, allocation or no-op/cancel
  choices, with deterministic safety gates outside the learned policy;
- a step reward based on fee- and slippage-adjusted portfolio P&L plus explicit
  inventory, capital, turnover, drawdown, stale-quote, and terminal liquidation
  penalties, with a declared entropic or other risk-sensitive objective;
- a value function, Q-function, or stochastic policy objective and Bellman
  recursion/training algorithm, rather than only terminal sigmoid output;
- transition tuples containing state, action, propensity/behavior-policy
  metadata, next state, reward, terminal flag, timing, and execution outcomes
  from historical replay or a separately validated simulator;
- benchmarks against the deterministic strategy, no-model and simple heuristic
  baselines, and the version 1 MLP under identical historical holdouts, fees,
  latency assumptions, and deterministic gates; and
- offline evaluation covering walk-forward splits, leakage controls, multiple
  seeds, confidence intervals, stress regimes, off-policy evaluation where
  applicable, action-support checks, ablations, and tail-risk/inventory/capital
  metrics before shadow deployment.

## 6. Events and Data Flow

Typed events are immutable dataclasses or validated models with explicit schema
versions. Representative event families are:

- Simulation: `ReplayLoaded`, `ReplayStarted`, `ReplayPaused`,
  `ReplayResumed`, `ReplayStopped`, `SimulationClockAdvanced`.
- Market data: `MarketObservationReceived`, `MarketDataRejected`,
  `MarketDataBecameStale`, `FeatureVectorCreated`,
  `FeatureVectorRejected`.
- Strategy: `QuoteCalculated`, `QuoteSkipped`, `QuoteCancelRequested`,
  `QuoteReplaceRequested`.
- Risk: `OrderRiskApproved`, `OrderRiskRejected`, `CapitalReserved`,
  `CapitalReleased`.
- Model research: `TrainingRunStarted`, `TrainingRunCompleted`,
  `EvaluationRunCompleted`, `ModelVersionRegistered`,
  `ModelPromotionApproved`, `ModelRolledBack`.
- Model inference: `InferenceRequested`, `InferenceCompleted`,
  `InferenceRejected`, `AdvisoryApplied`, `AdvisoryIgnored`.
- Execution: `PaperOrderAccepted`, `PaperOrderRevised`,
  `PaperOrderCancelled`, `PaperOrderReplaced`, `PaperOrderFilled`.
- Inventory: `InventoryPurchased`, `InventoryTransitioned`,
  `InventoryReserved`, `InventoryReleased`.
- Accounting: `FeeCharged`, `SettlementCompleted`, `PnLMarked`.
- Operations: `CommandAccepted`, `CommandRejected`, `ComponentDegraded`,
  `ComponentRecovered`, `AlertQueued`, `WebhookDeliveryAttempted`,
  `WebhookDelivered`, `WebhookDeliveryFailed`.

The core loop is:

1. StockX replay commits a validated normalized market observation; malformed,
   unsupported, or incomplete input is quarantined and processing stops for that
   record.
2. Feature extraction commits the versioned five-feature vector linked to the
   richer snapshot.
3. The event bus delivers the observation to quote and projection handlers and
   independently requests shadow or advisory inference when configured.
4. The quote engine computes deterministic desired bid and inventory-backed ask
   intents. In advisory mode only, a timely valid recommendation may apply a
   bounded allocation or quote-skew adjustment.
5. Deterministic risk gates approve or reject each order-changing intent after
   any advisory adjustment.
6. Paper execution atomically applies approved intents and capital or inventory
   reservations.
7. Later historical market or lifecycle events cause fills, cancellations, replacements,
   inventory transitions, settlements, and P&L updates.
8. Committed events update projections, metrics and alert subscriptions, and are
   streamed to the dashboard.
9. The loop repeats on each relevant market event and on a configurable quote
   maintenance tick, enabling cancellation or replacement even when no trade
   occurs.

Handlers must not publish observable follow-up events until the database
transaction containing their state change and audit events commits. In-process
delivery failures are retried from the durable event log.

Model training is not part of the latency-sensitive quote loop. A research run
selects immutable dataset manifests, creates train/validation/historical
holdout splits, materializes versioned vectors, trains artifacts, evaluates
them against registered baselines, and stores a promotion report. Registration
does not imply approval; shadow or advisory activation is a separate audited
operator command.

## 7. Persistence Model

PostgreSQL is authoritative. Core tables include:

- simulation runs, historical replay and synthetic scenario manifests, clock
  state, seeds, checksums, and strategy configuration;
- immutable source replay records or redacted raw payloads with checksums,
  normalized market observations, and quarantined data-quality failures;
- immutable feature-schema versions and feature vectors linked to source
  observations;
- quote decisions and risk decisions;
- immutable model versions, scaler/artifact references and hashes, model status,
  and audited promotion/rollback records;
- training runs, dataset/split lineage, configurations, seeds, checkpoints,
  metrics, and terminal status;
- evaluation runs, baseline comparisons, historical holdout and synthetic stress
  metrics, benchmark verdicts, and report artifacts;
- inference decisions containing observation/vector/model/scaler references,
  operating mode, output, interpreted recommendation, latency, fallback/error
  reason, and whether bounded advice was applied;
- paper orders, order revisions, replacement links, and fills;
- capital reservations, immutable accounting entries, and settlements;
- physical inventory lots and inventory transitions;
- current read projections;
- alert definitions and destinations with secret references rather than webhook
  URLs;
- webhook deliveries and immutable delivery attempts with redacted request
  metadata, status, timing, retry schedule, and sanitized outcomes; and
- append-only audit events for domain, operator, model-governance, data-quality,
  notification, and recovery activity.

The audit table contains globally ordered event IDs, event type and schema
version, aggregate ID and version, correlation and causation IDs, command
idempotency key where applicable, simulation and wall-clock timestamps, and a
JSON payload. Model-related rows also retain model, feature-schema, dataset, and
evaluation references where applicable. Audit rows are never updated or deleted
by normal application flows.

Domain state and its corresponding audit rows are committed in one transaction.
Database constraints enforce unique fill identifiers, one active reservation
per order, legal aggregate versions, and command idempotency. Accounting uses
balanced, immutable entries rather than mutable totals; displayed totals are
projections that can be rebuilt.

Feature schema versions are immutable and vector values must match their
declared ordered feature count. Foreign keys prevent inference against unknown
vectors, models, scalers, or snapshots. Only one model version may be advisory
for a declared scope at a time, and advisory activation requires a passing
benchmark evaluation plus an approval audit record. Training, evaluation, and
delivery state changes use legal transition constraints and retain immutable
attempt/history rows rather than overwriting evidence.

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
6. reconciles feature/model lineage and resumes unfinished training,
   evaluation, inference, and webhook work idempotently where safe;
7. keeps strategy execution disabled if core reconciliation fails and always
   falls back from advisory to deterministic behavior if model state is invalid;
   and
8. exposes recovery status and reason through REST, WebSocket, metrics, and
   health checks.

A paused or stopped run remains paused or stopped after restart. An active run
may resume only after successful reconciliation and according to an explicit
run-level `resume_on_restart` setting, which defaults to false.

## 9. Fees and Slippage

Fee schedules are versioned and effective-dated. They support percentage and
fixed components for purchase, sale, payment processing, shipping,
authentication, and other configured marketplace costs. The quote engine uses
the same fee calculator as accounting so displayed edge cannot differ from
settled P&L.

StockX research fixtures cover configurable seller fee tiers from 8% through
12%, a separately configured 3% processing charge, and explicit inbound and
outbound shipping amounts. These are scenario inputs, not assumed account
entitlements or permanently hard-coded production values. Unknown account tier
or shipping cost fails the affected decision closed.

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
- model version, feature schema, training/evaluation run, benchmark report,
  shadow inference, and advisory status read models;
- audited commands to enable/disable shadow mode, approve benchmark-qualified
  advisory promotion, or roll back to deterministic-only behavior;
- explicit paper-order cancellation for operator control;
- status, configuration, capital, active quotes, order history, fills,
  inventory, P&L, replay/scenario progress, data-quality failures, inference
  comparisons, alert delivery status, and audit events;
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

Research-run creation and model artifact registration may be exposed through
local operator endpoints, but training executes outside request handling and
returns a durable run identifier. The API clearly labels historical versus
synthetic results. It never accepts arbitrary executable model code or exposes
raw webhook secrets in read responses. Prometheus metrics use a separate
configurable endpoint or route; exposure beyond loopback requires the same
external access controls as the REST API.

## 11. React Dashboard

The dashboard is an operational control plane with these areas:

- **Controls:** load replay, set speed and seed, start/pause/resume/stop the
  simulator, enable/disable the strategy, control shadow mode, review and
  confirm qualified advisory promotion or rollback, and issue paper cancels.
- **System status:** backend, database, event bus, simulator, strategy, recovery,
  WebSocket connection, simulation clock, replay progress, historical/synthetic
  source kind, model mode, alert delivery, and stale-data state.
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
  source-kind label, shock definition, and deterministic replay or scenario
  controls.
- **Model research:** active feature/model/scaler versions, training and
  evaluation status, dataset lineage, historical benchmark and synthetic stress
  results, approval record, and artifact hashes.
- **Shadow/advisory comparison:** deterministic base decision, model output,
  bounded recommendation, whether it was ignored or applied, final gated
  decision, latency, fallback reason, and per-model aggregate performance.
- **Data quality:** quarantined malformed or unsupported payloads with safe
  reason codes and source references, never fabricated zero values.
- **Alerts:** redacted Discord/Slack destination label, logical alert, attempt
  count, delivery status, sanitized failure, and next retry time.
- **Audit/activity:** correlated operator commands, decisions, state
  transitions, errors, and recovery events.

Controls are disabled when their command is illegal in the current state, but
the backend remains the final authority. Destructive simulation reset requires
confirmation and creates an audit event. The UI visibly distinguishes wall time
from simulation time and realized P&L from unrealized P&L. Connection loss
freezes controls that require fresh state and triggers snapshot resynchronization
after reconnect.

The UI never presents synthetic scenario performance as a historical backtest
and never labels the sigmoid MLP as Deep Bellman Hedging or RL. Advisory
promotion shows the qualifying benchmark and requires explicit confirmation;
the dashboard states that deterministic gates remain authoritative.

## 12. Error Handling

- Fixture and market-data validation failures are quarantined with a reason;
  required snapshot or feature values that are absent, malformed, non-finite,
  unsupported, or out of range are never zero-filled or defaulted.
- Stale, missing, crossed, or nonsensical markets fail closed for new quotes and
  trigger cancellation of unsafe active quotes.
- Unsupported product families fail closed before feature extraction.
- Risk rejections are expected domain outcomes, not server errors, and include
  stable codes and relevant limit/current/proposed values.
- Missing or incompatible model/feature/scaler versions, inference timeout, and
  invalid model outputs record a failed inference and use the unmodified
  deterministic strategy; they never produce permissive defaults.
- Training or evaluation failure leaves the existing model status unchanged.
  A benchmark policy is versioned and frozen before evaluation; promotion fails
  unless all required historical-holdout, tail-risk, capital, inventory,
  turnover, and operational thresholds pass against the registered baselines.
- Invalid order or inventory transitions are rejected atomically and audited.
- Database failure prevents acknowledgement of uncommitted commands. The
  strategy enters a degraded, no-new-orders state until authoritative state is
  available and reconciled.
- Event handler failures use bounded retries with structured diagnostics.
  Exhaustion marks the component degraded and prevents dependent strategy
  actions; events remain recoverable from the audit log.
- Discord/Slack timeout or error follows the destination's bounded retry policy.
  Terminal failure is persisted, measured, and surfaced locally without
  blocking the triggering transaction or recursively alerting the same failure.
- Unknown fee schedules, rounding failures, or accounting imbalance halt the
  affected flow and fail readiness rather than estimate.
- UI errors retain the command correlation ID, explain whether a retry is safe,
  and never imply success before server confirmation.

## 13. Observability

Structured logs include correlation ID, causation ID, command ID, event ID,
simulation run, source kind, aggregate, product/size where applicable,
feature/model/run references where applicable, and wall and simulation times.
Sensitive configuration and webhook data are redacted at the producer and
formatter boundaries.

Prometheus metrics cover market-event throughput and lag; validation failures;
feature extraction; quote calculation and churn; risk approvals and rejections
by reason; bid-cap utilization; open orders; fills; fees; slippage; inventory by
lifecycle state; realized/unrealized P&L; historical versus synthetic runs;
training/evaluation status and duration; inference count, mode, latency,
fallback and applied/ignored advice; benchmark verdicts; webhook queue depth,
attempts, retries, latency and terminal failures; event-handler latency and
retries; WebSocket clients and resyncs; database latency; and reconciliation
failures. Labels use bounded identifiers and categories rather than style codes,
order IDs, webhook URLs, or other unbounded/sensitive values.

Optional Grafana dashboards may visualize these Prometheus series, but Grafana
is not required for safe operation and is not an authoritative data store.
Dashboard definitions are versioned deployment artifacts when supplied.

Health endpoints separate liveness from readiness. Readiness fails when the
database, migrations, reconciliation, accounting invariants, simulator, or
required event handlers cannot safely support commands. Traces follow a market
observation through quote, risk, execution, accounting, projection, and
WebSocket publication. Separate spans follow feature extraction, inference,
training/evaluation stages, and asynchronous alert delivery without joining
those operations to the quote transaction.

Operational invariants are continuously checked:

- available cash, reservations, and ledger balances reconcile;
- open buy principal is at most $1,500;
- each active ask has distinct sellable inventory backing;
- each fill maps to exactly one order and accounting effect;
- each feature vector has exactly five ordered values and references a valid
  snapshot and schema version;
- advisory influence references a passing benchmark approval and remains within
  configured allocation/skew bounds;
- final order intents pass every deterministic gate regardless of model mode;
- aggregate versions are contiguous; and
- projection positions do not exceed the committed audit-event position; and
- webhook attempts contain no configured secrets and follow legal delivery
  transitions.

## 14. Test Strategy

### Unit tests

- Quote calculations, threshold-based revise/cancel/replace behavior, and
  inventory-backed ask rules.
- Risk limits, especially exact values below, at, and above the $1,500 bid cap.
- Fee, slippage, decimal rounding, capital reservation, cost-basis, settlement,
  and realized/unrealized P&L calculations.
- All order and inventory lifecycle transitions, including illegal transitions.
- StockX normalization, family allowlisting, exact five-feature ordering and
  versioning, and rejection of missing, malformed, non-finite, zero-filled,
  unsupported, or stale observations.
- `SneakerHedgingNet` tensor shapes, deterministic seeded initialization,
  sigmoid output bounds, stable entropic-loss calculations, and failure on
  incompatible feature/scaler versions.
- Advisory clamping and proof that model output cannot override fee, capital,
  liquidity, inventory, stale-data, price-sanity, or exposure rejections.
- Webhook redaction, timeout classification, backoff, retry exhaustion,
  idempotency, and delivery-state transitions.
- Event schemas, version handling, idempotency, and deterministic identifiers.

### Property and invariant tests

- Random command and event sequences never produce negative available cash,
  excess open-bid exposure, double-reserved inventory, duplicate fills, or an
  unbalanced ledger.
- Buy slippage never improves and sell slippage never improves execution.
- Replaying the same ordered events is idempotent.
- Rebuilt projections equal incrementally maintained projections.
- Arbitrary model outputs, including NaN, Inf, extremes, errors, and timeouts,
  never turn a deterministic rejection into an approval or exceed configured
  allocation/skew bounds.
- Arbitrary malformed payloads never create snapshots, vectors, quotes, or
  orders and never silently substitute zero.

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
- Snapshot-to-vector-to-inference lineage and shadow/advisory persistence using
  a real test database.
- Model registration, benchmark rejection, audited promotion, rollback, and
  deterministic fallback after restart or artifact incompatibility.
- Asynchronous Discord/Slack dispatch using local fake servers for success,
  timeout, retryable error, terminal error, deduplication, redaction, and
  recovery of pending attempts.
- Prometheus endpoint format, bounded labels, and representative metric changes.

### Deterministic simulation tests

- Golden StockX historical replay scenarios limited to Jordan 1 Retro and Nike
  Dunk Low.
- Seeded replays produce identical decisions, fills, audit-event order, and
  terminal portfolio state.
- Replay speed changes wall-clock duration without changing simulation results.
- Pausing, restarting, and resuming preserves the simulation position and does
  not duplicate effects.
- Seeded GBM plus restock/event shocks are reproducible and remain labeled
  synthetic through events, storage, metrics, API, and dashboard.
- Historical replay, not synthetic scenarios, determines execution benchmark
  verdicts. Walk-forward splits enforce time ordering and product/size leakage
  checks.

### Model research and offline evaluation tests

- Training is reproducible from dataset, feature/scaler, code, config, seed, and
  artifact references; corrupted or mismatched artifacts fail closed.
- Entropic-risk evaluation is numerically stable and reports ordinary and tail
  metrics so loss improvement cannot conceal worse benchmark behavior.
- The deterministic strategy, no-model/simple heuristic baselines, and MLP run
  under identical fees, slippage, latency, gates, and historical holdouts.
- Benchmark policies are immutable during a run, require every configured gate,
  and cannot be bypassed by registering or manually selecting an artifact.
- Shadow mode produces no differences in placed/revised/cancelled paper orders
  compared with deterministic-only replay.
- Advisory mode changes only bounded allocation/skew fields, preserves the base
  decision, and leaves final risk authority deterministic.
- No test, API label, report, or dashboard copy claims Deep Bellman Hedging or RL
  without the separately required MDP, Bellman/policy training, transition data,
  baselines, and offline evaluation.

### Frontend tests

- Component tests for controls, status, capital/risk, quotes, fills, inventory,
  P&L, simulator, model research/comparison, data quality, alert delivery, and
  error states.
- Reducer tests for snapshots, ordered events, duplicate events, gaps, and
  resynchronization.
- API contract tests generated from or checked against the FastAPI schema.
- Accessibility tests for keyboard operation, labels, status announcements,
  focus behavior, and non-color-only state indicators.
- End-to-end tests for the complete operator workflow, disconnection recovery,
  risk rejection visibility, inventory lifecycle, deterministic replay, shadow
  comparison, qualified advisory promotion/rollback, and alert failure.

### Safety and scope tests

- Static configuration and dependency checks verify that version 1 has no live
  order endpoint, marketplace credential flow, TLS fingerprinting, Cloudflare
  or CAPTCHA bypass, proxy rotation for ban evasion, protection-circumvention
  code, or undocumented/private API integration.
- Adapter contract tests use only local fakes. A network-deny test ensures the
  default test and simulation paths require no marketplace network access;
  explicit local fake webhook tests are the only network-enabled exception.

## 15. Delivery Boundaries

The implementation plan should preserve independently reviewable slices:
domain types and persistence; StockX replay and normalization; feature schemas
and vectors; risk and accounting; paper execution; quote loop; GBM/shock
scenarios; PyTorch research and benchmark pipeline; shadow inference; guarded
advisory governance; API/event streaming; asynchronous alerts; Prometheus and
optional Grafana assets; and React dashboard. Each slice must include tests,
migrations where applicable, and observable failure behavior. Product code
already present is input to planning, not evidence that these integrated slices
are complete.

Version 1 is complete only when the continuous paper loop, physical inventory
lifecycle, recovery guarantees, five-feature lineage, reproducible model
research, shadow comparison, notification status, metrics, and dashboard are
integrated end to end for the two allowlisted families. Advisory behavior is
permitted only after benchmark approval and may remain disabled at release.

A future authorized data adapter is an extension point, not a version 1
deliverable. Deep Bellman Hedging/RL, broader product coverage, and live order
submission each require separate approved designs. Live order submission
remains excluded regardless of adapter availability or model performance.
