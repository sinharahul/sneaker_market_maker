# Sneaker Market Maker

Fee-aware analytics and an **offline** research stack for sneaker secondary-market
paper trading (StockX-first). The system normalizes marketplace-shaped
observations, prices transaction friction in `Decimal`, rejects trades that
violate risk limits, builds Bellman-ready transitions, and compares policies
(deterministic / heuristic / MLP / **PFHedge** baseline / **distributional IQL**).

Recommendations are gated by deterministic risk rules. **Shadow** mode never
changes the paper command stream; **advisory** requires explicit human
qualification. This project does **not** bypass marketplace protections or place
live orders.

| Layer | What it does |
|-------|----------------|
| Analytics core | `FeeSchedule`, `OpportunityEvaluator`, GBM stress paths |
| Research | Episodes → rewards → transitions → IQL / PFHedge → evaluation / OPE |
| Governance | Registry, qualification, shadow/advisory recommender |
| Local UI | Guided 5-minute demo + research comparison page |

Python **3.10–3.12**. Docs: [junior walkthrough](docs/research/junior-walkthrough.md),
[quantitative context](docs/research/QUANTITATIVE_CONTEXT.md),
[acceptance checklist](docs/research/acceptance-checklist.md).

---

## Setup

### Python

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

Optional: `pip install -e ".[dev]"` if you prefer the pyproject extra (same pins).

### Frontend

```bash
cd frontend
npm ci                             # or: npm install
```

Node **18+** recommended.

---

## Quick analytics example

```python
from decimal import Decimal

from sneaker_market_maker import (
    FeeSchedule,
    OpportunityEvaluator,
    SneakerDataPipeline,
)

payload = {
    "platform": "stockx",
    "styleCode": "DD1391-100",
    "shoeSize": 10,
    "highestBid": 100,
    "lowestAsk": 150,
    "daysSinceRelease": 100,
    "recentSales": [{"price": 140}, {"price": 145}, {"price": 150}],
}

snapshot, _ = SneakerDataPipeline().parse_payload(payload)
fees = FeeSchedule(
    seller_rate=Decimal("0.10"),
    processor_rate=Decimal("0.03"),
    inbound_shipping=Decimal("8"),
    outbound_shipping=Decimal("2"),
)
print(OpportunityEvaluator(fees).evaluate(snapshot))
```

---

## Demo

Two pages share one Vite frontend. The guided story is browser-only; the research
comparison page needs the Python API.

### 1. Start the Python backend (research UI + Swagger)

```bash
source .venv/bin/activate
uvicorn sneaker_market_maker.api.local_demo:app --host 127.0.0.1 --port 8000
```

| URL | Purpose |
|-----|---------|
| **http://127.0.0.1:8000/docs** | Swagger UI |
| **http://127.0.0.1:8000/redoc** | ReDoc |
| **http://127.0.0.1:8000/openapi.json** | OpenAPI schema |
| **http://127.0.0.1:8000/api/research/comparisons** | Fixture JSON for `/?view=research` |

Loopback only. Do not expose without auth.

### 2. Start the React frontend

```bash
cd frontend
npm run dev
```

Vite proxies `/api/*` → `http://127.0.0.1:8000`.

| Page | URL | Data source |
|------|-----|-------------|
| Guided demo | **http://127.0.0.1:5173/** | Hard-coded TS fixtures (`demoService.ts`) — Python optional |
| Research comparison | **http://127.0.0.1:5173/?view=research** | Python `GET /api/research/comparisons` |

If the API is down, the research page fails closed to **deterministic-only** (no
optimistic promotion).

| Control (guided demo) | Behavior |
|-----------------------|----------|
| **Pause / Resume** | Freeze or auto-advance beats |
| **Step** | Advance exactly one beat |
| **Restart** | Back to `healthy_spread` at t = 0 |

---

## Test

Use `--import-mode=importlib` so duplicate test module basenames
(`test_service.py` under registry vs transitions) collect cleanly.

### Unit / property / API / safety (no Docker)

```bash
source .venv/bin/activate
python -m pytest -m "not integration" -q --import-mode=importlib
```

Focused suites:

```bash
python -m pytest tests/research/iql -q --import-mode=importlib
python -m pytest tests/research/serving tests/research/registry -q --import-mode=importlib
python -m pytest tests/safety -q --import-mode=importlib
python -m pytest tests/api -q --import-mode=importlib
python -m pytest tests/acceptance -q --import-mode=importlib
```

### Frontend

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

### Integration (Postgres + Alembic + PFHedge pin check)

Requires Docker:

```bash
docker compose -f docker-compose.test.yml up -d --wait

export DATABASE_URL=postgresql+psycopg://research:research@localhost:55432/research_test
alembic upgrade head
python -m pytest -m integration -q --import-mode=importlib

docker compose -f docker-compose.test.yml down -v
```

### Lint

```bash
python -m ruff check src tests
```

---

## Repository layout

```text
src/sneaker_market_maker/
  core.py, pipeline.py, simulation.py   # analytics core
  research/                             # episodes, IQL, PFHedge, registry, serving
  persistence/                          # Postgres / in-memory transition store
  api/                                  # local FastAPI research plane
frontend/                               # Vite + React guided demo
docs/research/                          # walkthrough, context, acceptance
tests/                                  # unit, integration, safety, acceptance
```

---

## Design choices

- Money and fees use **`Decimal`** / PostgreSQL `NUMERIC`; tensors only at named ML boundaries.
- Invalid payloads and non-finite model outputs **fail closed**.
- Deterministic gates stay authoritative after any model suggestion.
- PFHedge is a **direct-hedging baseline**, not the Bellman/IQL engine.
- Synthetic stress (GBM) never counts as historical holdout evidence.
- No live marketplace clients, anti-bot bypass, or unsafe `pickle` checkpoints
  (safetensors only for IQL weights).

---

## Further reading

- [Junior developer walkthrough](docs/research/junior-walkthrough.md) — end-to-end how it works + math  
- [Quantitative context document](docs/research/QUANTITATIVE_CONTEXT.md) — architecture blueprint  
- [Advisory qualification](docs/research/advisory-qualification.md) — why code ≠ advisory approval  
- [PFHedge 0.23.0 compatibility](docs/compatibility/pfhedge-0.23.0.md)  
- [Acceptance checklist AC-01…AC-14](docs/research/acceptance-checklist.md)
