# 07 — Authoritative Store (Postgres + audit)

**What to build:** Paper Orders, fills, Inventory Lots, Paper Capital, replay run metadata, and an append-only audit trail persist in PostgreSQL so restart does not erase the paper book. Migrations are additive. Acceptance uses a real Postgres test database.

**Blocked by:** 05 — Paper Orders + Fee-Aware Fills + matching; 06 — Inventory Lots lifecycle

**Status:** ready-for-agent

- [ ] Core paper MM state survives process restart from Postgres
- [ ] Append-only audit records intents, gate decisions, fills, and lot transitions
- [ ] Money columns use exact decimal/integer types (no float accounting)
- [ ] Integration tests with Postgres testcontainer (same pattern as research) pass
- [ ] In-memory-only is not the accepted “done” path for this ticket
