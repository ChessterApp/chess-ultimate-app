# TWIC Database Indexer — Developer Documentation

**Last updated:** 2026-02-08  
**Author:** clawdbot  
**Status:** Phase 1 ✅ Complete | Phase 2 🔄 4.5% (paused)

---

## Overview

The TWIC (The Week in Chess) indexer converts a raw PGN file of 4.35 million grandmaster games into a searchable SQLite database with instant position lookup. It runs in two sequential phases.

**End goal:** Given any chess position (FEN), find all games in the database that reached that position — in milliseconds instead of hours.

---

## Source Data

| Item | Details |
|------|---------|
| **PGN file** | `/root/chess-app/backend/data/twic/twic_master_database.pgn` |
| **Size** | 3.57 GB |
| **Games** | 4,350,122 |
| **Coverage** | TWIC archives — top-level tournament games through late 2025 |

---

## Database

| Item | Details |
|------|---------|
| **Path** | `/root/chess-app/backend/data/twic/games_index.db` |
| **Engine** | SQLite (WAL mode) |
| **Current size** | 3.6 GB |
| **Target size** | ~15-20 GB (when Phase 2 completes) |

### Tables

| Table | Rows | Purpose |
|-------|------|---------|
| `games` | 4,350,122 | Game metadata (players, ELO, date, ECO, result, PGN offset) |
| `players` | 116,718 | Aggregated player stats (wins, losses, draws, ELO history) |
| `players_fts` | — | Full-text search on player names |
| `game_positions` | 13,817,775 | Board hashes for every position up to move 40 (**4.5% complete**) |
| `metadata` | — | Indexer metadata |

### Indexes (18 total)

**On `games`:** `idx_white_name`, `idx_black_name`, `idx_white_elo`, `idx_black_elo`, `idx_date`, `idx_year`, `idx_eco`, `idx_result`, `idx_white_fide`, `idx_black_fide`, `idx_event`

**On `game_positions`:** `idx_positions_hash` (board_hash), `idx_positions_game` (game_id)

**On `players`:** `idx_player_name`, `idx_player_elo`, `idx_player_fide`

---

## Phase 1 — Game Indexing ✅

### Objective

Parse the raw 3.57 GB PGN file and extract structured metadata for each game into a searchable SQLite database. Build player aggregation tables and search indexes.

### Script

**Location:** `/root/chess-app/backend/scripts/index_pgn_database.py`  
**Size:** 13,265 bytes  
**Language:** Python 3

### What it does

1. **[P1] Parse games** — Reads PGN headers (White, Black, WhiteElo, BlackElo, Result, Date, ECO, Event, Site, Round, WhiteFideId, BlackFideId). Records the byte offset and length of each game's PGN text for later retrieval.
2. **[P2] Build indexes** — Creates 11 B-tree indexes on frequently queried columns.
3. **[P3] Player aggregation** — Two-pass aggregation: first inserts all players seen as White, then merges Black-side stats. Calculates total games, wins, losses, draws, highest/latest ELO.
4. **[P4] Full-text search** — Creates an FTS5 virtual table on player names for autocomplete.

### Schema: `games`

```sql
CREATE TABLE games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    white_name TEXT, white_name_normalized TEXT,
    black_name TEXT, black_name_normalized TEXT,
    white_elo INTEGER, black_elo INTEGER,
    white_title TEXT, black_title TEXT,
    white_fide_id TEXT, black_fide_id TEXT,
    result TEXT, date TEXT, year INTEGER,
    eco TEXT, opening TEXT, variation TEXT,
    event TEXT, site TEXT, round TEXT,
    pgn_offset INTEGER, pgn_length INTEGER
);
```

### Schema: `players`

```sql
CREATE TABLE players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE, name_normalized TEXT,
    fide_id TEXT, title TEXT,
    highest_elo INTEGER, latest_elo INTEGER, latest_date TEXT,
    total_games INTEGER,
    wins_white INTEGER, wins_black INTEGER,
    losses_white INTEGER, losses_black INTEGER, draws INTEGER,
    first_game_date TEXT, last_game_date TEXT
);
```

### Safety guard

The script checks if the database already has >4M games before running. If so, it exits with a message instead of wiping data. To force a rebuild, delete the DB file manually or pass `--fresh`.

### Performance

| Metric | Value |
|--------|-------|
| **Parse speed** | ~12,800 games/sec |
| **Total time** | 7.7 minutes |
| **Batch size** | 2,000 games per commit |
| **Output** | 1.6 GB |

### Status: ✅ COMPLETE

All 4,350,122 games parsed, 116,718 players aggregated, 11 game indexes + FTS built.

---

## Phase 2 — Position Indexing 🔄

### Objective

For every game in the database, replay moves 1-40 and record a hash of each board position. This creates a lookup table: given any FEN, find all games that reached that position via a simple hash join — **O(1) lookup** instead of replaying millions of PGN games.

### Script

**Location:** `/root/chess-app/backend/scripts/add_position_index.py`  
**Size:** 8,248 bytes  
**Language:** Python 3  
**Dependencies:** `python-chess` (for PGN parsing and move replay)

### What it does

1. **Read games** — Iterates over all rows in `games` table ordered by `id`. Uses `pgn_offset` and `pgn_length` to seek directly into the PGN file and read each game's moves.
2. **Replay moves** — For each game, replays the mainline up to move 40 (80 half-moves / plies). At each position, computes a board hash.
3. **Store hashes** — Inserts `(game_id, ply, board_hash)` tuples into the `game_positions` table.
4. **Build indexes** — After all games are processed, creates `idx_positions_hash` (on `board_hash`) and `idx_positions_game` (on `game_id`).

### Board Hash Function

```python
def get_board_hash(board: chess.Board) -> str:
    fen = board.fen()
    parts = fen.split(' ')
    return ' '.join(parts[:4])  # pieces + side + castling + en-passant
```

This strips the halfmove and fullmove counters so transpositions from different move orders produce the same hash.

**Example:** `rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3`

### Schema: `game_positions`

```sql
CREATE TABLE game_positions (
    game_id INTEGER NOT NULL,
    ply INTEGER NOT NULL,
    board_hash TEXT NOT NULL,
    FOREIGN KEY (game_id) REFERENCES games(id)
);
CREATE INDEX idx_positions_hash ON game_positions(board_hash);
CREATE INDEX idx_positions_game ON game_positions(game_id);
```

### Resume support

The script detects an existing `game_positions` table, reads `MAX(game_id)`, and resumes from there. No data is lost on restart. Use `--fresh` to drop and rebuild from scratch.

### Graceful shutdown

Handles `SIGTERM` and `SIGINT`: flushes the current batch to disk, commits the transaction, then exits cleanly. This prevents data loss when the process is stopped by the OS or the user.

### Memory management

| Setting | Value | Purpose |
|---------|-------|---------|
| `cache_size` | -32000 (32 MB) | Prevents OOM on 8 GB server |
| `wal_autocheckpoint` | 1000 pages | Keeps WAL file small |
| `synchronous` | NORMAL | Balance speed vs durability |
| `busy_timeout` | 300s | Survives temporary DB locks from backend |
| Batch size | 50,000 rows | Commit frequency |
| Progress interval | 10,000 games | Log frequency |

### Performance

| Metric | Value |
|--------|-------|
| **Speed** | ~130 games/sec |
| **Positions per game** | ~71 (avg, up to 81 max) |
| **Memory usage** | ~70 MB |
| **Estimated total time** | ~9.3 hours for all 4.35M games |
| **Estimated total positions** | ~300M+ rows |
| **Estimated final DB size** | 15-20 GB |

### Current Status: 🔄 4.5% COMPLETE (paused)

| Metric | Value |
|--------|-------|
| **Games indexed** | 195,206 / 4,350,122 |
| **Positions stored** | 13,817,775 |
| **Resume point** | `game_id > 195206` |
| **Time spent so far** | ~25 min of processing (across multiple runs) |
| **Remaining** | ~8.9 hours |

### How to resume

```bash
# From the backend directory
cd /root/chess-app/backend

# Resume (picks up where it left off)
setsid nohup python3 -u scripts/add_position_index.py > /tmp/twic_phase2.log 2>&1 &

# Monitor progress
tail -f /tmp/twic_phase2.log

# Check memory usage
ps -o pid,rss,pcpu -p $(pgrep -f add_position_index)
```

### How to rebuild from scratch

```bash
# Phase 1 (only if games_index.db is missing or corrupted)
rm -f data/twic/games_index.db*
python3 -u scripts/index_pgn_database.py --fresh

# Phase 2 (drop existing positions and reindex)
python3 -u scripts/add_position_index.py --fresh
```

---

## Backend Integration

### File: `/root/chess-app/backend/api/openings.py`

The Debut (openings repertoire) feature uses the position index for game search.

**Key functions:**

| Function | Line | Purpose |
|----------|------|---------|
| `_has_position_index(conn)` | 360 | Checks if `game_positions` table exists |
| `_get_board_hash(fen)` | 367 | Converts FEN to board hash (same algorithm as indexer) |
| `fetch_internal_games_progressive()` | 373 | Main search — uses FAST PATH if index exists, SLOW PATH if not |

### Fast path (with position index)

```sql
SELECT DISTINCT g.* FROM games g
INNER JOIN game_positions gp ON g.id = gp.game_id
WHERE gp.board_hash = ?
ORDER BY g.date DESC
LIMIT ?
```

**Performance:** ~25ms for 84,000 matching games (measured on Jan 30 with full index).

### Slow path (without position index)

Falls back to replaying PGN games one by one, checking if each reaches the target position. Extremely slow — minutes to hours depending on the number of games.

---

## Known Issues & Lessons Learned

### Process management
- **OpenClaw exec cleanup kills child processes.** Always launch with `setsid` to detach from the process group.
- **Sub-agents respawn indexers unpredictably.** Never delegate long-running indexing to sub-agents.
- **Cron jobs and watchdogs can restart processes mid-run.** The `--fresh` guard on Phase 1 prevents accidental data wipes.

### Database concurrency
- **Backend `app.py` can lock the DB.** The indexer now has a 300-second busy timeout instead of crashing immediately.
- **Zombie processes hold WAL locks.** Always check `fuser` on the DB files before diagnosing issues.
- **WAL files can grow to multi-GB.** `wal_autocheckpoint=1000` keeps them manageable.

### Memory
- **OOM killer triggered at 3.8 GB RSS** (on 8 GB server). Reduced SQLite cache from 128MB to 32MB, and commit batch from 150K to 50K rows. Memory now stable at ~70 MB.

### Data integrity
- **DB corruption from concurrent writers.** Two processes writing with different journal modes can corrupt SQLite. Always ensure single-writer access.
- **WAL checkpoint needed after crash.** If the process dies, the WAL file may contain uncommitted data. Run `PRAGMA wal_checkpoint(TRUNCATE)` before restarting.

---

## File Reference

| File | Purpose |
|------|---------|
| `/root/chess-app/backend/data/twic/twic_master_database.pgn` | Raw PGN source (3.57 GB, immutable) |
| `/root/chess-app/backend/data/twic/games_index.db` | SQLite database (3.6 GB, growing) |
| `/root/chess-app/backend/scripts/index_pgn_database.py` | Phase 1 script (game parsing) |
| `/root/chess-app/backend/scripts/add_position_index.py` | Phase 2 script (position hashing) |
| `/root/chess-app/backend/api/openings.py` | Backend API that queries the index |
| `/tmp/twic_phase2.log` | Phase 2 runtime log |
| `/tmp/twic_full_index.log` | Combined Phase 1+2 log (last full run) |

---

## What Remains

1. **Complete Phase 2** — Resume position indexing for remaining 4,154,916 games (~8.9 hours)
2. **Build hash index** — `CREATE INDEX idx_positions_hash` runs automatically at the end of Phase 2
3. **Restart backend** — `systemctl restart chess-backend` to pick up the new index
4. **Verify** — Test FEN search in the Debut feature: should return results in <50ms
5. **Optional: Resume script for Phase 2** — Consider a systemd service or tmux session for reliability
