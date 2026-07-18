# 04 — OPE validity gate

**What to build:** Attach off-policy evaluation to the R2 train/eval report with a hard validity gate: when support or propensities are incomplete, emit OPE_NOT_VALID and never fabricate a WIS number; when valid, report WIS + ESS.

**Blocked by:** 03 — Walk-forward harness benchmark

**Status:** done

- [x] Partial support / missing propensities → OPE_NOT_VALID on the report
- [x] Valid support → WIS estimate and ESS present
- [x] No numeric OPE claim is invented when invalid
- [x] Unit tests cover valid and invalid paths (prior art: research OPE tests)
- [x] Harness/job output surfaces OPE status fail-closed
