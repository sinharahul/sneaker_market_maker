# 01 — Registry artifact → inference bind

**What to build:** Ops can pin a registry artifact id and load real weights plus encoder into the IQL inference port used by Strategy Modes. Encoder or schema mismatch fails closed. The inference port stays injectable so tests can still stub.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Registry-pinned artifact id binds into the IQL inference port (real weights + encoder)
- [x] Encoder / schema / compatibility mismatch fails closed (no silent quote)
- [x] Inference port remains injectable for CI and unit tests
- [x] Unit or Ops-seam test proves bind succeeds for a tiny compatible fixture and rejects a mismatched one
- [x] Deterministic Gate remains final — bind does not bypass Gate
