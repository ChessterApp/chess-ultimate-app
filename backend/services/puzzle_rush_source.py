"""
Puzzle Rush puzzle source — read-only picks from the Lichess puzzles SQLite DB.

Lichess semantics (spec §5.1): `fen` is the position BEFORE the opponent's setup
move; `moves` is space-separated UCI where moves[0] is the opponent setup move,
user moves sit at odd indices and opponent replies at even indices >= 2.

Quality: the spec filter (popularity >= 80 AND rating_deviation <= 80) is nearly
empty at the extremes of the DB (54 puzzles in 400-499, zero at >= 2800), which
would both flatten the ramp and make every pick scan a whole band. So each band
is sampled once (cached): if strict-quality rows are dense enough there, the
strict filter applies; otherwise the band falls back to popularity >= 80 only.

Selection never uses `ORDER BY random()` over a band (that scans the whole band).
Instead it seeks into `idx_puzzles_rating` at a random (rating, rowid) point and
takes the first qualifying row, falling back to scanning outward through the
band. Each pick is a handful of index seeks regardless of band size.
"""

import os
import random
import sqlite3
import threading

DEFAULT_DB_PATH = '/root/hermes-chess/data/puzzles.db'

BAND = 30
# Half-widths tried in order when the band (after exclusions) is empty.
WIDENED_BANDS = (BAND, 60, 120, 240, 480, 960, 1920, 4000)

STRICT_QUALITY_SQL = 'popularity >= 80 AND rating_deviation <= 80'
RELAXED_QUALITY_SQL = 'popularity >= 80'
DENSITY_SAMPLE = 300
MIN_STRICT_DENSITY = 0.05
COLUMNS = 'id, fen, moves, rating'


class NoPuzzleAvailable(Exception):
    pass


def target_rating(index: int) -> int:
    """Ramp (spec §7.8): target(i) = 400 + 45*i + 0.6*i^2, i = 0-based index."""
    return round(400 + 45 * index + 0.6 * index * index)


def _row_to_puzzle(row) -> dict:
    return {'id': row[0], 'fen': row[1], 'moves': row[2].split(), 'rating': row[3]}


class PuzzleSource:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv('PUZZLE_RUSH_DB_PATH', DEFAULT_DB_PATH)
        self._local = threading.local()
        self._max_rowid = None
        self._max_rating = None
        self._band_quality = {}

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
            self._local.conn = conn
        return conn

    def _rowid_ceiling(self) -> int:
        if self._max_rowid is None:
            self._max_rowid = self._conn().execute('SELECT max(rowid) FROM puzzles').fetchone()[0] or 1
        return self._max_rowid

    def _rating_ceiling(self) -> int:
        if self._max_rating is None:
            self._max_rating = self._conn().execute('SELECT max(rating) FROM puzzles').fetchone()[0] or 0
        return self._max_rating

    def _quality_sql(self, lo: int, hi: int) -> str:
        key = (lo, hi)
        if key not in self._band_quality:
            n, strict = self._conn().execute(
                f'SELECT count(*), coalesce(sum({STRICT_QUALITY_SQL}), 0) FROM '
                '(SELECT popularity, rating_deviation FROM puzzles WHERE rating BETWEEN ? AND ? LIMIT ?)',
                (lo, hi, DENSITY_SAMPLE),
            ).fetchone()
            dense = n > 0 and strict / n >= MIN_STRICT_DENSITY
            self._band_quality[key] = STRICT_QUALITY_SQL if dense else RELAXED_QUALITY_SQL
        return self._band_quality[key]

    def get(self, puzzle_id: str) -> dict | None:
        row = self._conn().execute(
            f'SELECT {COLUMNS} FROM puzzles WHERE id = ?', (puzzle_id,)
        ).fetchone()
        return _row_to_puzzle(row) if row else None

    def pick(self, index: int, exclude_ids=(), rng: random.Random | None = None) -> dict:
        """Pick a quality puzzle near target_rating(index), not in exclude_ids.

        Tries the ±30 band first and widens progressively only if it's empty.
        The ramp saturates at the hardest rating in the DB.
        """
        rng = rng or random.Random()
        target = min(target_rating(index), self._rating_ceiling())
        for half in WIDENED_BANDS:
            row = self._pick_in_band(target - half, target + half, list(exclude_ids), rng)
            if row:
                return _row_to_puzzle(row)
        raise NoPuzzleAvailable(f'no puzzle near rating {target}')

    def _pick_in_band(self, lo: int, hi: int, exclude: list, rng: random.Random):
        conn = self._conn()
        not_in = ''
        if exclude:
            not_in = f" AND id NOT IN ({','.join('?' * len(exclude))})"
        quality = self._quality_sql(lo, hi)
        base = f'SELECT {COLUMNS} FROM puzzles WHERE {quality}{not_in} AND '

        rating = rng.randint(lo, hi)
        rowid = rng.randint(1, self._rowid_ceiling())
        # (rating, rowid) seek, then wrap within that rating, then walk outward
        # through the band in index order. Every query is an index range scan.
        queries = (
            ('rating = ? AND rowid >= ? ORDER BY rowid LIMIT 1', (rating, rowid)),
            ('rating = ? AND rowid < ? ORDER BY rowid LIMIT 1', (rating, rowid)),
            ('rating > ? AND rating <= ? ORDER BY rating, rowid LIMIT 1', (rating, hi)),
            ('rating >= ? AND rating < ? ORDER BY rating DESC, rowid DESC LIMIT 1', (lo, rating)),
        )
        for clause, params in queries:
            row = conn.execute(base + clause, (*exclude, *params)).fetchone()
            if row:
                return row
        return None


_source: PuzzleSource | None = None


def get_puzzle_source() -> PuzzleSource:
    global _source
    if _source is None:
        _source = PuzzleSource()
    return _source
