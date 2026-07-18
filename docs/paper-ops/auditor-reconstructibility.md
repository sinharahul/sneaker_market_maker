# Auditor reconstructibility — Paper Ops

How to reconstruct Strategy Mode influence, Gate outcomes, and capital changes
from append-only events and status projections — without trusting the UI.

**Glossary:** [`CONTEXT.md`](../../CONTEXT.md)  
**Siblings:** [junior E2E](./junior-e2e-flow.md),
[operator cheat sheet](./operator-cheat-sheet.md)

---

## Authoritative surfaces

| Surface | Role |
|---------|------|
| `GET /api/paper/status` | Current mode, pause/fallback, registry, budget, last IQL summary, capital/pnl snapshot |
| `GET /api/paper/orders` / `fills` / `lots` / `capital` / `pnl` / `replay` | Book read models |
| WebSocket `/api/paper/events` | Ordered envelopes (`sequence`, `event_type`, `payload`, times) |
| Store audit (when run persisted) | Same logical event stream via paper store |

Money fields are **Decimal strings** in projections — not floats.

---

## Status projection fields (mode / IQL)

| Field | Meaning |
|-------|---------|
| `strategy_mode` | `deterministic` \| `advisory` \| `iql_primary` |
| `registry.model_id` | Bound research model id (or null) |
| `registry.state` | Registry state used for Model Qualification (or null) |
| `registry.artifact_hash` | Bound checkpoint hash when lineage present |
| `registry.encoder_version` / `state_schema_version` / `action_translator_version` | Compatibility lineage (null if unbound/stub) |
| `registry.unlocked_modes` | Strategy Modes the current registry state authorizes |
| `last_promote` | Last successful promote (`actor`, `reason`, `source`, `target`) or null |
| `inference_latency_budget_ms` | Pinned Inference Latency Budget |
| `pause_reason` | `null` \| `operator` \| `iql_unavailable` |
| `fallback_reason` | Advisory tick fallback code (e.g. `timeout`); null if none |
| `last_iql_action` | Last summarized HybridAction (`category`, tick offsets, `source`) or null |
| `replay.status` | `empty` \| `loaded` \| `running` \| `paused` \| `stopped` |
| `strategy_enabled` | Quote engine enabled flag |
| `audit_sequence` | Count of emitted envelopes |

**Distinguish pauses:** `replay.status == paused` alone is not enough — read
`pause_reason`.

---

## Audit `event_type` catalog (paper session)

### Replay / strategy lifecycle

| `event_type` | When |
|--------------|------|
| `replay.loaded` | Golden dataset loaded (`dataset_id` in payload) |
| `replay.started` | Clock running |
| `replay.paused` | Operator pause (`reason: operator`) |
| `replay.resumed` | Clock resumed |
| `replay.stopped` | Stopped |
| `replay.ticked` | Tick completed (`events`, `event_ids`) |
| `replay.paused_iql` | IQL-primary unavailability pause (`reason`) |
| `strategy.enabled` | Strategy enabled |
| `strategy.disabled` | Strategy disabled / actives cancelled |
| `order.cancel` | Manual cancel command path |

### Mode / inference

| `event_type` | When |
|--------------|------|
| `strategy.mode_set` | Mode accepted (`mode`, `changed`, registry fields) |
| `strategy.mode_rejected` | Qualification refuse (`mode`, `code`, `registry_state`) — **mode unchanged** |
| `inference.budget_set` | Latency budget pinned (`limit_ms`) |
| `inference.budget_rejected` | Invalid budget (e.g. above ceiling) |
| `strategy.advisory_fallback` | Advisory used deterministic base (`reason`) |
| `strategy.model_bound` | Real/CI checkpoint bound (lineage fields) |
| `strategy.bind_rejected` | Fail-closed bind (schema/encoder mismatch, …) |
| `strategy.model_promoted` | Registry promote succeeded (`actor`, `reason`, `source`, `target`) |
| `strategy.promote_rejected` | Illegal or incomplete promote |
| `transitions.exported` | Paper checkpoints exported to OfflineTransitions |

---

## Reconstruct common stories

### Deterministic golden fill

1. `replay.loaded` → `replay.started` → `strategy.enabled`
2. One or more `replay.ticked`
3. Status: `strategy_mode=deterministic`, `pause_reason=null`, fills/lots ≥ 1,
   capital cash ≠ initial
4. Confirm **no** `strategy.advisory_fallback` / `replay.paused_iql` required

### Advisory fallback (late IQL)

1. `strategy.mode_set` with `mode=advisory` (after qualified bind)
2. `replay.ticked` accompanied by `strategy.advisory_fallback` (`reason` e.g. `timeout`)
3. Status: `fallback_reason` set, `pause_reason=null`, `replay.status=running`
4. Orders show **deterministic-base** prices for that tick (not nudged)

### IQL-primary pause and recovery

1. `strategy.mode_set` with `mode=iql_primary`
2. On invalid/late: `replay.paused_iql` then `replay.status=paused`,
   `pause_reason=iql_unavailable`
3. No accepted IQL-authored orders for the failing tick (no silent substitute)
4. Recovery A: `strategy.mode_set` → `deterministic` (pause_reason becomes
   `operator`) → `replay.resumed` → further `replay.ticked`
5. Recovery B: healthy IQL restored → `replay.resumed` while still
   `iql_primary` → `replay.ticked` with `last_iql_action` populated

### Unqualified mode attempt

1. `strategy.mode_rejected` with `code=not_qualified`
2. Following status still shows previous `strategy_mode` (usually `deterministic`)

---

## Gate and money invariants (checks)

- Every Quote Intent path still evaluates the Deterministic Gate; rejected
  intents must not leave capital/lot mutations as if accepted.
- Paper Orders remain quantity **one**.
- Fee-Aware Fill projections expose quote/execution/fees/source event id.
- Inventory-backed ask: no sell without an available Inventory Lot.
- Paper Capital: initial \$2,500; open-buy principal cap \$1,500 of initial.

---

## Related tests (living examples)

- `tests/api/test_paper_ops_api.py` — golden deterministic control plane
- `tests/api/test_paper_ops_strategy_modes.py` — advisory / iql_primary / pause / recover
- `tests/api/test_paper_ops_set_mode_budget.py` — mode/budget idempotency + reject
- `tests/api/test_paper_ops_deterministic_mode.py` — deterministic never calls IQL
- `tests/api/test_paper_ops_r3_bind.py` — CI-pinned real artifact bind / Gate
- `tests/api/test_paper_ops_r4_promote.py` — promote path + qty-one regression
- `tests/observe/` + `tests/safety/test_observe_no_send.py` — L1 observe (no send)
