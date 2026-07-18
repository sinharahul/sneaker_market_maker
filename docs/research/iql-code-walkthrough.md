# IQL / deep learning code walkthrough

**Audience:** engineers learning how distributional IQL is implemented and how
it plugs into Continuous Paper Ops.  
**Scope date:** 2026-07-18  
**Framework:** **PyTorch** (`torch==2.2.2`). There is **no TensorFlow** in this
repo.

**Companions:** [`QUANTITATIVE_CONTEXT.md`](./QUANTITATIVE_CONTEXT.md) (full math) ·
[`junior-walkthrough.md`](./junior-walkthrough.md) (research layers) ·
[`senior-architect-walkthrough.md`](./senior-architect-walkthrough.md) ·
[`../paper-ops/junior-e2e-flow.md`](../paper-ops/junior-e2e-flow.md) (paper tick) ·
[`../MASTER.md`](../MASTER.md) (product map)

---

## 1. What problem the nets solve

You have logged transitions \((s, a, r, s', \gamma, \text{done})\) — from history
or paper export. You cannot freely explore a live book.

IQL learns three things:

| Network | Role |
|---------|------|
| **V(s)** | How good is this state? (distribution over returns) |
| **Q(s,a)** | How good is taking logged action \(a\) in \(s\)? (two critics) |
| **Actor π(a\|s)** | Policy that prefers high-advantage *logged* actions |

Classic IQL idea: fit V via **expectiles** of Q, fit Q via Bellman using V, fit
actor by **advantage-weighted** behavior cloning of logged actions — no online
environment loop.

This repo makes V and Q **distributional** (quantiles), not scalar, so risk can
enter via a certainty equivalent.

Code root: `src/sneaker_market_maker/research/iql/`.

| File | Responsibility |
|------|----------------|
| `dataset.py` | OfflineTransition rows → tensors / `TransitionBatch` |
| `networks.py` | `DistributionalValue`, `DistributionalQ`, twin pick, target copies |
| `math.py` | CE, Huber, quantile Huber, crossing loss |
| `trainer.py` | One IQL step: V → Q1/Q2 → actor → Polyak |
| `actor.py` | Hybrid discrete+continuous policy |
| `checkpoint.py` | Safetensors + JSON manifest (no pickle) |

---

## 2. Paper Ops integration (this is not research-only)

IQL **is** wired into the paper trading flow. Training stays offline; **Ops only
needs the actor** at tick time. Q/V stay in the research/retrain loop.

### Mental model

```text
Train (offline):  transitions → V, Q1, Q2, Actor  → checkpoint
Paper Ops:        bind Actor → advisory / iql_primary ticks → Gate → book
Export loop:      paper steps → OfflineTransitions → retrain again
```

### How paper uses IQL

Default Strategy Mode is `deterministic` → **no IQL call**. Switch to
`advisory` or `iql_primary` (after bind + qualification) and the tick path is:

1. Replay tick → match fills / advance lots  
2. Build `PaperDecisionState`  
3. `TimedIqlInference` → `CheckpointIqlInference.infer`  
4. Load **`HybridActor`** from safetensors → `deterministic(...)`  
5. `apply_strategy_mode` → Action Translator (nudge or author quotes)  
6. **Deterministic Gate** still final → paper orders  

| Piece | Role in paper |
|-------|----------------|
| Offline IQL train (`research/iql/`, retrain jobs) | Produces checkpoint with `actor.*` (plus Q/V for training) |
| Registry register / promote | Unlocks modes (`advisory_approved`, `benchmark_qualified`, …) |
| `bind-model` / `paper/artifact_bind.py` | Loads checkpoint into session as `CheckpointIqlInference` |
| Local demo | Pre-binds CI-pinned actor under `data/paper/artifacts/iql_ci_v1/` |
| Tick path (`paper/session.py` → `mode_path.py`) | Calls that port when mode ≠ `deterministic` |

### One-tick (all modes)

```mermaid
flowchart TD
  T[simulator.tick emits market events] --> MATCH[execution.match fills]
  MATCH --> LOTS[advance purchased lots if needed]
  LOTS --> INF{Strategy Mode}
  INF -->|deterministic| DET[QuoteEngine deterministic desired]
  INF -->|advisory / iql_primary| PDS[build Paper Decision State]
  PDS --> IQL[TimedIqlInference within latency budget]
  IQL --> MP[apply_strategy_mode]
  MP -->|advisory + invalid/late| FB[deterministic base + advisory_fallback]
  MP -->|iql_primary + invalid/late| PAUSE[pause replay pause_reason=iql_unavailable]
  MP -->|valid advisory| NUDGE[nudge deterministic base via Action Translator]
  MP -->|valid iql_primary| AUTH[translator authors desired quotes]
  DET --> GATE[Deterministic Gate]
  FB --> GATE
  NUDGE --> GATE
  AUTH --> GATE
  PAUSE --> STOP[no silent deterministic substitute]
  GATE -->|accepted| SUB[submit Paper Order]
  GATE -->|rejected| intent rejected
```

| Mode | Who authors desired quotes | If IQL fails |
|------|----------------------------|--------------|
| `deterministic` | Deterministic Strategy only | N/A — IQL not called |
| `advisory` | Deterministic base + bounded IQL nudge | Deterministic base that tick; **no pause** |
| `iql_primary` | IQL via Action Translator | **Pause** replay until healthy IQL or mode switch |

Gate remains final in every mode. Canonical Ops detail:
[`../paper-ops/junior-e2e-flow.md`](../paper-ops/junior-e2e-flow.md).

---

## 3. Data → tensors (`dataset.py`)

`TransitionDataset.from_repository` pulls `OfflineTransition` rows for a
manifest, **drops quarantined / non-trainable**, and packs:

- `state`, `next_state` — float feature vectors  
- `action` — continuous part (allocation + bid/ask ticks as floats)  
- `logged_category` — NO_OP / QUOTE / CANCEL index  
- `reward`, `discount`, `done`  
- `category_mask`, `bounds`, `active_dimensions` — for the hybrid actor  

That becomes a `TransitionBatch` for one `IQLTrainer.step`.

---

## 4. Networks (`networks.py`)

Small MLPs with SiLU:

**`DistributionalValue`:** \(s \mapsto\) vector of quantile levels  
`Linear → SiLU → Linear → SiLU → Linear(quantile_count)`

**`DistributionalQ`:** \([s; a] \mapsto\) quantile vector  
Same shape; input is state concat action.

**Twin Q + conservative pick:** training uses `q1` and `q2`.  
`select_conservative_quantiles` keeps the twin whose certainty equivalent is
**worse** (more pessimistic) — double-Q style conservatism.

**Targets:** `create_inference_target` deep-copies V/Q1/Q2, freezes grads.
Soft-updated later (Polyak).

---

## 5. Math helpers (`math.py`)

**Certainty equivalent** of a quantile vector \(z\) with risk \(\eta\):

- \(\eta = 0\): mean  
- small \(\eta\): mean − ½η·variance (approx)  
- else: entropic CE  
  \(\mathrm{CE}(z) = -\frac{1}{\eta}\bigl(\log\sum_i e^{-\eta z_i} - \log N\bigr)\)

So “value” for advantage / twin selection is a **risk-adjusted scalar**, not a
raw mean.

**Smooth Huber:** squared near 0, linear outside `kappa` — robust regression.

**Pairwise quantile Huber:** QR-DQN-style loss between predicted quantiles and
Bellman targets, weighted by quantile fractions \(\tau\).

**Crossing loss:** `relu(q[i] - q[i+1])` — penalizes unsorted quantiles.

---

## 6. One training step (`trainer.py`)

`IQLTrainer.step(batch)` runs four updates, all fail-closed on NaNs/Inf.

### 6.1 Value (expectile of Q)

```text
target_q = conservative(target_q1(s,a), target_q2(s,a))   # no grad
δ = CE(target_q) - CE(V(s))
w = expectile if δ≥0 else (1 - expectile)   # asymmetric weight
value_loss = mean( w * (Huber(V - target_q) + λ_ce·δ²) ) + λ_cross·crossing(V)
```

Intuition: V tracks a **tilted** regression of Q (expectile), plus optional CE
match and quantile order.

### 6.2 Critics Q1 / Q2 (Bellman)

```text
bellman = r + γ · (1 - done) · target_V(s')     # no grad on target_V
q_i_loss = pairwise_quantile_huber(Q_i(s,a), bellman, fractions, κ)
```

Same target for both twins; each optimized separately. This is “fit Q to reward
+ discounted next V” in **quantile space**.

### 6.3 Actor (advantage-weighted BC)

```text
advantage = CE(conservative_Q(s,a)) - CE(V(s))
weight = clamp(exp(β · advantage), max=max_weight)   # clipped
actor_loss = - mean( weight * log π(a_logged | s) )
```

Only **logged** actions get probability mass (offline). High advantage → higher
weight → imitate those actions more.

### 6.4 Optimizers + Polyak

Each of V, Q1, Q2, actor: zero_grad → backward → **clip_grad_norm** → step.
Non-finite loss/grad aborts the step.

Every `target_cadence` successful steps:

```text
θ_target ← (1-τ)·θ_target + τ·θ_online
```

for V, Q1, Q2 (`target_tau`).

### Config knobs (`IQLConfig`)

| Field | Effect |
|-------|--------|
| `expectile` | Asymmetry of V regression (classic IQL) |
| `eta` | Risk aversion in CE / twin selection |
| `beta` | How sharply advantage reweights the actor |
| `kappa` | Huber transition |
| `lambda_ce` / `lambda_cross` | Extra V CE match / quantile order |
| `exp_clip` / `max_weight` | Stability of AWR weights |
| `target_tau` / `target_cadence` | Target net lag |

Tiny CI/demo trainers use small `hidden_dim` / few quantiles / few steps — same
algorithm, smaller nets.

---

## 7. `actor.py` in detail

Path: `src/sneaker_market_maker/research/iql/actor.py`.

The market-making action is **hybrid**:

| Part | Meaning | Shape / range |
|------|---------|----------------|
| **Category** | `NO_OP` / `QUOTE` / `CANCEL` | discrete index in `{0,1,2}` |
| **Continuous** | allocation + bid/ask offsets | 3 floats after squash |

`HybridActor` is the policy net π(a|s). Training uses `log_prob` (density of a
*logged* action). Paper Ops uses `deterministic` (argmax + mean, no sampling).

### 7.1 `ActorAction`

Frozen dataclass returned by `deterministic`: chosen category, squashed
continuous vector, and log π(category|s).

### 7.2 `masked_log_softmax`

- Illegal categories get the most negative float → softmax ≈ 0.  
- Fail-closed if a row has **no** legal category.  
- Returns **log** probabilities (stable for BC / AWR).

### 7.3 `squash_continuous`

Network outputs unconstrained `raw` (length 3):

1. Dim 0 → `sigmoid` → allocation ∈ (0, 1)  
2. Dims 1–2 → `tanh` → (−1, 1), then affine map into `[low, high]` from `bounds`

`bounds` layout: `[..., 0, :]` = lows, `[..., 1, :]` = highs for the two offset
dims.

### 7.4 `transformed_normal_log_prob`

Training needs log π(continuous | s, category). The base distribution is Normal
in **pre-squash** space; continuous actions live in **squashed** space, so you
invert the squash and subtract the log Jacobian:

```text
allocation a ∈ (0,1)  ←  σ(u)     ⇒  u = logit(a),   Jacobian term uses a(1−a)
offset o ∈ [L,H]      ←  from tanh ⇒  invert to unit, atanh, Jacobian of tanh + scale
log π(a) = log N(raw | μ, σ) − log|Jacobian|
```

Inactive dims (e.g. NO_OP has no offsets) are zeroed via `active_dimensions`.
`log_std` is clamped to `[-5, 2]` before `exp` so σ stays sane.

### 7.5 Architecture (`_head` + `HybridActor`)

Three small MLPs (`Linear → SiLU → Linear → SiLU → Linear`):

```text
category_head(s)           → 3 logits
mean_head([s; one_hot(c)]) → 3 means  (pre-squash)
log_std_head(...)          → 3 log-σ
```

Continuous heads are **conditioned on category**: quoting and canceling can have
different continuous params.

### 7.6 `deterministic` — Ops / eval path

No sampling: argmax category, squash the **mean** (ignore std). That is what
`CheckpointIqlInference` calls on each paper tick.

### 7.7 `log_prob` — training path

Returns `log π(category | s) + log π(continuous | s, category)`. IQL actor loss
is roughly `-mean(weight * log_prob(...))` on **logged** actions.

### How Ops loads the actor

`CheckpointIqlInference` (`paper/artifact_bind.py`) constructs
`HybridActor(state_dim, hidden_dim=8)`, loads `actor.*` safetensors keys, then:

```python
action = self._actor.deterministic(encoded_state, mask, bounds)
```

Q/V are not imported on that path.

---

## 8. PyTorch tutorial (required for this code)

### Install / import

```bash
# already in requirements.txt / pyproject.toml
torch==2.2.2
```

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal
```

### APIs `actor.py` actually needs

| Concept | PyTorch call | Role in `actor.py` |
|---------|--------------|--------------------|
| Module | `nn.Module`, `nn.Sequential`, `nn.Linear`, `nn.SiLU` | Network layers |
| Softmax in log space | `torch.log_softmax` | Category probs |
| Mask logits | `tensor.masked_fill` | Illegal actions |
| Activations | `torch.sigmoid`, `torch.tanh`, `torch.logit`, `torch.atanh` | Squash / unsquash |
| Concat / gather | `torch.cat`, `.gather`, `.argmax` | Heads + pick category |
| One-hot | `F.one_hot` | Condition continuous on category |
| Gaussian density | `Normal(mean, std).log_prob(x)` | Pre-squash log density |
| Autograd | `loss.backward()`, `optimizer.step()` | Used by trainer |

### Minimal toy that mirrors the actor

```python
import torch
import torch.nn as nn
import torch.nn.functional as F

class TinyHybrid(nn.Module):
    def __init__(self, state_dim: int = 4):
        super().__init__()
        self.cat = nn.Linear(state_dim, 3)
        self.mean = nn.Linear(state_dim + 3, 3)

    def deterministic(self, state, mask, bounds):
        logits = self.cat(state)
        logits = logits.masked_fill(~mask, torch.finfo(logits.dtype).min)
        log_p = torch.log_softmax(logits, dim=-1)
        category = log_p.argmax(dim=-1)

        one_hot = F.one_hot(category, 3).to(state.dtype)
        raw = self.mean(torch.cat([state, one_hot], dim=-1))
        allocation = torch.sigmoid(raw[..., :1])
        unit = torch.tanh(raw[..., 1:])
        low, high = bounds[..., 0, :], bounds[..., 1, :]
        offsets = low + 0.5 * (unit + 1.0) * (high - low)
        continuous = torch.cat([allocation, offsets], dim=-1)
        return category, continuous


B, S = 2, 4
state = torch.randn(B, S)
mask = torch.tensor([[True, True, False], [True, True, True]])
bounds = torch.tensor([[[-2.0, -2.0], [2.0, 2.0]]]).expand(B, 2, 2)
cat, cont = TinyHybrid().deterministic(state, mask, bounds)
print(cat, cont)
```

### Training vs inference

```python
# Training (conceptual — see IQLTrainer)
log_pi = actor.log_prob(state, mask, bounds, logged_cat, logged_cont, active)
actor_loss = -(advantage_weights * log_pi).mean()
actor_optimizer.zero_grad()
actor_loss.backward()
actor_optimizer.step()

# Inference (paper)
actor.eval()
with torch.no_grad():
    out = actor.deterministic(state, mask, bounds)
# out.category, out.continuous → Action Translator → Gate
```

### If you know TensorFlow (map only — do not add TF)

| TensorFlow | PyTorch (this code) |
|------------|---------------------|
| `tf.keras.layers.Dense` | `nn.Linear` |
| `tf.nn.silu` / Swish | `nn.SiLU` |
| `tf.nn.log_softmax` | `torch.log_softmax` |
| `tf.one_hot` | `F.one_hot` |
| `tfp.distributions.Normal(...).log_prob` | `Normal(...).log_prob` |
| `tf.sigmoid` / `tf.math.atanh` | `torch.sigmoid` / `torch.atanh` |
| `model(x, training=False)` | `actor.eval()` + `torch.no_grad()` |
| `GradientTape` | autograd via `.backward()` |

There is **no required TensorFlow code** for this project.

---

## 9. Checkpoints

Safetensors + JSON manifest (architecture, hashes, step). No pickle /
`torch.load` of untrusted blobs. R2 train writes full nets; Ops bind typically
needs **`actor.*`** weights only for forward quoting.

---

## 10. One-sentence summary

**Fit distributional Q to a Bellman backup through V; fit V as an expectile of
Q; pull the hybrid actor toward logged actions that look better than V — all
offline, all finite-checked; paper Ops binds only the actor’s greedy action,
and the Deterministic Gate remains final.**

---

## 11. Related paths

| Concern | Location |
|---------|----------|
| Trainer / nets / actor | `src/sneaker_market_maker/research/iql/` |
| Offline retrain loop | `src/sneaker_market_maker/research/retrain/` |
| Ops inference port | `src/sneaker_market_maker/paper/inference.py` |
| Checkpoint bind | `src/sneaker_market_maker/paper/artifact_bind.py` |
| Mode authorship | `src/sneaker_market_maker/paper/mode_path.py` |
| Decision state encode | `src/sneaker_market_maker/paper/decision_state.py` |
| CI-pinned artifact | `data/paper/artifacts/iql_ci_v1/` |
| Acceptance | `tests/research/iql/`, `tests/api/test_paper_ops_r3_bind.py` |
