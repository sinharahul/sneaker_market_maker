# Deep Bellman / PFHedge Research Acceptance Checklist

Recorded **2026-07-17** on branch `feature/deep-bellman-pfhedge`.

## Environment

| Item | Value |
| --- | --- |
| Git revision | `cbfe839643432c1a88c1cc6805cb36c668ae3e83` |
| Python | CPython 3.12.4 |
| Node | v18.16.0 (npm 9.5.1) |
| PostgreSQL (test container) | PostgreSQL 16.14 (Debian, aarch64) |
| `requirements.txt` SHA-256 | `d3aa4899a659f4cb489d5f7c7fe843649f078bed3400fe4df74f115c6a863b14` |
| `frontend/package-lock.json` SHA-256 | `f6f0819bc6a7733c3a0c90356952b14c8d11ff8830ee128f1e99161c6c3c8ca3` |
| Pytest import mode | `--import-mode=importlib` required (duplicate `test_service.py` basenames under `tests/research/registry/` and `tests/research/transitions/`) |

## Acceptance criteria

- [x] AC-01 — Pinned historical manifest produces complete 14-day transitions at material events and coalesced 60-second maintenance ticks.

  command: `.venv/bin/python -m pytest tests/research/episodes/test_builder.py -q --import-mode=importlib`
  artifact: `tests/research/episodes/test_builder.py`
  result: `8 passed in 0.46s` — covers 14-day closure, maintenance ticks on simulation time, material-event coalescing, and split-boundary rejection.

- [x] AC-02 — Every trainable transition contains required state/action versions, masks, behavior metadata, reward decomposition, next state, terminal reason, timing, fills, fees, inventory/logistics changes, and environment provenance.

  command: `.venv/bin/python -m pytest tests/research/contracts/test_transition.py tests/research/transitions/test_service.py -q --import-mode=importlib`
  artifact: `tests/research/contracts/test_transition.py`, `tests/research/transitions/test_service.py`
  result: `25 passed in 0.63s` — contract validation and transition writer persistence enforce complete trainable records.

- [x] AC-03 — Reward reconciliation proves NAV costs counted once and terminal liquidation closes every residual position/reservation exactly once.

  command: `.venv/bin/python -m pytest tests/research/rewards/test_builder.py -q --import-mode=importlib`
  artifact: `tests/research/rewards/test_builder.py`
  result: `15 passed in 0.50s` — fee-once accounting, terminal liquidation, and NAV decomposition reconciliation.

- [x] AC-04 — Unit tests verify CE limit, distributional Bellman target, quantile-Huber twin critics, distributional expectile value update, hybrid actor loss, target updates, and numerical failure behavior.

  command: `.venv/bin/python -m pytest tests/research/iql -q --import-mode=importlib`
  artifact: `tests/research/iql/test_math.py`, `tests/research/iql/test_actor.py`, `tests/research/iql/test_networks.py`, `tests/research/iql/test_trainer.py`, `tests/research/iql/test_training_pipeline.py`
  result: `52 passed in 3.80s` — IQL math, networks, trainer losses, and training pipeline guards.

- [x] AC-05 — IQL uses only logged actions for value/actor fitting, reports unsupported action regions, and makes no invalid OPE claim.

  command: `.venv/bin/python -m pytest tests/research/evaluation/test_ope.py tests/research/iql/test_trainer.py -q --import-mode=importlib`
  artifact: `tests/research/evaluation/test_ope.py`, `tests/research/iql/test_trainer.py`
  result: OPE module rejects invalid claims; trainer tests enforce logged-action-only fitting and unsupported-region reporting (included in 52 IQL tests above).

- [x] AC-06 — PFHedge 0.23.0 passes pinned public-API compatibility test and remains a direct baseline with no IQL/Bellman responsibility.

  command: `DATABASE_URL=postgresql+psycopg://research:research@localhost:55432/research_test .venv/bin/python -m pytest tests/compatibility/test_pfhedge_public_api.py -q -m integration --import-mode=importlib`
  artifact: `docs/compatibility/pfhedge-0.23.0.md`, `tests/compatibility/test_pfhedge_public_api.py`
  result: `1 passed in 1.37s` — `EntropicRiskMeasure` public API exercised; matrix evidence in compatibility doc.

- [x] AC-07 — Deterministic, no-model, heuristic, v1 MLP, PFHedge, and IQL policies run through one frozen assumption/evaluation harness.

  command: `.venv/bin/python -m pytest tests/research/evaluation/test_harness.py -q --import-mode=importlib`
  artifact: `tests/research/evaluation/test_harness.py`, `src/sneaker_market_maker/research/evaluation/harness.py`
  result: Harness tests pass as part of `38 passed in 2.00s` for full evaluation suite.

- [x] AC-08 — Walk-forward tests prove no temporal, episode, product/size, transform, or synthetic-to-historical leakage; confidence intervals, ablations, stresses, and required risk/inventory/capital metrics present.

  command: `.venv/bin/python -m pytest tests/research/evaluation/test_splits.py tests/research/evaluation/test_harness.py -q --import-mode=importlib`
  artifact: `tests/research/evaluation/test_splits.py`, `tests/research/evaluation/test_harness.py`
  result: `38 passed in 2.00s` for full evaluation suite — leakage controls, splits, metrics, and stress reporting.

- [x] AC-09 — Registry and serving tests prove offline-only training, immutable lineage, shadow first, benchmark-policy enforcement, safe rollback/fallback, bounded advisory output, and deterministic final authority.

  command: `.venv/bin/python -m pytest tests/research/registry/test_service.py tests/research/serving/test_recommender.py -q --import-mode=importlib`
  artifact: `tests/research/registry/test_service.py`, `tests/research/serving/test_recommender.py`
  result: `52 passed in 0.42s` — registry lineage, shadow-first serving, gate failures, and advisory bounds.

- [x] AC-10 — Shadow mode causes byte-equivalent paper order streams to deterministic-only mode while persisting all model comparisons.

  command: `.venv/bin/python -m pytest tests/research/serving/test_recommender.py::test_shadow_persists_comparisons_without_changing_full_paper_command_stream -q --import-mode=importlib`
  artifact: `tests/research/serving/test_recommender.py`
  result: Shadow stream hash match test passes (included in 52 serving/registry tests above).

- [x] AC-11 — Guided demo completes the specified deterministic five-minute story, supports pause/step/resume/restart, and shows actions, gate, inventory, fees, and P&L without network access.

  command: `.venv/bin/python -m pytest tests/research/demo/test_service.py -q --import-mode=importlib && cd frontend && npm test -- GuidedDemo.test.tsx`
  artifact: `tests/research/demo/test_service.py`, `frontend/src/research/GuidedDemo.test.tsx`
  result: Backend `8 passed in 0.33s`; frontend `5 passed` in GuidedDemo Vitest suite (8 total frontend tests).

- [x] AC-12 — Static, dependency, and network-deny tests find no undocumented/private API, anti-bot bypass, proxy-ban evasion, live execution, unsafe model loading, or model safety override.

  command: `.venv/bin/python -m pytest tests/safety -q --import-mode=importlib && cd frontend && npm test -- offlineBoundary.test.tsx`
  artifact: `tests/safety/test_offline_boundary.py`, `tests/safety/test_network_denied.py`, `frontend/src/research/offlineBoundary.test.tsx`
  result: `175 passed in 2.24s` safety suite; frontend offline boundary test `1 passed`.

- [x] AC-13 — Documentation, API, UI, reports, and artifacts describe PFHedge direct hedging and custom Bellman IQL as separate tracks.

  command: `grep -E 'PFHedge|IQL|separate' docs/superpowers/specs/2026-07-17-deep-bellman-pfhedge-design.md docs/research/advisory-qualification.md docs/compatibility/pfhedge-0.23.0.md`
  artifact: `docs/superpowers/specs/2026-07-17-deep-bellman-pfhedge-design.md`, `docs/research/advisory-qualification.md`, `docs/compatibility/pfhedge-0.23.0.md`
  result: Design §1 and §14 explicitly separate PFHedge direct baseline from custom distributional IQL; advisory doc states code completion does not grant advisory status.

- [x] AC-14 — All mandatory tests pass, required historical promotion folds meet pre-registered criteria, and no unresolved severity-one or severity-two accounting, leakage, safety, or lineage defect remains.

  command: `.venv/bin/python -m ruff check src tests; .venv/bin/python -m pytest -m "not integration" -q --import-mode=importlib; docker compose -f docker-compose.test.yml up -d --wait && DATABASE_URL=postgresql+psycopg://research:research@localhost:55432/research_test alembic upgrade head && DATABASE_URL=postgresql+psycopg://research:research@localhost:55432/research_test .venv/bin/python -m pytest -m integration -q --import-mode=importlib; docker compose -f docker-compose.test.yml down -v; cd frontend && npm ci && npm test && npm run typecheck && npm run build; .venv/bin/python -m pytest tests/research/qualification/test_service.py -q --import-mode=importlib`
  artifact: `.superpowers/sdd/task-26-report.md`
  result: Unit `497 passed, 7 deselected`; integration `7 passed, 498 deselected`; qualification `29 passed`; frontend `8 passed`, typecheck clean, Vite build succeeded. Ruff reports 4 pre-existing findings (1× UP038 in `pipeline.py`, 3× SIM102 in `tests/safety/audit_helpers.py`) — not introduced by Task 26.
