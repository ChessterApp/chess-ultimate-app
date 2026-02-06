#!/usr/bin/env python3
"""
PGN Database Indexer for TWIC Master Database

Parses the TWIC master database (3.6GB, ~4.3M games) and creates a SQLite index
for fast searching by player name, ELO, date, ECO, and other criteria.

Usage:
    python scripts/index_pgn_database.py

The indexer stores byte offsets to the original PGN file, allowing on-demand
retrieval of full game PGN without duplicating the data.

Estimated runtime: 15-30 minutes for 4.3M games
Output: data/twic/games_index.db (~500MB)
"""

import sqlite3
import re
import os
import sys
import time
import unicodedata
from typing import Dict, Optional, Tuple, Generator
from datetime import datetime

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
PGN_PATH = os.path.join(BACKEND_DIR, "data/twic/twic_master_database.pgn")
DB_PATH = os.path.join(BACKEND_DIR, "data/twic/games_index.db")

# Batch size for commits (balance between speed and memory)
BATCH_SIZE = 10000

# Progress reporting interval
PROGRESS_INTERVAL = 50000


def normalize_name(name: str) -> str:
    """
    Normalize player name for searching.
    - Convert to lowercase
    - Remove accents/diacritics
    - Remove commas and extra spaces
    - Handle "Lastname,Firstname" format
    """
    if not name:
        return ""

    # Remove accents/diacritics
    normalized = unicodedata.normalize('NFKD', name)
    normalized = ''.join(c for c in normalized if not unicodedata.combining(c))

    # Lowercase and clean
    normalized = normalized.lower()
    normalized = normalized.replace(",", " ").replace("  ", " ").strip()

    return normalized


def parse_elo(elo_str: str) -> Optional[int]:
    """Parse ELO string to integer, handling missing/invalid values."""
    if not elo_str or elo_str == "?" or elo_str == "0":
        return None
    try:
        return int(elo_str)
    except ValueError:
        return None


def extract_year(date_str: str) -> Optional[int]:
    """Extract year from PGN date format (YYYY.MM.DD)."""
    if not date_str or date_str.startswith("?"):
        return None
    try:
        return int(date_str.split(".")[0])
    except (ValueError, IndexError):
        return None


def create_database(db_path: str) -> sqlite3.Connection:
    """Create SQLite database with schema for game indexing."""

    # Remove existing database if present
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Main games table
    cursor.execute('''
        CREATE TABLE games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            white_name TEXT NOT NULL,
            white_name_normalized TEXT NOT NULL,
            black_name TEXT NOT NULL,
            black_name_normalized TEXT NOT NULL,
            white_elo INTEGER,
            black_elo INTEGER,
            white_title TEXT,
            black_title TEXT,
            white_fide_id TEXT,
            black_fide_id TEXT,
            result TEXT,
            date TEXT,
            year INTEGER,
            eco TEXT,
            opening TEXT,
            variation TEXT,
            event TEXT,
            site TEXT,
            round TEXT,
            pgn_offset INTEGER NOT NULL,
            pgn_length INTEGER NOT NULL
        )
    ''')

    # Players aggregation table
    cursor.execute('''
        CREATE TABLE players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            name_normalized TEXT NOT NULL,
            fide_id TEXT,
            title TEXT,
            highest_elo INTEGER,
            latest_elo INTEGER,
            latest_date TEXT,
            total_games INTEGER DEFAULT 0,
            wins_white INTEGER DEFAULT 0,
            wins_black INTEGER DEFAULT 0,
            losses_white INTEGER DEFAULT 0,
            losses_black INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0,
            first_game_date TEXT,
            last_game_date TEXT
        )
    ''')

    # Metadata table for tracking index status
    cursor.execute('''
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    conn.commit()
    print("Database schema created successfully")
    return conn


def create_indexes(conn: sqlite3.Connection):
    """Create indexes after data insertion for better performance."""
    cursor = conn.cursor()

    print("Creating indexes (this may take a few minutes)...")

    # Games table indexes
    indexes = [
        ("idx_white_name", "games(white_name_normalized)"),
        ("idx_black_name", "games(black_name_normalized)"),
        ("idx_white_elo", "games(white_elo)"),
        ("idx_black_elo", "games(black_elo)"),
        ("idx_date", "games(date)"),
        ("idx_year", "games(year)"),
        ("idx_eco", "games(eco)"),
        ("idx_result", "games(result)"),
        ("idx_white_fide", "games(white_fide_id)"),
        ("idx_black_fide", "games(black_fide_id)"),
        ("idx_event", "games(event)"),
    ]

    for idx_name, idx_def in indexes:
        print(f"  Creating {idx_name}...")
        cursor.execute(f"CREATE INDEX {idx_name} ON {idx_def}")

    # Players table indexes
    cursor.execute("CREATE INDEX idx_player_name ON players(name_normalized)")
    cursor.execute("CREATE INDEX idx_player_fide ON players(fide_id)")
    cursor.execute("CREATE INDEX idx_player_elo ON players(highest_elo)")

    conn.commit()
    print("All indexes created successfully")


def create_fts_index(conn: sqlite3.Connection):
    """Create full-text search index for player names."""
    cursor = conn.cursor()

    print("Creating full-text search index...")

    # Create FTS5 virtual table for player search
    cursor.execute('''
        CREATE VIRTUAL TABLE players_fts USING fts5(
            name,
            name_normalized,
            content='players',
            content_rowid='id'
        )
    ''')

    # Populate FTS index
    cursor.execute('''
        INSERT INTO players_fts(rowid, name, name_normalized)
        SELECT id, name, name_normalized FROM players
    ''')

    conn.commit()
    print("Full-text search index created")


def parse_pgn_games(pgn_path: str) -> Generator[Tuple[Dict[str, str], int, int], None, None]:
    """
    Generator that yields (headers_dict, byte_offset, pgn_length) for each game.
    Uses streaming to handle large files efficiently.
    """

    with open(pgn_path, 'rb') as f:
        game_start = 0
        headers = {}
        in_headers = False
        current_line_start = 0

        while True:
            line_bytes = f.readline()
            if not line_bytes:
                break

            try:
                line = line_bytes.decode('utf-8', errors='replace').strip()
            except:
                line = line_bytes.decode('latin-1', errors='replace').strip()

            # Detect start of new game (Event header)
            if line.startswith('[Event '):
                # If we have a previous game, yield it
                if headers and 'Event' in headers:
                    game_end = current_line_start
                    yield (headers, game_start, game_end - game_start)

                # Start new game
                game_start = current_line_start
                headers = {}
                in_headers = True

            # Parse header lines
            if line.startswith('[') and line.endswith(']'):
                match = re.match(r'\[(\w+)\s+"([^"]*)"\]', line)
                if match:
                    headers[match.group(1)] = match.group(2)

            current_line_start = f.tell()

        # Yield last game
        if headers and 'Event' in headers:
            yield (headers, game_start, current_line_start - game_start)


def update_player_stats(cursor: sqlite3.Connection, player_data: dict):
    """Update or insert player statistics."""

    name = player_data['name']
    name_normalized = player_data['name_normalized']

    # Check if player exists
    cursor.execute(
        "SELECT id, highest_elo, latest_date, total_games, wins_white, wins_black, "
        "losses_white, losses_black, draws, first_game_date, last_game_date "
        "FROM players WHERE name = ?",
        (name,)
    )
    existing = cursor.fetchone()

    if existing:
        # Update existing player
        player_id, highest_elo, latest_date, total_games, wins_w, wins_b, losses_w, losses_b, draws, first_date, last_date = existing

        new_highest = max(highest_elo or 0, player_data.get('elo') or 0) or None
        new_total = total_games + 1

        # Update wins/losses/draws based on color and result
        if player_data['color'] == 'white':
            if player_data['result'] == '1-0':
                wins_w += 1
            elif player_data['result'] == '0-1':
                losses_w += 1
            elif player_data['result'] == '1/2-1/2':
                draws += 1
        else:  # black
            if player_data['result'] == '0-1':
                wins_b += 1
            elif player_data['result'] == '1-0':
                losses_b += 1
            elif player_data['result'] == '1/2-1/2':
                draws += 1

        # Update date range
        game_date = player_data.get('date', '')
        if game_date and (not first_date or game_date < first_date):
            first_date = game_date
        if game_date and (not last_date or game_date > last_date):
            last_date = game_date

        # Update latest ELO if this is a more recent game
        new_latest_elo = existing[1]  # Keep existing
        new_latest_date = latest_date
        if game_date and player_data.get('elo'):
            if not latest_date or game_date >= latest_date:
                new_latest_elo = player_data['elo']
                new_latest_date = game_date

        cursor.execute('''
            UPDATE players SET
                highest_elo = ?,
                latest_elo = ?,
                latest_date = ?,
                total_games = ?,
                wins_white = ?,
                wins_black = ?,
                losses_white = ?,
                losses_black = ?,
                draws = ?,
                first_game_date = ?,
                last_game_date = ?,
                fide_id = COALESCE(fide_id, ?),
                title = COALESCE(title, ?)
            WHERE id = ?
        ''', (
            new_highest, new_latest_elo, new_latest_date, new_total,
            wins_w, wins_b, losses_w, losses_b, draws,
            first_date, last_date,
            player_data.get('fide_id'), player_data.get('title'),
            player_id
        ))
    else:
        # Insert new player
        wins_w = wins_b = losses_w = losses_b = draws = 0
        if player_data['color'] == 'white':
            if player_data['result'] == '1-0':
                wins_w = 1
            elif player_data['result'] == '0-1':
                losses_w = 1
            elif player_data['result'] == '1/2-1/2':
                draws = 1
        else:
            if player_data['result'] == '0-1':
                wins_b = 1
            elif player_data['result'] == '1-0':
                losses_b = 1
            elif player_data['result'] == '1/2-1/2':
                draws = 1

        cursor.execute('''
            INSERT INTO players (
                name, name_normalized, fide_id, title, highest_elo, latest_elo,
                latest_date, total_games, wins_white, wins_black, losses_white,
                losses_black, draws, first_game_date, last_game_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name, name_normalized,
            player_data.get('fide_id'), player_data.get('title'),
            player_data.get('elo'), player_data.get('elo'),
            player_data.get('date'),
            wins_w, wins_b, losses_w, losses_b, draws,
            player_data.get('date'), player_data.get('date')
        ))


def index_database():
    """Main indexing function."""

    print("=" * 60)
    print("TWIC Database Indexer")
    print("=" * 60)

    # Verify PGN file exists
    if not os.path.exists(PGN_PATH):
        print(f"ERROR: PGN file not found: {PGN_PATH}")
        sys.exit(1)

    file_size = os.path.getsize(PGN_PATH)
    print(f"PGN file: {PGN_PATH}")
    print(f"File size: {file_size / (1024**3):.2f} GB")
    print(f"Output: {DB_PATH}")
    print()

    # Create database
    conn = create_database(DB_PATH)
    cursor = conn.cursor()

    # Track progress
    start_time = time.time()
    game_count = 0
    batch_count = 0
    player_cache = {}  # Cache player updates for batch processing

    print("Parsing PGN and inserting games...")
    print()

    for headers, offset, length in parse_pgn_games(PGN_PATH):
        game_count += 1
        batch_count += 1

        # Extract and normalize data
        white_name = headers.get('White', 'Unknown')
        black_name = headers.get('Black', 'Unknown')
        white_norm = normalize_name(white_name)
        black_norm = normalize_name(black_name)

        white_elo = parse_elo(headers.get('WhiteElo', ''))
        black_elo = parse_elo(headers.get('BlackElo', ''))

        date = headers.get('Date', '')
        year = extract_year(date)
        result = headers.get('Result', '*')

        # Insert game record
        cursor.execute('''
            INSERT INTO games (
                white_name, white_name_normalized, black_name, black_name_normalized,
                white_elo, black_elo, white_title, black_title,
                white_fide_id, black_fide_id, result, date, year,
                eco, opening, variation, event, site, round,
                pgn_offset, pgn_length
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            white_name, white_norm, black_name, black_norm,
            white_elo, black_elo,
            headers.get('WhiteTitle', ''), headers.get('BlackTitle', ''),
            headers.get('WhiteFideId', ''), headers.get('BlackFideId', ''),
            result, date, year,
            headers.get('ECO', ''), headers.get('Opening', ''),
            headers.get('Variation', ''), headers.get('Event', ''),
            headers.get('Site', ''), headers.get('Round', ''),
            offset, length
        ))

        # Update player statistics (white)
        update_player_stats(cursor, {
            'name': white_name,
            'name_normalized': white_norm,
            'elo': white_elo,
            'fide_id': headers.get('WhiteFideId', ''),
            'title': headers.get('WhiteTitle', ''),
            'date': date,
            'result': result,
            'color': 'white'
        })

        # Update player statistics (black)
        update_player_stats(cursor, {
            'name': black_name,
            'name_normalized': black_norm,
            'elo': black_elo,
            'fide_id': headers.get('BlackFideId', ''),
            'title': headers.get('BlackTitle', ''),
            'date': date,
            'result': result,
            'color': 'black'
        })

        # Commit in batches
        if batch_count >= BATCH_SIZE:
            conn.commit()
            batch_count = 0

        # Progress report
        if game_count % PROGRESS_INTERVAL == 0:
            elapsed = time.time() - start_time
            rate = game_count / elapsed
            print(f"  Processed {game_count:,} games ({rate:.0f} games/sec)")

    # Final commit
    conn.commit()

    elapsed = time.time() - start_time
    print()
    print(f"Game insertion complete: {game_count:,} games in {elapsed:.1f} seconds")
    print(f"Average rate: {game_count/elapsed:.0f} games/second")
    print()

    # Create indexes
    create_indexes(conn)

    # Create FTS index
    create_fts_index(conn)

    # Get player count
    cursor.execute("SELECT COUNT(*) FROM players")
    player_count = cursor.fetchone()[0]

    # Store metadata
    cursor.execute("INSERT INTO metadata VALUES ('indexed_at', ?)", (datetime.now().isoformat(),))
    cursor.execute("INSERT INTO metadata VALUES ('game_count', ?)", (str(game_count),))
    cursor.execute("INSERT INTO metadata VALUES ('player_count', ?)", (str(player_count),))
    cursor.execute("INSERT INTO metadata VALUES ('pgn_file', ?)", (PGN_PATH,))
    conn.commit()

    # Final stats
    db_size = os.path.getsize(DB_PATH)
    total_time = time.time() - start_time

    print()
    print("=" * 60)
    print("INDEXING COMPLETE")
    print("=" * 60)
    print(f"Total games indexed: {game_count:,}")
    print(f"Unique players: {player_count:,}")
    print(f"Database size: {db_size / (1024**2):.1f} MB")
    print(f"Total time: {total_time/60:.1f} minutes")
    print(f"Output: {DB_PATH}")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    index_database()
