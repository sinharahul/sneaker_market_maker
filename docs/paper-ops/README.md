# Continuous Paper Market-Maker — Ops docs

End-to-end documentation for the **Continuous Paper Market-Maker** control plane
(Ops Dashboard + `/api/paper`). This is **not** the Guided Demo and **not** the
research comparison page.

**Glossary:** [`CONTEXT.md`](../../CONTEXT.md)  
**ADRs:** [`0001`](../adr/0001-golden-historical-replay-for-v1.md),
[`0002`](../adr/0002-deterministic-first-paper-mm.md),
[`0003`](../adr/0003-iql-strategy-modes-gate-final.md)  
**Slice specs:** [First Shippable](../superpowers/specs/2026-07-17-continuous-paper-mm-first-slice.md),
[Model-Integrated](../superpowers/specs/2026-07-18-model-integrated-paper-slice.md)

| Doc | Audience | Read when you need… |
|-----|----------|---------------------|
| [junior-e2e-flow.md](./junior-e2e-flow.md) | New contributor | How one tick flows from replay → Strategy Mode → Gate → fills, with module map |
| [operator-cheat-sheet.md](./operator-cheat-sheet.md) | Operator | URLs, commands, and what to click when IQL pauses |
| [auditor-reconstructibility.md](./auditor-reconstructibility.md) | Auditor / reviewer | Audit `event_type`s and status projection fields |

**Local demo:** backend `uvicorn sneaker_market_maker.api.local_demo:app --host 127.0.0.1 --port 8000`, frontend `npm run dev` → Ops at http://127.0.0.1:5173/?view=ops
