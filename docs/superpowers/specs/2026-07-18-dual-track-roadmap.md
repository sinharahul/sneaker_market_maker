# Dual-Track Roadmap — Research↔Paper Loop + Live Readiness

**Date:** 2026-07-18  
**Status:** Track R **complete** (R0–R4); L1 **shipped**; L2–L5 open — living progress in `docs/ROADMAP.md`  
**Glossary:** `CONTEXT.md`  
**ADRs:** `docs/adr/0001-golden-historical-replay-for-v1.md`, `docs/adr/0002-deterministic-first-paper-mm.md`, `docs/adr/0003-iql-strategy-modes-gate-final.md`, `docs/adr/0005-pfhedge-paper-mode-deferred.md`  
**Living roadmap:** `docs/ROADMAP.md`  
**Depends on:** First Shippable Slice + Model-Integrated Paper Slice (R0 done)  
**Parent design:** `docs/superpowers/specs/2026-07-17-market-maker-dashboard-design.md` (scoped to research loop + live readiness; not full §11)

## Problem Statement

Paper Ops and research both shipped Strategy Modes and offline IQL, but the loop was weakly closed: paper experience did not reliably become training data that retrained and re-bound **real** registry artifacts into Ops. Separately, live readiness needed a gated track so observe/rehearse work could proceed without implying order send. This dual-track roadmap closed that gap.

## Solution

Execute two parallel tracks. **Track R** (now complete) closes the research↔paper loop: paper → OfflineTransition plumbing → offline retrain/evaluate → registry qualify/promote → bind real artifacts into Strategy Modes (PFHedge paper mode deferred — ADR-0005). **Track L** builds live **readiness** in parallel (L1 read-only observe shipped; next shadow “would quote”, kill-switch + runbooks) but **forbids live-send** until Track R paper-loop exit criteria are met and **ADR-0004** (live adapter + Gate-final + no protection bypass + kill-switch) is accepted. Milestone phases use exit criteria and candidate work items; calendar dates are omitted. Hard invariants stay: Decimal money, Deterministic Gate final, Product-Family Allowlist, no anti-bot bypass.

## User Stories

### Track R — Research↔Paper loop

1. As a researcher, I want paper fills and quote decisions exported as OfflineTransition candidates, so that paper experience becomes training data.
2. As a researcher, I want fee-once rewards on paper-derived transitions, so that IQL does not learn fantasy gross-spread edge.
3. As a researcher, I want invalid paper→transition rows quarantined, so that incomplete accounting cannot enter training.
4. As a researcher, I want lineage from transition to paper run/tick/fill ids, so that training rows are auditable.
5. As a researcher, I want a seeded golden/paper run to produce at least one trainable batch, so that R1 is acceptance-proven.
6. As a researcher, I want to retrain distributional IQL on a pinned mix of paper and historical transitions, so that models improve from closed-loop data.
7. As a researcher, I want FrozenAssumptions hashed on retrain jobs, so that evaluation worlds stay comparable.
8. As a researcher, I want EvaluationHarness reports for the new artifact vs baselines, so that promotion is evidence-based.
9. As a researcher, I want OPE to return OPE_NOT_VALID when support fails, so that we never fabricate policy value.
10. As a researcher, I want the new checkpoint registered in RegistryService, so that lineage is immutable.
11. As an operator, I want Ops Strategy Modes to bind a real registry artifact on the happy path, so that stubs are test-only.
12. As an operator, I want encoder/schema mismatch to fail closed, so that incompatible models cannot quote.
13. As an operator, I want projections showing model id, registry state, encoder and Action Translator versions, so that I know what is bound.
14. As an operator, I want `advisory` nudge and `iql_primary` pause semantics preserved with real weights, so that Gate-final behavior does not regress.
15. As an operator, I want Model Qualification still enforced for mode entry, so that unqualified models cannot author paper quotes.
16. As an operator, I want Inference Latency Budget still applied to real inference, so that late models fail closed.
17. As a researcher, I want promotion/qualification visible without only using research comparison, so that Ops can complete the loop.
18. As a researcher, I want promote decisions audited, so that who qualified what is reconstructible.
19. As a researcher, I want PFHedge paper Strategy Mode either deferred with an explicit reason or added only behind an ADR and Gate-final rules, so that baselines do not silently become live paper authors.
20. As a developer, I want R1 acceptance at Paper Ops Control Plane + transition repository seams, so that export is proven without UI-only proof.
21. As a developer, I want the IQL inference port to remain injectable, so that CI can stub while production binds real artifacts.
22. As an auditor, I want Decimal money preserved across paper→reward→capital paths, so that float never invents cash.
23. As an auditor, I want Deterministic Gate final under all post-R0 modes with real models, so that models never approve orders.
24. As an operator, I want `deterministic` always available without qualification, so that I can fail closed during retrain/bind outages.
25. As a researcher, I want walk-forward and train-fold-only scaler rules unchanged when paper data joins historical, so that leakage controls hold.
26. As a developer, I want content hashes on paper-derived transitions, so that silent mutation is detectable.
27. As an operator, I want a documented bind/qualify runbook, so that closing the loop is operable.
28. As a researcher, I want terminal/lot clearance rules respected in paper-derived rewards, so that episode-end economics stay honest.
29. As a developer, I want candidate work items listed under phases without auto-filing GitHub issues, so that `/to-tickets` remains the filing gate.
30. As a product owner, I want R0 marked done (Model-Integrated Paper), so that the roadmap does not re-litigate Strategy Modes.

### Track L — Live readiness

31. As an operator, I want a read-only StockX-shaped market data port, so that I can observe live/allowlisted books without order credentials.
32. As an operator, I want Product-Family Allowlist enforced on read-only ingest, so that live observe stays scoped.
33. As a developer, I want corrupt live payloads to fail closed, so that bad data does not invent liquidity.
34. As a safety engineer, I want tests proving the read-only port cannot place orders, so that readiness cannot smuggle send.
35. As an operator, I want shadow “would quote” logging against read-only books, so that I can rehearse Strategy Mode without sending.
36. As an auditor, I want shadow logs to include intent, gate result, and reason codes, so that rehearsal is reconstructible.
37. As an operator, I want shadow observe start/stop without mutating paper capital, so that paper and live-rehearse stay separated.
38. As a safety engineer, I want byte-level or contract-level proof that no marketplace order endpoint is called in L1–L2, so that “no send” is testable.
39. As an operator, I want a human kill-switch design before any live-send, so that incidents can halt new orders.
40. As a staff engineer, I want ADR-0004 written and accepted before live-send, so that adapter + Gate-final + no bypass + kill-switch are decided deliberately.
41. As an operator, I want runbooks for who may enable send, capital caps, allowlist, and incident stop, so that live-send is operable safely.
42. As an operator, I want live-send default off and human-gated, so that enablement is intentional.
43. As an operator, I want live-send only after Track R paper-loop exit (R1–R3) and L3/ADR-0004, so that we do not send before the paper loop is proven.
44. As an operator, I want qty-one, allowlist, and Gate-final on live intents, so that live inherits paper risk DNA.
45. As an operator, I want kill-switch to stop new sends immediately, so that blast radius is bounded.
46. As a product owner, I want L5 expansion only via explicit allowlist/ADR updates, so that scope creep is controlled.
47. As a safety engineer, I want no anti-bot / CAPTCHA / protection-bypass work in this roadmap, so that live readiness stays lawful and policy-aligned.
48. As a developer, I want Synthetic Scenario and GBM barred from live-readiness proof claims, so that stress tools cannot fake venue evidence.
49. As an auditor, I want live shadow and any future live-send audit trails append-only, so that incidents are reconstructible.
50. As a researcher, I want Track L not to block Track R progress, so that paper-loop closure can proceed in parallel with observe-only work.

## Implementation Decisions

- **Test seams (approved):**  
  - **Track R:** Paper Ops Control Plane (REST + ordered projections) **and** research transition/train/registry path (paper-derived OfflineTransition → retrain → register → Ops bind real artifact).  
  - **Track L:** Observe-only market-data port + shadow “would quote” log; **no** order-send API until ADR-0004 and L4.
- **Living doc:** `docs/ROADMAP.md` holds phases, exit criteria, and candidate work items; this file is the agent-ready PRD.
- **Phase style:** Milestone phases with exit criteria; no calendar dates; sprint-sized candidates are illustrative until `/to-tickets`.
- **Track R sequence:** R0–R4 **done** (paper→transition → retrain → bind → promote; PFHedge deferred ADR-0005).  
- **Track L sequence:** L1 read-only port **done** → L2 shadow would-quote → L3 kill-switch/runbooks/ADR-0004 → L4 tiny human-gated live-send (gated on R proof) → L5 expand carefully.  
- **Live-send gate:** Forbidden until (1) Track R exit for R1–R3 (**met**), (2) ADR-0004 accepted, (3) human enable default-off.  
- **ADR-0004:** Still deferred until live-send is contemplated; roadmap states the requirement (adapter + Gate-final + no protection bypass + kill-switch).  
- **Reuse:** Existing FeeSchedule/Decimal, OfflineTransition/RewardBuilder patterns, RegistryService states, Strategy Modes, Action Translator, Inference Latency Budget, Deterministic Gate — do not invent a second promotion or gate system.  
- **Stubs:** Allowed in tests and as injectable ports; R3 happy path binds real / CI-pinned registry artifacts.  
- **PFHedge:** Not a paper Strategy Mode — **deferred** ([ADR-0005](../../adr/0005-pfhedge-paper-mode-deferred.md)); remains research comparison.  
- **Allowlist:** Jordan 1 Retro + Nike Dunk Low unless an explicit later expansion.  
- **Safety:** Offline/network deny posture for paper/research unchanged; live readiness must not introduce send clients before L4.  
- **Links:** MASTER.md and README point at `docs/ROADMAP.md` and this spec.

## Testing Decisions

- Good tests assert **external behavior** at the approved seams, not internal private helpers as the sole proof.
- **R1:** Seeded paper run → transition repository contains trainable rows with lineage; quarantine path tested for incomplete effects.
- **R2:** Train/eval job produces harness report + registry register; OPE invalid path covered; leakage/split tests remain green.
- **R3:** Acceptance with real or CI-pinned small artifact: `advisory` nudge and `iql_primary` pause under Gate; unqualified mode rejected; encoder mismatch fail-closed.
- **L1–L2:** Ingest allowlist + fail-closed payload; shadow log fields; explicit tests that no order-send client/endpoint is invoked.
- **L3–L4:** ADR presence is a process gate; kill-switch dry-run tests when implementation exists; live-send tests only after ADR-0004 scope is opened.
- Prior art: `tests/api/test_paper_ops_strategy_modes.py`, `tests/api/test_paper_ops_api.py`, `tests/research/contracts/test_transition.py`, `tests/research/iql/test_trainer.py`, `tests/research/evaluation/test_ope.py`, `tests/safety/`, Model-Integrated Paper acceptance.
- Do not use Ops Vitest or Guided Demo alone as Track R/L proof.

## Out of Scope

- Writing ADR-0004 in this publish (requirement only)
- Auto-filing all candidate items as GitHub issues
- Live-send implementation before R1–R3 exit + ADR-0004
- Ungated model trading or model override of Deterministic Gate
- Anti-bot, CAPTCHA, or marketplace protection bypass
- Treating Synthetic Scenario / GBM stress as historical or live proof
- Float money in capital ledgers
- Multi-quantity model allocation tickets
- Discord/Slack/Prometheus as ship requirements
- Replacing Golden Historical Replay claims with fixture-only evidence

## Further Notes

- Shared grill decisions (2026-07-18): research integration = close the loop; live = parallel readiness + delayed send; doc = `docs/ROADMAP.md`; shape = milestones + exit criteria + candidate items; ADR-0004 deferred until live-send.
- R0 reference: `docs/superpowers/specs/2026-07-18-model-integrated-paper-slice.md` and ADR-0003.
- Next process step when starting a phase: `/to-tickets` for that phase only, then implement.
- Financial objective of Track R remains improve risk-adjusted **paper** NAV under fees/inventory/capital — measured under frozen harness; not guaranteed by enabling IQL alone.
