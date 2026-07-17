# Deep Bellman IQL and PFHedge Research Subsystem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline-only, reproducible research subsystem that compares deterministic, heuristic, v1 MLP, PFHedge 0.23.0 direct-hedging, and custom risk-sensitive distributional IQL policies while preserving deterministic risk gates as the final authority.

**Architecture:** Extend the current package as a modular monolith with explicit `research`, `persistence`, and `api` package boundaries plus a separate Vite/React frontend. Domain contracts remain independent of SQLAlchemy, PyTorch, PFHedge, FastAPI, and React. Unit tests use in-memory ports; PostgreSQL/Alembic tests begin only after the contracts are stable. PFHedge is an independent direct-policy baseline; all Bellman targets, distributional critics, IQL losses, support checks, registry policy, and serving gates are custom code.

**Tech Stack:** Python 3.10-3.12, NumPy 1.26.4, PyTorch 2.2.2, PFHedge 0.23.0, safetensors 0.4.5, FastAPI 0.115.0, Pydantic 2.9.2, SQLAlchemy 2.0.35, Alembic 1.13.3, PostgreSQL 16, psycopg 3.2.3, pytest 8.3.3, Hypothesis 6.115.0, Ruff 0.6.9, React 18.3.1, TypeScript 5.6.2, Vite 5.4.8, Vitest 2.1.1, Testing Library 16.0.1.

**Global Constraints:**

- TDD is mandatory: add one focused failing test, run it and verify the stated failure, add only the implementation required for that test, rerun it, then run the affected suite.
- Keep money and accounting values as `Decimal`/PostgreSQL `NUMERIC`; convert to tensors only at a named validated boundary.
- Keep files below 300 lines. Split by responsibility before crossing that limit; do not create `utils.py`, `models.py`, or another catch-all module.
- Preserve existing `FeeSchedule`, `MarketSnapshot`, `SneakerDataPipeline.FEATURE_NAMES`, and seeded GBM behavior through adapters and compatibility tests.
- Historical and synthetic provenance is immutable. Synthetic evidence never contributes to a historical holdout claim.
- No marketplace client, credential, execution port, live-network integration test, anti-bot code, arbitrary model code upload, or unsafe pickle loading.
- Unit tests must not require Docker, PostgreSQL, PFHedge downloads, or network access. Mark only the explicit PostgreSQL and clean-environment compatibility tests `integration`.
- `requirements.txt` is the reproducible application/test lock input requested by the spec; `pyproject.toml` carries the same direct version constraints and package/tool metadata.
- Deterministic gates run after model canonicalization and clamping and remain authoritative in shadow and advisory modes. Shadow mode must be byte-equivalent to deterministic-only paper commands.
- Every artifact, transition, run, recommendation, and registry mutation has immutable lineage and a content hash. Corrections append versions; they never overwrite research evidence.
- Do not fabricate advisory thresholds. Tests use explicit fixture benchmark policies; production defaults leave advisory qualification disabled.
- Each task below is an independently testable vertical deliverable and ends in one focused commit. Do not combine tasks into a giant commit.

## File Responsibility Map

### Repository and dependency boundary

- `requirements.txt` — exact Python runtime, research, backend, database, and test pins.
- `pyproject.toml` — matching direct dependencies, Python range, `integration` marker, and Ruff/pytest configuration.
- `docs/compatibility/pfhedge-0.23.0.md` — supported Python/OS matrix, exact commands, and recorded results.
- `docker-compose.test.yml` — isolated PostgreSQL 16 test service only.

### Domain and research contracts

- `src/sneaker_market_maker/research/contracts/state.py` — `StateSchema`, `EncodedState`, masks, bounds, and lineage.
- `src/sneaker_market_maker/research/contracts/action.py` — `ActionCategory`, `HybridAction`, canonicalization.
- `src/sneaker_market_maker/research/contracts/transition.py` — decision, behavior policy, reward, and transition contracts.
- `src/sneaker_market_maker/research/contracts/experiment.py` — episode, split, assumptions, run, report, and registry contracts.
- `src/sneaker_market_maker/research/ports.py` — Protocols for accounting, transition storage, artifacts, policies, gates, and clocks.
- `src/sneaker_market_maker/research/adapters/legacy.py` — wrappers around `FeeSchedule`, `MarketSnapshot`, five-vector, and GBM.

### Episode, accounting, and persistence

- `src/sneaker_market_maker/research/episodes/events.py` — normalized replay event types and stable ordering.
- `src/sneaker_market_maker/research/episodes/builder.py` — 14-day boundaries, material-event decisions, 60-second coalesced ticks.
- `src/sneaker_market_maker/research/encoding/schema.py` — fail-closed state validation and tensor encoding.
- `src/sneaker_market_maker/research/rewards/builder.py` — fee-once NAV reward and reconciliation.
- `src/sneaker_market_maker/research/transitions/service.py` — complete/idempotent Bellman transition assembly.
- `src/sneaker_market_maker/persistence/database.py` — SQLAlchemy engine/session factory.
- `src/sneaker_market_maker/persistence/research_tables.py` — additive research metadata tables.
- `src/sneaker_market_maker/persistence/research_repository.py` — atomic PostgreSQL repository implementation.
- `alembic.ini`, `alembic/env.py`, `alembic/versions/20260717_01_research_subsystem.py` — additive schema migration.

### Evaluation and policy tracks

- `src/sneaker_market_maker/research/evaluation/splits.py` — leakage-safe walk-forward folds.
- `src/sneaker_market_maker/research/evaluation/harness.py` — common frozen simulator/evaluation loop.
- `src/sneaker_market_maker/research/evaluation/metrics.py` — return/risk/inventory/support metrics and block bootstrap.
- `src/sneaker_market_maker/research/evaluation/ope.py` — explicit OPE validity and supported estimators.
- `src/sneaker_market_maker/research/policies/baselines.py` — deterministic, no-model, heuristic, and v1 MLP adapters.
- `src/sneaker_market_maker/research/pfhedge/adapter.py` — bounded direct PFHedge policy and entropic objective only.
- `src/sneaker_market_maker/research/iql/math.py` — CE, Huber, quantile-Huber, crossing, and Polyak math.
- `src/sneaker_market_maker/research/iql/networks.py` — distributional twin-Q/value modules.
- `src/sneaker_market_maker/research/iql/actor.py` — masked hybrid actor, transforms, and active-dimension log probability.
- `src/sneaker_market_maker/research/iql/trainer.py` — ordered value/Q/actor/target updates.
- `src/sneaker_market_maker/research/iql/dataset.py` — trainable transition loading and exclusion reasons.
- `src/sneaker_market_maker/research/iql/checkpoint.py` — allowlisted tensor/state-dict checkpoint format and hashes.

### Registry, serving, API, and UI

- `src/sneaker_market_maker/research/registry/service.py` — immutable registration and legal state transitions.
- `src/sneaker_market_maker/research/serving/recommender.py` — shadow/advisory inference, canonicalization, gates, fallback.
- `src/sneaker_market_maker/api/app.py` — loopback FastAPI application composition.
- `src/sneaker_market_maker/api/research_routes.py` — typed research reads and idempotent audited commands.
- `src/sneaker_market_maker/api/research_events.py` — bounded ordered WebSocket envelopes.
- `frontend/package.json`, `frontend/package-lock.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts` — isolated frontend build.
- `frontend/src/research/types.ts` — generated-equivalent explicit API contracts.
- `frontend/src/research/api.ts` — local research API client.
- `frontend/src/research/ResearchPage.tsx` — assumptions, comparisons, support, lineage, registry, and traces.
- `frontend/src/research/GuidedDemo.tsx` — pause/step/resume/restart deterministic story.
- `src/sneaker_market_maker/research/demo/fixture.py` — five-minute pinned demo events and prerecorded model outputs.
- `src/sneaker_market_maker/research/demo/service.py` — deterministic demo state machine.
- `src/sneaker_market_maker/research/qualification/service.py` — pre-registered advisory qualification report.
- `src/sneaker_market_maker/research/acceptance.py` — validates complete acceptance evidence.
- `docs/research/acceptance-checklist.md` — command, artifact, and result evidence for all approved criteria.

Every type named in an interface below is defined in the same task or an earlier task. Tensor shape notation such as `[B, K]` is descriptive; Python annotations use `torch.Tensor`.

## Slice-to-Task Coverage

- Dependency/compatibility prerequisite: Task 1.
- Slice 1, contracts and migrations: Tasks 2-5.
- Slice 2, episode/reward construction: Tasks 6-9.
- Slice 3, shared evaluation harness: Tasks 10-12.
- Slice 4, PFHedge direct baseline: Tasks 1 and 13.
- Slice 5, custom distributional IQL: Tasks 14-18.
- Slice 6, registry and shadow serving: Tasks 19-20.
- Slice 7, FastAPI/React and guided demo: Tasks 21-23.
- Slice 8, advisory qualification: Tasks 24-26.

### Task 1: Pin Dependencies and Prove the Compatibility Matrix

**Interfaces**

- Consumes: Python executables `python3.10`, `python3.11`, `python3.12`; public `pfhedge.nn.EntropicRiskMeasure(a: float = 1.0)`.
- Produces: `requirements.txt`; matching `[project].dependencies`; pytest marker `integration`; compatibility record.

**Files**

- Create: `requirements.txt`
- Modify: `pyproject.toml`
- Create: `tests/compatibility/test_pfhedge_public_api.py`
- Create: `docs/compatibility/pfhedge-0.23.0.md`

- [ ] Add the failing compatibility test:

```python
import importlib.metadata

import torch
from pfhedge.nn import EntropicRiskMeasure


def test_pfhedge_023_entropic_risk_measure_public_api() -> None:
    assert importlib.metadata.version("pfhedge") == "0.23.0"
    pnl = torch.tensor([[-1.0, 0.0], [1.0, 2.0]], dtype=torch.float64)
    result = EntropicRiskMeasure(a=0.5)(pnl, target=torch.zeros_like(pnl))
    expected = torch.logsumexp(-0.5 * pnl, dim=0) / 0.5 - torch.log(
        torch.tensor(2.0, dtype=torch.float64)
    ) / 0.5
    assert result.shape == torch.Size([2])
    torch.testing.assert_close(result, expected)
```

- [ ] Run `python -m pytest tests/compatibility/test_pfhedge_public_api.py -q`. Expected failure: `ModuleNotFoundError: No module named 'pfhedge'`.
- [ ] Create `requirements.txt` with these exact lines:

```text
numpy==1.26.4
torch==2.2.2
pfhedge==0.23.0
tqdm==4.66.5
safetensors==0.4.5
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.9.2
sqlalchemy==2.0.35
alembic==1.13.3
psycopg[binary]==3.2.3
httpx==0.27.2
pytest==8.3.3
pytest-cov==5.0.0
hypothesis==6.115.0
ruff==0.6.9
```

- [ ] Mirror those direct pins in `pyproject.toml`, set `requires-python = ">=3.10,<3.13"`, and add `markers = ["integration: requires an isolated external service or clean environment"]`.
- [ ] In `docs/compatibility/pfhedge-0.23.0.md`, record matrix rows for CPython 3.10, 3.11, and 3.12 on macOS/Linux, each using `python -m venv .matrix/<version>`, `python -m pip install -r requirements.txt`, the exact compatibility test above, and `python -m pip check`. Record actual pass/fail and package versions; a failed row blocks implementation.
- [ ] Run `python -m pip install -r requirements.txt && python -m pytest tests/compatibility/test_pfhedge_public_api.py -q && python -m pip check`. Expected: `1 passed` and `No broken requirements found`.
- [ ] Commit: `git add requirements.txt pyproject.toml tests/compatibility docs/compatibility && git commit -m "build: pin research compatibility matrix"`

### Task 2: Introduce Versioned State and Hybrid Action Contracts

**Interfaces**

- Consumes: `MarketSnapshot`, `SneakerDataPipeline.FEATURE_NAMES`.
- Produces: `StateSchema.validate(payload: Mapping[str, object]) -> None`; `canonicalize_action(action: RawHybridAction, bounds: ActionBounds, mask: ActionMask) -> HybridAction`.

**Files**

- Create: `src/sneaker_market_maker/research/contracts/state.py`
- Create: `src/sneaker_market_maker/research/contracts/action.py`
- Create: `src/sneaker_market_maker/research/adapters/legacy.py`
- Create: `tests/research/contracts/test_state_action.py`

- [ ] Write tests asserting the five feature names/order are frozen, `NO_OP`/`CANCEL` neutralize continuous values, `QUOTE` is tick-rounded and clamped, masked categories fail closed, and non-finite/missing required state raises `StateValidationError`.
- [ ] Run `python -m pytest tests/research/contracts/test_state_action.py -q`. Expected failure: `ModuleNotFoundError: No module named 'sneaker_market_maker.research'`.
- [ ] Implement these exact public contracts:

```python
class ActionCategory(str, Enum):
    NO_OP = "NO_OP"
    QUOTE = "QUOTE"
    CANCEL = "CANCEL"


@dataclass(frozen=True)
class ActionMask:
    no_op: bool
    quote: bool
    cancel: bool


@dataclass(frozen=True)
class ActionBounds:
    bid_low: int
    bid_high: int
    ask_low: int
    ask_high: int


@dataclass(frozen=True)
class RawHybridAction:
    category: ActionCategory
    allocation: float
    bid_offset_ticks: float
    ask_offset_ticks: float


@dataclass(frozen=True)
class HybridAction:
    category: ActionCategory
    allocation: float
    bid_offset_ticks: int
    ask_offset_ticks: int


def canonicalize_action(
    action: RawHybridAction, bounds: ActionBounds, mask: ActionMask
) -> HybridAction:
    allowed = {
        ActionCategory.NO_OP: mask.no_op,
        ActionCategory.QUOTE: mask.quote,
        ActionCategory.CANCEL: mask.cancel,
    }
    if not allowed[action.category]:
        raise ValueError("masked action category")
    if action.category is not ActionCategory.QUOTE:
        return HybridAction(action.category, 0.0, 0, 0)
    values = (action.allocation, float(action.bid_offset_ticks), float(action.ask_offset_ticks))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("action values must be finite")
    return HybridAction(
        action.category,
        min(1.0, max(0.0, action.allocation)),
        min(bounds.bid_high, max(bounds.bid_low, round(action.bid_offset_ticks))),
        min(bounds.ask_high, max(bounds.ask_low, round(action.ask_offset_ticks))),
    )
```

- [ ] Implement `StateSchema(version: str, feature_names: tuple[str, ...], required_fields: tuple[str, ...])` and `LegacyFiveVectorAdapter.encode(snapshot: MarketSnapshot, fee_rate: Decimal) -> tuple[float, float, float, float, float]`; reject non-finite output.
- [ ] Run `python -m pytest tests/research/contracts/test_state_action.py tests/test_pipeline.py tests/test_core.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research tests/research && git commit -m "feat: add versioned research contracts"`

### Task 3: Define Bellman-Ready Transition, Provenance, and Propensity Contracts

**Interfaces**

- Consumes: `HybridAction`, `ActionMask`, `ActionBounds`.
- Produces: `BehaviorPolicy`; `RewardRecord`; `DecisionPoint`; `OfflineTransition.validate_trainable() -> None`.

**Files**

- Create: `src/sneaker_market_maker/research/contracts/transition.py`
- Create: `tests/research/contracts/test_transition.py`

- [ ] Add tests that construct one complete transition and reject missing next state, unreconciled reward, absent schema versions, missing source hashes, invalid terminal reason, and deterministic policies falsely carrying a nonzero density.
- [ ] Run `python -m pytest tests/research/contracts/test_transition.py -q`. Expected failure: import of `BehaviorPolicy` fails.
- [ ] Implement frozen dataclasses with exact fields:

```python
@dataclass(frozen=True)
class BehaviorPolicy:
    version: str
    collection_mode: str
    categorical_propensity: float | None
    active_continuous_log_density: float | None
    joint_log_propensity: float | None
    deterministic: bool
    support_method: str
    support_version: str
    missingness_reason: str | None


@dataclass(frozen=True)
class RewardRecord:
    version: str
    total: Decimal
    nav_delta: Decimal
    penalties: Mapping[str, Decimal]
    explanatory_costs: Mapping[str, Decimal]
    ledger_entry_ids: tuple[str, ...]
    reconciled: bool


@dataclass(frozen=True)
class OfflineTransition:
    transition_id: UUID
    episode_id: UUID
    decision_index: int
    state: Mapping[str, object]
    proposed_action: HybridAction
    post_gate_action: HybridAction
    reward: RewardRecord
    next_state: Mapping[str, object]
    done: bool
    terminal_reason: str | None
    elapsed_seconds: int
    discount: float
    action_mask: ActionMask
    action_bounds: ActionBounds
    behavior: BehaviorPolicy
    state_schema_version: str
    action_schema_version: str
    reward_schema_version: str
    source_record_ids: tuple[str, ...]
    provenance_label: Literal["historical", "synthetic"]
    dataset_version: str
    scenario_version: str
    simulator_version: str
    gate_policy_version: str
    code_revision: str
    random_seed: int
    content_hash: str

    def validate_trainable(self) -> None:
        if not self.reward.reconciled:
            raise ValueError("reward is not reconciled")
        if not self.next_state:
            raise ValueError("next state is required")
        if self.done != (self.terminal_reason is not None):
            raise ValueError("terminal reason must match done")
        if not self.source_record_ids or not self.content_hash:
            raise ValueError("provenance is incomplete")
```

- [ ] Add propensity validation: probabilities are finite in `(0, 1]`; stochastic rows require all three propensity values; deterministic rows require all three to be `None` and a missingness reason.
- [ ] Run `python -m pytest tests/research/contracts/test_transition.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/contracts tests/research/contracts && git commit -m "feat: define Bellman transition contract"`

### Task 4: Add Additive Alembic/PostgreSQL Persistence

**Interfaces**

- Consumes: `OfflineTransition`.
- Produces: `ResearchRepository.add_transition(transition: OfflineTransition) -> AddResult`; `ResearchRepository.get_transition(transition_id: UUID) -> OfflineTransition | None`.

**Files**

- Create: `src/sneaker_market_maker/persistence/database.py`
- Create: `src/sneaker_market_maker/persistence/research_tables.py`
- Create: `src/sneaker_market_maker/persistence/research_repository.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/20260717_01_research_subsystem.py`
- Create: `tests/persistence/test_research_repository_unit.py`

- [ ] First test an `InMemoryResearchRepository` through the same `TransitionRepository` Protocol: first insert returns `AddResult.CREATED`, identical identity/hash returns `AddResult.EXISTING`, and same identity/different hash raises `TransitionConflict`.
- [ ] Run `python -m pytest tests/persistence/test_research_repository_unit.py -q`. Expected failure: import of `TransitionRepository` fails.
- [ ] Define:

```python
class AddResult(str, Enum):
    CREATED = "created"
    EXISTING = "existing"


class TransitionRepository(Protocol):
    def add_transition(self, transition: OfflineTransition) -> AddResult:
        raise NotImplementedError

    def get_transition(self, transition_id: UUID) -> OfflineTransition | None:
        raise NotImplementedError
```

- [ ] Implement additive tables named `mdp_state_schemas`, `action_schemas`, `reward_schemas`, `encoder_versions`, `episode_manifests`, `decision_points`, `behavior_policies`, `offline_transitions`, `research_runs`, `research_artifacts`, `registry_models`, `registry_status_history`, and `recommendations`. Use UUID primary keys, `JSONB` payloads, `NUMERIC(38, 18)` rewards, non-null version/hash/provenance columns, FKs, and unique `(episode_id, decision_index, state_schema_version, action_schema_version, reward_schema_version)`.
- [ ] Keep migration `down_revision = None` because the repository has no prior Alembic history; `downgrade()` drops only these new tables in reverse FK order.
- [ ] Run `python -m pytest tests/persistence/test_research_repository_unit.py -q`. Expected: all pass without PostgreSQL.
- [ ] Commit: `git add src/sneaker_market_maker/persistence alembic.ini alembic tests/persistence && git commit -m "feat: add additive research persistence"`

### Task 5: Verify PostgreSQL Transaction and Correction Semantics

**Interfaces**

- Consumes: `DATABASE_URL`, Alembic migration, `ResearchRepository`.
- Produces: atomic transition/behavior/reward persistence and append-only correction versions.

**Files**

- Create: `docker-compose.test.yml`
- Create: `tests/integration/test_postgres_research_repository.py`
- Modify: `src/sneaker_market_maker/persistence/research_repository.py`

- [ ] Add `@pytest.mark.integration` tests for migration upgrade/downgrade/upgrade, FK rejection, transaction rollback after injected reward insert failure, idempotent retry, and correction insertion with `supersedes_transition_id` while the original remains unchanged.
- [ ] Run `DATABASE_URL=postgresql+psycopg://research:research@localhost:55432/research_test python -m pytest tests/integration/test_postgres_research_repository.py -q`. Expected failure: before service startup, `OperationalError: connection refused`.
- [ ] Add a PostgreSQL 16 service on port `55432`, database/user/password `research_test`/`research`/`research`, with a healthcheck. Implement repository writes inside `with session.begin():`, inserting behavior, reward JSON, and transition atomically.
- [ ] Use this transaction boundary; `_insert_transition` must use SQLAlchemy Core inserts against the mapped tables and return the reconstructed row:

```python
def add_transition(self, transition: OfflineTransition) -> AddResult:
    identity = (
        transition.episode_id,
        transition.decision_index,
        transition.state_schema_version,
        transition.action_schema_version,
        transition.reward_schema_version,
    )
    with self.session_factory() as session, session.begin():
        existing = self._get_by_identity(session, identity)
        if existing is not None:
            if existing.content_hash != transition.content_hash:
                raise TransitionConflict("transition identity has different content")
            return AddResult.EXISTING
        self._insert_behavior(session, transition)
        self._insert_reward(session, transition)
        self._insert_transition(session, transition)
    return AddResult.CREATED
```
- [ ] Run `docker compose -f docker-compose.test.yml up -d --wait && DATABASE_URL=postgresql+psycopg://research:research@localhost:55432/research_test alembic upgrade head && DATABASE_URL=postgresql+psycopg://research:research@localhost:55432/research_test python -m pytest tests/integration/test_postgres_research_repository.py -q`. Expected: all pass.
- [ ] Run `docker compose -f docker-compose.test.yml down -v`.
- [ ] Commit: `git add docker-compose.test.yml src/sneaker_market_maker/persistence tests/integration && git commit -m "test: verify research postgres transactions"`

### Task 6: Build Deterministic Fourteen-Day Episodes

**Interfaces**

- Consumes: `Sequence[NormalizedEvent]`, `EpisodeConfig`.
- Produces: `EpisodeBuilder.build(events: Sequence[NormalizedEvent], config: EpisodeConfig) -> Episode`.

**Files**

- Create: `src/sneaker_market_maker/research/episodes/events.py`
- Create: `src/sneaker_market_maker/research/episodes/builder.py`
- Create: `tests/research/episodes/test_builder.py`

- [ ] Test stable same-timestamp reduction, a material event coincident with a 60-second boundary producing one decision, maintenance ticks independent of replay speed, exact 14-day closure, no split-boundary crossing, exhausted replay terminal reason, and `gamma = exp(-rho * elapsed_seconds)`.
- [ ] Run `python -m pytest tests/research/episodes/test_builder.py -q`. Expected failure: import of `EpisodeBuilder` fails.
- [ ] Implement:

```python
@dataclass(frozen=True)
class NormalizedEvent:
    source_id: str
    simulation_time: datetime
    stable_order: int
    kind: EventKind
    payload: Mapping[str, object]
    provenance: Literal["historical", "synthetic"]


@dataclass(frozen=True)
class EpisodeConfig:
    episode_id: UUID
    start: datetime
    split_end: datetime
    discount_rate: float
    maintenance_seconds: int = 60
    duration: timedelta = timedelta(days=14)


class EpisodeBuilder:
    def build(self, events: Sequence[NormalizedEvent], config: EpisodeConfig) -> Episode:
        end = min(config.start + config.duration, config.split_end)
        if end != config.start + config.duration:
            raise ValueError("episode crosses split boundary")
        ordered = sorted(events, key=lambda event: (event.simulation_time, event.stable_order))
        return self._reduce_with_ticks(ordered, config, end)
```

- [ ] Define `EventKind` with `BOOK`, `FILL`, `QUOTE`, `INVENTORY`, `LOGISTICS`, `FEE`, `REGIME`, `RESTOCK`, `SETTLEMENT`, `FRESHNESS`, and `RISK_LIMIT`; define `DecisionPoint(index: int, simulation_time: datetime, elapsed_seconds: int, reasons: tuple[EventKind, ...], source_ids: tuple[str, ...], discount: float)` and `Episode(episode_id: UUID, start: datetime, end: datetime, decisions: tuple[DecisionPoint, ...], terminal_reason: str)`.
- [ ] `_reduce_with_ticks` must reduce all events at a timestamp before emitting one decision, advance ticks from the previous decision, coalesce exact-boundary material events, preserve all source IDs/provenance, and terminate exactly once.
- [ ] Run `python -m pytest tests/research/episodes/test_builder.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/episodes tests/research/episodes && git commit -m "feat: build deterministic research episodes"`

### Task 7: Encode Rich State and Legal Action Masks

**Interfaces**

- Consumes: `StateSchema`, reduced simulator `Mapping[str, object]`.
- Produces: `StateEncoder.encode(state: Mapping[str, object]) -> EncodedState`; `MaskBuilder.build(state: Mapping[str, object]) -> tuple[ActionMask, ActionBounds]`.

**Files**

- Create: `src/sneaker_market_maker/research/encoding/schema.py`
- Create: `tests/research/encoding/test_schema.py`

- [ ] Test declared ordering, units, clipping, categorical vocabulary, padding masks, missingness indicators, train-only scaler version, ask requiring sellable inventory, cancel requiring cancellable quote, `NO_OP` availability, and quarantine on required missing/non-finite values.
- [ ] Run `python -m pytest tests/research/encoding/test_schema.py -q`. Expected failure: import of `StateEncoder` fails.
- [ ] Implement `EncodedState(values: torch.Tensor, collection_mask: torch.Tensor, missingness: torch.Tensor, schema_version: str, scaler_version: str)` and:
- [ ] Define `Scaler(version: str, fold_hash: str, means: Mapping[str, float], scales: Mapping[str, float])`, `StateSchema(version: str, continuous: tuple[str, ...], required: tuple[str, ...], categorical_vocabularies: Mapping[str, tuple[str, ...]], collection_limits: Mapping[str, int])`, and `StateValidationError(ValueError)`.

```python
class StateEncoder:
    def encode(self, state: Mapping[str, object]) -> EncodedState:
        self.schema.validate(state)
        values = torch.tensor(
            [self.scaler.transform(name, float(state[name])) for name in self.schema.continuous],
            dtype=torch.float32,
        )
        if not torch.isfinite(values).all():
            raise StateValidationError("encoded state is non-finite")
        return EncodedState(
            values=values,
            collection_mask=self._collection_mask(state),
            missingness=self._missingness(state),
            schema_version=self.schema.version,
            scaler_version=self.scaler.version,
        )
```

- [ ] Ensure `Scaler.fit(rows, split)` rejects every split except `"train"` and serializes means/scales plus source fold hash.
- [ ] Run `python -m pytest tests/research/encoding/test_schema.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/encoding tests/research/encoding && git commit -m "feat: encode validated research state"`

### Task 8: Reconcile Fee-Once Reward and Terminal Closure

**Interfaces**

- Consumes: `AccountingProjection`, `PenaltyStatistics`, `RewardConfig`.
- Produces: `RewardBuilder.build(before, after, penalties, terminal) -> RewardRecord`.

**Files**

- Create: `src/sneaker_market_maker/research/rewards/builder.py`
- Create: `tests/research/rewards/test_builder.py`

- [ ] Test exact formula, every component summing within `Decimal("1e-12")`, fees shown as explanatory but not subtracted twice, one named accrual for a cost absent from NAV, duplicate ledger IDs rejected, nonnegative penalties, and terminal inventory/reservations closed exactly once.
- [ ] Run `python -m pytest tests/research/rewards/test_builder.py -q`. Expected failure: import of `RewardBuilder` fails.
- [ ] Implement the exact calculation:

```python
nav_delta = (after.nav - before.nav) / config.initial_nav
penalty_total = (
    config.lambda_age * penalties.age
    + config.lambda_capital * penalties.capital
    + config.lambda_turnover * penalties.turnover
    + config.lambda_drawdown * penalties.drawdown
    + config.lambda_stale * penalties.stale
    + (config.lambda_terminal * penalties.liquidation if terminal else Decimal("0"))
)
total = nav_delta - penalty_total
```

- [ ] Define `AccountingProjection(nav: Decimal, ledger_entry_ids: tuple[str, ...], seller_fees: Decimal, processor_fees: Decimal, shipping: Decimal, authentication: Decimal, slippage: Decimal, open_reservations: tuple[str, ...], physical_lots: tuple[str, ...])`, `PenaltyStatistics(age: Decimal, capital: Decimal, turnover: Decimal, drawdown: Decimal, stale: Decimal, liquidation: Decimal)`, and `RewardConfig(version: str, initial_nav: Decimal, lambda_age: Decimal, lambda_capital: Decimal, lambda_turnover: Decimal, lambda_drawdown: Decimal, lambda_stale: Decimal, lambda_terminal: Decimal, tolerance: Decimal)`.
- [ ] `AccountingProjection` must include `nav`, `ledger_entry_ids`, `seller_fees`, `processor_fees`, `shipping`, `authentication`, `slippage`, `open_reservations`, and `physical_lots`; `RewardBuilder` verifies each explanatory cost is already represented by a ledger ID or creates exactly one supplied accrual ID.
- [ ] Run `python -m pytest tests/research/rewards/test_builder.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/rewards tests/research/rewards && git commit -m "feat: reconcile fee-once rewards"`

### Task 9: Persist Complete Trainable Transitions

**Interfaces**

- Consumes: adjacent `DecisionPoint` pairs, proposed/post-gate actions, behavior policy, reward, provenance.
- Produces: `TransitionService.record(input: TransitionInput) -> AddResult`.

**Files**

- Create: `src/sneaker_market_maker/research/transitions/service.py`
- Create: `tests/research/transitions/test_service.py`

- [ ] Test complete next-state linkage, atomic content hashing, fill/order/fee/inventory/logistics attribution, action propensity, reconciliation gating, idempotent retry, and non-trainable status with stable reason when legacy data lacks propensity or logistics outcomes.
- [ ] Run `python -m pytest tests/research/transitions/test_service.py -q`. Expected failure: import of `TransitionService` fails.
- [ ] Implement `TransitionInput` with exact fields `current`, `next`, `proposed_action`, `post_gate_action`, `behavior`, `reward`, `effects`, and `lineage`; canonical JSON must sort keys and encode `Decimal` as strings before SHA-256.
- [ ] Give those fields exact types: `current: DecisionPoint`, `next: DecisionPoint`, `proposed_action: HybridAction`, `post_gate_action: HybridAction`, `behavior: BehaviorPolicy`, `reward: RewardRecord`, `effects: StepEffects`, and `lineage: TransitionLineage`. Define `StepEffects(order_ids: tuple[str, ...], fill_ids: tuple[str, ...], fee_ledger_ids: tuple[str, ...], inventory_transition_ids: tuple[str, ...], logistics_transition_ids: tuple[str, ...], settlement_ids: tuple[str, ...])` and `TransitionLineage(state_schema_version: str, action_schema_version: str, reward_schema_version: str, dataset_version: str, scenario_version: str, simulator_version: str, gate_policy_version: str, code_revision: str, random_seed: int, provenance_label: Literal["historical", "synthetic"])`.
- [ ] Implement:

```python
class TransitionService:
    def record(self, input: TransitionInput) -> AddResult:
        transition = self.assembler.assemble(input)
        transition.validate_trainable()
        return self.repository.add_transition(transition)
```

- [ ] Catch only `TrainabilityError` to persist a quarantined row and reason; never make up missing values and never catch repository failures.
- [ ] Run `python -m pytest tests/research/transitions/test_service.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/transitions tests/research/transitions && git commit -m "feat: record complete offline transitions"`

### Task 10: Generate Leakage-Safe Walk-Forward Folds

**Interfaces**

- Consumes: `Sequence[EpisodeManifest]`, `WalkForwardConfig`.
- Produces: `WalkForwardSplitter.split(manifests: Sequence[EpisodeManifest], config: WalkForwardConfig) -> tuple[Fold, ...]`.

**Files**

- Create: `src/sneaker_market_maker/research/contracts/experiment.py`
- Create: `src/sneaker_market_maker/research/evaluation/splits.py`
- Create: `tests/research/evaluation/test_splits.py`

- [ ] Test chronological train/validation/test ordering, no source-event duplicate, no episode overlap, no product/size lineage crossing folds, scaler fit only on train, augmentation only on train/declared validation stress, frozen holdout hash, and historical labels surviving mixed exports.
- [ ] Run `python -m pytest tests/research/evaluation/test_splits.py -q`. Expected failure: import of `WalkForwardSplitter` fails.
- [ ] Implement:

```python
@dataclass(frozen=True)
class Fold:
    fold_id: str
    train_episode_ids: tuple[UUID, ...]
    validation_episode_ids: tuple[UUID, ...]
    test_episode_ids: tuple[UUID, ...]
    frozen_holdout_hash: str


class WalkForwardSplitter:
    def split(
        self, manifests: Sequence[EpisodeManifest], config: WalkForwardConfig
    ) -> tuple[Fold, ...]:
        ordered = tuple(sorted(manifests, key=lambda item: item.start))
        self._assert_unique_sources(ordered)
        self._assert_non_overlapping(ordered)
        folds = self._window(ordered, config)
        self._assert_lineage_isolated(folds, ordered)
        return folds
```

- [ ] Define `EpisodeManifest(episode_id: UUID, start: datetime, end: datetime, split: Literal["train", "validation", "test"], product_size_lineage: str, source_record_ids: tuple[str, ...], provenance: Literal["historical", "synthetic"], checksum: str)` and `WalkForwardConfig(train_episodes: int, validation_episodes: int, test_episodes: int, step_episodes: int)`, validating every count is positive.
- [ ] Make overlap/lineage errors name both episode IDs and fail before scaler fitting.
- [ ] Run `python -m pytest tests/research/evaluation/test_splits.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/contracts/experiment.py src/sneaker_market_maker/research/evaluation tests/research/evaluation && git commit -m "feat: add leakage-safe walk-forward folds"`

### Task 11: Run Every Policy Through One Evaluation Harness

**Interfaces**

- Consumes: `EvaluationPolicy.recommend(state: EncodedState, mask: ActionMask, bounds: ActionBounds) -> PolicyOutput`; `FrozenAssumptions`; episodes.
- Produces: `EvaluationHarness.run(policy, episodes, assumptions) -> EvaluationReport`.

**Files**

- Create: `src/sneaker_market_maker/research/ports.py`
- Create: `src/sneaker_market_maker/research/policies/baselines.py`
- Create: `src/sneaker_market_maker/research/evaluation/harness.py`
- Create: `src/sneaker_market_maker/research/evaluation/metrics.py`
- Create: `tests/research/evaluation/test_harness.py`

- [ ] Test deterministic/no-model/heuristic/v1 MLP adapters receive byte-identical serialized assumptions and episodes; all outputs pass through the same simulator, fees, slippage, latency, terminal policy, and gates.
- [ ] Run `python -m pytest tests/research/evaluation/test_harness.py -q`. Expected failure: import of `EvaluationHarness` fails.
- [ ] Define:

```python
class EvaluationPolicy(Protocol):
    @property
    def policy_id(self) -> str:
        raise NotImplementedError

    def recommend(
        self, state: EncodedState, mask: ActionMask, bounds: ActionBounds
    ) -> PolicyOutput:
        raise NotImplementedError


@dataclass(frozen=True)
class FrozenAssumptions:
    episode_hash: str
    fee_version: str
    slippage_version: str
    logistics_version: str
    terminal_policy_version: str
    gate_policy_version: str
    latency_ms: int
```

- [ ] Define `PolicyOutput(action: RawHybridAction, score: float | None, policy_id: str, latency_ms: int)`, `MetricInterval(point: float, lower: float, upper: float, confidence: float)`, and `EvaluationReport(policy_id: str, assumptions_hash: str, metrics: Mapping[str, MetricInterval], support_coverage: float, numerical_failures: int, seed_results: Mapping[int, Mapping[str, float]], historical: bool)`. The harness canonicalizes every `PolicyOutput.action` before simulation.
- [ ] `EvaluationReport` must include net return, CE, mean/median, VaR, CVaR, worst block, max drawdown, inventory age/stranding, capital utilization/reservation time, turnover/cancel/fill/gate rates, support coverage, latency, numerical failures, seed dispersion, and episode-block bootstrap intervals.
- [ ] Run `python -m pytest tests/research/evaluation/test_harness.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/ports.py src/sneaker_market_maker/research/policies src/sneaker_market_maker/research/evaluation tests/research/evaluation && git commit -m "feat: evaluate policies under frozen assumptions"`

### Task 12: Enforce Support Diagnostics and Honest OPE

**Interfaces**

- Consumes: logged propensities, evaluation action probabilities, `SupportDiagnostics`.
- Produces: `assess_ope_validity(behavior: Sequence[BehaviorPolicy], support: SupportDiagnostics, nuisance_model_hash: str | None) -> OPEValidity`; `weighted_importance_sampling(returns: Tensor, evaluation_log_prob: Tensor, behavior_log_prob: Tensor) -> OPEEstimate`.

**Files**

- Create: `src/sneaker_market_maker/research/evaluation/ope.py`
- Create: `tests/research/evaluation/test_ope.py`

- [ ] Test trustworthy nonzero joint propensities permit WIS, deterministic/missing/zero propensity returns status `"OPE_NOT_VALID"` with stable reason, weak effective sample size is reported, and fitted-Q/doubly-robust methods are unavailable without validated nuisance-model lineage.
- [ ] Run `python -m pytest tests/research/evaluation/test_ope.py -q`. Expected failure: import of `assess_ope_validity` fails.
- [ ] Implement:

```python
@dataclass(frozen=True)
class OPEValidity:
    valid: bool
    status: Literal["VALID", "OPE_NOT_VALID"]
    reason: str | None


@dataclass(frozen=True)
class SupportDiagnostics:
    supported_fraction: float
    effective_sample_size: float
    trustworthy_joint_propensities: bool


@dataclass(frozen=True)
class OPEEstimate:
    value: float
    effective_sample_size: float
    method: Literal["WIS"]


def weighted_importance_sampling(
    returns: torch.Tensor,
    evaluation_log_prob: torch.Tensor,
    behavior_log_prob: torch.Tensor,
) -> OPEEstimate:
    log_weights = evaluation_log_prob - behavior_log_prob
    if not torch.isfinite(log_weights).all():
        raise ValueError("non-finite importance weight")
    weights = torch.softmax(log_weights, dim=0)
    estimate = torch.sum(weights * returns)
    ess = torch.reciprocal(torch.sum(weights.square()))
    return OPEEstimate(float(estimate), float(ess), "WIS")
```

- [ ] Run `python -m pytest tests/research/evaluation/test_ope.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/evaluation/ope.py tests/research/evaluation/test_ope.py && git commit -m "feat: enforce honest offline evaluation"`

### Task 13: Add the PFHedge Direct-Policy Baseline

**Interfaces**

- Consumes: shared scenario tensor `[batch, time, features]`, bounds tensor, terminal simulator P&L.
- Produces: `PFHedgeDirectPolicy.forward(state: Tensor, bounds: Tensor) -> Tensor`; `PFHedgeTrainer.loss(pnl: Tensor) -> Tensor`.

**Files**

- Create: `src/sneaker_market_maker/research/pfhedge/adapter.py`
- Create: `tests/research/pfhedge/test_adapter.py`

- [ ] Test bounded continuous output shape `[batch, time, 3]`, same simulator cost path as baselines, deterministic seeded fit, public `EntropicRiskMeasure`, and absence of PFHedge imports from `research/iql`.
- [ ] Run `python -m pytest tests/research/pfhedge/test_adapter.py -q`. Expected failure: import of `PFHedgeDirectPolicy` fails.
- [ ] Implement:

```python
class PFHedgeDirectPolicy(nn.Module):
    def __init__(self, feature_count: int, hidden: int = 64) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(feature_count, hidden),
            nn.Tanh(),
            nn.Linear(hidden, 3),
        )

    def forward(self, state: Tensor, bounds: Tensor) -> Tensor:
        raw = self.network(state)
        allocation = torch.sigmoid(raw[..., :1])
        offsets = torch.tanh(raw[..., 1:])
        low, high = bounds[..., 0, :], bounds[..., 1, :]
        mapped = low + (offsets + 1.0) * 0.5 * (high - low)
        return torch.cat((allocation, mapped), dim=-1)


class PFHedgeTrainer:
    def __init__(self, risk_aversion: float) -> None:
        self.criterion = EntropicRiskMeasure(a=risk_aversion)

    def loss(self, pnl: Tensor) -> Tensor:
        return self.criterion(pnl)
```

- [ ] Document in module docstring and report metadata: PFHedge optimizes terminal direct-policy risk; it does not implement Bellman targets, IQL, categorical posture, replay support, promotion, or gates.
- [ ] Run `python -m pytest tests/research/pfhedge/test_adapter.py tests/compatibility/test_pfhedge_public_api.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/pfhedge tests/research/pfhedge && git commit -m "feat: add PFHedge direct baseline"`

### Task 14: Implement Certainty Equivalent and Quantile-Huber Math

**Interfaces**

- Consumes: PyTorch tensors of quantiles/targets and persisted scalar hyperparameters.
- Produces: `certainty_equivalent`; `smooth_huber`; `pairwise_quantile_huber_loss`; `quantile_crossing_loss`.

**Files**

- Create: `src/sneaker_market_maker/research/iql/math.py`
- Create: `tests/research/iql/test_math.py`

- [ ] Add exact-value and autograd tests for CE at zero, near-zero series, float64 log-sum-exp, non-finite rejection, Huber branches, quantile sign/weights, `1/K²` reduction, and crossing penalty.
- [ ] Run `python -m pytest tests/research/iql/test_math.py -q`. Expected failure: import of `certainty_equivalent` fails.
- [ ] Implement exactly:

```python
def certainty_equivalent(
    quantiles: Tensor, eta: float, epsilon: float = 1e-6
) -> Tensor:
    if eta < 0:
        raise ValueError("eta must be non-negative")
    if not torch.isfinite(quantiles).all():
        raise FloatingPointError("quantiles must be finite")
    z = quantiles.to(torch.float64)
    mean = z.mean(dim=-1)
    if eta == 0.0:
        return mean
    if abs(eta) < epsilon:
        variance = ((z - mean.unsqueeze(-1)) ** 2).mean(dim=-1)
        return mean - 0.5 * eta * variance
    return -(torch.logsumexp(-eta * z, dim=-1) - math.log(z.shape[-1])) / eta


def smooth_huber(error: Tensor, kappa: float) -> Tensor:
    absolute = error.abs()
    return torch.where(
        absolute <= kappa,
        0.5 * error.square(),
        kappa * (absolute - 0.5 * kappa),
    )


def pairwise_quantile_huber_loss(
    predicted: Tensor, target: Tensor, fractions: Tensor, kappa: float
) -> Tensor:
    error = target.detach().unsqueeze(-2) - predicted.unsqueeze(-1)
    indicator = (error < 0).to(predicted.dtype)
    weights = (fractions.view(1, -1, 1) - indicator).abs()
    return (weights * smooth_huber(error, kappa)).mean()


def quantile_crossing_loss(quantiles: Tensor) -> Tensor:
    return torch.relu(quantiles[..., :-1] - quantiles[..., 1:]).mean()
```

- [ ] Run `python -m pytest tests/research/iql/test_math.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/iql/math.py tests/research/iql/test_math.py && git commit -m "feat: implement distributional risk math"`

### Task 15: Implement Distributional Value and Twin-Q Networks

**Interfaces**

- Consumes: state tensor `[B, state_dim]`, action tensor `[B, action_dim]`.
- Produces: `DistributionalValue.forward(state) -> Tensor[B, K]`; `DistributionalQ.forward(state, action) -> Tensor[B, K]`; `select_conservative_quantiles(q1, q2, eta) -> Tensor[B, K]`.

**Files**

- Create: `src/sneaker_market_maker/research/iql/networks.py`
- Create: `tests/research/iql/test_networks.py`

- [ ] Test exact shapes, independent critic initialization, finite-output rejection, lower-CE row-wise critic selection, index-1 tie break, and target copies requiring no gradients.
- [ ] Run `python -m pytest tests/research/iql/test_networks.py -q`. Expected failure: import of `DistributionalValue` fails.
- [ ] Implement separate MLP instances:

```python
class DistributionalValue(nn.Module):
    def __init__(self, state_dim: int, hidden_dim: int, quantile_count: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, quantile_count),
        )

    def forward(self, state: Tensor) -> Tensor:
        result = self.net(state)
        if not torch.isfinite(result).all():
            raise FloatingPointError("value output is non-finite")
        return result


def select_conservative_quantiles(q1: Tensor, q2: Tensor, eta: float) -> Tensor:
    choose_first = certainty_equivalent(q1, eta) <= certainty_equivalent(q2, eta)
    return torch.where(choose_first.unsqueeze(-1), q1, q2)
```

- [ ] `DistributionalQ` uses the same architecture on `torch.cat((state, action), dim=-1)`; instantiate critics independently and deep-copy inference-only targets with every parameter `requires_grad_(False)`.
- [ ] Run `python -m pytest tests/research/iql/test_networks.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/iql/networks.py tests/research/iql/test_networks.py && git commit -m "feat: add distributional value critics"`

### Task 16: Implement the Masked, Squashed Hybrid Actor

**Interfaces**

- Consumes: state, category mask `[B,3]`, offset bounds `[B,2,2]`, logged category and continuous action.
- Produces: `HybridActor.deterministic(state: Tensor, mask: Tensor, bounds: Tensor) -> ActorAction`; `HybridActor.log_prob(state: Tensor, mask: Tensor, bounds: Tensor, category: Tensor, continuous: Tensor, active_dimensions: Tensor) -> Tensor`.

**Files**

- Create: `src/sneaker_market_maker/research/iql/actor.py`
- Create: `tests/research/iql/test_actor.py`

- [ ] Test invalid categories have zero probability and are never selected, fully masked rows raise, sigmoid allocation and affine-tanh offsets stay bounded under arbitrary finite logits, deterministic output uses masked argmax/transformed means, inactive dimensions contribute zero log density, and active dimensions include sigmoid/tanh Jacobians.
- [ ] Run `python -m pytest tests/research/iql/test_actor.py -q`. Expected failure: import of `HybridActor` fails.
- [ ] Implement masked logits and transforms:

```python
def masked_log_softmax(logits: Tensor, mask: Tensor) -> Tensor:
    if not mask.any(dim=-1).all():
        raise ValueError("fully masked action row")
    safe_min = torch.finfo(logits.dtype).min
    return torch.log_softmax(logits.masked_fill(~mask, safe_min), dim=-1)


def squash_continuous(raw: Tensor, bounds: Tensor) -> Tensor:
    allocation = torch.sigmoid(raw[..., :1])
    unit_offsets = torch.tanh(raw[..., 1:])
    low, high = bounds[..., 0, :], bounds[..., 1, :]
    offsets = low + 0.5 * (unit_offsets + 1.0) * (high - low)
    return torch.cat((allocation, offsets), dim=-1)
```

- [ ] Implement the exact transformed density below. `mean` and `log_std` come from heads evaluated on `torch.cat((state, one_hot(category, 3)), dim=-1)`; clamp `log_std` to `[-5, 2]`. For `NO_OP` and `CANCEL`, `active_dimensions` is all false and the result is categorical-only.

```python
def transformed_normal_log_prob(
    mean: Tensor,
    log_std: Tensor,
    continuous: Tensor,
    bounds: Tensor,
    active_dimensions: Tensor,
) -> Tensor:
    epsilon = torch.finfo(continuous.dtype).eps
    allocation = continuous[..., :1].clamp(epsilon, 1.0 - epsilon)
    allocation_raw = torch.logit(allocation)
    low, high = bounds[..., 0, :], bounds[..., 1, :]
    offset_active = active_dimensions[..., 1:]
    span = torch.where(offset_active, high - low, torch.ones_like(high))
    unit_offsets = (2.0 * (continuous[..., 1:] - low) / span - 1.0).clamp(
        -1.0 + epsilon, 1.0 - epsilon
    )
    unit_offsets = torch.where(offset_active, unit_offsets, torch.zeros_like(unit_offsets))
    offset_raw = torch.atanh(unit_offsets)
    raw = torch.cat((allocation_raw, offset_raw), dim=-1)
    base = Normal(mean, log_std.clamp(-5.0, 2.0).exp()).log_prob(raw)
    allocation_log_jacobian = torch.log(allocation * (1.0 - allocation))
    offset_log_jacobian = torch.log1p(-unit_offsets.square()) + torch.log(
        span / 2.0
    )
    log_jacobian = torch.cat((allocation_log_jacobian, offset_log_jacobian), dim=-1)
    return ((base - log_jacobian) * active_dimensions).sum(dim=-1)
```

- [ ] `HybridActor.log_prob` adds `masked_log_softmax(category_logits, mask).gather(1, category[:, None]).squeeze(1)` to `transformed_normal_log_prob(mean, log_std, continuous, bounds, active_dimensions)`.
- [ ] Define `ActorAction(category: Tensor, continuous: Tensor, categorical_log_probability: Tensor)`; `category` has shape `[B]`, `continuous` has shape `[B,3]`, and the log probability has shape `[B]`.
- [ ] Add Hypothesis tests with finite raw values in `[-80, 80]`.
- [ ] Run `python -m pytest tests/research/iql/test_actor.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/iql/actor.py tests/research/iql/test_actor.py && git commit -m "feat: add masked hybrid actor"`

### Task 17: Enforce the IQL Update Ordering and Detached Targets

**Interfaces**

- Consumes: `TransitionBatch`; value/twin-Q/actor modules; `IQLConfig`.
- Produces: `IQLTrainer.step(batch: TransitionBatch) -> StepMetrics`.

**Files**

- Create: `src/sneaker_market_maker/research/iql/trainer.py`
- Create: `tests/research/iql/test_trainer.py`

- [ ] Test the call order is value → Q1/Q2 → actor → targets; value uses only logged actions and stopped conservative target-Q; Q target is `r + gamma*(1-done)*target_value(next_state)` with no bootstrap at terminal; actor advantage is recomputed and detached; target networks receive no gradients; Polyak runs only after successful optimizer steps.
- [ ] Run `python -m pytest tests/research/iql/test_trainer.py -q`. Expected failure: import of `IQLTrainer` fails.
- [ ] Implement value and Q losses:

```python
with torch.no_grad():
    target_q = select_conservative_quantiles(
        self.target_q1(batch.state, batch.action),
        self.target_q2(batch.state, batch.action),
        config.eta,
    )
value = self.value(batch.state)
delta = certainty_equivalent(target_q, config.eta) - certainty_equivalent(value, config.eta)
expectile_weight = torch.where(delta >= 0, config.expectile, 1.0 - config.expectile)
value_loss = (
    expectile_weight
    * (
        smooth_huber(value - target_q, config.kappa).mean(dim=-1)
        + config.lambda_ce * delta.square()
    )
).mean() + config.lambda_cross * quantile_crossing_loss(value)

with torch.no_grad():
    bellman_target = batch.reward.unsqueeze(-1) + (
        batch.discount * (~batch.done).to(batch.reward.dtype)
    ).unsqueeze(-1) * self.target_value(batch.next_state)
q1_loss = pairwise_quantile_huber_loss(
    self.q1(batch.state, batch.action), bellman_target, self.fractions, config.kappa
)
q2_loss = pairwise_quantile_huber_loss(
    self.q2(batch.state, batch.action), bellman_target, self.fractions, config.kappa
)
```

- [ ] Implement actor weight exactly:

```python
with torch.no_grad():
    conservative_q = select_conservative_quantiles(
        self.target_q1(batch.state, batch.action),
        self.target_q2(batch.state, batch.action),
        config.eta,
    )
    advantage = certainty_equivalent(conservative_q, config.eta) - certainty_equivalent(
        self.value(batch.state), config.eta
    )
    weight = torch.exp(torch.clamp(config.beta * advantage, -config.exp_clip, config.exp_clip))
    weight = torch.clamp(weight, max=config.max_weight)
actor_loss = -(weight * self.actor.log_prob_logged(batch)).mean()
```

- [ ] Define `TransitionBatch(state: Tensor, action: Tensor, reward: Tensor, next_state: Tensor, done: Tensor, discount: Tensor, category_mask: Tensor, bounds: Tensor, logged_category: Tensor, active_dimensions: Tensor)`, `IQLConfig(eta: float, expectile: float, kappa: float, lambda_ce: float, lambda_cross: float, beta: float, exp_clip: float, max_weight: float, max_grad_norm: float, target_tau: float, target_cadence: int)`, and `StepMetrics(value_loss: float, q1_loss: float, q2_loss: float, actor_loss: float, gradient_norm: float, target_updated: bool)`.
- [ ] Assert finite inputs/losses/gradients, clip gradients at persisted `max_grad_norm`, and abort the step before target updates on any failure. Polyak uses `target = tau*online + (1-tau)*target`.
- [ ] Run `python -m pytest tests/research/iql/test_trainer.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/iql/trainer.py tests/research/iql/test_trainer.py && git commit -m "feat: implement ordered IQL updates"`

### Task 18: Load Replay, Checkpoint Safely, and Run Seeded IQL Smoke Training

**Interfaces**

- Consumes: trainable `OfflineTransition` rows and immutable run manifest.
- Produces: `TransitionDataset`; `CheckpointStore.save/load`; reproducible tiny training run.

**Files**

- Create: `src/sneaker_market_maker/research/iql/dataset.py`
- Create: `src/sneaker_market_maker/research/iql/checkpoint.py`
- Create: `tests/research/iql/test_training_pipeline.py`

- [ ] Test invalid rows are excluded with reason counts, tiny fixture overfits downward in all three losses, same seed gives identical hashes, different twin critics remain distinct, corrupt/non-finite data fails the run, incomplete/hash-mismatched checkpoints cannot resume, and PFHedge is absent from loaded IQL modules.
- [ ] Run `python -m pytest tests/research/iql/test_training_pipeline.py -q`. Expected failure: import of `TransitionDataset` fails.
- [ ] Implement `TransitionDataset.from_repository(repository, manifest_id) -> tuple[TransitionDataset, ExclusionCounts]` and tensor fields `state`, `action`, `reward`, `next_state`, `done`, `discount`, `category_mask`, `bounds`, and logged active-dimension mask.
- [ ] Define `ExclusionCounts(reasons: Mapping[str, int], accepted: int, rejected: int)` and `CheckpointManifest(architecture: Literal["distributional_iql_v1"], run_manifest_hash: str, environment_hash: str, step: int, tensor_hash: str, complete: bool)`. Define `CheckpointStore.save(path: Path, manifest: CheckpointManifest, tensors: Mapping[str, Tensor]) -> str` and `CheckpointStore.load(path: Path, expected_run_manifest_hash: str, expected_environment_hash: str) -> tuple[CheckpointManifest, dict[str, Tensor]]`.
- [ ] Save primitive metadata to canonical `manifest.json` and model/optimizer tensors to `weights.safetensors` with `safetensors.torch.save_file`; verify SHA-256 before `safetensors.torch.load_file`, reconstruct only allowlisted architecture names, and never call `pickle`, `torch.save`, or `torch.load`.
- [ ] Implement the safe load boundary:

```python
def load(
    self,
    path: Path,
    expected_run_manifest_hash: str,
    expected_environment_hash: str,
) -> tuple[CheckpointManifest, dict[str, Tensor]]:
    manifest = CheckpointManifest.from_json((path / "manifest.json").read_text())
    if not manifest.complete:
        raise CheckpointError("checkpoint is incomplete")
    if manifest.architecture != "distributional_iql_v1":
        raise CheckpointError("architecture is not allowlisted")
    if manifest.run_manifest_hash != expected_run_manifest_hash:
        raise CheckpointError("run manifest mismatch")
    if manifest.environment_hash != expected_environment_hash:
        raise CheckpointError("environment mismatch")
    tensor_path = path / "weights.safetensors"
    if sha256(tensor_path.read_bytes()).hexdigest() != manifest.tensor_hash:
        raise CheckpointError("tensor hash mismatch")
    return manifest, load_file(tensor_path)
```
- [ ] Run `python -m pytest tests/research/iql/test_training_pipeline.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/iql tests/research/iql/test_training_pipeline.py && git commit -m "feat: add reproducible IQL training pipeline"`

### Task 19: Register Immutable Models with Legal Promotion States

**Interfaces**

- Consumes: artifact hash, compatibility contract, benchmark report, actor identity.
- Produces: `RegistryService.register(artifact_hash: str, compatibility: CompatibilityContract, benchmark_report_id: UUID, actor: str) -> RegistryModel`; `RegistryService.transition(model_id: UUID, target: RegistryState, actor: str, reason: str) -> RegistryModel`.

**Files**

- Create: `src/sneaker_market_maker/research/registry/service.py`
- Create: `tests/research/registry/test_service.py`

- [ ] Test immutability, artifact/hash/schema/finite/replay/latency/restart validation, all legal transitions, illegal skips, mandatory benchmark criteria, audited rollback, transaction failure rollback, and registration granting no serving status.
- [ ] Run `python -m pytest tests/research/registry/test_service.py -q`. Expected failure: import of `RegistryService` fails.
- [ ] Implement enum states `CANDIDATE`, `VALIDATED`, `SHADOW`, `BENCHMARK_QUALIFIED`, `ADVISORY_APPROVED`, `ROLLED_BACK`, `REJECTED` and exact adjacency:

```python
LEGAL_TRANSITIONS = {
    RegistryState.CANDIDATE: {RegistryState.VALIDATED, RegistryState.REJECTED},
    RegistryState.VALIDATED: {RegistryState.SHADOW, RegistryState.REJECTED},
    RegistryState.SHADOW: {RegistryState.BENCHMARK_QUALIFIED, RegistryState.ROLLED_BACK},
    RegistryState.BENCHMARK_QUALIFIED: {
        RegistryState.ADVISORY_APPROVED,
        RegistryState.ROLLED_BACK,
    },
    RegistryState.ADVISORY_APPROVED: {RegistryState.ROLLED_BACK},
    RegistryState.ROLLED_BACK: set(),
    RegistryState.REJECTED: set(),
}
```

- [ ] Define `CompatibilityContract(state_schema_version: str, action_schema_version: str, encoder_version: str, reward_version: str, architecture: str, environment_hash: str)`, `BenchmarkCriterion(name: str, comparison: Literal["minimum", "maximum", "required"], threshold: float | bool)`, `BenchmarkPolicy(version: str, criteria: tuple[BenchmarkCriterion, ...], frozen_at: datetime)`, and `RegistryModel(model_id: UUID, artifact_hash: str, compatibility: CompatibilityContract, benchmark_report_id: UUID, state: RegistryState, created_at: datetime)`.
- [ ] Keep benchmark thresholds in a versioned `BenchmarkPolicy` fixture supplied before evaluation; `transition` checks every required fold/stress/support/seed/shadow result and blocks on any missing criterion.
- [ ] Run `python -m pytest tests/research/registry/test_service.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/registry tests/research/registry && git commit -m "feat: govern immutable model registry"`

### Task 20: Serve Shadow Recommendations Without Changing Paper Commands

**Interfaces**

- Consumes: deterministic recommendation, optional PFHedge/IQL output, registry status, support/health/drift, deterministic `GatePort`.
- Produces: `RecommendationService.recommend(request: RecommendationRequest) -> RecommendationRecord`.

**Files**

- Create: `src/sneaker_market_maker/research/serving/recommender.py`
- Create: `tests/research/serving/test_recommender.py`

- [ ] Test schema/finite/mask checks, canonicalization, rounding/clamping, weak support, timeout, drift, incompatible lineage, missing artifact, unhealthy service, each gate failure, stable fallback reason, and advisory output unable to reverse deterministic rejection.
- [ ] Add a golden test serializing the full paper command stream in deterministic-only and shadow modes and asserting `deterministic_bytes == shadow_bytes`, while shadow persists model comparisons.
- [ ] Run `python -m pytest tests/research/serving/test_recommender.py -q`. Expected failure: import of `RecommendationService` fails.
- [ ] Implement:

```python
candidate = (
    canonicalize_action(request.selected_model_action, request.bounds, request.mask)
    if request.selected_model_action is not None
    else None
)
gate_result = (
    self.gates.evaluate(candidate, request.risk_state)
    if candidate is not None
    else GateResult(False, (("model_output_present", False),))
)
if request.registry_state is RegistryState.SHADOW:
    final_action = request.deterministic_action
elif (
    request.registry_state is RegistryState.ADVISORY_APPROVED
    and candidate is not None
    and gate_result.accepted
):
    final_action = candidate
else:
    final_action = request.deterministic_action
return RecommendationRecord(
    deterministic_action=request.deterministic_action,
    pfhedge_action=request.pfhedge_action,
    iql_action=request.iql_action,
    canonical_action=candidate,
    gate_results=gate_result.results,
    final_action=final_action,
    fallback_reason=self._fallback_reason(request, gate_result),
)
```

- [ ] Define `RecommendationRequest(request_id: UUID, deterministic_action: HybridAction, pfhedge_action: RawHybridAction | None, iql_action: RawHybridAction | None, selected_model_action: RawHybridAction | None, bounds: ActionBounds, mask: ActionMask, risk_state: Mapping[str, object], registry_state: RegistryState, support_ok: bool, healthy: bool, drifted: bool, lineage_compatible: bool)`; `GateResult(accepted: bool, results: tuple[tuple[str, bool], ...])`; and `RecommendationRecord(request_id: UUID, deterministic_action: HybridAction, pfhedge_action: RawHybridAction | None, iql_action: RawHybridAction | None, canonical_action: HybridAction | None, gate_results: tuple[tuple[str, bool], ...], final_action: HybridAction, fallback_reason: str | None)`.
- [ ] The service Protocols expose no execution method or credential. Timeouts use an injected clock and fail closed.
- [ ] Run `python -m pytest tests/research/serving/test_recommender.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/serving tests/research/serving && git commit -m "feat: add inert shadow recommendations"`

### Task 21: Expose Local Research REST and Ordered Events

**Interfaces**

- Consumes: repository/query services, registry/run commands, event sequence store.
- Produces: FastAPI reads, idempotent commands, `ResearchEventEnvelope`.

**Files**

- Create: `src/sneaker_market_maker/api/app.py`
- Create: `src/sneaker_market_maker/api/research_routes.py`
- Create: `src/sneaker_market_maker/api/research_events.py`
- Create: `tests/api/test_research_api.py`

- [ ] Test reads for manifests/quality/runs/checkpoints/reports/registry/comparisons/recommendations; idempotent create/cancel/validate/register/shadow/advisory/rollback commands; durable run IDs; ordered WebSocket sequence; bounded payloads; no arbitrary code field; and loopback default.
- [ ] Run `python -m pytest tests/api/test_research_api.py -q`. Expected failure: import of `create_app` fails.
- [ ] Implement `create_app(services: ResearchServices) -> FastAPI`; command endpoints require `Idempotency-Key`, return `202` plus stable command/run ID, and write audit records in the same transaction as state changes.
- [ ] Define recursive alias `JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]`, `ResearchServices(query_service: ResearchQueryService, command_service: ResearchCommandService, event_service: ResearchEventService)`, and Protocol methods `ResearchQueryService.get(resource: str, resource_id: UUID | None) -> JsonValue`, `ResearchCommandService.execute(command: str, payload: Mapping[str, JsonValue], idempotency_key: str) -> UUID`, and `ResearchEventService.after(sequence: int) -> Sequence[ResearchEventEnvelope]`.
- [ ] Define:

```python
class ResearchEventEnvelope(BaseModel):
    sequence: int
    event_id: UUID
    event_type: Literal[
        "run.progress",
        "evaluation.completed",
        "registry.changed",
        "shadow.compared",
        "recommendation.fallback",
        "health.changed",
    ]
    simulation_time: datetime | None
    wall_time: datetime
    correlation_id: UUID
    payload: dict[str, JsonValue]
```

- [ ] Reject payloads over 64 KiB and tensor/blob fields; external binding requires an injected authentication dependency, while default CLI/config binds `127.0.0.1`.
- [ ] Run `python -m pytest tests/api/test_research_api.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/api tests/api && git commit -m "feat: expose governed research API"`

### Task 22: Build the React Research Comparison View

**Interfaces**

- Consumes: `/api/research/*` JSON and ordered research event envelopes.
- Produces: accessible `ResearchPage` with assumptions, lineage, folds/seeds/CIs, support warnings, provenance, ablations, registry, and recommendation traces.

**Files**

- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/research/types.ts`
- Create: `frontend/src/research/api.ts`
- Create: `frontend/src/research/ResearchPage.tsx`
- Create: `frontend/src/research/ResearchPage.test.tsx`

- [ ] Create this exact `frontend/package.json` dependency boundary:

```json
{
  "name": "sneaker-market-maker-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "build": "tsc --noEmit && vite build"
  },
  "dependencies": {
    "react": "18.3.1",
    "react-dom": "18.3.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "6.6.2",
    "@testing-library/react": "16.0.1",
    "@types/react": "18.3.10",
    "@types/react-dom": "18.3.0",
    "@vitejs/plugin-react": "4.3.2",
    "jsdom": "25.0.1",
    "typescript": "5.6.2",
    "vite": "5.4.8",
    "vitest": "2.1.1"
  }
}
```
- [ ] Run `cd frontend && npm install`. Expected: `package-lock.json` is generated with no installation error.
- [ ] Write a frontend test rendering fixture data and asserting visible frozen assumptions, explicit “Historical”/“Synthetic” badges, PFHedge “Direct hedging baseline” label, IQL “Custom Bellman IQL” label, confidence intervals, an “OPE not valid” warning, registry status, and every deterministic/PFHedge/IQL/canonical/gate/final trace stage.
- [ ] Run `cd frontend && npm test -- ResearchPage.test.tsx`. Expected failure: `Failed to resolve import "./ResearchPage"`.
- [ ] Implement explicit discriminated TypeScript types; `ResearchPage` renders semantic headings, tables with captions, status text independent of color, and buttons with accessible names. API errors render deterministic-only status, never optimistic promotion.
- [ ] Define `PolicyTrackView` exactly as `{ id: string; kind: "deterministic" | "heuristic" | "v1_mlp" | "pfhedge" | "iql"; name: string; provenance: "historical" | "synthetic"; ope: { valid: boolean; summary: string }; netReturn: { point: number; lower: number; upper: number } }` and `ResearchPageProps` as `{ assumptions: FrozenAssumptionsView; tracks: PolicyTrackView[]; registry: RegistryView; trace: RecommendationTraceView }`; define every field of the latter three interfaces from the corresponding Task 11, 19, and 20 JSON names without renaming.
- [ ] Keep the comparison rendering explicit:

```tsx
export function PolicyTrack({ track }: { track: PolicyTrackView }): JSX.Element {
  const label =
    track.kind === "pfhedge"
      ? "PFHedge — Direct hedging baseline"
      : track.kind === "iql"
        ? "IQL — Custom Bellman IQL"
        : track.name;
  return (
    <section aria-labelledby={`track-${track.id}`}>
      <h3 id={`track-${track.id}`}>{label}</h3>
      <p>{track.provenance === "historical" ? "Historical" : "Synthetic"}</p>
      <p>{track.ope.valid ? track.ope.summary : "OPE not valid"}</p>
      <p>{`Net return 95% CI: ${track.netReturn.lower} to ${track.netReturn.upper}`}</p>
    </section>
  );
}
```
- [ ] Run `cd frontend && npm test -- ResearchPage.test.tsx && npm run typecheck`. Expected: all pass.
- [ ] Commit: `git add frontend && git commit -m "feat: add research comparison UI"`

### Task 23: Deliver the Deterministic Five-Minute Guided Demo

**Interfaces**

- Consumes: pinned fixture events and prerecorded PFHedge/IQL outputs.
- Produces: `DemoService.pause/resume/restart/step/snapshot`; `GuidedDemo`.

**Files**

- Create: `src/sneaker_market_maker/research/demo/fixture.py`
- Create: `src/sneaker_market_maker/research/demo/service.py`
- Create: `tests/research/demo/test_service.py`
- Create: `frontend/src/research/GuidedDemo.tsx`
- Create: `frontend/src/research/GuidedDemo.test.tsx`

- [ ] Backend tests assert the exact six beats in order: healthy spread, deterministic bid, paper buy fill, shipping/authentication progression, inventory-backed ask/paper sale, deterministic gate rejection. Assert restart byte-equivalence and one coalesced decision per step.
- [ ] Run `python -m pytest tests/research/demo/test_service.py -q`. Expected failure: import of `DemoService` fails.
- [ ] Implement immutable `DEMO_EVENTS` spanning exactly 300 simulation seconds with fixed seed `20260717`; `DemoService.step()` increments one event index, `restart()` restores index zero and initial cash/NAV/inventory, and no method performs I/O.
- [ ] Pin these event rows in `DEMO_EVENTS`: `(0, "healthy_spread", NO_OP, 2500.00, 2500.00)`, `(60, "deterministic_bid", QUOTE, 2500.00, 2500.00)`, `(120, "paper_buy_fill", NO_OP, 2312.00, 2498.00)`, `(180, "shipping_authenticated", NO_OP, 2312.00, 2502.00)`, `(240, "inventory_ask_sale", QUOTE, 2524.50, 2524.50)`, `(300, "risk_gate_rejection", NO_OP, 2524.50, 2524.50)`, where tuple fields are simulation second, beat, final category, cash, and NAV. The sale row itemizes seller fee `15.00`, processor fee `4.50`, inbound shipping `8.00`, outbound shipping `2.00`, and realized P&L `24.50`; all other missing fee components are explicit `Decimal("0")`.
- [ ] Define `DemoSnapshot(index: int, simulation_second: int, paused: bool, beat: str, deterministic_action: HybridAction, pfhedge_score: float, iql_shadow_action: HybridAction, final_action: HybridAction, inventory_state: str, fees: Mapping[str, Decimal], cash: Decimal, nav: Decimal, realized_pnl: Decimal, unrealized_pnl: Decimal)` and exact methods `pause() -> DemoSnapshot`, `resume() -> DemoSnapshot`, `restart() -> DemoSnapshot`, `step() -> DemoSnapshot`, and `snapshot() -> DemoSnapshot`.
- [ ] Implement one-decision stepping:

```python
def step(self) -> DemoSnapshot:
    if self._index < len(self._events) - 1:
        self._index += 1
    return self.snapshot()

def restart(self) -> DemoSnapshot:
    self._index = 0
    self._paused = True
    return self.snapshot()
```
- [ ] Frontend test with fake timers asserts pause freezes, resume advances, step advances exactly one beat, restart restores the first snapshot, and each frame displays deterministic action, PFHedge score, IQL shadow action, final gated action, inventory lifecycle, itemized fees, cash/NAV, and realized/unrealized P&L.
- [ ] Run `cd frontend && npm test -- GuidedDemo.test.tsx`. Expected failure: `Failed to resolve import "./GuidedDemo"`.
- [ ] Implement accessible controls and a live-region beat description; use only fixture API data and no fetch from the component.
- [ ] Run `python -m pytest tests/research/demo/test_service.py -q && cd frontend && npm test -- GuidedDemo.test.tsx && npm run typecheck`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/demo tests/research/demo frontend/src/research && git commit -m "feat: add deterministic guided demo"`

### Task 24: Prove Offline-Only Safety and Network Denial

**Interfaces**

- Consumes: complete Python/frontend source trees and research services under test.
- Produces: static safety audit and network-denied end-to-end research suite.

**Files**

- Create: `tests/safety/test_offline_boundary.py`
- Create: `tests/safety/test_network_denied.py`
- Create: `frontend/src/research/offlineBoundary.test.ts`

- [ ] Add AST tests rejecting imports/usages of `requests`, `aiohttp`, marketplace SDKs, `subprocess` in model loading, unguarded `pickle.load`, credential environment names, execution methods, Cloudflare/CAPTCHA/TLS fingerprint/proxy rotation terms, and dependencies from research serving to a paper/live execution adapter.
- [ ] Run `python -m pytest tests/safety/test_offline_boundary.py -q`. Expected failure: until the allowlist is encoded, an assertion lists all reviewed network-capable backend modules.
- [ ] Implement a narrow allowlist containing only FastAPI/uvicorn local API modules and psycopg PostgreSQL transport; explicitly reject marketplace hosts and model-provided paths/code.
- [ ] Deny network in executable tests with:

```python
@pytest.fixture
def deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_connect(self: socket.socket, address: object) -> None:
        raise NetworkDenied(f"network disabled: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
```
- [ ] Monkeypatch `socket.socket.connect` to raise `NetworkDenied`, then run episode construction, reward, evaluation, PFHedge inference, IQL inference, registry, shadow recommendation, and demo tests with local fixtures.
- [ ] Frontend test stubs `globalThis.fetch` to throw and proves `GuidedDemo` still completes from injected fixture state.
- [ ] Run `python -m pytest tests/safety -q && cd frontend && npm test -- offlineBoundary.test.ts`. Expected: all pass.
- [ ] Commit: `git add tests/safety frontend/src/research/offlineBoundary.test.ts && git commit -m "test: prove offline research boundary"`

### Task 25: Qualify Advisory Mode Without Fabricating Approval

**Interfaces**

- Consumes: immutable benchmark policy, required historical fold reports, stress reports, support/seed results, completed shadow window, operational drill results.
- Produces: `QualificationService.evaluate(input: QualificationInput) -> QualificationReport`; optional audited registry transition only after explicit approval.

**Files**

- Create: `src/sneaker_market_maker/research/qualification/service.py`
- Create: `tests/research/qualification/test_service.py`
- Create: `docs/research/advisory-qualification.md`

- [ ] Test lower confidence bounds versus deterministic/heuristic baselines, non-inferiority for CVaR/drawdown/inventory/capital/turnover/gate rejection, all required folds, stress ceilings, support coverage, seed stability, minimum shadow observations, byte-equivalent paper streams, restart/rollback/drift/artifact drills, and any missing/failing criterion blocking qualification.
- [ ] Run `python -m pytest tests/research/qualification/test_service.py -q`. Expected failure: import of `QualificationService` fails.
- [ ] Implement:

```python
class QualificationService:
    def evaluate(self, input: QualificationInput) -> QualificationReport:
        results = tuple(
            CriterionResult(
                name=criterion.name,
                passed=self._evaluate_criterion(criterion, input),
            )
            for criterion in input.benchmark_policy.criteria
        )
        return QualificationReport(
            benchmark_policy_version=input.benchmark_policy.version,
            artifact_hash=input.artifact_hash,
            criteria=results,
            qualified=all(result.passed for result in results),
        )
```

- [ ] Define `CriterionResult(name: str, passed: bool)`, `QualificationInput(benchmark_policy: QualificationBenchmarkPolicy, artifact_hash: str, historical_reports: tuple[EvaluationReport, ...], stress_reports: tuple[EvaluationReport, ...], shadow_observations: int, shadow_stream_hash_match: bool, drill_results: Mapping[str, bool])`, `QualificationBenchmarkPolicy(version: str, criteria: tuple[QualificationCriterion, ...])`, `QualificationCriterion(name: str, source: Literal["historical", "stress", "shadow", "drill"], metric: str, comparison: Literal["minimum", "maximum", "required"], threshold: float | bool)`, and `QualificationReport(benchmark_policy_version: str, artifact_hash: str, criteria: tuple[CriterionResult, ...], qualified: bool)`. `QualificationService._evaluate_criterion(criterion, input) -> bool` handles these four fixed sources; APIs cannot supply executable predicates.
- [ ] `approve(report, actor, confirmation)` requires `report.qualified`, exact confirmation text containing artifact hash and benchmark policy version, and current state `BENCHMARK_QUALIFIED`; otherwise leave deterministic-only/shadow behavior unchanged.
- [ ] Document that code completion does not grant advisory status, business thresholds must be pre-registered externally, and advisory can remain disabled indefinitely.
- [ ] Run `python -m pytest tests/research/qualification/test_service.py tests/research/registry/test_service.py tests/research/serving/test_recommender.py -q`. Expected: all pass.
- [ ] Commit: `git add src/sneaker_market_maker/research/qualification tests/research/qualification docs/research && git commit -m "feat: enforce advisory qualification"`

### Task 26: Run the Complete Acceptance Suite

**Interfaces**

- Consumes: all prior deliverables; `Path` to the acceptance checklist.
- Produces: `verify_acceptance(checklist: Path) -> None`; reproducible local acceptance evidence.

**Files**

- Modify: `docs/compatibility/pfhedge-0.23.0.md`
- Create: `docs/research/acceptance-checklist.md`
- Create: `src/sneaker_market_maker/research/acceptance.py`
- Create: `tests/acceptance/test_acceptance_manifest.py`

- [ ] Add a test that calls `verify_acceptance(Path("docs/research/acceptance-checklist.md"))`, requires checked entries `AC-01` through `AC-14`, and requires nonempty `command`, `artifact`, and `result` values for each entry.
- [ ] Run `python -m pytest tests/acceptance/test_acceptance_manifest.py -q`. Expected failure: `ModuleNotFoundError: No module named 'sneaker_market_maker.research.acceptance'`.
- [ ] Implement the minimal verifier:

```python
def verify_acceptance(checklist: Path) -> None:
    text = checklist.read_text()
    for number in range(1, 15):
        criterion = f"AC-{number:02d}"
        if f"- [x] {criterion}" not in text:
            raise AssertionError(f"{criterion} is not checked")
        section = text.split(f"- [x] {criterion}", maxsplit=1)[1].split("- [x]", maxsplit=1)[0]
        for field in ("command:", "artifact:", "result:"):
            value = next(
                (line.split(field, maxsplit=1)[1].strip() for line in section.splitlines() if field in line),
                "",
            )
            if not value:
                raise AssertionError(f"{criterion} missing {field[:-1]}")
```

- [ ] Run `python -m ruff check src tests`.
- [ ] Run `python -m pytest -m "not integration" -q`. Expected: all unit/property/API/safety tests pass with network denied where specified.
- [ ] Run `docker compose -f docker-compose.test.yml up -d --wait && DATABASE_URL=postgresql+psycopg://research:research@localhost:55432/research_test alembic upgrade head && DATABASE_URL=postgresql+psycopg://research:research@localhost:55432/research_test python -m pytest -m integration -q`. Expected: compatibility and PostgreSQL integration tests pass.
- [ ] Run `docker compose -f docker-compose.test.yml down -v`.
- [ ] Run `cd frontend && npm ci && npm test && npm run typecheck && npm run build`. Expected: Vitest, TypeScript, and Vite succeed.
- [ ] Record command outputs, Python/Node/PostgreSQL versions, requirement hash, frontend lock hash, and git revision in `docs/research/acceptance-checklist.md`; check every one of the 14 approved acceptance criteria with a direct test/report link.
- [ ] Run `python -m pytest tests/acceptance/test_acceptance_manifest.py -q`. Expected: all pass.
- [ ] Verify `git diff --check` and inspect `git status --short`; only intended subsystem, dependency, migration, test, frontend, and documentation files may be present.
- [ ] Commit: `git add docs/compatibility docs/research && git commit -m "docs: record research acceptance evidence"`
