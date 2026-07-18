# Exercise the research pipeline

Contributor runbook: how to **test and feel** the offline research stack
(episodes → rewards → transitions → evaluation / IQL / PFHedge → registry →
serving → safety → Guided Demo / research UI).

**Not this doc:** Continuous Paper Market-Maker Ops / Strategy Modes — see
[`docs/paper-ops/`](../paper-ops/README.md).

**Related:** [junior walkthrough](./junior-walkthrough.md) (concepts),
[acceptance checklist](./acceptance-checklist.md) (AC evidence record),
[master overview](../MASTER.md).

---

## Prerequisites

```bash
cd /path/to/sneaker_market_maker
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

Frontend (for UI lab / Vitest):

```bash
cd frontend && npm ci               # or: npm install
```

**Always** pass `--import-mode=importlib` to pytest. Duplicate basenames
(`test_service.py` under registry vs transitions) break default import mode.

---

## 1. Five-minute smoke (no Docker)

**Research-focused smoke** (fast signal that the research tree still collects):

```bash
source .venv/bin/activate
.venv/bin/python -m pytest tests/research tests/safety tests/api/test_research_api.py \
  -q --import-mode=importlib -m "not integration"
```

**Full non-integration suite** (repo-wide, includes paper tests too):

```bash
.venv/bin/python -m pytest -m "not integration" -q --import-mode=importlib
```

**You’re done when:** pytest exits 0. Failures here block deeper work.

---

## 2. Layer ladder (command → what it proves)

Run from repo root with venv active. Prefer this order when debugging a broken
pipeline.

| Step | Command | Proves |
|------|---------|--------|
| Episodes | `.venv/bin/python -m pytest tests/research/episodes -q --import-mode=importlib` | 14-day schedules, material events, maintenance ticks |
| Rewards | `.venv/bin/python -m pytest tests/research/rewards -q --import-mode=importlib` | Fee-once NAV, terminal liquidation |
| Contracts / transitions | `.venv/bin/python -m pytest tests/research/contracts tests/research/transitions -q --import-mode=importlib` | Trainable transition completeness + persistence |
| Encoding | `.venv/bin/python -m pytest tests/research/encoding -q --import-mode=importlib` | State schema / encoder contracts |
| Evaluation | `.venv/bin/python -m pytest tests/research/evaluation -q --import-mode=importlib` | Walk-forward splits, harness policies, OPE fail-closed |
| IQL | `.venv/bin/python -m pytest tests/research/iql -q --import-mode=importlib` | Math, networks, trainer, training pipeline guards |
| PFHedge adapter (unit) | `.venv/bin/python -m pytest tests/research/pfhedge -q --import-mode=importlib` | Adapter wiring without Docker |
| Registry | `.venv/bin/python -m pytest tests/research/registry -q --import-mode=importlib` | Immutable lineage, promotion states |
| Qualification | `.venv/bin/python -m pytest tests/research/qualification -q --import-mode=importlib` | Human qualification gates |
| Serving | `.venv/bin/python -m pytest tests/research/serving -q --import-mode=importlib` | Shadow byte-identical paper stream; advisory bounds; Gate final |
| Demo service | `.venv/bin/python -m pytest tests/research/demo -q --import-mode=importlib` | Guided demo fixture state machine |
| Safety | `.venv/bin/python -m pytest tests/safety -q --import-mode=importlib` | Offline boundary + network deny |
| Research API | `.venv/bin/python -m pytest tests/api/test_research_api.py tests/api/test_local_demo_swagger.py -q --import-mode=importlib` | Local FastAPI research plane |

**PFHedge public-API pin** needs Docker (integration marker) — see §4.

---

## 3. Acceptance map (AC-01 … AC-14)

Authoritative recorded evidence: [`acceptance-checklist.md`](./acceptance-checklist.md)
(may cite an older git revision — re-run commands on current `main`).

| AC | Theme | Command (re-run) |
|----|--------|------------------|
| AC-01 | Episodes | `.venv/bin/python -m pytest tests/research/episodes/test_builder.py -q --import-mode=importlib` |
| AC-02 | Transition completeness | `.venv/bin/python -m pytest tests/research/contracts/test_transition.py tests/research/transitions/test_service.py -q --import-mode=importlib` |
| AC-03 | Fee-once rewards | `.venv/bin/python -m pytest tests/research/rewards/test_builder.py -q --import-mode=importlib` |
| AC-04 | IQL math / trainer | `.venv/bin/python -m pytest tests/research/iql -q --import-mode=importlib` |
| AC-05 | Logged actions + OPE | `.venv/bin/python -m pytest tests/research/evaluation/test_ope.py tests/research/iql/test_trainer.py -q --import-mode=importlib` |
| AC-06 | PFHedge 0.23.0 pin | Needs Docker — see §4 (`tests/compatibility/test_pfhedge_public_api.py`) |
| AC-07 | Shared evaluation harness | `.venv/bin/python -m pytest tests/research/evaluation/test_harness.py -q --import-mode=importlib` |
| AC-08 | Walk-forward / leakage | `.venv/bin/python -m pytest tests/research/evaluation/test_splits.py tests/research/evaluation/test_harness.py -q --import-mode=importlib` |
| AC-09 | Registry + serving | `.venv/bin/python -m pytest tests/research/registry/test_service.py tests/research/serving/test_recommender.py -q --import-mode=importlib` |
| AC-10 | Shadow stream identity | `.venv/bin/python -m pytest tests/research/serving/test_recommender.py::test_shadow_persists_comparisons_without_changing_full_paper_command_stream -q --import-mode=importlib` |
| AC-11 | Guided demo | `.venv/bin/python -m pytest tests/research/demo/test_service.py -q --import-mode=importlib` then `cd frontend && npm test -- GuidedDemo.test.tsx` |
| AC-12 | Safety / offline | `.venv/bin/python -m pytest tests/safety -q --import-mode=importlib` then `cd frontend && npm test -- offlineBoundary.test.tsx` |
| AC-13 | Docs separate PFHedge vs IQL | Manual doc review (see checklist) |
| AC-14 | Full mandatory gate | Ruff + non-integration pytest + Docker integration + frontend build (see checklist) |

---

## 4. Optional: Docker full acceptance

Required for AC-06 (PFHedge pin) and Postgres persistence integration.

```bash
docker compose -f docker-compose.test.yml up -d --wait

export DATABASE_URL=postgresql+psycopg://research:research@localhost:55432/research_test
alembic upgrade head

.venv/bin/python -m pytest -m integration -q --import-mode=importlib

# Explicit PFHedge pin (also selected by -m integration):
.venv/bin/python -m pytest tests/compatibility/test_pfhedge_public_api.py -q -m integration --import-mode=importlib

docker compose -f docker-compose.test.yml down -v
```

**You’re done when:** integration tests pass and the container is torn down.

---

## 5. UI lab (feel the research surfaces)

Backend (research fixtures + Swagger):

```bash
source .venv/bin/activate
uvicorn sneaker_market_maker.api.local_demo:app --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend && npm run dev
```

| URL | What to try |
|-----|-------------|
| http://127.0.0.1:5173/ | **Guided demo** — Pause / Resume / Step / Restart through six beats (fixture-only; no API required) |
| http://127.0.0.1:5173/?view=research | **Research comparison** — needs API; if API is down, UI fails closed to deterministic-only |
| http://127.0.0.1:8000/docs | Swagger for `/api/research/*` |
| http://127.0.0.1:8000/api/research/comparisons | Fixture JSON the research page consumes |

Frontend automated checks:

```bash
cd frontend
npm test
npm run typecheck
```

---

## 6. Not this pipeline

| Concern | Go here |
|---------|---------|
| Paper Ops golden replay / Strategy Modes | [`docs/paper-ops/`](../paper-ops/README.md) |
| Glossary | [`CONTEXT.md`](../../CONTEXT.md) |
| Concepts / math layers | [`junior-walkthrough.md`](./junior-walkthrough.md) |
| Recorded AC evidence | [`acceptance-checklist.md`](./acceptance-checklist.md) |

---

## Quick “green for research” checklist

1. [ ] Research smoke (§1) green  
2. [ ] Layer ladder (§2) green for the area you touched  
3. [ ] Matching ACs (§3) re-run if you changed that layer  
4. [ ] Docker (§4) if you touched persistence / PFHedge pin  
5. [ ] Guided Demo Step works; research page loads with API up (§5)  
