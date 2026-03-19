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
    python scripts/add_position_index.py                    # Full indexing (resume mode)
    python scripts/add_position_index.py --start-game-id 1 --end-game-id 100000  # Chunk mode
    python scripts/add_position_index.py --fresh            # Rebuild from scratch
"""

import sqlite3
import chess
import chess.pgn
import io
import os
import sys
import time
import signal
import argparse

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
PGN_PATH = os.path.join(BACKEND_DIR, "data/twic/twic_master_database.pgn")
DB_PATH = os.path.join(BACKEND_DIR, "data/twic/games_index.db")

MAX_PLY = 50  # Index positions up to move 25 (50 half-moves)
BATCH_SIZE = 2000  # Games per batch commit (reduced for memory)
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
    # Parse arguments
    parser = argparse.ArgumentParser(
        description='Index chess positions from TWIC database',
        epilog='Examples:\n'
               '  %(prog)s                                    # Resume from last game\n'
               '  %(prog)s --start-game-id 1 --end-game-id 100000 --nice-level 15  # Chunk mode\n'
               '  %(prog)s --fresh                            # Rebuild from scratch',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--start-game-id', type=int, default=None,
                        help='Start game ID for this chunk (inclusive)')
    parser.add_argument('--end-game-id', type=int, default=None,
                        help='End game ID for this chunk (inclusive)')
    parser.add_argument('--nice-level', type=int, default=10,
                        help='Process nice level 0-19 (higher = lower priority)')
    parser.add_argument('--fresh', action='store_true',
                        help='Rebuild from scratch (drop existing table)')
    
    args = parser.parse_args()
    
    # Set process priority
    if args.nice_level > 0:
        try:
            os.nice(args.nice_level)
            print(f"[index] Set process nice level to {args.nice_level}")
        except Exception as e:
            print(f"[index] Warning: Could not set nice level: {e}")
    
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run index_pgn_database.py first!")
        sys.exit(1)

    if not os.path.exists(PGN_PATH):
        print(f"ERROR: PGN file not found at {PGN_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH, timeout=300)  # 5 min busy timeout
    conn.execute("PRAGMA journal_mode=DELETE")  # DELETE mode — no WAL bloat on low-memory servers
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-16000")  # 16MB cache (low memory server)
    conn.execute("PRAGMA temp_store=FILE")  # Use disk for temp, save RAM
    # No WAL autocheckpoint needed — using DELETE journal mode

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
        print(f"[index] game_positions table exists: {count:,} rows, max game_id={max_id:,}")
        if args.fresh:
            print("[index] --fresh flag: dropping and rebuilding.")
            conn.execute("DROP TABLE game_positions")
            conn.commit()
        else:
            # Resume mode: skip games already indexed (unless in chunk mode)
            if args.start_game_id is None:
                resume_from = max_id
                print(f"[index] Resuming from game_id > {resume_from:,}")
    
    if not existing or args.fresh:
        conn.execute('''
            CREATE TABLE game_positions (
                game_id INTEGER NOT NULL,
                ply INTEGER NOT NULL,
                board_hash TEXT NOT NULL,
                move_san TEXT,
                FOREIGN KEY (game_id) REFERENCES games(id)
            )
        ''')
        conn.commit()
        print("[index] Created game_positions table.")

    # Get total games count
    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    
    # Determine game range
    if args.start_game_id and args.end_game_id:
        # Chunk mode
        range_start = args.start_game_id
        range_end = args.end_game_id
        remaining = conn.execute(
            "SELECT COUNT(*) FROM games WHERE id >= ? AND id <= ?",
            (range_start, range_end)
        ).fetchone()[0]
        mode_str = f"CHUNK mode: games {range_start:,} to {range_end:,}"
    else:
        # Resume mode
        range_start = resume_from + 1
        range_end = total_games
        remaining = conn.execute(
            "SELECT COUNT(*) FROM games WHERE id > ?",
            (resume_from,)
        ).fetchone()[0]
        mode_str = f"RESUME mode: from game {range_start:,}"
    
    print(f"[index] {mode_str}")
    print(f"[index] Total games: {total_games:,} | Remaining: {remaining:,}")

    if total_games == 0:
        print("[index] No games found. Run index_pgn_database.py first!")
        sys.exit(1)

    if remaining == 0:
        print("[index] All games in range already indexed! Nothing to do.")
        sys.exit(0)

    # Process games
    start_time = time.time()
    games_processed = 0
    positions_inserted = 0
    errors = 0
    batch = []

    # Read games with their PGN offsets
    if args.start_game_id and args.end_game_id:
        query = "SELECT id, pgn_offset, pgn_length FROM games WHERE id >= ? AND id <= ? ORDER BY id"
        params = (args.start_game_id, args.end_game_id)
    else:
        query = "SELECT id, pgn_offset, pgn_length FROM games WHERE id > ? ORDER BY id"
        params = (resume_from,)
    
    cursor = conn.execute(query, params)

    with open(PGN_PATH, 'r', errors='replace') as pgn_file:
        for game_id, pgn_offset, pgn_length in cursor:
            if shutdown_flag[0]:
                print(f"\n[index] Graceful shutdown — flushing {len(batch)} pending records...")
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

                # Collect all mainline moves to look ahead for move_san
                moves = list(game.mainline_moves())

                # Index starting position (move_san = the first move played)
                board_hash = get_board_hash(board)
                move_san = board.san(moves[0]) if moves else None
                batch.append((game_id, ply, board_hash, move_san))

                for i, move in enumerate(moves):
                    board.push(move)
                    ply += 1

                    if ply > MAX_PLY:
                        break

                    board_hash = get_board_hash(board)
                    # move_san = the next move played from this position
                    next_san = board.san(moves[i + 1]) if i + 1 < len(moves) else None
                    batch.append((game_id, ply, board_hash, next_san))

                positions_inserted += ply + 1

            except Exception as e:
                errors += 1
                if errors <= 10:
                    print(f"[index] Error on game {game_id}: {e}")

            games_processed += 1

            # Batch insert (keep batches small to limit memory)
            if len(batch) >= BATCH_SIZE * 5:
                conn.executemany(
                    "INSERT INTO game_positions (game_id, ply, board_hash, move_san) VALUES (?, ?, ?, ?)",
                    batch
                )
                conn.commit()
                batch = []

            # Progress
            if games_processed % PROGRESS_INTERVAL == 0:
                elapsed = time.time() - start_time
                rate = games_processed / elapsed
                eta = (remaining - games_processed) / rate if rate > 0 else 0
                
                if args.start_game_id:
                    # Chunk mode progress
                    chunk_size = args.end_game_id - args.start_game_id + 1
                    chunk_pct = (games_processed / chunk_size) * 100
                    print(
                        f"[index] Chunk progress: {chunk_pct:.1f}% ({games_processed:,}/{chunk_size:,}) | "
                        f"{positions_inserted:,} positions | "
                        f"{rate:.0f} games/sec | "
                        f"ETA: {eta/60:.0f} min",
                        flush=True
                    )
                else:
                    # Resume mode progress
                    overall_pct = ((resume_from + games_processed) / total_games) * 100
                    print(
                        f"[index] [{overall_pct:.1f}%] {resume_from + games_processed:,}/{total_games:,} games | "
                        f"{positions_inserted:,} positions | "
                        f"{rate:.0f} games/sec | "
                        f"ETA: {eta/60:.0f} min",
                        flush=True
                    )

    # Final batch
    if batch:
        conn.executemany(
            "INSERT INTO game_positions (game_id, ply, board_hash, move_san) VALUES (?, ?, ?, ?)",
            batch
        )
        conn.commit()

    elapsed = time.time() - start_time
    print(f"\n[index] === Position indexing complete ===")
    print(f"[index] Games processed: {games_processed:,}")
    print(f"[index] Positions stored: {positions_inserted:,}")
    print(f"[index] Errors: {errors}")
    print(f"[index] Time: {elapsed/60:.1f} minutes")

    # Only build indexes if NOT in chunk mode (indexes are built after all chunks complete)
    if not args.start_game_id:
        print("\n[index] Building indexes (this may take a while)...")

        try:
            print("[index]   Creating index on board_hash...")
            t = time.time()
            conn.execute("CREATE INDEX idx_positions_hash ON game_positions(board_hash)")
            conn.commit()
            print(f"[index]   Done in {time.time()-t:.1f}s")
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                print("[index]   Index already exists, skipping")
            else:
                raise

        try:
            print("[index]   Creating index on game_id...")
            t = time.time()
            conn.execute("CREATE INDEX idx_positions_game ON game_positions(game_id)")
            conn.commit()
            print(f"[index]   Done in {time.time()-t:.1f}s")
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                print("[index]   Index already exists, skipping")
            else:
                raise

    # Final stats
    try:
        db_size = os.path.getsize(DB_PATH)
        print(f"\n[index] Database size: {db_size / (1024**3):.2f} GB")
    except:
        pass
    
    print("[index] Done!")


if __name__ == '__main__':
    main()
