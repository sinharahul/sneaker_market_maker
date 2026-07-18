# 04 — Gate / qty-one regression after promote

**What to build:** After promote + bind, golden/`advisory`/`iql_primary` paths still keep Deterministic Gate final and quantity one. Promote/qualify cannot bypass Gate or invent multi-qty quotes.

**Blocked by:** 01 — Ops promote / qualify command; 02 — Promote path on Ops projections

**Status:** done

- [x] Acceptance covers promote → bind → model mode tick under Gate
- [x] Open/filled paper orders remain quantity one
- [x] Gate rejection still blocks order mutation
- [x] Promote alone does not enable live-send or ungated model trading
- [x] R4 phase exit criteria marked when this acceptance + PFHedge decision (03) are done
