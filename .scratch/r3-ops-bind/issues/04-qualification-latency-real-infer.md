# 04 — Qualification + latency on real infer

**What to build:** Model Qualification still gates entry into model-backed Strategy Modes, and the Inference Latency Budget still applies when inference is real — late or unqualified models fail closed rather than authoring paper quotes.

**Blocked by:** 01 — Registry artifact → inference bind

**Status:** done

- [x] Unqualified model cannot enter `advisory` / `iql_primary` (fail closed)
- [x] Inference Latency Budget is measured against real inference calls
- [x] Exceeding latency budget fails closed (no late quote authored)
- [x] Qualification and latency outcomes are visible in Ops events or projections
- [x] Tests cover unqualified reject and latency-budget reject on the real-infer path
