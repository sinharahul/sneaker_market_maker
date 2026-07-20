# Codebase Guide — architecture & flow diagrams

A code-level map of the Sneaker Market Maker: what each module does, how a live
paper tick flows end-to-end, and how the offline research pipeline feeds models
back into Ops. This complements the existing docs rather than repeating them:

- **[MASTER.md](MASTER.md)** — conceptual overview (what market making *is*).
- **[../CONTEXT.md](../CONTEXT.md)** — the authoritative glossary. Terms in **bold**
  below (Deterministic Gate, Strategy Mode, Inventory Lot, …) are defined there.
- **[ROADMAP.md](ROADMAP.md)** — Track R / L-levels and what is gated.
- This file — the wiring between the code that implements all of it.

> Verification status (last checked): **707 non-integration + 9 integration tests
> pass**; Alembic migrations apply on Postgres; the offline IQL job and the online
> paper API were driven end-to-end. See [§9](#9-correctness-verification).

---

## 1. Layered architecture

```mermaid
flowchart TB
    subgraph API["API layer — src/api/"]
        A1["paper_routes.py<br/>command / query / SSE events"]
        A2["research_routes.py"]
        A3["app.py · local_demo.py<br/>FastAPI factory"]
    end

    subgraph PAPER["Paper Ops — src/paper/ (the ONLINE loop)"]
        P1["session.py<br/>PaperOpsSession — control plane"]
        P2["replay/simulator.py<br/>Golden Historical Replay"]
        P3["strategy_mode.py · mode_path.py<br/>mode routing + qualification"]
        P4["quote_engine.py<br/>Deterministic Strategy"]
        P5["inference.py · action_translator.py<br/>IQL bridge"]
        P6["gate.py<br/>Deterministic Gate (final authority)"]
        P7["execution.py · orders.py · inventory.py<br/>fills · lots · capital"]
    end

    subgraph RESEARCH["Research — src/research/ (the OFFLINE loop)"]
        R1["episodes/ · rewards/ · transitions/<br/>experience → training data"]
        R2["iql/<br/>distributional IQL trainer + actor"]
        R3["evaluation/<br/>metrics · OPE · splits"]
        R4["registry/ · qualification/<br/>promotion ladder"]
        R5["serving/recommender.py<br/>shadow / advisory"]
        R6["pfhedge/adapter.py<br/>direct-hedging baseline"]
    end

    subgraph CORE["Analytics core — src/"]
        C1["core.py<br/>FeeSchedule · OpportunityEvaluator"]
        C2["pipeline.py<br/>payload → MarketSnapshot → features"]
        C3["simulation.py<br/>GBM stress paths"]
    end

    subgraph STORE["Persistence — src/persistence/"]
        S1["Postgres (NUMERIC) — Authoritative Store"]
        S2["in-memory repos (tests)"]
    end

    API --> PAPER
    PAPER --> CORE
    PAPER -->|export step effects| RESEARCH
    RESEARCH -->|bind real weights| PAPER
    PAPER --> STORE
    RESEARCH --> STORE
```

**Reading it:** the API is a thin command/query bus over `PaperOpsSession`. The
paper package is the **online** market-making loop; the research package is the
**offline** learning loop. They are joined by two arrows only — paper *exports*
experience to research, and research *binds* qualified weights back into paper —
and the **Deterministic Gate** sits on the paper side so a model can never bypass
it. Money flows through `core.py` (Decimal fees/economics) everywhere.

---

## 2. Repository map

| Path | Responsibility |
|---|---|
| `core.py` | `FeeSchedule`, `MarketSnapshot`, `RiskLimits`, `OpportunityEvaluator` — the Decimal economics used by both loops. |
| `pipeline.py` | `SneakerDataPipeline` — normalize heterogeneous marketplace JSON → validated `MarketSnapshot` + `float32` feature matrix. Fails closed on bad payloads. |
| `simulation.py` | Seeded GBM / shock paths for **stress only** — never execution evidence. |
| `paper/session.py` | `PaperOpsSession` — the online control plane. Command bus (`execute`), read models (`get`), event log (`after`). Owns the tick loop. |
| `paper/replay/` | Golden Historical Replay Dataset loader, manifest/checksum, `simulator.py` (the market clock). |
| `paper/quote_engine.py` | **Deterministic Strategy** — desired two-sided quotes from market/inventory/capital/fees. Always the fail-closed baseline. |
| `paper/strategy_mode.py` | Mode state machine + **Model Qualification** (which registry state authorizes which mode). |
| `paper/mode_path.py` | `apply_strategy_mode` — routes a tick through deterministic / advisory / iql_primary. |
| `paper/inference.py`, `action_translator.py` | Build **Paper Decision State**, run IQL under a latency budget, translate `HybridAction` → Quote Intents. |
| `paper/gate.py` | **Deterministic Gate** — allowlist + capital reservation checks; final authority on every place/revise/cancel/replace. |
| `paper/execution.py`, `orders.py`, `inventory.py`, `capital.py` | Order matching, **Fee-Aware Fills**, **Inventory Lots**, **Paper Capital** ($2,500 start, $1,500 buy-reserve cap). |
| `paper/export_transitions.py`, `transition_bridge.py`, `reward_projection.py` | Turn paper step effects into research `OfflineTransition`s. |
| `research/episodes/`, `rewards/`, `transitions/` | Experience → episodes → fee-once rewards → transition store. |
| `research/iql/` | Distributional IQL: `dataset`, `networks`, `trainer`, `actor`, `checkpoint` (safetensors only). |
| `research/evaluation/` | `metrics`, `ope` (off-policy evaluation), `splits`, `harness`. |
| `research/registry/`, `qualification/` | Model registry state machine + qualification service. |
| `research/serving/recommender.py` | Fail-closed shadow + bounded advisory recommendations. |
| `research/retrain/` | `train_job`, `register_job`, `mixed_manifest`, `benchmark`, `ope_gate` — the offline retrain jobs. |
| `research/pfhedge/adapter.py` | PFHedge **direct-hedging baseline** (ADR-0005: *not* a paper Strategy Mode). |
| `api/` | FastAPI: `paper_routes`, `research_routes`, SSE event streams, `local_demo` factory. |
| `persistence/` | Postgres models/tables/repositories (Authoritative Store) + in-memory repos for tests; Alembic in `alembic/`. |
| `observe/` | Read-only allowlisted market observation (L1 live-readiness) — no send client. |

---

## 3. The online loop — a paper tick, end to end

This is the heart of the system: `PaperOpsSession._cmd_tick`
([`paper/session.py`](../src/sneaker_market_maker/paper/session.py)). One tick
pulls a batch of market events and, **for each event**, runs match → inference →
strategy → gate → submit → persist.

```mermaid
flowchart TD
    START([tick command]) --> SIM["simulator.tick()<br/>→ batch of MarketReplayEvents"]
    SIM --> LOOP{"for each event<br/>in batch"}

    LOOP --> MATCH["execution.match(event)<br/>→ Fee-Aware Fills"]
    MATCH --> LOTS["attribute fees · advance<br/>BUY lots → AVAILABLE"]
    LOTS --> SYNC1["quotes.sync_capital()"]

    SYNC1 --> MODEQ{"Strategy Mode<br/>== deterministic?"}
    MODEQ -->|yes| DET["quotes.on_market(event)<br/>Deterministic Strategy"]
    MODEQ -->|no| INFER["inference_for_event:<br/>build Decision State →<br/>encode → IQL (latency budget)"]

    INFER --> APPLY["apply_strategy_mode(mode, inference)"]
    DET --> APPLY

    APPLY --> PAUSE{"pause_for_iql?<br/>(iql_primary + invalid/late)"}
    PAUSE -->|yes| PSE["simulator.pause()<br/>emit replay.paused_iql"] --> BREAK([break batch])
    PAUSE -->|no| SUBMIT["submit intents where<br/>GateDecision.accepted"]

    SUBMIT --> SYNC2["sync_capital()"]
    SYNC2 --> EMIT["emit step effects<br/>(persist to Store)"]
    EMIT --> LOOP

    LOOP -->|batch done| TICKED["emit replay.ticked"] --> END([return event id])
```

**Step-by-step:**

1. **Replay clock** — `simulator.tick()` yields the next batch of
   `MarketReplayEvent`s from the **Golden Historical Replay Dataset** (versioned,
   checksummed, allowlisted). This is the only market-event source in V1.
2. **Match & fills** — `execution.match` fills any resting Paper Orders the event
   crosses. Each fill is **fee-aware** (records quoted vs execution price,
   slippage, fee-schedule version, total fees) and updates capital/lots/P&L.
3. **Lot lifecycle** — a BUY fill creates a lot; the ledger advances it
   `PURCHASED → AVAILABLE` so it can later back an ask (**Inventory Lot** rule:
   only available lots back asks).
4. **Inference (only when the mode uses a model)** — `_inference_for_event`
   builds the research-compatible **Paper Decision State** from the live book +
   event, encodes it with the registry-pinned encoder, and runs the IQL port
   under the **Inference Latency Budget** (default 100 ms). Deterministic mode
   skips this entirely.
5. **Strategy routing** — `apply_strategy_mode` (see [§4](#4-strategy-mode-routing))
   produces `(QuoteIntent, GateDecision)` pairs. The **Gate is evaluated here**,
   during authorship — the session only ever *submits* pre-approved intents.
6. **IQL-primary pause** — if the mode is `iql_primary` and IQL was missing/late/
   invalid, the replay clock **pauses** rather than silently substituting the
   deterministic strategy (a core safety invariant), and the batch breaks.
7. **Submit & persist** — accepted intents are submitted to `execution`, capital
   is re-synced, and **step effects** are emitted and persisted to the
   Authoritative Store (also the raw material for the offline loop).

---

## 4. Strategy Mode routing

`apply_strategy_mode` ([`paper/mode_path.py`](../src/sneaker_market_maker/paper/mode_path.py))
decides how much authority the model has this tick. **Every path still ends at the
Deterministic Gate.**

```mermaid
flowchart TD
    IN([mode + inference]) --> D{mode?}

    D -->|deterministic| DET["Deterministic Strategy only<br/>quotes.on_market"]

    D -->|advisory| AV{"inference<br/>valid?"}
    AV -->|no / late| AVFB["deterministic base<br/>+ record fallback_reason"]
    AV -->|yes| AVN["deterministic base<br/>+ bounded IQL nudge<br/>(ActionTranslator, ±ticks)"]
    AVN -->|TranslatorError| AVFB

    D -->|iql_primary| IQ{"inference<br/>valid?"}
    IQ -->|no / late| PAUSE["pause replay clock<br/>(do NOT substitute)"]
    IQ -->|yes| IQA["IQL authors Quote Intents"]
    IQA -->|TranslatorError| PAUSE

    DET --> GATE
    AVFB --> GATE
    AVN --> GATE
    IQA --> GATE["Deterministic Gate<br/>accept / reject"]
    GATE --> OUT([gated Quote Intents])
    PAUSE --> OUTP([no intents · replay paused])
```

- **Deterministic** — model never runs; the fail-closed baseline. Needs no
  qualification.
- **Advisory** — deterministic proposes the base quote, a *bounded* IQL nudge
  (±5 ticks via `ActionBounds`) skews it; any problem falls back to the base for
  that tick. Requires registry state `advisory_approved`.
- **IQL-primary** — IQL authors intents; on any failure the **clock pauses** so
  the system never pretends to be model-driven while quietly running
  deterministic. Requires at least `benchmark_qualified`.

Mode changes go through `StrategyModeMachine.set_mode`, which **raises
`QualificationError` (fail-closed, no mutation)** unless `mode_is_qualified`
approves the current registry state — this is **Model Qualification**.

---

## 5. The Deterministic Gate

`DeterministicGate.evaluate` ([`paper/gate.py`](../src/sneaker_market_maker/paper/gate.py))
is the single mandatory authority on book mutation. It is pure and fail-closed.

```mermaid
flowchart TD
    IN([QuoteIntent + Capital]) --> FAM{"product family<br/>allowlisted?"}
    FAM -->|no| RJ1[reject: UNSUPPORTED_FAMILY]
    FAM -->|yes| SIDE{side?}

    SIDE -->|SELL| SOK["accept<br/>(inventory-backed ask)"]

    SIDE -->|BUY| KIND{kind?}
    KIND -->|CANCEL| REL["release reservation<br/>→ accept"]
    KIND -->|PLACE / REVISE / REPLACE| CHK

    CHK["reserve buy principal"] --> C1{"principal &gt; 0<br/>and fees ≥ 0?"}
    C1 -->|no| RJ2[reject: INVALID_INTENT]
    C1 -->|yes| C2{"needed ≤ cash<br/>after release?"}
    C2 -->|no| RJ3[reject: INSUFFICIENT_CASH]
    C2 -->|yes| C3{"reserved ≤<br/>$1,500 buy cap?"}
    C3 -->|no| RJ4[reject: OPEN_BUY_CAP_EXCEEDED]
    C3 -->|yes| ACC["accept<br/>+ updated capital"]
```

Key invariants: **$2,500** starting **Paper Capital**, **60% / $1,500** open-buy
reservation cap that does **not** grow with profits, and a `REPLACE` that atomically
releases the old reservation before reserving the new one. Sells are inventory-backed
(one physical pair, quantity one, all-or-nothing fill).

---

## 6. The offline loop — experience to qualified model

The research package turns recorded paper experience into a trained, evaluated,
registry-promoted model that Ops can bind. Driven by the jobs in
[`research/retrain/`](../src/sneaker_market_maker/research/retrain/).

```mermaid
flowchart LR
    STEP["paper step effects<br/>(Authoritative Store)"] --> EXP["export_transitions<br/>→ OfflineTransition"]
    EXP --> EPI["episodes/builder<br/>events → episodes"]
    EPI --> REW["rewards/builder<br/>fee-once reward"]
    REW --> DS["iql/dataset<br/>+ mixed_manifest<br/>(offline + synthetic)"]
    DS --> TRAIN["iql/trainer<br/>run_offline_iql_train"]
    TRAIN --> CKPT["iql/checkpoint<br/>(safetensors)"]
    CKPT --> EVAL["evaluation/<br/>metrics · OPE · splits"]
    EVAL --> BENCH["retrain/benchmark<br/>+ ope_gate"]
    BENCH --> REG["registry.register<br/>→ CANDIDATE"]
    REG --> PROMO["promote through ladder<br/>(see §7)"]
    PROMO --> BIND["Ops bind-model<br/>real weights → paper"]
    BIND -.->|used at runtime| STEP
```

Highlights: rewards are **fee-once** (fees charged exactly once per round trip);
training data is a **mixed manifest** of real offline transitions + bounded
synthetic augmentation (synthetic never counts as holdout evidence); the
**`ope_gate`** blocks promotion unless off-policy evaluation clears its bar;
checkpoints are **safetensors only** (no unsafe pickle). PFHedge sits alongside as
a **direct-hedging baseline** for comparison, not as a paper quote author.

---

## 7. Registry promotion ladder & Model Qualification

`RegistryService` ([`research/registry/service.py`](../src/sneaker_market_maker/research/registry/service.py))
enforces a strict state machine; **each legal edge is validated** (benchmarks,
compatibility contract, sha256). Ops selects Strategy Modes only for states that
qualify them.

```mermaid
stateDiagram-v2
    [*] --> CANDIDATE
    CANDIDATE --> VALIDATED
    CANDIDATE --> REJECTED
    VALIDATED --> SHADOW
    VALIDATED --> REJECTED
    SHADOW --> BENCHMARK_QUALIFIED : unlocks iql_primary
    SHADOW --> ROLLED_BACK
    BENCHMARK_QUALIFIED --> ADVISORY_APPROVED : unlocks advisory
    BENCHMARK_QUALIFIED --> ROLLED_BACK
    ADVISORY_APPROVED --> ROLLED_BACK
    REJECTED --> [*]
    ROLLED_BACK --> [*]
```

The qualification mapping (`mode_is_qualified` in `strategy_mode.py`):

| Strategy Mode | Requires registry state |
|---|---|
| `deterministic` | none (always available) |
| `iql_primary` | `benchmark_qualified` *or* `advisory_approved` |
| `advisory` | `advisory_approved` |

Note the ordering quirk: `iql_primary` is unlocked at `benchmark_qualified`, one
rung *below* `advisory` — because advisory nudging a live deterministic base is
held to a stricter bar than IQL running in the fully-paused-on-failure primary mode.

---

## 8. Running the pipelines

### Setup (once)
```bash
cd ~/sneaker_market_maker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
```

### Online pipeline (paper Ops control plane)
```bash
# 1. start the API / control plane
uvicorn sneaker_market_maker.api.local_demo:app --host 127.0.0.1 --port 8000
#    Swagger at http://127.0.0.1:8000/docs

# 2. drive it (browser Ops dashboard)
cd frontend && npm ci && npm run dev
#    Ops Dashboard: http://127.0.0.1:5173/?view=ops
```
The command flow is `load → start → tick … → pause/stop`, plus `set-mode`,
`promote-model`, `bind-model` — all through `PaperOpsSession.execute`. Read models
come from `GET /api/paper/...`; the event stream is SSE.

### Offline pipeline (research / IQL)
```bash
source .venv/bin/activate
# exercise the full research ladder (documented smoke → acceptance path)
python -m pytest tests/research/iql -q --import-mode=importlib
# the retrain job itself is research/retrain/train_job.py::run_offline_iql_train
```
Full walkthrough: [`docs/research/exercise-pipeline.md`](research/exercise-pipeline.md).

### Integration (Postgres + Alembic + PFHedge pin)
```bash
docker compose -f docker-compose.test.yml up -d --wait
export DATABASE_URL=postgresql+psycopg://research:research@localhost:55432/research_test
alembic upgrade head
python -m pytest -m integration -q --import-mode=importlib
docker compose -f docker-compose.test.yml down -v
```

---

## 9. Correctness verification

What was executed against this checkout to confirm the project is sound:

| Check | Result |
|---|---|
| Unit / property / API / safety / acceptance (`-m "not integration"`) | **707 passed** |
| Integration (Postgres + Alembic + PFHedge pin) | **9 passed** |
| Alembic `upgrade head` on a fresh Postgres | clean |
| Offline IQL train job driven standalone | runs, emits checkpoint |
| Online paper API driven `load → start → tick` | fills booked, capital mutated, step effects persisted |
| `ruff check src tests` | clean except a few nested-`if` style nits in test helpers |

**Design invariants that hold in code** (not just docs):
- The Deterministic Gate is the only path to book mutation; models author/nudge
  but never approve — confirmed in `session._cmd_tick` (submits only
  `decision.accepted`).
- `iql_primary` **pauses** the clock on model failure instead of silently falling
  back — confirmed in `mode_path` + `session`.
- Mode changes are **fail-closed** on qualification — `set_mode` raises without
  mutating.
- Money is `Decimal` end to end; tensors appear only at named ML boundaries.
- Fees are charged **once** per round trip; synthetic paths are never holdout
  evidence.

No correctness defects were found. The only lint findings are cosmetic
(collapsible nested `if`s in test helpers) and do not affect behavior.

---

## 10. File index (quick jump)

- Online tick loop → [`paper/session.py`](../src/sneaker_market_maker/paper/session.py) `_cmd_tick`
- Mode routing → [`paper/mode_path.py`](../src/sneaker_market_maker/paper/mode_path.py)
- Qualification → [`paper/strategy_mode.py`](../src/sneaker_market_maker/paper/strategy_mode.py)
- Gate → [`paper/gate.py`](../src/sneaker_market_maker/paper/gate.py)
- Economics → [`core.py`](../src/sneaker_market_maker/core.py)
- Payload normalization → [`pipeline.py`](../src/sneaker_market_maker/pipeline.py)
- IQL training → [`research/retrain/train_job.py`](../src/sneaker_market_maker/research/retrain/train_job.py)
- Registry → [`research/registry/service.py`](../src/sneaker_market_maker/research/registry/service.py)
- Recommender → [`research/serving/recommender.py`](../src/sneaker_market_maker/research/serving/recommender.py)
