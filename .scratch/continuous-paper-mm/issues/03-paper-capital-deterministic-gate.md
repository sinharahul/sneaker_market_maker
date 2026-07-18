# 03 — Paper Capital + Deterministic Gate

**What to build:** Quote Intents pass through a Deterministic Gate that enforces Paper Capital rules ($2,500.00 start; $1,500.00 open-buy principal cap on initial capital; cash after reservations and expected buy-side fees/slippage) and fail closed with stable reason codes. No model path can weaken the gate.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Gate rejects buys that breach open-buy principal cap or available cash after fees/slippage reserve
- [ ] Open-buy cap does not increase with paper profits
- [ ] Replace releases old reservation and reserves new amount atomically (failure cannot double-reserve)
- [ ] Rejection reasons are stable and machine-readable
- [ ] Unit/property tests cover gate behavior without requiring full replay
