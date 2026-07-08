#!/usr/bin/env python3
"""
Incremental TWIC Indexer — indexes new PGN files into existing games_index.db,
then indexes positions for the new games.

Usage:
    python3 incremental_index.py /path/to/file1.pgn /path/to/file2.pgn ...
    python3 incremental_index.py --glob '/root/chess-app/backend/data/twic/downloads/twic16{24..36}.pgn'
"""

import sqlite3, re, os, sys, time, gc, traceback, unicodedata, glob
import chess
import chess.pgn
import io

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(BACKEND_DIR, "data/twic/games_index.db")
MASTER_PGN = os.path.join(BACKEND_DIR, "data/twic/twic_master_database.pgn")

sys.path.insert(0, SCRIPT_DIR)
from backfill_pgn_offsets import backfill_master_offsets

BATCH_SIZE = 2000
MAX_PLY = 50


def normalize_name(name):
    if not name: return ""
    n = unicodedata.normalize('NFKD', name)
    n = ''.join(c for c in n if not unicodedata.combining(c))
    return n.lower().replace(",", " ").replace("  ", " ").strip()


def parse_elo(s):
    if not s or s in ("?", "0"): return None
    try: return int(s)
    except: return None


def extract_year(d):
    if not d or d.startswith("?"): return None
    try: return int(d.split(".")[0])
    except: return None


def get_board_hash(board):
    fen = board.fen()
    parts = fen.split(' ')
    return ' '.join(parts[:4])


def parse_pgn_file(path):
    """Parse a single PGN file, yielding (headers, raw_pgn_text) for each game."""
    with open(path, 'rb') as f:
        content = f.read()

    text = content.decode('utf-8', errors='replace')
    # Split into games by [Event lines
    games_raw = re.split(r'\n(?=\[Event )', text)

    for raw in games_raw:
        raw = raw.strip()
        if not raw or not raw.startswith('[Event '):
            continue
        hdr = {}
        for m in re.finditer(r'\[(\w+)\s+"([^"]*)"\]', raw):
            hdr[m.group(1)] = m.group(2)
        if 'Event' in hdr:
            yield hdr, raw


def index_positions_for_game(game_id, pgn_text):
    """Parse PGN text and return list of (game_id, ply, board_hash, move_san) tuples."""
    positions = []
    try:
        game = chess.pgn.read_game(io.StringIO(pgn_text))
        if not game:
            return positions

        board = game.board()
        # Starting position
        positions.append((game_id, 0, get_board_hash(board), None))

        ply = 0
        for move in game.mainline_moves():
            san = board.san(move)
            board.push(move)
            ply += 1
            if ply > MAX_PLY:
                break
            positions.append((game_id, ply, get_board_hash(board), san))
    except Exception:
        pass
    return positions


def main():
    # Collect PGN files from arguments
    pgn_files = []
    for arg in sys.argv[1:]:
        if '*' in arg or '?' in arg:
            pgn_files.extend(sorted(glob.glob(arg)))
        elif os.path.isfile(arg):
            pgn_files.append(arg)
        else:
            print(f"WARNING: {arg} not found, skipping")

    if not pgn_files:
        print("Usage: python3 incremental_index.py file1.pgn file2.pgn ...")
        print("No PGN files provided.")
        sys.exit(1)

    print(f"{'='*50}")
    print(f"Incremental TWIC Indexer")
    print(f"Files: {len(pgn_files)}")
    print(f"DB: {DB_PATH}")
    print(f"{'='*50}")

    # Connect to existing DB
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-256000")
    conn.execute("PRAGMA temp_store=MEMORY")

    existing_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    existing_positions = conn.execute("SELECT COUNT(*) FROM game_positions").fetchone()[0]
    print(f"Existing: {existing_games:,} games, {existing_positions:,} positions")

    # Phase 1: Index games from individual PGN files
    print(f"\n[P1] Indexing games from {len(pgn_files)} PGN files...")
    t0 = time.time()
    cur = conn.cursor()
    new_games = 0
    errs = 0
    game_pgn_texts = {}  # game_id -> pgn_text for position indexing
    batch = []

    # Build set of existing games for dedup (white_normalized, black_normalized, date, event)
    print("  Loading existing game signatures for dedup...", flush=True)
    existing_sigs = set()
    for row in conn.execute("SELECT white_name_normalized, black_name_normalized, date, event FROM games"):
        existing_sigs.add((row[0], row[1], row[2], row[3]))
    print(f"  {len(existing_sigs):,} existing signatures loaded")
    skipped = 0

    for pgn_file in pgn_files:
        fname = os.path.basename(pgn_file)
        file_games = 0
        print(f"  Processing {fname}...", end=" ", flush=True)

        for hdr, raw_pgn in parse_pgn_file(pgn_file):
            try:
                wn = hdr.get('White', 'Unknown')
                bn = hdr.get('Black', 'Unknown')
                d = hdr.get('Date', '')
                sig = (normalize_name(wn), normalize_name(bn), d, hdr.get('Event', ''))
                if sig in existing_sigs:
                    skipped += 1
                    continue
                existing_sigs.add(sig)
                batch.append((wn, normalize_name(wn), bn, normalize_name(bn),
                    parse_elo(hdr.get('WhiteElo', '')), parse_elo(hdr.get('BlackElo', '')),
                    hdr.get('WhiteTitle', ''), hdr.get('BlackTitle', ''),
                    hdr.get('WhiteFideId', ''), hdr.get('BlackFideId', ''),
                    hdr.get('Result', '*'), d, extract_year(d),
                    hdr.get('ECO', ''), hdr.get('Opening', ''),
                    hdr.get('Variation', ''), hdr.get('Event', ''),
                    hdr.get('Site', ''), hdr.get('Round', ''),
                    0, 0,  # pgn_offset, pgn_length — placeholder
                    raw_pgn))  # keep raw PGN for position indexing

                if len(batch) >= BATCH_SIZE:
                    _flush_game_batch(cur, conn, batch, game_pgn_texts)
                    new_games += len(batch)
                    batch = []
                    gc.collect()

                file_games += 1
            except Exception as e:
                errs += 1
                if errs <= 20:
                    print(f"\n  ERR: {e}", flush=True)

        if batch:
            _flush_game_batch(cur, conn, batch, game_pgn_texts)
            new_games += len(batch)
            batch = []

        print(f"{file_games:,} games", flush=True)

    el = time.time() - t0
    print(f"\n[P1] Done: {new_games:,} new games in {el:.1f}s ({skipped:,} duplicates skipped, {errs} errors)")

    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    print(f"Total games now: {total_games:,}")

    # Phase 1.5: Backfill pgn_offset / pgn_length for newly inserted games.
    # Phase 1 inserts (0, 0) placeholders because the position in the master PGN
    # is unknown at INSERT time; this scans the master tail and resolves them by
    # signature so /games/<id>/pgn can seek+read correctly.
    print(f"\n[P1.5] Backfilling pgn_offset/pgn_length from master PGN...")
    t_bf = time.time()
    matched, unmatched = backfill_master_offsets(conn)
    print(f"[P1.5] Done in {time.time() - t_bf:.1f}s (matched={matched:,}, unmatched={unmatched})")

    # Phase 2: Index positions for new games
    print(f"\n[P2] Indexing positions for {len(game_pgn_texts):,} new games...")
    t1 = time.time()
    pos_batch = []
    pos_count = 0
    games_done = 0

    for game_id, pgn_text in game_pgn_texts.items():
        positions = index_positions_for_game(game_id, pgn_text)
        pos_batch.extend(positions)
        pos_count += len(positions)
        games_done += 1

        if len(pos_batch) >= 10000:
            cur.executemany(
                "INSERT INTO game_positions (game_id, ply, board_hash, move_san) VALUES (?,?,?,?)",
                pos_batch)
            conn.commit()
            pos_batch = []
            if games_done % 10000 == 0:
                print(f"  {games_done:,}/{len(game_pgn_texts):,} games, {pos_count:,} positions", flush=True)

    if pos_batch:
        cur.executemany(
            "INSERT INTO game_positions (game_id, ply, board_hash, move_san) VALUES (?,?,?,?)",
            pos_batch)
        conn.commit()

    el2 = time.time() - t1
    print(f"\n[P2] Done: {pos_count:,} positions in {el2:.1f}s")

    # Phase 3: Rebuild players table
    print(f"\n[P3] Rebuilding players...")
    t2 = time.time()
    rebuild_players(conn)
    el3 = time.time() - t2
    print(f"[P3] Done in {el3:.1f}s")

    # Update metadata
    from datetime import datetime
    cur.execute("INSERT OR REPLACE INTO metadata VALUES ('indexed_at',?)", (datetime.now().isoformat(),))
    cur.execute("INSERT OR REPLACE INTO metadata VALUES ('game_count',?)", (str(total_games),))
    player_count = cur.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    cur.execute("INSERT OR REPLACE INTO metadata VALUES ('player_count',?)", (str(player_count),))
    conn.commit()

    total_positions = conn.execute("SELECT COUNT(*) FROM game_positions").fetchone()[0]
    tt = time.time() - t0
    print(f"\n{'='*50}")
    print(f"DONE: +{new_games:,} games, +{pos_count:,} positions")
    print(f"Totals: {total_games:,} games, {total_positions:,} positions")
    print(f"Time: {tt/60:.1f} min")
    print(f"{'='*50}")
    conn.close()


def _flush_game_batch(cur, conn, batch, game_pgn_texts):
    """Insert a batch of games and track their IDs for position indexing."""
    for row in batch:
        # row has 22 elements: 21 columns + raw_pgn
        game_data = row[:21]  # everything except raw_pgn
        raw_pgn = row[21]
        cur.execute('''INSERT INTO games (white_name,white_name_normalized,
            black_name,black_name_normalized,white_elo,black_elo,white_title,
            black_title,white_fide_id,black_fide_id,result,date,year,eco,
            opening,variation,event,site,round,pgn_offset,pgn_length)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', game_data)
        game_id = cur.lastrowid
        game_pgn_texts[game_id] = raw_pgn
    conn.commit()


def rebuild_players(conn):
    """Rebuild players table from all games."""
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS players_fts")
    cur.execute("DROP TABLE IF EXISTS players")
    cur.execute('''CREATE TABLE players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL, name_normalized TEXT NOT NULL,
        fide_id TEXT, title TEXT,
        highest_elo INTEGER, latest_elo INTEGER, latest_date TEXT,
        total_games INTEGER DEFAULT 0,
        wins_white INTEGER DEFAULT 0, wins_black INTEGER DEFAULT 0,
        losses_white INTEGER DEFAULT 0, losses_black INTEGER DEFAULT 0,
        draws INTEGER DEFAULT 0,
        first_game_date TEXT, last_game_date TEXT)''')
    conn.commit()

    print("  White side...", flush=True)
    cur.execute('''INSERT INTO players (name, name_normalized, fide_id, title, highest_elo,
        total_games, wins_white, losses_white, draws, first_game_date, last_game_date)
    SELECT white_name, white_name_normalized, MAX(NULLIF(white_fide_id,'')),
        MAX(NULLIF(white_title,'')), MAX(white_elo), COUNT(*),
        SUM(CASE WHEN result='1-0' THEN 1 ELSE 0 END),
        SUM(CASE WHEN result='0-1' THEN 1 ELSE 0 END),
        SUM(CASE WHEN result='1/2-1/2' THEN 1 ELSE 0 END),
        MIN(date), MAX(date) FROM games GROUP BY white_name''')
    conn.commit()

    print("  Black side merge...", flush=True)
    for row in conn.execute('''SELECT black_name, black_name_normalized,
        MAX(NULLIF(black_fide_id,'')), MAX(NULLIF(black_title,'')),
        MAX(black_elo), COUNT(*),
        SUM(CASE WHEN result='0-1' THEN 1 ELSE 0 END),
        SUM(CASE WHEN result='1-0' THEN 1 ELSE 0 END),
        SUM(CASE WHEN result='1/2-1/2' THEN 1 ELSE 0 END),
        MIN(date), MAX(date) FROM games GROUP BY black_name'''):
        nm, nm_n, fid, ttl, melo, tot, wb, lb, db, fd, ld = row
        cur.execute('''UPDATE players SET total_games=total_games+?, wins_black=?,
            losses_black=?, draws=draws+?,
            highest_elo=MAX(COALESCE(highest_elo,0),?),
            fide_id=COALESCE(fide_id,?), title=COALESCE(title,?),
            first_game_date=MIN(COALESCE(first_game_date,'9999'),?),
            last_game_date=MAX(COALESCE(last_game_date,''),?)
        WHERE name=?''', (tot, wb, lb, db, melo or 0, fid, ttl, fd or '9999', ld or '', nm))
        if cur.rowcount == 0:
            cur.execute('''INSERT INTO players (name, name_normalized, fide_id, title,
                highest_elo, total_games, wins_white, wins_black, losses_white, losses_black,
                draws, first_game_date, last_game_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (nm, nm_n, fid, ttl, melo if melo and melo > 0 else None,
                 tot, 0, wb, 0, lb, db, fd, ld))
    conn.commit()

    cur.execute("CREATE INDEX IF NOT EXISTS idx_player_name ON players(name_normalized)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_player_fide ON players(fide_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_player_elo ON players(highest_elo)")
    conn.commit()

    # FTS
    cur.execute('''CREATE VIRTUAL TABLE players_fts USING fts5(
        name, name_normalized, content='players', content_rowid='id')''')
    cur.execute('''INSERT INTO players_fts(rowid, name, name_normalized)
        SELECT id, name, name_normalized FROM players''')
    conn.commit()

    pc = cur.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    print(f"  {pc:,} players", flush=True)


if __name__ == "__main__":
    main()
