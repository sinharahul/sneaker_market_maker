# 06 — Inventory Lots lifecycle

**What to build:** Buy Fee-Aware Fills create Inventory Lots that progress through the physical lifecycle (purchase through available, reserve, sale, settlement, plus exceptions). Only available lots back asks; reserved lots cannot back another ask. Lot state is visible to operators.

**Blocked by:** 05 — Paper Orders + Fee-Aware Fills + matching

**Status:** ready-for-agent

- [ ] Buy fill creates a uniquely identified Inventory Lot with landed cost basis
- [ ] Only available lots can back an ask Quote Intent
- [ ] Reservation is exclusive; double-reserve fails closed
- [ ] Sale/settlement and exception paths update lot state and audit
- [ ] Tests cover lifecycle transitions and ask-backing rules
