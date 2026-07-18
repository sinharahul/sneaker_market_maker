# 01 — Read-only observation port + allowlist

**What to build:** A StockX-shaped **read-only** market observation port that yields allowlisted product-family snapshots/events. No order credentials and no order API on this port. Reuse Product-Family Allowlist and replay-compatible event shape where practical.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Port delivers allowlisted StockX-shaped observations (fixture or recorded responses OK)
- [x] Families outside the Product-Family Allowlist are rejected
- [x] Port surface cannot accept or use order-placement credentials
- [x] Unit/seam test proves allowlisted observe succeeds and off-allowlist fails
- [x] No live-send or shadow-would-quote behaviour in this ticket
