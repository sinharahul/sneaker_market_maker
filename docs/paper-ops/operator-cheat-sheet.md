# Operator cheat sheet — Paper Ops

Run and control the Continuous Paper Market-Maker. Projections from `/api/paper`
are authoritative — the UI does not invent book state.

**Glossary:** [`CONTEXT.md`](../../CONTEXT.md)  
**Siblings:** [junior E2E](./junior-e2e-flow.md),
[auditor reconstructibility](./auditor-reconstructibility.md),
[bind/qualify runbook](./bind-qualify-runbook.md)  
**Roadmap:** Track R closed; demo binds CI-pinned IQL ([ROADMAP](../ROADMAP.md)).

---

## Start locally

```bash
source .venv/bin/activate
uvicorn sneaker_market_maker.api.local_demo:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend && npm run dev
```

| Surface | URL |
|---------|-----|
| **Ops Dashboard** | http://127.0.0.1:5173/?view=ops |
| Guided demo (not Ops) | http://127.0.0.1:5173/ |
| Research comparison (not Ops) | http://127.0.0.1:5173/?view=research |
| Swagger | http://127.0.0.1:8000/docs |

Loopback only. Local demo session already binds the CI-pinned IQL artifact as
`advisory_approved` — you can set `advisory` / `iql_primary` without a manual bind.

---

## Typical golden session (Ops UI)

1. **Load golden replay**
2. **Start**
3. **Enable strategy**
4. Optional: **Mode: advisory** or **iql_primary** (demo is pre-qualified)
5. **Tick** (repeat) — watch orders / fills / lots / cash / P&L
6. Optional: **Pause** / **Resume** / **Stop**

Status should show `Strategy Mode: deterministic` unless you change it.

---

## REST commands

`POST /api/paper/commands/{command}` with header `Idempotency-Key` (required).
Same key + same JSON body → same result; same key + different body → `409`.

| Command | Body (typical) | Effect |
|---------|----------------|--------|
| `load` | `{"seed": 7, "speed": 1}` | Load golden_v1; returns `run_id` |
| `start` | `{}` | Replay RUNNING |
| `pause` | `{}` | Operator pause (`pause_reason=operator`) |
| `resume` | `{}` | Resume if allowed (see IQL pause) |
| `stop` | `{}` | Stop / reset cursor |
| `enable` | `{}` | Strategy on |
| `disable` | `{}` | Strategy off; cancel actives through Gate |
| `tick` | `{}` | Advance replay; quote / match |
| `set-mode` | `{"mode": "deterministic"\|"advisory"\|"iql_primary"}` | Strategy Mode (qualification enforced) |
| `set-budget` | `{"limit_ms": 100}` | Inference Latency Budget (default 100, max 250) |
| `bind-model` | `{"use_ci_pin": true}` or `checkpoint_dir` | Bind real IQL checkpoint + lineage |
| `promote-model` | `{"model_id","target","actor","reason"}` | One legal registry edge (needs attached registry) |
| `export-from-run` | `{}` or `{"run_id"}` | Export paper checkpoints → OfflineTransitions |
| `cancel` | side / product_family / … | Manual cancel intent through Gate |

### Reads

`GET /api/paper/{resource}` for `status`, `capital`, `orders`, `fills`, `lots`,
`pnl`, `replay`, `transitions`.

Events: WebSocket `/api/paper/events?after=0`.

---

## Strategy Mode controls (Ops UI)

Buttons: **Mode: deterministic** | **advisory** | **iql_primary**.

Read from status (do not assume local UI state):

- `strategy_mode`
- `registry.model_id` / `registry.state` / `registry.artifact_hash`
- `registry.encoder_version` / `registry.action_translator_version`
- `registry.unlocked_modes`
- `last_promote` (actor / reason / source → target)
- `inference_latency_budget_ms`
- `fallback_reason` (advisory tick fallback)
- `pause_reason` (`operator` vs `iql_unavailable`)
- `last_iql_action` summary

**Qualification:** `advisory` / `iql_primary` require registry state (see table).
Unqualified attempts return `400` and **do not** change mode. Full promote/bind
steps: [bind-qualify-runbook.md](./bind-qualify-runbook.md).

| Mode | Registry requirement |
|------|----------------------|
| `deterministic` | None |
| `advisory` | `advisory_approved` |
| `iql_primary` | `benchmark_qualified` or `advisory_approved` |

---

## When replay shows “paused (IQL unavailable)”

1. Confirm status: `pause_reason == iql_unavailable`, `strategy_mode == iql_primary`.
2. **Do not** expect silent deterministic quoting while mode stays `iql_primary`.
3. Recover either:
   - Switch to **Mode: deterministic**, then **Resume**, then continue ticking, or
   - Restore healthy IQL (re-bind / fix latency), then **Resume**.
4. Operator **Pause** is labeled **paused (operator)** — different reason.

Resume while still `iql_primary` and IQL unhealthy → command fails (`400`).

---

## Fail-closed reminders

- Gate rejects stay rejected; open book does not mutate on reject.
- Ask without available Inventory Lot is withheld / fails at Gate.
- Paper Capital reserve/cash rules apply in every Strategy Mode.
- Idempotency keys prevent double-click thrash on mode/budget.
- Encoder / schema mismatch at bind fails closed (no silent quote).
