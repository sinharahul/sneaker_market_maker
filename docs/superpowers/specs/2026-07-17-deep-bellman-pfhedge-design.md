# Deep Bellman IQL and PFHedge Research Subsystem Design

**Date:** 2026-07-17
**Status:** Approved subsystem design; awaiting written-spec review
**Depends on:** `2026-07-17-market-maker-dashboard-design.md`

## 1. Purpose and approved boundary

This document specifies a separate offline quantitative-research subsystem for
the sneaker market maker. It adds a custom PyTorch, risk-sensitive,
distributional, IQL-style Bellman track and an independent PFHedge 0.23.0
direct deep-hedging baseline. Both consume shared replay scenarios, costs,
slippage, deterministic gates, and holdouts. They are separate research tracks:
PFHedge is not the Bellman or IQL engine, and performance from one track is not
evidence about the other.

The subsystem produces bounded recommendations only. It never places, revises,
cancels, or executes an order; moves money; creates inventory; or overrides a
deterministic safety decision. Training is offline. Deployment progresses
through registry validation and shadow mode before bounded advisory use can be
considered.

This design does not approve:

- live marketplace execution or account automation;
- undocumented or private marketplace APIs;
- Cloudflare, CAPTCHA, access-control, or TLS-fingerprint bypass;
- fingerprint/proxy rotation or proxy-ban evasion;
- treating synthetic data as historical evidence; or
- treating the existing five-input MLP as Bellman IQL.

No product code or dependency file is part of this design phase.

## 2. Relationship to the base system

The approved dashboard design remains authoritative for the modular
market-maker, React control plane, FastAPI service, PostgreSQL audit history,
historical replay, deterministic quoting, paper execution, physical inventory,
exact accounting, alerts, and operational safety. This document supersedes
only its provisional Deep Bellman/RL research-boundary text. Existing analytics
code is input to migration, not evidence that the subsystem already exists.

The current analytics core supplies useful concepts—`FeeSchedule`,
`MarketSnapshot`, the ordered five-vector, fail-closed normalization, and seeded
GBM paths—but it is not yet the richer MDP, transition store, event-driven
simulator, IQL trainer, PFHedge baseline, registry, or governed inference path
specified here.

## 3. Architecture

The subsystem is isolated behind versioned contracts:

```text
Historical StockX-first replay ----\
                                    +--> episode builder --> transition store
Labeled GBM/event/logistics -------/                           |
                                                                v
                              +------------------- shared experiment manifest
                              |                                 |
                    custom PyTorch IQL                  PFHedge direct baseline
                              |                                 |
                              +---------- evaluation -----------+
                                                |
                                      immutable model registry
                                                |
                                  shadow recommendation service
                                                |
                           canonicalize -> clamp -> deterministic gates
                                                |
                                  advisory result or deterministic fallback
```

Modules and responsibilities:

- **Scenario adapter:** converts historical and synthetic source events into
  one versioned simulator contract without erasing provenance.
- **Episode builder:** creates deterministic 14-day episodes and material-event
  decision points, adding a 60-second simulation-time maintenance tick when no
  material event occurs.
- **State encoder:** validates the rich state, emits masks, and transforms
  training tensors under an immutable schema/scaler version.
- **Reward/accounting adapter:** reads exact accounting projections and emits a
  normalized objective decomposition without duplicating fees.
- **Transition writer:** atomically persists complete transition and
  environment lineage.
- **IQL trainer:** implements distributional twin-Q Bellman learning,
  distributional expectile value fitting, and advantage-weighted hybrid actor
  fitting in custom PyTorch.
- **PFHedge adapter:** trains an independent direct-policy baseline with
  PFHedge 0.23.0 risk-measure support through documented public APIs.
- **Evaluation service:** runs frozen policies under identical assumptions and
  produces leakage-controlled benchmark reports.
- **Registry and inference adapter:** validates immutable artifacts and emits
  shadow/advisory recommendations; it has no execution port.
- **Deterministic recommendation gate:** canonicalizes and clamps model output,
  checks action support and health, applies existing safety gates, and records
  the final advisory result.

Training jobs run outside request handling and the quote loop. PostgreSQL stores
metadata and audit records; immutable tensor datasets, checkpoints, and reports
may use content-addressed local artifact storage with hashes in PostgreSQL.

## 4. MDP

### 4.1 Time and episodes

An episode spans exactly 14 days of simulation time. A decision point occurs on
a material normalized event—book/spread movement beyond the configured
materiality threshold, fill, quote state change, inventory/logistics event,
fee/regime/restock event, settlement, stale/fresh transition, or risk-limit
change—and at every 60-second maintenance boundary. Events at the same timestamp
use the replay manifest's stable ordering, then one decision is taken from the
fully reduced state. A material event coincident with a maintenance boundary
creates one decision point, not two.

Let \(t\) index decisions, \(\Delta t_t\) be elapsed simulation seconds,
\(\rho\) be the persisted continuous-time discount rate, and
\(\gamma_t=\exp(-\rho\Delta t_t)\). A fixed per-decision discount is allowed
only as a separately versioned experiment and cannot be compared as if
identical. Episodes end at the 14-day boundary or an explicit terminal reason
such as exhausted replay, invalid environment, or forced safety stop.

### 4.2 State

For every configured product/size, \(S_t\) contains:

- simulation timestamp, elapsed and remaining horizon, decision index,
  source/regime labels, and historical/synthetic indicator;
- product identity, size, and the immutable core vector
  `[highest_bid, lowest_ask, days_since_release, volatility_48h, fee_rate]`,
  with vector, transform, and source-snapshot versions;
- spread, recent sales/liquidity, staleness and data-quality state, recent
  restock/event-shock indicators, and bounded event-history summaries;
- open bid/ask orders, prices, quote ages, reservation links, recent fills,
  matching eligibility, and safe queue proxies when actually available;
- physical lots by lifecycle state, landed cost basis, age, sellability,
  reservation, expected logistics/authentication/settlement timing, and
  exception state;
- exact cash projected to model units, open-order principal, fee/slippage
  reserves, pending settlements, gross/net exposure, NAV, peak NAV, and
  drawdown;
- fee schedule, slippage, mark, reward, simulator, and gate-policy versions;
  and
- categorical and continuous action masks/bounds plus missingness indicators.

The state schema declares ordering, units, normalization, clipping, categorical
vocabularies, maximum collection sizes, padding, and masks. Padding is never
interpreted as a real order or lot. Required missing/non-finite values quarantine
the transition rather than receiving a permissive default.

### 4.3 Hybrid action

For each product/size \(j\), the recommendation is

\[
A_t^j=(C_t^j,\alpha_t^j,\delta_{b,t}^j,\delta_{a,t}^j),
\]

where \(C\in\{\text{NO\_OP},\text{QUOTE},\text{CANCEL}\}\),
\(\alpha\in[0,1]\) is allocation relative to the deterministic per-market
capacity, and bid/ask offsets satisfy configured state-dependent bounds
\(\delta_b\in[\ell_b(S),u_b(S)]\) and
\(\delta_a\in[\ell_a(S),u_a(S)]\). Offsets are expressed in integer ticks after
deterministic rounding. They adjust a deterministic reference quote; they are
not raw executable prices.

Masks remove illegal categorical choices before sampling or scoring. Examples:
`QUOTE` on the ask side requires sellable inventory, and `CANCEL` requires a
cancellable quote. The mask does not replace final gates. For `NO_OP` and
`CANCEL`, continuous fields are ignored and persisted in canonical neutral
form. A fully masked row is invalid and falls back to deterministic behavior;
`NO_OP` must normally remain available.

The actor has a masked categorical logit head and continuous heads conditioned
on state and chosen category. Allocation uses a sigmoid transform. Offset heads
use tanh followed by an affine transform to the current bounds. Training
log-probability includes categorical probability and transformed continuous
density only for semantically active dimensions, including Jacobian
corrections. In deterministic inference, category uses masked argmax and
continuous heads use their transformed means.

### 4.4 Transition and terminal behavior

The transition is
\((S_t,A_t,R_{t+1},S_{t+1},D_{t+1})\). Open recommendations are interpreted by
the same simulator and deterministic gates used for every baseline. At terminal
time, open quotes are cancelled, reservations are released, pending settlement
is handled by the versioned terminal policy, and physical inventory is marked
to conservative liquidation value net of remaining costs and disposal
haircuts. Terminal handling is part of the final reward; no bootstrap occurs
when \(D=1\).

## 5. Reward and cost integrity

Let \(N_t\) be exact fee-aware portfolio NAV under a versioned mark policy,
\(N_0>0\) initial capital, and \(p_{k,t}\) dimensionless penalties. The reward is

\[
R_{t+1} =
\frac{N_{t+1}-N_t}{N_0}
-\lambda_{\rm age}p_{\rm age,t}
-\lambda_{\rm capital}p_{\rm capital,t}
-\lambda_{\rm turnover}p_{\rm turnover,t}
-\lambda_{\rm dd}p_{\rm drawdown,t}
-\lambda_{\rm stale}p_{\rm stale,t}
-D_{t+1}\lambda_{\rm term}p_{\rm liquidation,t}.
\]

Here \(R_{t+1}\) is the dimensionless objective reward, \(D_{t+1}\in\{0,1\}\)
is the terminal indicator, each \(p_{\cdot,t}\) is a nonnegative normalized
penalty statistic, and each \(\lambda_\cdot\ge0\) is its persisted coefficient.
NAV includes realized and accrued seller, processor, shipping, authentication,
and slippage costs exactly once through the shared fee/accounting service.
Those cost amounts are persisted as explanatory reward components but are not
subtracted again as penalties. A cost not yet in NAV may be accrued once by a
named ledger/projection entry; the reward builder records that entry ID.
Penalty terms cover only non-cash preferences or constraint pressure. The
reward manifest defines each denominator, cap, coefficient, mark convention,
and terminal policy. Components sum exactly to the stored reward within a
declared tolerance.

Inventory age uses lot-value-weighted age beyond configured grace periods;
capital usage uses time-weighted reserved/initial capital; turnover uses
notional changed plus cancellations; drawdown uses increase in drawdown from
peak fee-aware NAV; stale-quote cost uses unsafe exposure duration; and terminal
liquidation captures the residual haircut and unresolved lifecycle burden not
already posted to NAV. Changing any definition creates a new reward version.

## 6. Risk-sensitive distributional IQL

### 6.1 Certainty equivalent

For a return random variable \(Z\) and risk aversion \(\eta\ge0\),

\[
\operatorname{CE}_{\eta}(Z)=
\begin{cases}
-\eta^{-1}\log \mathbb{E}[\exp(-\eta Z)], & \eta>0,\\
\mathbb{E}[Z], & \eta=0.
\end{cases}
\]

The trainer persists \(\eta\), reward scale, discount convention, and return
units. For quantiles \(z_1,\ldots,z_K\), CE uses equal mass and float64
`logsumexp`:

\[
\widehat{\operatorname{CE}}_\eta(z)
=-\frac{\operatorname{logsumexp}(-\eta z_1,\ldots,-\eta z_K)-\log K}{\eta}.
\]

When \(|\eta|<\epsilon_\eta\), a series-stable implementation uses
\(\bar z-\eta\,\widehat{\mathrm{Var}}(z)/2\), reaching \(\bar z\) at zero.
Inputs and losses must be finite; failures abort the batch/run rather than
silently clipping returns. Gradient norms may be clipped by a persisted limit.

### 6.2 Networks

- Two critics \(Z_{Q_{\theta_1}}(s,a)\) and
  \(Z_{Q_{\theta_2}}(s,a)\) output \(K\) fixed quantiles.
- A distributional value network \(Z_{V_\psi}(s)\) outputs the same \(K\)
  quantiles.
- Slowly updated target copies
  \(Z_{Q_{\bar\theta_1}},Z_{Q_{\bar\theta_2}},Z_{V_{\bar\psi}}\) are inference
  only: \(\bar w\leftarrow \tau_{\rm target}w+
  (1-\tau_{\rm target})\bar w\), with update cadence and coefficient persisted.
- The hybrid actor \(\pi_\phi(a\mid s)\) has the masked categorical and
  squashed continuous heads defined above.

All networks consume the same versioned encoder. Twin critics are independently
initialized. The conservative dataset-action distribution \(Z_Q^-\) is the
target critic whose CE is lower for that row; ties use critic index.

### 6.3 Coherent loss and update sequence

Each optimizer step samples only valid dataset transitions and runs in this
order:

1. **Value update from supported actions.** For logged \(a_t\), compute
   \(q^-=\operatorname{stopgrad}Z_Q^-(s_t,a_t)\),
   \(v=Z_{V_\psi}(s_t)\), and
   \(\Delta=\operatorname{CE}_\eta(q^-)-
   \operatorname{CE}_\eta(v)\). With expectile
   \(\xi\in(0.5,1)\), set
   \(w_\xi(\Delta)=\xi\) if \(\Delta\ge0\), otherwise \(1-\xi\).
   Minimize

   \[
   L_V=w_\xi(\Delta)\left[
   K^{-1}\sum_k h_\kappa(v_k-q^-_k)
   +\lambda_{\rm CE}\Delta^2\right]
   +\lambda_{\rm cross}L_{\rm crossing}(v),
   \]

   where \(h_\kappa\) is smooth Huber loss. This is an IQL-style expectile fit
   using only dataset-supported actions while retaining an implementable
   distributional \(Z_V\) for Bellman targets. The CE term fixes the
   risk-sensitive scalar objective; quantile alignment carries the return
   shape. No actor sample is used in this value target.

2. **Twin distributional Q update.** Draw target value quantiles
   \(z'_{V,j}=Z_{V_{\bar\psi},j}(s_{t+1})\) and form

   \[
   y_j=r_{t+1}+\gamma_t(1-d_{t+1})z'_{V,j}.
   \]

   Each critic minimizes the pairwise quantile-Huber loss

   \[
   L_{Q_i}=\frac{1}{K^2}\sum_{k,j}
   \left|\tau_k-\mathbf{1}\{y_j-z_{Q_i,k}<0\}\right|
   \mathcal H_\kappa(y_j-z_{Q_i,k}),
   \]

   with stopped target gradients. This explicitly learns
   \(Z_Q(s,a)\overset D=R+\gamma(1-D)Z_V(s')\).

3. **Hybrid actor update.** Recompute a stopped conservative advantage

   \[
   A_\eta(s_t,a_t)=
   \operatorname{CE}_\eta(Z_Q^-(s_t,a_t))-
   \operatorname{CE}_\eta(Z_V(s_t)).
   \]

   Use \(W=\min(W_{\max},\exp(\operatorname{clip}(\beta A_\eta,
   -c,c)))\) and minimize weighted negative log-likelihood of the logged
   category and active continuous dimensions. Invalid or unavailable logged
   actions are excluded with a reason count; no action is relabeled to appear
   supported.

4. **Target update.** After successful optimizer steps, Polyak-update target
   value and critic networks. Evaluation uses frozen targets/checkpoints.

Loss coefficients, quantile fractions, Huber threshold, \(\xi,\beta,W_{\max}\),
gradient limits, optimizer settings, update ratios, and target cadence are
fully persisted. Reward normalization is fitted on training folds only and
included in artifact lineage. Logits for masked actions use the dtype's safe
minimum before normalized log-softmax; at least one valid category is asserted.

In these equations, \(K\) is the quantile count; \(\tau_k\in(0,1)\) is fixed
quantile fraction \(k\); \(z_{Q_i,k}\) is critic \(i\)'s predicted quantile;
\(\mathcal H_\kappa\) and \(h_\kappa\) are the quantile and smooth Huber terms
with threshold \(\kappa>0\); \(d_{t+1}\) is the sampled terminal flag;
\(\xi\) is the upper expectile; \(\beta>0\) is advantage temperature;
\(c>0\) is the exponent-input bound; \(W_{\max}\ge1\) is the final actor-weight
cap; \(\lambda_{\rm CE}>0\) makes the scalar CE update an expectile fit; and
\(\lambda_{\rm cross}\ge0\) weights quantile-crossing regularization.
\(L_{\rm crossing}\) penalizes
\(\max(0,v_k-v_{k+1})\). Symbols with bars are target-network parameters and
`stopgrad` removes their argument from gradient propagation.

This is offline IQL-style learning, not online exploration. Propensity metadata
supports diagnostics and limited OPE but is not required by the Bellman loss.

## 7. PFHedge 0.23.0 track

PFHedge 0.23.0 is pinned as an independent direct deep-hedging baseline and for
its public `EntropicRiskMeasure`/risk-utility support. A thin adapter tensorizes
the shared scenario state and bounded continuous recommendation, evaluates the
same fee/slippage/logistics simulator, and optimizes terminal risk directly.
It does not supply the IQL replay buffer, categorical posture, Bellman target,
distributional critic, expectile value fit, action-support logic, or promotion
decision.

Only documented public PFHedge 0.23.0 APIs may be used. Implementation starts
with a compatibility test that imports the pinned package and verifies the
exact risk-measure call and tensor shape. If PFHedge cannot natively express a
hybrid action or sneaker instrument, custom PyTorch adapter code owns that
mapping; the design does not claim PFHedge provides it. No private attributes,
undocumented extension points, or claims about unsupported PFHedge features are
allowed.

The future `requirements.txt` will pin a Python-compatible `torch`, `numpy`,
`pfhedge==0.23.0`, backend/frontend runtime dependencies, and test/lint tooling
after a clean-environment compatibility matrix is run. It is intentionally not
created in this design phase.

## 8. Data, transition persistence, and schema additions

Historical data is StockX-first replay with immutable manifests. Synthetic
augmentation is separately labeled and consists of seeded GBM plus explicit
restock, logistics delay/failure, authentication, liquidity, fee, and named
event shocks. Synthetic rows never acquire historical provenance through
mixing, export, or evaluation.

Add versioned records equivalent to:

- `mdp_state_schemas`, `action_schemas`, `reward_schemas`, and immutable
  encoder/scaler versions;
- `episode_manifests` with source windows, 14-day boundaries, split/fold,
  seed, scenario and simulator versions, checksums, and provenance;
- `decision_points` with material-event reasons, maintenance coalescing,
  source/simulation/wall times, and elapsed duration;
- `offline_transitions` with state and next-state payload/artifact references,
  state/action/reward schema versions, logged proposed and post-gate actions,
  masks/bounds, done flag and terminal reason;
- `behavior_policies` and per-transition policy version, collection mode,
  categorical propensity, active continuous log density, joint log propensity,
  deterministic-policy indicator, support method/version, and missingness
  reason;
- reward total, every NAV/cost/penalty component, NAV/ledger references, fee
  schedule, slippage/mark/terminal-policy versions, and reconciliation status;
- orders, quote ages, fills, fees, reservations, inventory/logistics
  before/after transitions, and settlement outcomes attributable to the step;
- environment provenance: source records, historical/synthetic label, dataset,
  scenario, code revision, simulator, gate policy, configuration, and random
  seed/hash;
- `research_runs`, checkpoints, metrics, holdout assignments, environment lock,
  lineage hashes, and terminal status;
- registry model versions, artifact hashes, compatibility contract, state,
  benchmark report, approvals, rollback reason, and immutable status history;
  and
- recommendation records containing deterministic action, PFHedge score/action,
  IQL shadow action, canonical/clamped action, every gate result, final advisory
  action, fallback, latency, and eventual outcome.

Large tensors may be content-addressed artifacts, but a transition row remains
queryable and pins hashes atomically. Inserts are idempotent by
episode/decision/schema identity. A transition becomes trainable only after
reward reconciliation and next-state linkage pass. Corrections create a new
version; research evidence is never overwritten.

## 9. Training and evaluation pipeline

1. Validate source manifests, exact accounting reconciliation, schemas,
   provenance, action bounds, masks, and terminal closure.
2. Build chronological 14-day episodes without crossing split boundaries.
3. Assign rolling train/validation/test windows before fitting scalers or
   augmentation. Prevent duplicate source events, overlapping episodes, and
   product/size lineage leakage across a fold.
4. Fit transformations on training data only. Add separately labeled synthetic
   augmentation to training, and optionally validation stress suites, never to
   historical holdout claims.
5. Train deterministic/no-model, heuristic, existing v1 MLP, PFHedge, and IQL
   tracks with multiple declared seeds and immutable manifests.
6. Tune on validation only, freeze candidate and benchmark policy, then evaluate
   once on walk-forward historical holdouts plus separately reported stresses.
7. Report bootstrap confidence intervals at the episode/block level, action
   coverage and effective support, and seed dispersion.
8. Run OPE only where assumptions hold. Per-decision/weighted importance
   sampling requires trustworthy nonzero joint propensities; fitted-Q or
   doubly-robust estimates require validated nuisance models. Deterministic or
   unsupported regions are marked “OPE not valid,” not assigned a score.
9. Run ablations for CE risk aversion, distributional versus scalar critic,
   expectile, twin-critic conservatism, synthetic augmentation, reward
   penalties, logistics state, exogenous events, masks, and actor heads.
10. Register immutable artifacts and reports; registration alone grants no
    serving status.

All policies use identical episode boundaries, state information available at
decision time, fees, slippage, latency assumptions, inventory/logistics,
terminal liquidation, gates, and holdouts. Report net P&L/NAV return, CE,
mean/median return, VaR/CVaR and worst-block loss, max drawdown, inventory age
and stranded units, capital utilization/reservation time, turnover/cancel rate,
fill and gate-rejection rates, action-support coverage, latency, numerical
failures, and confidence intervals.

Stress regimes include spread collapse, illiquidity, stale data, volatility
spikes, restocks, adverse gaps, fee/shipping increases, authentication failure,
logistics delay/loss, settlement delay, clustered fills, and terminal inventory.

## 10. Registry, promotion, and runtime safety

Registry states are `CANDIDATE`, `VALIDATED`, `SHADOW`,
`BENCHMARK_QUALIFIED`, `ADVISORY_APPROVED`, `ROLLED_BACK`, and `REJECTED`, with
audited legal transitions. A model is immutable after registration.

Promotion criteria are versioned and frozen before holdout evaluation. A
candidate must:

- pass lineage, schema, artifact, deterministic replay, finite-output, latency,
  and restart tests;
- meet a configured lower confidence bound for net return and CE relative to
  deterministic and heuristic baselines;
- not breach configured non-inferiority margins for CVaR, drawdown, inventory
  age/stranding, capital usage, turnover, or gate rejection;
- retain configured action-support coverage and remain stable across seeds;
- pass every required historical fold and stress safety ceiling; and
- complete a minimum shadow observation window with zero changes to the paper
  order stream.

Threshold values belong to the benchmark-policy version and must be approved
before training; this document does not fabricate business thresholds. Failure
of any mandatory criterion blocks promotion.

At inference, model outputs are schema-checked, finite, masked, canonicalized,
rounded, and clamped. Weak support, timeout, drift alarm, incompatible lineage,
missing artifact, invalid output, unhealthy service, or any gate failure records
a stable reason and falls back to the deterministic recommendation. Even an
`ADVISORY_APPROVED` model can only influence bounded recommendations. There is
no execution credential, marketplace client, or safety-override interface in
the research service.

## 11. API and React changes

Add local, authenticated-if-exposed read models for episode/data manifests,
transition quality, research runs, checkpoints, benchmark reports, registry
lineage, model comparisons, shadow/advisory state, and recommendation traces.
Idempotent audited commands create/cancel offline runs, validate/register
artifacts, enable/disable shadow mode, approve a benchmark-qualified advisory,
and roll back. Training is asynchronous and returns a durable run ID. APIs do
not accept arbitrary executable model code.

WebSocket events report run progress, evaluation completion, registry changes,
shadow comparisons, fallbacks, and drift/health changes using the base ordered
event envelope. They never stream secrets or unbounded tensor payloads.

The React research view shows frozen assumptions, lineage, fold/seed results,
confidence intervals, support warnings, historical versus synthetic labels,
ablation results, registry state, and deterministic/PFHedge/IQL comparisons.
Recommendation details show the deterministic action, PFHedge score and mapped
action, IQL shadow action, canonical/clamped recommendation, each deterministic
gate, final advisory result, and eventual outcome.

### Guided demo mode

Provide a deterministic, local, five-minute simulation-time story with
pause/step/resume/restart:

1. a healthy spread appears;
2. the deterministic strategy recommends a bid;
3. the bid receives a paper buy fill;
4. the physical pair advances through shipping and authentication;
5. an inventory-backed ask is posted and receives a paper sale;
6. a later recommendation is rejected by a deterministic risk gate.

The demo continuously displays deterministic action, PFHedge score, IQL shadow
action, final gated action, inventory lifecycle, itemized fees, cash/NAV, and
realized/unrealized P&L. It uses pinned local fixtures, models or prerecorded
versioned outputs, a fixed seed, deterministic event order, and no external
network. Restart returns to the same initial state; stepping advances exactly
one coalesced decision point.

## 12. Error handling, security, and observability

Data/schema/lineage errors quarantine affected transitions. Accounting or reward
reconciliation errors block training. NaN/Inf, exploding loss, invalid masks,
empty batches, target incompatibility, artifact corruption, out-of-memory, or
checkpoint failure marks the run failed with a sanitized reason; it never
promotes a partial artifact. Resumption is allowed only from a complete,
hash-verified checkpoint with the same manifest and environment.

Serving errors are fail-closed to deterministic-only behavior. Registry updates
and advisory changes are transactional and audited. Artifact loading uses an
allowlisted local format and expected architecture; untrusted pickle or
arbitrary code loading is prohibited. Paths are canonicalized, hashes verified,
inputs bounded, logs redacted, and APIs loopback-only unless an authenticated
external layer is configured. Dependencies are pinned and scanned.

Structured logs and traces include run, episode, fold, seed, dataset/scenario,
schema, model, reward, gate, and correlation IDs with both clocks. Metrics cover
transition validation/reconciliation, source mix, action support, run
stage/duration/failure, losses and gradient health, Q/value/advantage/CE
distributions, quantile crossing, actor saturation, evaluation metrics,
registry transitions, inference latency/fallback, mask/gate rejections, drift,
and demo state. IDs with unbounded cardinality remain log fields, not metric
labels. Alerts cover reconciliation failure, repeated numerical failure,
artifact mismatch, drift, shadow divergence, attempted illegal promotion, and
unexpected advisory use.

## 13. Test strategy

- **Math/unit:** CE at zero and near-zero \(\eta\), float64 log-sum-exp,
  time-aware discounting, terminal no-bootstrap, quantile-Huber sign/weights,
  expectile asymmetry, conservative twin selection, detached targets, Polyak
  updates, clipped advantage weights, mask normalization, squashing/Jacobians,
  offset rounding, and reward-component reconciliation.
- **Property:** arbitrary actor outputs remain bounded; invalid categories are
  never selected; model output cannot reverse a gate rejection; fees enter NAV
  once; replay speed does not alter transitions; terminal inventory closes
  exactly once; persisted components sum to reward.
- **Persistence/integration:** transition completeness, behavior propensity,
  schema/version FKs, idempotent writes, artifact hashes, correction versioning,
  restart/resume, registry legal transitions, audited rollback, and PostgreSQL
  transaction boundaries.
- **Training:** deterministic seeded smoke run, critic/value/actor update
  isolation, overfit-on-tiny-fixture checks, target-gradient absence, corrupt
  data/checkpoint failure, clean-environment PFHedge 0.23.0 public-API
  compatibility, and proof that PFHedge is not imported by the IQL engine.
- **Evaluation:** walk-forward split and overlap sentinels, train-only scalers,
  synthetic-label preservation, multiple seeds/CIs, frozen holdout, support
  diagnostics, invalid-OPE labeling, ablations, and identical-assumption
  baseline harness.
- **Safety/security:** static and network-deny tests prove no live marketplace
  execution, credential path, private API, Cloudflare/TLS bypass, proxy-ban
  evasion, unsafe artifact loading, or model-to-execution dependency.
- **API/UI/E2E:** idempotent run commands, ordered events, failure/fallback
  states, accessible comparison views, promotion confirmation, rollback, and a
  golden five-minute demo covering every story beat and control.

## 14. Acceptance criteria

The subsystem is accepted only when:

1. A pinned historical manifest deterministically produces complete 14-day
   transitions at material events and coalesced 60-second ticks.
2. Every trainable transition contains all required state/action versions,
   masks/bounds, behavior policy/propensity metadata, reward decomposition,
   next state, terminal reason, timing, fills, fees, inventory/logistics
   changes, and environment provenance.
3. Reward reconciliation proves NAV costs are counted once and terminal
   liquidation closes every residual position/reservation exactly once.
4. Unit tests verify the stated CE limit, distributional Bellman target,
   quantile-Huber twin critics, distributional expectile value update, hybrid
   actor loss, target updates, and numerical failure behavior.
5. IQL uses only logged actions for value/actor fitting, reports unsupported
   action regions, and makes no invalid OPE claim.
6. PFHedge 0.23.0 passes a pinned public-API compatibility test and remains a
   direct baseline with no IQL/Bellman responsibility.
7. Deterministic, no-model, heuristic, v1 MLP, PFHedge, and IQL policies run
   through one frozen assumption/evaluation harness.
8. Walk-forward tests prove no temporal, episode, product/size, transform, or
   synthetic-to-historical leakage; multiple-seed confidence intervals,
   ablations, stresses, and required risk/inventory/capital metrics are present.
9. Registry and serving tests prove offline-only training, immutable lineage,
   shadow first, benchmark-policy enforcement, safe rollback/fallback, bounded
   advisory output, and deterministic final authority.
10. Shadow mode causes byte-equivalent paper order streams to deterministic-only
    mode while persisting all model comparisons.
11. The guided demo completes the specified deterministic five-minute story,
    supports pause/step/resume/restart, and shows actions, gate, inventory,
    fees, and P&L without network access.
12. Static, dependency, and network-deny tests find no undocumented/private
    API, anti-bot/access-control bypass, proxy-ban evasion, live execution,
    unsafe model loading, or model safety override.
13. Documentation, API, UI, reports, and artifacts describe PFHedge direct
    hedging and custom Bellman IQL as separate tracks.
14. All mandatory tests pass, required historical promotion folds meet their
    pre-registered criteria, and no unresolved severity-one or severity-two
    accounting, leakage, safety, or lineage defect remains.

## 15. Phased implementation slices

1. **Contracts and migrations:** MDP/state/action/reward schemas, manifests,
   transitions, behavior metadata, artifact references, and compatibility
   adapters to the existing core.
2. **Episode/reward construction:** event coalescing, 60-second ticks, 14-day
   closure, rich state encoder, masks, exact NAV adapter, fee-once reward, and
   historical/synthetic provenance.
3. **Shared evaluation harness:** deterministic/no-model/heuristic/v1 MLP
   adapters, frozen assumptions, walk-forward splits, metrics, support checks,
   CI reporting, and stress suites.
4. **PFHedge baseline:** dependency compatibility spike, public-API adapter,
   direct entropic-risk training, reproducibility, and baseline reports.
5. **Custom distributional IQL:** networks, losses, replay loader, checkpointing,
   numerical guards, seeded training, and ablations.
6. **Registry and shadow serving:** immutable lineage, benchmark policy,
   compatibility checks, recommendation records, fallback, drift, rollback,
   and proof of behavioral inertness.
7. **React/API and guided demo:** research views, audited commands, ordered
   events, comparison trace, accessibility, and deterministic five-minute mode.
8. **Advisory qualification:** historical holdouts, stresses, shadow window,
   operational drills, and explicit approval of a benchmark-qualified artifact.

Each slice includes migrations, tests, observability, rollback, and updated
contracts. Advisory qualification may remain disabled indefinitely; completion
of research code does not imply promotion.

## 16. Migration and compatibility

The existing five-vector retains its ordering and gains an immutable semantic
schema/version rather than changing in place. `MarketSnapshot`, `FeeSchedule`,
and seeded GBM behavior are wrapped behind new ports first; exact Decimal
accounting stays authoritative, while explicit validated conversions create
model tensors. Existing tests remain compatibility tests.

Database additions are additive initially. Backfill may create source states
and provenance, but historical rows lacking a trustworthy action propensity,
next state, fee reconciliation, or logistics outcome remain marked
non-trainable; values are not invented. Existing v1 MLP artifacts remain
`baseline_direct_policy` and cannot be relabeled IQL or PFHedge. API fields and
events are added under new schema versions, and older dashboard clients ignore
unknown research events. Registry rollback always supports deterministic-only
operation.

An implementation plan must preserve these slices and the separation between
PFHedge direct hedging, custom Bellman IQL, deterministic safety, and paper
execution.
