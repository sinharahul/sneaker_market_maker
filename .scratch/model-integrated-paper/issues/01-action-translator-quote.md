# 01 — Action Translator — QUOTE mapping

**What to build:** A versioned Action Translator maps research `QUOTE` HybridActions to quantity-one paper desired prices as touch ± (ticks × pinned tick_size). Translator version and tick_size are pinable on a run. Allocation does not change order size.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `QUOTE` maps to bid/ask dollar offsets from ticks × tick_size at quantity one
- [x] Translator version and tick_size are explicit and pinable
- [x] Allocation is ignored for sizing
- [x] Unit tests cover happy path and tick_size pinning
