#!/usr/bin/env python3
"""
Position Hash Indexer for TWIC Database

Adds a `game_positions` table to games_index.db that stores a board hash
for every position in every game up to move 40. This enables instant
FEN-based position search using a simple hash lookup.

Prerequisites:
    - games_index.db must exist with the `games` table populated
    - python-chess must be installed (`pip install chess`)

Usage:
    python scripts/add_position_index.py

Estimated output: ~15-20GB for 4.3M games (move 1-40 = ~100M+ positions)
Estimated runtime: 2-4 hours depending on CPU
"""

import sqlite3
import chess
import chess.pgn
import io
import os
import sys
import time
import signal

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
PGN_PATH = os.path.join(BACKEND_DIR, "data/twic/twic_master_database.pgn")
DB_PATH = os.path.join(BACKEND_DIR, "data/twic/games_index.db")

MAX_PLY = 80  # Index positions up to move 40 (80 half-moves)
BATCH_SIZE = 5000  # Games per batch commit
PROGRESS_INTERVAL = 10000


def get_board_hash(board: chess.Board) -> str:
    """
    Generate a compact hash of the board position.
    Uses the board part of FEN (pieces only) — this is what we match against.
    Strips move counters so transpositions from different move orders match.
    """
    fen = board.fen()
    # Use first 4 parts: pieces, side-to-move, castling, en-passant
    parts = fen.split(' ')
    return ' '.join(parts[:4])


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run index_pgn_database.py first!")
        sys.exit(1)

    if not os.path.exists(PGN_PATH):
        print(f"ERROR: PGN file not found at {PGN_PATH}")
        sys.exit(1)

    # Parse --fresh flag (only way to drop table)
    fresh = '--fresh' in sys.argv

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-32000")  # 32MB cache (keep memory low)
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA wal_autocheckpoint=1000")  # Checkpoint WAL frequently

    # Graceful shutdown on SIGTERM
    shutdown_flag = [False]
    def handle_signal(signum, frame):
        print(f"\n  Signal {signum} received — flushing batch and exiting gracefully...")
        shutdown_flag[0] = True
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Check if table already exists
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='game_positions'"
    ).fetchone()

    resume_from = 0
    if existing:
        count = conn.execute("SELECT COUNT(*) FROM game_positions").fetchone()[0]
        max_id = conn.execute("SELECT COALESCE(MAX(game_id), 0) FROM game_positions").fetchone()[0]
        print(f"game_positions table exists: {count:,} rows, max game_id={max_id:,}")
        if fresh:
            print("--fresh flag: dropping and rebuilding.")
            conn.execute("DROP TABLE game_positions")
            conn.commit()
        else:
            # Resume mode: skip games already indexed
            resume_from = max_id
            print(f"Resuming from game_id > {resume_from:,}")
    
    if not existing or fresh:
        conn.execute('''
            CREATE TABLE game_positions (
                game_id INTEGER NOT NULL,
                ply INTEGER NOT NULL,
                board_hash TEXT NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games(id)
            )
        ''')
        conn.commit()
        print("Created game_positions table.")

    # Get total games count
    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    remaining = conn.execute("SELECT COUNT(*) FROM games WHERE id > ?", (resume_from,)).fetchone()[0]
    print(f"Total games: {total_games:,} | Remaining: {remaining:,}")

    if total_games == 0:
        print("No games found. Run index_pgn_database.py first!")
        sys.exit(1)

    if remaining == 0:
        print("All games already indexed! Nothing to do.")
        print("Use --fresh to rebuild from scratch.")
        sys.exit(0)

    # Process games
    start_time = time.time()
    games_processed = 0
    positions_inserted = 0
    errors = 0
    batch = []

    # Read games with their PGN offsets (resume-aware)
    cursor = conn.execute(
        "SELECT id, pgn_offset, pgn_length FROM games WHERE id > ? ORDER BY id",
        (resume_from,)
    )

    with open(PGN_PATH, 'r', errors='replace') as pgn_file:
        for game_id, pgn_offset, pgn_length in cursor:
            if shutdown_flag[0]:
                print(f"\n  Graceful shutdown — flushing {len(batch)} pending records...")
                break

            try:
                # Read PGN from file
                pgn_file.seek(pgn_offset)
                pgn_text = pgn_file.read(pgn_length)

                # Parse game
                game = chess.pgn.read_game(io.StringIO(pgn_text))
                if game is None:
                    errors += 1
                    continue

                # Walk through moves and hash each position
                board = game.board()
                ply = 0

                # Index starting position
                board_hash = get_board_hash(board)
                batch.append((game_id, ply, board_hash))

                for move in game.mainline_moves():
                    board.push(move)
                    ply += 1

                    if ply > MAX_PLY:
                        break

                    board_hash = get_board_hash(board)
                    batch.append((game_id, ply, board_hash))

                positions_inserted += ply + 1

            except Exception as e:
                errors += 1
                if errors <= 10:
                    print(f"  Error on game {game_id}: {e}")

            games_processed += 1

            # Batch insert (keep batches small to limit memory)
            if len(batch) >= BATCH_SIZE * 10:
                conn.executemany(
                    "INSERT INTO game_positions (game_id, ply, board_hash) VALUES (?, ?, ?)",
                    batch
                )
                conn.commit()
                batch = []

            # Progress
            if games_processed % PROGRESS_INTERVAL == 0:
                elapsed = time.time() - start_time
                rate = games_processed / elapsed
                eta = (remaining - games_processed) / rate if rate > 0 else 0
                overall_pct = ((resume_from + games_processed) / total_games) * 100
                print(
                    f"  [{overall_pct:.1f}%] {resume_from + games_processed:,}/{total_games:,} games | "
                    f"{positions_inserted:,} new positions | "
                    f"{rate:.0f} games/sec | "
                    f"ETA: {eta/60:.0f} min | "
                    f"Errors: {errors}",
                    flush=True
                )

    # Final batch
    if batch:
        conn.executemany(
            "INSERT INTO game_positions (game_id, ply, board_hash) VALUES (?, ?, ?)",
            batch
        )
        conn.commit()

    elapsed = time.time() - start_time
    print(f"\n=== Position indexing complete ===")
    print(f"Games processed: {games_processed:,}")
    print(f"Positions indexed: {positions_inserted:,}")
    print(f"Errors: {errors}")
    print(f"Time: {elapsed/60:.1f} minutes")

    # Build indexes
    print("\nBuilding indexes (this may take a while)...")

    print("  Creating index on board_hash...")
    t = time.time()
    conn.execute("CREATE INDEX idx_positions_hash ON game_positions(board_hash)")
    conn.commit()
    print(f"  Done in {time.time()-t:.1f}s")

    print("  Creating index on game_id...")
    t = time.time()
    conn.execute("CREATE INDEX idx_positions_game ON game_positions(game_id)")
    conn.commit()
    print(f"  Done in {time.time()-t:.1f}s")

    # Final stats
    db_size = os.path.getsize(DB_PATH)
    print(f"\nDatabase size: {db_size / (1024**3):.2f} GB")
    print("Done! Position search is now available.")


if __name__ == '__main__':
    main()
