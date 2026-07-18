# 03 — Paper Decision State builder

**What to build:** From the live paper book and current market event, build a research-compatible Paper Decision State suitable for the registry-pinned encoder. Missing required fields or schema mismatch fails closed.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Builder produces a research-compatible decision state from paper capital, lots, orders, and market event
- [x] Missing required fields fail closed with a stable error
- [x] Unit tests cover happy path and fail-closed gaps
