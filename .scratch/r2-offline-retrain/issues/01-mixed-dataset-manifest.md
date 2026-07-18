# 01 — Mixed dataset manifest

**What to build:** Build a versioned dataset manifest that joins R1 paper-exported OfflineTransitions with a pinned historical transition set. Non-trainable rows are excluded or marked quarantined; the mix gets a stable content hash so train jobs can pin exactly what they consumed.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Manifest lists paper-run transition ids and historical transition ids (or content hashes) with versions
- [x] Non-trainable / quarantined rows are not silently treated as train data
- [x] Manifest content hash is stable for identical inputs
- [x] Unit or research-seam test proves a tiny fixture mix builds and hashes
- [x] Fail-closed when required historical pin or paper export is missing
