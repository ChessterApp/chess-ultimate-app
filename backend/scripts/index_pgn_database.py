#!/usr/bin/env python3
"""TWIC Database Indexer - Robust version"""

import sqlite3, re, os, sys, time, gc, traceback, unicodedata
from datetime import datetime

# SAFETY: Never nuke a working database
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'twic', 'games_index.db')
if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 100_000_000:  # >100MB
    try:
        _c = sqlite3.connect(DB_PATH)
        _g = _c.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        _c.close()
        if _g > 4_000_000:
            print(f"SAFETY: Database already has {_g:,} games ({os.path.getsize(DB_PATH)/1e9:.1f}GB). Phase 1 is DONE.")
            print("If you really need to rebuild, delete the file manually first.")
            sys.exit(0)
    except:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
PGN_PATH = os.path.join(BACKEND_DIR, "data/twic/twic_master_database.pgn")
DB_PATH = os.path.join(BACKEND_DIR, "data/twic/games_index.db")
BATCH_SIZE = 2000
PROGRESS_INTERVAL = 50000

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

def setup_db(path):
    if os.path.exists(path):
        if '--fresh' in sys.argv:
            for ext in ('', '-wal', '-shm', '-journal'):
                p = path + ext
                if os.path.exists(p): os.remove(p)
            print("Removed old DB")
        else:
            try:
                tc = sqlite3.connect(path)
                c = tc.execute("SELECT COUNT(*) FROM games").fetchone()[0]
                tc.close()
                if c > 100000:
                    print(f"DB has {c:,} games. Use --fresh.")
                    sys.exit(0)
            except:
                for ext in ('', '-wal', '-shm', '-journal'):
                    p = path + ext
                    if os.path.exists(p): os.remove(p)

    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-256000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute('''CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        white_name TEXT NOT NULL, white_name_normalized TEXT NOT NULL,
        black_name TEXT NOT NULL, black_name_normalized TEXT NOT NULL,
        white_elo INTEGER, black_elo INTEGER,
        white_title TEXT, black_title TEXT,
        white_fide_id TEXT, black_fide_id TEXT,
        result TEXT, date TEXT, year INTEGER,
        eco TEXT, opening TEXT, variation TEXT,
        event TEXT, site TEXT, round TEXT,
        pgn_offset INTEGER NOT NULL, pgn_length INTEGER NOT NULL)''')
    conn.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)')
    conn.commit()
    print("[OK] Database ready", flush=True)
    return conn

def create_game_indexes(conn):
    print("[IDX] Creating game indexes...", flush=True)
    for name, defn in [
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
    ]:
        print(f"  {name}...", flush=True)
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {defn}")
        conn.commit()
    print("[IDX] Done", flush=True)

def build_players(conn):
    cur = conn.cursor()
    print("[PLR] Building players...", flush=True)
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
    wc = cur.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    print(f"  {wc:,} from white", flush=True)

    print("  Black side merge...", flush=True)
    cur2 = conn.cursor()
    cur2.execute('''SELECT black_name, black_name_normalized,
        MAX(NULLIF(black_fide_id,'')), MAX(NULLIF(black_title,'')),
        MAX(black_elo), COUNT(*),
        SUM(CASE WHEN result='0-1' THEN 1 ELSE 0 END),
        SUM(CASE WHEN result='1-0' THEN 1 ELSE 0 END),
        SUM(CASE WHEN result='1/2-1/2' THEN 1 ELSE 0 END),
        MIN(date), MAX(date) FROM games GROUP BY black_name''')

    upd = ins = 0
    new_batch = []
    for row in cur2:
        nm, nm_n, fid, ttl, melo, tot, wb, lb, db, fd, ld = row
        cur.execute('''UPDATE players SET total_games=total_games+?, wins_black=?,
            losses_black=?, draws=draws+?,
            highest_elo=MAX(COALESCE(highest_elo,0),?),
            fide_id=COALESCE(fide_id,?), title=COALESCE(title,?),
            first_game_date=MIN(COALESCE(first_game_date,'9999'),?),
            last_game_date=MAX(COALESCE(last_game_date,''),?)
        WHERE name=?''', (tot, wb, lb, db, melo or 0, fid, ttl, fd or '9999', ld or '', nm))
        if cur.rowcount == 0:
            new_batch.append((nm, nm_n, fid, ttl,
                melo if melo and melo > 0 else None,
                tot, 0, wb, 0, lb, db, fd, ld))
            ins += 1
        else:
            upd += 1
        if len(new_batch) >= 5000:
            cur.executemany('''INSERT INTO players (name, name_normalized, fide_id, title,
                highest_elo, total_games, wins_white, wins_black, losses_white, losses_black,
                draws, first_game_date, last_game_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', new_batch)
            new_batch = []
            conn.commit()
        if (upd+ins) % 100000 == 0 and (upd+ins) > 0:
            print(f"  {upd+ins:,} (upd:{upd:,} new:{ins:,})", flush=True)
            conn.commit()
    if new_batch:
        cur.executemany('''INSERT INTO players (name, name_normalized, fide_id, title,
            highest_elo, total_games, wins_white, wins_black, losses_white, losses_black,
            draws, first_game_date, last_game_date)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', new_batch)
    conn.commit()
    print(f"  Upd:{upd:,} New:{ins:,}", flush=True)

    print("  Player indexes...", flush=True)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_player_name ON players(name_normalized)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_player_fide ON players(fide_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_player_elo ON players(highest_elo)")
    conn.commit()
    pc = cur.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    print(f"[PLR] {pc:,} players", flush=True)
    return pc

def create_fts(conn):
    print("[FTS] Creating...", flush=True)
    conn.execute("DROP TABLE IF EXISTS players_fts")
    conn.execute('''CREATE VIRTUAL TABLE players_fts USING fts5(
        name, name_normalized, content='players', content_rowid='id')''')
    conn.execute('''INSERT INTO players_fts(rowid, name, name_normalized)
        SELECT id, name, name_normalized FROM players''')
    conn.commit()
    print("[FTS] Done", flush=True)

def parse_pgn(path):
    with open(path, 'rb') as f:
        gs = 0; hdr = {}; pos = 0
        while True:
            lb = f.readline()
            if not lb: break
            try: line = lb.decode('utf-8', errors='replace').strip()
            except: line = lb.decode('latin-1', errors='replace').strip()
            if line.startswith('[Event '):
                if hdr and 'Event' in hdr:
                    yield (hdr, gs, pos - gs)
                gs = pos; hdr = {}
            if line.startswith('[') and line.endswith(']'):
                m = re.match(r'\[(\w+)\s+"([^"]*)"\]', line)
                if m: hdr[m.group(1)] = m.group(2)
            pos = f.tell()
        if hdr and 'Event' in hdr:
            yield (hdr, gs, pos - gs)

def main():
    print("=" * 50, flush=True)
    print("TWIC Indexer (robust)", flush=True)
    print("=" * 50, flush=True)
    if not os.path.exists(PGN_PATH):
        print(f"ERROR: {PGN_PATH} not found"); sys.exit(1)
    fsz = os.path.getsize(PGN_PATH)
    print(f"PGN: {fsz/(1024**3):.2f} GB", flush=True)

    conn = setup_db(DB_PATH)
    cur = conn.cursor()
    t0 = time.time(); gc_count = 0; errs = 0; batch = []

    print("\n[P1] Parsing games...", flush=True)
    try:
        for hdr, off, ln in parse_pgn(PGN_PATH):
            gc_count += 1
            try:
                wn = hdr.get('White','Unknown'); bn = hdr.get('Black','Unknown')
                d = hdr.get('Date','')
                batch.append((wn, normalize_name(wn), bn, normalize_name(bn),
                    parse_elo(hdr.get('WhiteElo','')), parse_elo(hdr.get('BlackElo','')),
                    hdr.get('WhiteTitle',''), hdr.get('BlackTitle',''),
                    hdr.get('WhiteFideId',''), hdr.get('BlackFideId',''),
                    hdr.get('Result','*'), d, extract_year(d),
                    hdr.get('ECO',''), hdr.get('Opening',''),
                    hdr.get('Variation',''), hdr.get('Event',''),
                    hdr.get('Site',''), hdr.get('Round',''), off, ln))
                if len(batch) >= BATCH_SIZE:
                    cur.executemany('''INSERT INTO games (white_name,white_name_normalized,
                        black_name,black_name_normalized,white_elo,black_elo,white_title,
                        black_title,white_fide_id,black_fide_id,result,date,year,eco,
                        opening,variation,event,site,round,pgn_offset,pgn_length)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', batch)
                    conn.commit(); batch = []
                    if gc_count % (BATCH_SIZE * 50) == 0: gc.collect()
                if gc_count % PROGRESS_INTERVAL == 0:
                    el = time.time()-t0; rt = gc_count/el
                    pct = (off/fsz)*100
                    print(f"  {gc_count:,} ({pct:.1f}%) | {rt:.0f}/s | err:{errs}", flush=True)
            except Exception as e:
                errs += 1
                if errs <= 20: print(f"  ERR {gc_count}: {e}", flush=True)
        if batch:
            cur.executemany('''INSERT INTO games (white_name,white_name_normalized,
                black_name,black_name_normalized,white_elo,black_elo,white_title,
                black_title,white_fide_id,black_fide_id,result,date,year,eco,
                opening,variation,event,site,round,pgn_offset,pgn_length)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', batch)
            conn.commit()
    except Exception as e:
        print(f"\nFATAL at {gc_count}: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        try: conn.commit()
        except: pass
        sys.exit(1)

    el = time.time()-t0
    print(f"\n[P1] Done: {gc_count:,} games, {el:.0f}s, {gc_count/max(el,1):.0f}/s", flush=True)

    print("\n[P2] Indexes...", flush=True)
    create_game_indexes(conn); gc.collect()

    print("\n[P3] Players...", flush=True)
    pc = build_players(conn); gc.collect()

    print("\n[P4] FTS...", flush=True)
    create_fts(conn)

    cur.execute("INSERT OR REPLACE INTO metadata VALUES ('indexed_at',?)", (datetime.now().isoformat(),))
    cur.execute("INSERT OR REPLACE INTO metadata VALUES ('game_count',?)", (str(gc_count),))
    cur.execute("INSERT OR REPLACE INTO metadata VALUES ('player_count',?)", (str(pc),))
    conn.commit()

    dsz = os.path.getsize(DB_PATH)
    tt = time.time()-t0
    print(f"\n{'='*50}", flush=True)
    print(f"DONE: {gc_count:,} games, {pc:,} players", flush=True)
    print(f"DB: {dsz/(1024**2):.0f} MB | Time: {tt/60:.1f} min", flush=True)
    print(f"{'='*50}", flush=True)
    conn.close()

if __name__ == "__main__":
    main()
