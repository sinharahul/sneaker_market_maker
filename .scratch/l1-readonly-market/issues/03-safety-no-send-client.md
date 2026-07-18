# 03 — Safety: no send client in port tree

**What to build:** Automated safety proof that the L1 read-only port package cannot place marketplace orders — no order SDK methods, no place/submit order calls, no order-send credentials wired into the port.

**Blocked by:** 01 — Read-only observation port + allowlist

**Status:** done

- [x] Safety tests scoped to the L1 port tree (extend `tests/safety/` patterns as needed)
- [x] No `place_order` / `submit_order` (or equivalent) reachable from the port
- [x] No marketplace order-send client imported by the port package
- [x] CI fails if a send client is introduced under the L1 port path
- [x] Docs state L1 is observe-only until L4 + ADR-0004
