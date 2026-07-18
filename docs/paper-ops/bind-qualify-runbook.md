# Operator runbook — bind & qualify a registry artifact for Paper Ops

**Audience:** operators closing the research↔paper loop  
**Glossary:** [`CONTEXT.md`](../../CONTEXT.md)  
**ADRs:** [`0003`](../adr/0003-iql-strategy-modes-gate-final.md) (Gate final)  
**Roadmap:** R3 in [`ROADMAP.md`](../ROADMAP.md)

This runbook covers **pin → qualify (registry state) → bind → set mode**. Live-send is out of scope (Track L / ADR-0004).

## Prerequisites

- Paper Ops Control Plane running (local demo or equivalent)
- A safetensors IQL checkpoint whose `CompatibilityContract` matches Ops:
  - `state_schema_version` = `paper-decision-v1`
  - `action_schema_version` = `action-translator-v1`
  - `encoder_version` = `paper-decision-encoder-v1`
  - `architecture` = `distributional_iql_v1`
- Registry state that authorizes the mode you want:
  - `advisory` → `advisory_approved`
  - `iql_primary` → `benchmark_qualified` or `advisory_approved`
  - `deterministic` → always available (no qualification)

## Bind (happy path)

### Local demo

`create_demo_app()` already binds the **CI-pinned** artifact under
`data/paper/artifacts/iql_ci_v1` as `advisory_approved`. Open Ops and use
`set-mode` → `advisory` or `iql_primary`.

### REST command

```http
POST /api/paper/commands/bind-model
Idempotency-Key: bind-<unique>
```

**CI pin (recommended for smoke):**

```json
{
  "model_id": "ops-iql-1",
  "registry_state": "advisory_approved",
  "use_ci_pin": true
}
```

**Explicit checkpoint** (directory must include `ops_lineage.json` sidecar):

```json
{
  "model_id": "ops-iql-1",
  "registry_state": "advisory_approved",
  "checkpoint_dir": "/path/to/checkpoint"
}
```

Success emits `strategy.model_bound`. Failure emits `strategy.bind_rejected` and returns HTTP 400 (fail closed — no silent quote).

## Verify projections

`GET /api/paper/status` → `registry` should show:

| Field | Meaning |
|-------|---------|
| `model_id` | Bound model identity |
| `state` | Registry qualification state |
| `artifact_hash` | Checkpoint tensor hash |
| `encoder_version` | Paper decision encoder |
| `state_schema_version` | Must be `paper-decision-v1` |
| `action_translator_version` | Must be `action-translator-v1` |

Unbound / stub-only sessions leave version fields `null` (no invented lineage).

## Qualify & set mode

1. Ensure registry state matches the mode (above).
2. `POST …/set-mode` with `{"mode":"advisory"}` or `{"mode":"iql_primary"}`.
3. Rejected → `strategy.mode_rejected` / HTTP 400 (`not_qualified`). Session stays on prior mode.
4. Pin latency: `POST …/set-budget` with `{"limit_ms": 100}` (ceiling 250).

## Fail-closed behaviours

| Condition | Effect |
|-----------|--------|
| Encoder / schema / translator mismatch at bind | Bind rejected; mode unchanged |
| No inference port in model mode | Advisory falls back to deterministic; `iql_primary` pauses |
| Latency over budget | Same as invalid inference (`timeout`) |
| Gate rejection | Order not sent; Gate remains final |
| Bind outage | Use `deterministic` (always available) |

## Audit trail

Look for (in order): `strategy.model_bound` → `strategy.mode_changed` → `market.tick` / fill events. Reconstruct with [`auditor-reconstructibility.md`](./auditor-reconstructibility.md).
