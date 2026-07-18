# Roadmap — Research↔Paper loop + Live readiness

**Status:** living roadmap (milestone phases; no calendar dates)  
**Glossary:** [`CONTEXT.md`](../CONTEXT.md)  
**Formal slice spec:** [`superpowers/specs/2026-07-18-dual-track-roadmap.md`](superpowers/specs/2026-07-18-dual-track-roadmap.md)  
**Hard invariants:** Decimal money · Deterministic Gate final · no anti-bot / protection bypass · Product-Family Allowlist unless explicitly expanded · **no live-send without ADR-0004**

---

## Why two tracks

| Track | Goal |
|-------|------|
| **R — Research↔Paper loop** | Close the loop: paper fills → transitions → retrain IQL → registry qualify → bind **real** artifacts into Ops Strategy Modes |
| **L — Live readiness** | Parallel observe/rehearse work (read-only data, shadow “would quote”, kill-switch design). **Live-send only after Track R exit criteria + ADR-0004** |

```text
Track R (paper/offline)          Track L (parallel, no send until gate)
R0 done ──► R1 ──► R2 ──► R3 ──► R4
                │
                └── paper-loop proven ──► unlock L4 live-send (after ADR-0004)
L1 ──► L2 ──► L3 ──► (wait) ──► L4 ──► L5
```

---

## Track R — Research↔Paper loop

### R0 — Now (done)

Model-Integrated Paper Slice: Strategy Modes + Gate-final IQL; stub/port OK for acceptance.

**Exit:** shipped (see ADR-0003 + model-integrated spec).

### R1 — Paper → transition plumbing

Turn Continuous Paper Market-Maker decisions/fills into research-compatible `OfflineTransition` rows (fee-once rewards, past-only state, quarantine invalid).

**Exit criteria**

- [ ] Paper run emits append-only transition candidates with lineage to run/tick/fill ids  
- [ ] Invalid/incomplete rows quarantine fail-closed (not silent train)  
- [ ] Golden/paper acceptance: ≥1 trainable batch from a seeded paper run  

**Candidate work items** (illustrative — file via `/to-tickets` when starting R1)

1. Paper→research adapter for Paper Decision State / effects → transition input  
2. Fee-once reward projection from paper capital/lots ledger  
3. Content-hash quarantine + Postgres/research repo persistence  
4. Ops/research command or job to “export transitions from run X”  
5. Acceptance test at Paper Ops + transition repository seams  

### R2 — Offline retrain on paper + historical mix

Retrain / fine-tune distributional IQL on paper-derived + historical transitions under frozen assumptions; evaluate with harness/OPE when valid.

**Exit criteria**

- [ ] Train job consumes R1 artifacts + pinned historical mix  
- [ ] EvaluationHarness report + registry `register` of new artifact  
- [ ] Walk-forward / leakage controls unchanged (train-fold scaler, etc.)  

**Candidate work items**

1. Dataset manifest joining paper + historical transitions  
2. Train entrypoint with frozen assumption hash  
3. Benchmark vs deterministic / prior IQL under harness  
4. OPE validity gate (no fabricated WIS when support fails)  
5. Checkpoint/safetensors register into RegistryService  

### R3 — Bind production artifacts in Ops (no stubs on happy path)

Ops Strategy Modes load registry-pinned real weights + encoder; stubs remain test-only.

**Exit criteria**

- [ ] `advisory` / `iql_primary` happy path uses real registry artifact  
- [ ] Encoder/schema mismatch fail-closed  
- [ ] Acceptance: golden replay + real (or CI-pinned small) artifact proves nudge/pause under Gate  

**Candidate work items**

1. Production inference binding from registry artifact id  
2. Ops projection: model id, state, encoder/translator versions  
3. Remove stub from default demo path (keep injectable port for tests)  
4. Latency budget + qualification checks against real infer  
5. Docs: operator bind/qualify runbook  

### R4 — Promotion UX + optional PFHedge paper mode

Richer registry promotion UX; optional PFHedge as a later paper Strategy Mode (ADR if needed).

**Exit criteria**

- [ ] Operator can see promote/qualify path without only using research comparison  
- [ ] PFHedge paper mode either explicitly deferred with reason or shipped behind ADR + Gate-final  

**Candidate work items**

1. Thin promotion/qualification controls on Ops or dedicated surface  
2. Audit promote decisions  
3. PFHedge paper mode spike doc / ADR decision  
4. Regression: Gate still final; qty-one unchanged  

---

## Track L — Live readiness (parallel)

### L1 — Read-only market data port

StockX-shaped **read-only** market observations; Product-Family Allowlist preserved; no order API.

**Exit criteria**

- [ ] Port delivers allowlisted snapshots/events without credentials that can place orders  
- [ ] Fail-closed on corrupt payloads (same spirit as `SneakerDataPipeline`)  
- [ ] Safety tests: no send client in tree for this port  

### L2 — Shadow live (“would quote”)

Log what Strategy Mode **would** quote against live/read-only book; never send; compare optionally to paper.

**Exit criteria**

- [ ] Shadow log reconstructible (intent, gate result, reason)  
- [ ] Byte-proof: no marketplace order endpoint called  
- [ ] Operator can start/stop shadow observe without affecting paper capital  

### L3 — Kill-switch + runbooks + ADR-0004

Human kill-switch design, ops runbooks, and **ADR-0004** (live adapter + Gate-final + no protection bypass + kill-switch) **before any live-send**.

**Exit criteria**

- [ ] ADR-0004 accepted  
- [ ] Kill-switch behavior specified and testable in dry-run  
- [ ] Runbook: who may enable send, allowlist, capital caps, incident stop  

### L4 — Tiny allowlisted live-send (human gated)

Only after **Track R paper-loop exit** (at least R1–R3 proven) **and** L3/ADR-0004.

**Exit criteria**

- [ ] Human-gated enable; default off  
- [ ] Qty-one / allowlist / Gate-final on live intents  
- [ ] Immediate kill-switch stops new sends  

### L5 — Expand carefully

Widen products/capital/modes only with explicit allowlist/ADR updates.

---

## Cross-cutting non-goals (until explicitly reopened)

- Live-send without ADR-0004  
- Ungated model trading  
- Anti-bot / CAPTCHA / protection bypass  
- Treating Synthetic Scenario / GBM as historical execution proof  
- Float money in capital ledgers  
- Auto-filing every candidate item as GitHub issues (use `/to-tickets` per phase)

---

## Related docs

| Doc | Role |
|-----|------|
| [`MASTER.md`](MASTER.md) | Product front door |
| [`adr/0001`](adr/0001-golden-historical-replay-for-v1.md)–[`0003`](adr/0003-iql-strategy-modes-gate-final.md) | Replay, deterministic-first, Gate-final IQL |
| [`superpowers/specs/2026-07-18-model-integrated-paper-slice.md`](superpowers/specs/2026-07-18-model-integrated-paper-slice.md) | R0 done slice |
| [`superpowers/specs/2026-07-18-dual-track-roadmap.md`](superpowers/specs/2026-07-18-dual-track-roadmap.md) | Agent-ready roadmap spec |
