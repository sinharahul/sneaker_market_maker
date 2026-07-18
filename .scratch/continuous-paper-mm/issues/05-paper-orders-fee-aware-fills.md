# 05 — Paper Orders + Fee-Aware Fills + matching

**What to build:** Gated Quote Intents become Paper Orders (quantity one). The paper execution engine matches them against replayed market events with deterministic rules; fills happen at most once in full and record Fee-Aware Fill fields (quote price, execution price, slippage, fee schedule version, total fees) updating capital.

**Blocked by:** 04 — Quote engine → Quote Intents (continuous)

**Status:** ready-for-agent

- [ ] Accepted Paper Orders are quantity one and never partially fill
- [ ] Matching is deterministic for the same replay events and order state
- [ ] Each Fee-Aware Fill links to its source market event and fee/slippage versions
- [ ] Paper Capital updates correctly on buy/sell fills
- [ ] Control-plane or execution-port tests prove fill observability
