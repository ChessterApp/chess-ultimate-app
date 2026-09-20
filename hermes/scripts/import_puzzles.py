#!/usr/bin/env python3
"""Build (or refresh) the coach's puzzle database from the Lichess puzzle set.

    # one-off download (CC0, ~250 MB compressed, ~5M puzzles)
    curl -LO https://database.lichess.org/lichess_db_puzzle.csv.zst

    # build /root/hermes-chess/data/puzzles.db (default PUZZLES_DB_PATH)
    python scripts/import_puzzles.py lichess_db_puzzle.csv.zst

    # a small local subset for development / tests
    python scripts/import_puzzles.py lichess_db_puzzle.csv.zst --db ./puzzles-dev.db --limit 50000

Accepts a plain .csv or a .zst archive (via the `zstandard` package or the
`zstd` CLI). Re-running replaces the tables atomically: the new data is built
in a temporary file and moved into place, so a running Hermes never sees a
half-built database. Idempotent.
"""

import argparse
import csv
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.puzzle_db import PUZZLES_DB_PATH, SCHEMA  # noqa: E402

BATCH = 20_000


def open_csv(path: str):
    """Yield CSV rows from a .csv or .csv.zst file."""
    if path.endswith(".zst"):
        try:
            import zstandard  # type: ignore

            fh = open(path, "rb")
            reader = zstandard.ZstdDecompressor().stream_reader(fh)
            text = io.TextIOWrapper(reader, encoding="utf-8")
        except ImportError:
            proc = subprocess.Popen(["zstd", "-dc", path], stdout=subprocess.PIPE)
            text = io.TextIOWrapper(proc.stdout, encoding="utf-8")
    else:
        text = open(path, encoding="utf-8", newline="")
    return csv.DictReader(text)


def build(csv_path: str, db_path: str, limit: int = 0, min_popularity: int = -100) -> int:
    tmp_dir = os.path.dirname(os.path.abspath(db_path)) or "."
    os.makedirs(tmp_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="puzzles-", suffix=".db", dir=tmp_dir)
    os.close(fd)
    os.unlink(tmp_path)

    conn = sqlite3.connect(tmp_path)
    conn.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
    conn.executescript(SCHEMA)

    rows, theme_rows, total, started = [], [], 0, time.time()

    def flush():
        conn.executemany(
            "INSERT OR REPLACE INTO puzzles VALUES (?,?,?,?,?,?,?,?,?,?)", rows
        )
        conn.executemany(
            "INSERT OR IGNORE INTO puzzle_themes VALUES (?,?,?)", theme_rows
        )
        rows.clear()
        theme_rows.clear()

    for rec in open_csv(csv_path):
        try:
            rating = int(rec["Rating"])
            popularity = int(rec.get("Popularity") or 0)
        except (TypeError, ValueError):
            continue
        if popularity < min_popularity:
            continue
        themes = (rec.get("Themes") or "").strip()
        rows.append((
            rec["PuzzleId"], rec["FEN"], rec["Moves"], rating,
            int(rec.get("RatingDeviation") or 0), popularity,
            int(rec.get("NbPlays") or 0), themes,
            rec.get("GameUrl") or None, (rec.get("OpeningTags") or "").strip() or None,
        ))
        for theme in themes.split():
            theme_rows.append((rec["PuzzleId"], theme, rating))
        total += 1
        if len(rows) >= BATCH:
            flush()
            if total % (BATCH * 10) == 0:
                print(f"  {total:,} puzzles ({time.time() - started:.0f}s)", flush=True)
        if limit and total >= limit:
            break
    flush()

    conn.execute("INSERT OR REPLACE INTO meta VALUES ('imported_at', ?)",
                 (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),))
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('source', ?)", (os.path.basename(csv_path),))
    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    shutil.move(tmp_path, db_path)
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="lichess_db_puzzle.csv or .csv.zst")
    ap.add_argument("--db", default=PUZZLES_DB_PATH, help=f"target SQLite file (default {PUZZLES_DB_PATH})")
    ap.add_argument("--limit", type=int, default=0, help="stop after N puzzles (dev subsets)")
    ap.add_argument("--min-popularity", type=int, default=-100,
                    help="skip puzzles below this Lichess popularity (-100..100)")
    args = ap.parse_args()

    started = time.time()
    total = build(args.csv, args.db, limit=args.limit, min_popularity=args.min_popularity)
    size_mb = os.path.getsize(args.db) / 1e6
    print(f"done: {total:,} puzzles -> {args.db} ({size_mb:.0f} MB, {time.time() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
