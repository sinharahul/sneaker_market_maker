# 05 — Paper Orders + Fee-Aware Fills + matching

**What to build:** Gated Quote Intents become Paper Orders (quantity one). The paper execution engine matches them against replayed market events with deterministic rules; fills happen at most once in full and record Fee-Aware Fill fields (quote price, execution price, slippage, fee schedule version, total fees) updating capital.

**Blocked by:** 04 — Quote engine → Quote Intents (continuous)

**Status:** done

- [x] Accepted Paper Orders are quantity one and never partially fill
- [x] Matching is deterministic for the same replay events and order state
- [x] Each Fee-Aware Fill links to its source market event and fee/slippage versions
- [x] Paper Capital updates correctly on buy/sell fills
- [x] Control-plane or execution-port tests prove fill observability
