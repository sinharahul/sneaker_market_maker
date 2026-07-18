# 09 — Advisory Mode nudge path

**What to build:** In `advisory` with a qualified model and valid IQL within budget, Deterministic Strategy proposes the base quote; Action Translator applies a bounded IQL tick nudge; Deterministic Gate remains final; resulting Paper Orders are observable.

**Blocked by:** 01 — QUOTE mapping; 02 — CANCEL/NO_OP; 04 — inference port; 07 — set-mode; 08 — deterministic unchanged

**Status:** done

- [x] Valid IQL nudge changes desired prices relative to deterministic base within bounds
- [x] All resulting intents still pass through the Deterministic Gate
- [x] Control-plane or session tests show nudged orders under stub IQL
