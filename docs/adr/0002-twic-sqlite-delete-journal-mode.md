# ADR-0002: TWIC SQLite in DELETE journal mode (not WAL)

- **Status:** Accepted
- **Date:** 2026-06-01 (back-dated; decision predates this ADR)
- **Deciders:** Alex
- **Tags:** `backend, db, sqlite, perf, ops`

## Context

The TWIC dataset lives in local SQLite files under `backend/data/twic/` — ~42 GB total across `chess_data.db`, `chess_database.db`, `chess_games.db`, and the derived `games_index.db` (4.35M games, 285M positions, 116K players). It is read-heavy at runtime (analysis lookups, opening trees, player search) and append-/rebuild-heavy during index maintenance (`add_position_index.py`, `incremental_index.py`).

The VPS hosting this database is a 2 vCPU / 4 GB RAM DigitalOcean droplet. Disk is the dominant constraint — both because the dataset is large relative to free space and because WAL files for a database this size can balloon during long-running writes before a checkpoint catches up. We hit this concretely while rebuilding the position index: WAL grew unbounded on the low-memory box, IO stalled, and the rebuild had to be restarted.

SQLite's default journaling is **DELETE** (rollback journal, deleted at commit). The popular alternative is **WAL** (write-ahead log, better for concurrent reads). Choosing between them has direct cost on this box.

## Options considered

1. **WAL (Write-Ahead Logging)** — readers don't block writers, faster commits.
   - Pros: better read/write concurrency; faster small writes; recommended default in most modern SQLite advice.
   - Cons: `.db-wal` and `.db-shm` files persist alongside the database and can grow large during long write transactions; checkpoints add a step in maintenance; on a low-RAM box with multi-hour index rebuilds, the WAL can balloon and exhaust disk before SQLite checkpoints it.
2. **DELETE (rollback journal)** — the SQLite default; journal file written and deleted per transaction.
   - Pros: no persistent WAL file to manage; predictable disk footprint; simpler operationally; no checkpointing logic in scripts.
   - Cons: readers can block during writes; small-write throughput is lower than WAL; not the trendy choice.
3. **MEMORY / OFF journaling** — fastest, but loses durability.
   - Pros: maximum write speed.
   - Cons: any crash mid-write corrupts the DB. Not acceptable for a 42 GB dataset that takes hours to rebuild.

## Decision

We run the TWIC SQLite databases in **DELETE journal mode** with `synchronous=NORMAL` and `temp_store=FILE`. This is set explicitly in the index maintenance scripts (e.g. `backend/scripts/add_position_index.py`) and is the mode the runtime backend opens these files in.

## Consequences

- **Positive:**
  - No WAL/SHM sidecar files growing under the dataset — disk usage is predictable.
  - Long-running rebuilds (`add_position_index.py`, `incremental_index.py`) don't risk filling the disk via WAL growth.
  - One fewer thing to monitor on the VPS.
  - `temp_store=FILE` keeps temp scratch off RAM, which matters on the 4 GB box.
- **Negative:**
  - Concurrent read-while-write is reduced — readers may block during index writes. Acceptable because heavy writes only happen during the weekly TWIC update window (Wed 03:00 UTC), not during normal user traffic.
  - Small-transaction throughput is lower than WAL would give us. Not the bottleneck here — bulk operations dominate.
- **Follow-ups:**
  - If we ever move TWIC off this droplet to a beefier box (or a Postgres backend), revisit. WAL becomes the right call once disk + RAM aren't the constraint.
  - Document the PRAGMA set in `backend/scripts/` as the canonical TWIC connection profile so new scripts don't drift to WAL by accident.

## Notes

- The CLAUDE.md "Important Rules" forbid modifying `backend/data/twic/` files directly — this ADR is the *why* behind that rule.
- Concrete prior-art incident: WAL growth during a position-index rebuild on a similar low-memory machine pushed us to DELETE mode; the inline comment in `backend/scripts/add_position_index.py` (`# DELETE mode — no WAL bloat on low-memory servers`) records the same call at the code level.
