# Roadmap — Research↔Paper loop + Live readiness

**Status:** living roadmap (milestone phases; no calendar dates)  
**Product scope:** StockX-first **sneaker market-making** — paper Ops + offline learning + live readiness (not paper-only).  
**Progress (2026-07-18):** **Track R complete** (R0–R4). **L1 shipped.** Next: **L2** shadow would-quote → **L3** kill-switch / ADR-0004 (**live-send still off**).  
**Glossary:** [`CONTEXT.md`](../CONTEXT.md)  
**Formal slice spec:** [`superpowers/specs/2026-07-18-dual-track-roadmap.md`](superpowers/specs/2026-07-18-dual-track-roadmap.md)  
**Hard invariants:** Decimal money · Deterministic Gate final · no anti-bot / protection bypass · Product-Family Allowlist unless explicitly expanded · **no live-send without ADR-0004**

---

## Why two tracks

| Track | Goal |
|-------|------|
| **R — Research↔Paper loop** | Close the learning loop: paper fills → transitions → retrain IQL → registry qualify → bind **real** artifacts into Strategy Modes (done) |
| **L — Live readiness** | Observe/rehearse toward **live** market making (read-only data → shadow “would quote” → kill-switch). **Live-send only after Track R exit + ADR-0004** |

```text
Track R (paper/offline)                    Track L (parallel, no send until gate)
R0 ✅ ──► R1 ✅ ──► R2 ✅ ──► R3 ✅ ──► R4 ✅
                                              │
                paper-loop proven ────────────┼──► unlock L4 live-send (after ADR-0004)
L1 ✅ ──► L2 ──► L3 ──► (wait) ──► L4 ──► L5
```

---

## Track R — Research↔Paper loop

### R0 — Now (done)

Model-Integrated Paper Slice: Strategy Modes + Gate-final IQL; stub/port OK for acceptance.

**Exit:** shipped (see ADR-0003 + model-integrated spec).

### R1 — Paper → transition plumbing

Turn Continuous Paper Market-Maker decisions/fills into research-compatible `OfflineTransition` rows (fee-once rewards, past-only state, quarantine invalid).

**Exit criteria**

- [x] Paper run emits append-only transition candidates with lineage to run/tick/fill ids  
- [x] Invalid/incomplete rows quarantine fail-closed (not silent train)  
- [x] Golden/paper acceptance: ≥1 trainable batch from a seeded paper run  

**Candidate work items** (filed — see `.scratch/r1-paper-transition/issues/`) — **all done**

1. `01` Paper step effects capture ✅  
2. `02` Fee-once paper reward projection ✅  
3. `03` Paper→OfflineTransition assembler ✅  
4. `04` Persist + export-from-run command ✅  
5. `05` Acceptance: golden run → ≥1 trainable batch ✅

### R2 — Offline retrain on paper + historical mix

Retrain / fine-tune distributional IQL on paper-derived + historical transitions under frozen assumptions; evaluate with harness/OPE when valid.

**Exit criteria**

- [x] Train job consumes R1 artifacts + pinned historical mix  
- [x] EvaluationHarness report + registry `register` of new artifact  
- [x] Walk-forward / leakage controls unchanged (train-fold scaler, etc.)  

**Candidate work items** (filed — see `.scratch/r2-offline-retrain/issues/`)

1. `01` Mixed dataset manifest ✅  
2. `02` Offline IQL train job ✅  
3. `03` Walk-forward harness benchmark ✅  
4. `04` OPE validity gate (parallel with 05 after 03) ✅  
5. `05` Registry register artifact (parallel with 04 after 03) ✅ 

### R3 — Bind production artifacts in Ops (no stubs on happy path)

Ops Strategy Modes load registry-pinned real weights + encoder; stubs remain test-only.

**Exit criteria**

- [x] `advisory` / `iql_primary` happy path uses real registry artifact  
- [x] Encoder/schema mismatch fail-closed  
- [x] Acceptance: golden replay + real (or CI-pinned small) artifact proves nudge/pause under Gate  

**Candidate work items** (filed — see `.scratch/r3-ops-bind/issues/`)

1. `01` Registry artifact → inference bind ✅  
2. `02` Ops projection of bound model ✅  
3. `03` Happy path: no stub on advisory / iql_primary ✅  
4. `04` Qualification + latency on real infer (parallel with 02/03 after 01) ✅  
5. `05` Golden acceptance + bind/qualify runbook ✅  

### R4 — Promotion UX + optional PFHedge paper mode

Richer registry promotion UX; optional PFHedge as a later paper Strategy Mode (ADR if needed).

**Exit criteria**

- [x] Operator can see promote/qualify path without only using research comparison  
- [x] PFHedge paper mode either explicitly deferred with reason or shipped behind ADR + Gate-final  

**Candidate work items** (filed — see `.scratch/r4-promotion-ux/issues/`)

1. `01` Ops promote / qualify command ✅  
2. `02` Promote path on Ops projections ✅  
3. `03` PFHedge paper mode decision (parallel with 01) ✅ — deferred: [`adr/0005`](adr/0005-pfhedge-paper-mode-deferred.md)  
4. `04` Gate / qty-one regression after promote ✅  

---

## Track L — Live readiness (parallel)

### L1 — Read-only market data port

StockX-shaped **read-only** market observations; Product-Family Allowlist preserved; no order API.

**Exit criteria**

- [x] Port delivers allowlisted snapshots/events without credentials that can place orders  
- [x] Fail-closed on corrupt payloads (same spirit as `SneakerDataPipeline`)  
- [x] Safety tests: no send client in tree for this port  

**Candidate work items** (filed — see `.scratch/l1-readonly-market/issues/`)

1. `01` Read-only observation port + allowlist ✅  
2. `02` Fail-closed corrupt payload ingest ✅  
3. `03` Safety: no send client in port tree (parallel with 02 after 01) ✅  
4. `04` L1 acceptance fixture + observe docs ✅  

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
| [`adr/0005-pfhedge-paper-mode-deferred.md`](adr/0005-pfhedge-paper-mode-deferred.md) | R4: PFHedge stays research-only |
| [`observe/README.md`](observe/README.md) | L1 read-only observe port |
| [`paper-ops/bind-qualify-runbook.md`](paper-ops/bind-qualify-runbook.md) | Promote / bind / qualify Ops path |
| [`superpowers/specs/2026-07-18-model-integrated-paper-slice.md`](superpowers/specs/2026-07-18-model-integrated-paper-slice.md) | R0 done slice |
| [`superpowers/specs/2026-07-18-dual-track-roadmap.md`](superpowers/specs/2026-07-18-dual-track-roadmap.md) | Dual-track PRD (Track R done; L1 done) |
