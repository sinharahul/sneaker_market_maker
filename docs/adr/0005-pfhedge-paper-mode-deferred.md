# ADR-0005 — PFHedge as paper Strategy Mode: deferred

**Status:** Accepted (defer)  
**Date:** 2026-07-18  
**Parent:** Track R / R4 in `docs/ROADMAP.md`

## Decision

**PFHedge remains research-comparison only.** It is **not** a Continuous Paper Market-Maker Strategy Mode in this roadmap phase.

## Context

R4 asked whether PFHedge should become a paper Strategy Mode (Gate-final) or stay deferred. Shipping it now would add a second authorship path beside deterministic / advisory / iql_primary without a clear operator need, and allocation semantics in the PFHedge adapter do not map cleanly to qty-one paper quotes without a dedicated ADR and Mode Qualification story.

## Consequences

- Research comparison and harness baselines may continue to use PFHedge.
- Paper Ops Strategy Modes stay: `deterministic`, `advisory`, `iql_primary` only.
- Any future PFHedge paper mode requires a new ADR that states Gate-final, qty-one, Product-Family Allowlist, and Model Qualification explicitly — and must not bypass the Deterministic Gate.
- Live-send remains gated by Track L / ADR-0004 independently of this decision.

## Links

- [`docs/ROADMAP.md`](../ROADMAP.md) R4  
- [`CONTEXT.md`](../../CONTEXT.md)  
- [`adr/0003-iql-strategy-modes-gate-final.md`](0003-iql-strategy-modes-gate-final.md)  
