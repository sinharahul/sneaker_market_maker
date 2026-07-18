# 02 — Fee-once paper reward projection

**What to build:** From adjacent paper step-effects (t → t+1), project a fee-once research RewardRecord: normalized NAV change minus configured penalties, with ledger entry ids explaining fee/shipping/auth/slippage costs — so training never sees fantasy gross-spread P&L.

**Blocked by:** 01 — Paper step effects capture

**Status:** done

- [x] Adjacent step effects produce a RewardRecord consistent with fee-once accounting
- [x] Explanatory ledger ids present for each cost increment (or explicit zero/absent per contract)
- [x] Incomplete accounting quarantines / fails closed instead of inventing reward
- [x] Money remains Decimal through the projection (no float cash)
- [x] Unit tests cover profitable fill, fee-heavy fill, and incomplete-ledger quarantine
