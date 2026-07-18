# 03 — Paper→OfflineTransition assembler

**What to build:** Assemble research-compatible OfflineTransition rows from paper decision state, logged/gated actions, fee-once rewards, and next-step state — with content hash, discount/terminal fields, and validate_trainable vs quarantine for incomplete rows.

**Blocked by:** 02 — Fee-once paper reward projection

**Status:** done

- [x] Assembler emits OfflineTransition-shaped rows from paper-derived inputs
- [x] Content hash is stable for identical inputs
- [x] validate_trainable accepts complete rows; incomplete rows quarantine fail-closed
- [x] Past-only / adjacent-tick rule: no future leakage from later paper ticks
- [x] Unit tests cover happy-path assembly and quarantine of missing next-state or reward
