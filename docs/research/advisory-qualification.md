# Advisory Qualification

Advisory mode is not granted by code completion, deployment, or passing unit tests.
A model may remain in deterministic-only or shadow operation indefinitely.

## Pre-registered benchmark policy

Business thresholds belong to an externally approved, version-frozen
`QualificationBenchmarkPolicy`. The qualification service does not ship production
defaults that auto-qualify candidates. Every criterion must be declared explicitly
before evaluation; missing or failing criteria block qualification.

`QualificationService.evaluate` consumes immutable inputs only:

- historical fold `EvaluationReport` values with confidence intervals and seed results
- stress-scenario `EvaluationReport` values
- completed shadow-window observations and byte-equivalent paper-stream proof
- operational drill outcomes (`restart`, `rollback`, `drift`, `artifact`)

It produces a `QualificationReport` with per-criterion pass/fail results. APIs cannot
inject executable predicates; `_evaluate_criterion` handles only the fixed sources
`historical`, `stress`, `shadow`, and `drill`.

## Explicit approval

`QualificationService.approve` may transition a registry model from
`BENCHMARK_QUALIFIED` to `ADVISORY_APPROVED` only when:

1. the report is fully qualified,
2. the model artifact hash matches the report,
3. the actor supplies confirmation text containing both the artifact hash and the
   benchmark policy version, and
4. the registry state is currently `BENCHMARK_QUALIFIED`.

Any failed check leaves deterministic-only and shadow behavior unchanged.

## Operational expectation

Research teams register benchmark-policy versions and thresholds outside this
repository. Until an audited approval occurs, recommendation serving continues to
fall back to deterministic actions even when evaluation artifacts exist locally.
