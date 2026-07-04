#!/usr/bin/env python3
"""Incremental TWIC indexer - adds only new games from a known offset."""

import sqlite3, re, os, sys, time, gc, unicodedata
from datetime import datetime

DB_PATH = '/root/chess-app/backend/data/twic/games_index.db'
PGN_PATH = '/root/chess-app/backend/data/twic/twic_master_database.pgn'
BATCH_SIZE = 2000

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

def parse_pgn_from_offset(path, start_offset):
    """Parse PGN file starting from a byte offset."""
    with open(path, 'rb') as f:
        f.seek(start_offset)
        hdr = {}
        game_start = start_offset
        pos = start_offset
        
        while True:
            lb = f.readline()
            if not lb:
                break
            try:
                line = lb.decode('utf-8', errors='replace').strip()
            except:
                line = lb.decode('latin-1', errors='replace').strip()
            
            if line.startswith('[Event '):
                if hdr and 'Event' in hdr:
                    yield (hdr, game_start, pos - game_start)
                game_start = pos
                hdr = {}
            
            if line.startswith('[') and line.endswith(']'):
                m = re.match(r'\[(\w+)\s+"([^"]*)"\]', line)
                if m:
                    hdr[m.group(1)] = m.group(2)
            
            pos = f.tell()
        
        if hdr and 'Event' in hdr:
            yield (hdr, game_start, pos - game_start)

def main():
    print("=" * 50)
    print("TWIC Incremental Indexer")
    print("=" * 50)
    
    if not os.path.exists(DB_PATH):
        print("ERROR: Database not found"); sys.exit(1)
    if not os.path.exists(PGN_PATH):
        print("ERROR: PGN not found"); sys.exit(1)
    
    conn = sqlite3.connect(DB_PATH)
    
    # Verify journal mode is DELETE
    jm = conn.execute('PRAGMA journal_mode').fetchone()[0]
    print(f"Journal mode: {jm}")
    if jm != 'delete':
        print("Switching to DELETE journal mode...")
        conn.execute('PRAGMA journal_mode=DELETE')
    
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA cache_size=-50000')  # ~50MB
    conn.execute('PRAGMA temp_store=MEMORY')
    
    # Get current state
    cur = conn.cursor()
    old_count = cur.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    max_end = cur.execute("SELECT MAX(pgn_offset + pgn_length) FROM games").fetchone()[0]
    
    print(f"Current games: {old_count:,}")
    print(f"Current max PGN end: {max_end:,}")
    
    file_size = os.path.getsize(PGN_PATH)
    print(f"PGN file size: {file_size:,}")
    
    new_bytes = file_size - max_end
    if new_bytes <= 0:
        print("No new data to index!")
        conn.close()
        return
    
    print(f"New data: {new_bytes:,} bytes ({new_bytes/1024/1024:.1f} MB)")
    print(f"Starting parse from offset {max_end:,}...")
    
    t0 = time.time()
    new_games = 0
    errs = 0
    batch = []
    dates_seen = set()
    
    for hdr, off, ln in parse_pgn_from_offset(PGN_PATH, max_end):
        new_games += 1
        try:
            wn = hdr.get('White', 'Unknown')
            bn = hdr.get('Black', 'Unknown')
            d = hdr.get('Date', '')
            if d and not d.startswith('?'):
                dates_seen.add(d)
            
            batch.append((
                wn, normalize_name(wn), bn, normalize_name(bn),
                parse_elo(hdr.get('WhiteElo', '')),
                parse_elo(hdr.get('BlackElo', '')),
                hdr.get('WhiteTitle', ''), hdr.get('BlackTitle', ''),
                hdr.get('WhiteFideId', ''), hdr.get('BlackFideId', ''),
                hdr.get('Result', '*'), d, extract_year(d),
                hdr.get('ECO', ''), hdr.get('Opening', ''),
                hdr.get('Variation', ''), hdr.get('Event', ''),
                hdr.get('Site', ''), hdr.get('Round', ''),
                off, ln
            ))
            
            if len(batch) >= BATCH_SIZE:
                cur.executemany('''INSERT INTO games (white_name,white_name_normalized,
                    black_name,black_name_normalized,white_elo,black_elo,white_title,
                    black_title,white_fide_id,black_fide_id,result,date,year,eco,
                    opening,variation,event,site,round,pgn_offset,pgn_length)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', batch)
                conn.commit()
                batch = []
                if new_games % 10000 == 0:
                    el = time.time() - t0
                    print(f"  {new_games:,} games | {new_games/max(el,1):.0f}/s", flush=True)
                    gc.collect()
        except Exception as e:
            errs += 1
            if errs <= 10:
                print(f"  ERR at game {new_games}: {e}")
    
    if batch:
        cur.executemany('''INSERT INTO games (white_name,white_name_normalized,
            black_name,black_name_normalized,white_elo,black_elo,white_title,
            black_title,white_fide_id,black_fide_id,result,date,year,eco,
            opening,variation,event,site,round,pgn_offset,pgn_length)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', batch)
        conn.commit()
    
    el = time.time() - t0
    new_total = cur.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    
    # Update metadata
    cur.execute("INSERT OR REPLACE INTO metadata VALUES ('indexed_at',?)",
                (datetime.now().isoformat(),))
    cur.execute("INSERT OR REPLACE INTO metadata VALUES ('game_count',?)",
                (str(new_total),))
    conn.commit()

    # Best-effort: tell the backend to drop its stale position-count cache so
    # the debut UI reflects the new game count. Must not fail Phase 1 if the
    # backend is down.
    try:
        import urllib.request
        req = urllib.request.Request(
            'http://127.0.0.1:5001/api/openings/_cache/invalidate',
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            print(f"Cache invalidate: HTTP {resp.status}")
    except Exception as e:
        print(f"Cache invalidate skipped: {e}")

    # Date range
    sorted_dates = sorted(dates_seen)
    min_date = sorted_dates[0] if sorted_dates else "?"
    max_date = sorted_dates[-1] if sorted_dates else "?"
    
    print(f"\n{'='*50}")
    print(f"INCREMENTAL INDEX COMPLETE")
    print(f"{'='*50}")
    print(f"New games added: {new_games:,}")
    print(f"Errors: {errs}")
    print(f"Date range: {min_date} to {max_date}")
    print(f"Previous total: {old_count:,}")
    print(f"New total: {new_total:,}")
    print(f"Time: {el:.1f}s ({new_games/max(el,1):.0f} games/s)")
    print(f"{'='*50}")
    
    conn.close()

if __name__ == "__main__":
    main()
