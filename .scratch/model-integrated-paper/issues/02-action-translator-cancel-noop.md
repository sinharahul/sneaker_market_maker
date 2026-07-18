# 02 — Action Translator — CANCEL / NO_OP

**What to build:** The Action Translator handles `CANCEL` (cancel actives) and `NO_OP` (no new intents), and fails closed on out-of-bounds or invalid tick values rather than inventing quotes.

**Blocked by:** 01 — Action Translator — QUOTE mapping

**Status:** done

- [x] `CANCEL` translates to cancel-side semantics without placing new quotes
- [x] `NO_OP` emits no new Quote Intents
- [x] Invalid/out-of-bounds tick inputs fail closed with a stable error
- [x] Unit tests cover CANCEL, NO_OP, and fail-closed cases
