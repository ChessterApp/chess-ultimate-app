"""Puzzle database: the Lichess puzzle set (CC0) in a local SQLite file.

Same deployment pattern as the TWIC games index — a file on the Hermes host,
built once by ``scripts/import_puzzles.py`` from
https://database.lichess.org/lichess_db_puzzle.csv.zst and refreshed by
re-running the script.

Lichess CSV columns: PuzzleId, FEN, Moves, Rating, RatingDeviation,
Popularity, NbPlays, Themes, GameUrl, OpeningTags. ``FEN`` is the position
*before* the opponent's last move; ``Moves`` (UCI, space-separated) starts
with that opponent move, and the solution the student must find begins at
the second move. :func:`present_puzzle` applies the first move so the coach
gets the position the student actually faces plus the solution in SAN.
"""

import logging
import os
import random
import sqlite3
from pathlib import Path
from typing import Optional

import chess

logger = logging.getLogger(__name__)

PUZZLES_DB_PATH = os.environ.get(
    "PUZZLES_DB_PATH", "/root/hermes-chess/data/puzzles.db"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS puzzles (
    id TEXT PRIMARY KEY,
    fen TEXT NOT NULL,
    moves TEXT NOT NULL,
    rating INTEGER NOT NULL,
    rating_deviation INTEGER,
    popularity INTEGER,
    nb_plays INTEGER,
    themes TEXT NOT NULL DEFAULT '',
    game_url TEXT,
    opening_tags TEXT
);
CREATE TABLE IF NOT EXISTS puzzle_themes (
    puzzle_id TEXT NOT NULL,
    theme TEXT NOT NULL,
    rating INTEGER NOT NULL,
    PRIMARY KEY (theme, rating, puzzle_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_puzzles_rating ON puzzles(rating);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

# Lichess theme tags the coach may ask for, with RU/KK aliases so a Russian
# request ("дай задачу на вилку") maps onto the English tag. Extend freely.
THEME_ALIASES = {
    "fork": ("вилка", "вилк", "двойной удар", "айыр"),
    "pin": ("связка", "связк", "байлан"),
    "skewer": ("сквозной удар", "сквозн", "рентген"),
    "discoveredAttack": ("открытое нападение", "открыт", "вскрыт"),
    "doubleCheck": ("двойной шах",),
    "sacrifice": ("жертва", "жертв", "құрбан"),
    "mate": ("мат", "матов"),
    "mateIn1": ("мат в 1", "мат в один", "мат в одинход"),
    "mateIn2": ("мат в 2", "мат в два"),
    "mateIn3": ("мат в 3", "мат в три"),
    "mateIn4": ("мат в 4", "мат в четыре"),
    "mateIn5": ("мат в 5", "мат в пять"),
    "backRankMate": ("мат по последней", "последняя горизонталь", "слабая первая"),
    "smotheredMate": ("спёртый мат", "спертый мат"),
    "hangingPiece": ("висячая фигура", "висяч", "незащищённая", "незащищенная"),
    "trappedPiece": ("ловля фигуры", "ловля", "запертая фигура"),
    "promotion": ("превращение", "проходная", "превращ"),
    "advancedPawn": ("далеко продвинутая пешка", "продвинутая пешка"),
    "attraction": ("завлечение", "завлеч"),
    "deflection": ("отвлечение", "отвлеч"),
    "clearance": ("освобождение", "освобожд"),
    "interference": ("перекрытие", "перекрыт"),
    "intermezzo": ("промежуточный ход", "промежуточ"),
    "quietMove": ("тихий ход",),
    "zugzwang": ("цугцванг",),
    "xRayAttack": ("рентген",),
    "capturingDefender": ("уничтожение защитника", "защитник"),
    "exposedKing": ("открытый король", "раскрытый король"),
    "kingsideAttack": ("атака на королевском", "королевский фланг"),
    "queensideAttack": ("атака на ферзевом", "ферзевый фланг"),
    "defensiveMove": ("защита", "защитный ход", "оборон"),
    "endgame": ("эндшпиль", "окончание", "эндшпил"),
    "middlegame": ("миттельшпиль", "середина игры"),
    "opening": ("дебют", "дебютн"),
    "pawnEndgame": ("пешечный эндшпиль", "пешечное окончание", "пешечн"),
    "rookEndgame": ("ладейный эндшпиль", "ладейное окончание", "ладейн"),
    "bishopEndgame": ("слоновый эндшпиль", "слоновое окончание"),
    "knightEndgame": ("коневой эндшпиль", "коневое окончание"),
    "queenEndgame": ("ферзевый эндшпиль", "ферзевое окончание"),
    "queenRookEndgame": ("ферзь против ладьи",),
    "oneMove": ("в один ход", "одноходов"),
    "short": ("короткая",),
    "long": ("длинная",),
    "veryLong": ("очень длинная",),
    "crushing": ("разгром",),
    "advantage": ("преимущество", "выигрыш материала"),
    "equality": ("уравнение",),
    "master": ("партия мастера", "мастерск"),
    "masterVsMaster": ("между мастерами",),
    "superGM": ("супергроссмейстер",),
}

_LOWER_THEMES = {t.lower(): t for t in THEME_ALIASES}


def resolve_theme(text: Optional[str]) -> Optional[str]:
    """Map a theme name or RU/KK phrase to a Lichess theme tag (or None)."""
    if not text:
        return None
    raw = text.strip()
    if raw.lower() in _LOWER_THEMES:
        return _LOWER_THEMES[raw.lower()]
    low = raw.lower()
    # Longest alias first so "мат в 2" beats "мат".
    best = None
    best_len = 0
    for theme, aliases in THEME_ALIASES.items():
        for alias in aliases:
            if alias in low and len(alias) > best_len:
                best, best_len = theme, len(alias)
    return best


def connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or PUZZLES_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def db_available(db_path: Optional[str] = None) -> bool:
    path = Path(db_path or PUZZLES_DB_PATH)
    return path.is_file() and path.stat().st_size > 0


def present_puzzle(row: dict) -> dict:
    """Turn a raw puzzle row into what the coach and the board need.

    Applies the opponent's setup move to the stored FEN, converts the solution
    to SAN, and reports whose move it is.
    """
    board = chess.Board(row["fen"])
    uci_moves = row["moves"].split()
    setup_move = board.parse_uci(uci_moves[0])
    setup_san = board.san(setup_move)
    board.push(setup_move)
    puzzle_fen = board.fen()

    solution_san = []
    replay = board.copy()
    for uci in uci_moves[1:]:
        move = replay.parse_uci(uci)
        solution_san.append(replay.san(move))
        replay.push(move)

    themes = [t for t in (row.get("themes") or "").split() if t]
    openings = [t for t in (row.get("opening_tags") or "").split() if t]
    return {
        "puzzle_id": row["id"],
        "fen": puzzle_fen,
        "side_to_move": "white" if board.turn == chess.WHITE else "black",
        "last_move_san": setup_san,
        "solution": solution_san,
        "solution_uci": uci_moves[1:],
        "rating": row["rating"],
        "themes": themes,
        "opening_tags": openings,
        "source": row.get("game_url") or "lichess",
    }


def load_puzzle(puzzle_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    """Fetch one puzzle by Lichess id, presented for the board (or None)."""
    if not db_available(db_path):
        return None
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT * FROM puzzles WHERE id = ?", (puzzle_id,)).fetchone()
    finally:
        conn.close()
    return present_puzzle(dict(row)) if row else None


def find_puzzles(
    theme: Optional[str] = None,
    rating: Optional[int] = None,
    spread: int = 100,
    opening: Optional[str] = None,
    exclude_ids: Optional[list] = None,
    count: int = 1,
    min_popularity: int = 50,
    db_path: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> list[dict]:
    """Random puzzles matching *theme* near *rating* (widening the band if needed).

    Sampling is an index seek, not ``ORDER BY RANDOM()``: pick a random rating
    inside the band, walk the ``(theme, rating, puzzle_id)`` index from there
    for a handful of candidates, then filter by popularity / opening /
    exclusions in Python. On the full 6.1M-puzzle set this is milliseconds;
    the sort-everything approach took 6–10 s for common themes.
    """
    if not db_available(db_path):
        return []
    rng = rng or random
    count = max(1, min(int(count or 1), 10))
    exclude = set(exclude_ids or [])
    # Wider candidate window when a post-filter (opening) will discard most rows.
    window = 200 if opening else 25
    conn = connect(db_path)
    try:
        if rating:
            bands = [spread, spread * 2, spread * 4, 4_000]
            centre = rating
        else:
            # No rating requested: sample uniformly over the ratings that exist
            # (a fixed 0–6000 window would wrap to the floor half the time and
            # hand out 500-rated puzzles).
            row = conn.execute("SELECT MIN(rating), MAX(rating) FROM puzzles").fetchone()
            r_min, r_max = (row[0] or 0), (row[1] or 0)
            centre = (r_min + r_max) // 2
            bands = [max(1, (r_max - r_min) // 2)]

        def _walk(start: int, hi: int) -> list:
            if theme:
                cur = conn.execute(
                    "SELECT puzzle_id FROM puzzle_themes "
                    "WHERE theme = ? AND rating BETWEEN ? AND ? "
                    "ORDER BY rating, puzzle_id LIMIT ?",
                    (theme, start, hi, window),
                )
                return [r["puzzle_id"] for r in cur]
            cur = conn.execute(
                "SELECT id FROM puzzles WHERE rating BETWEEN ? AND ? ORDER BY rating LIMIT ?",
                (start, hi, window),
            )
            return [r["id"] for r in cur]

        for band in bands:
            lo, hi = max(0, centre - band), centre + band
            picked: dict = {}
            for _ in range(6):
                start_rating = rng.randint(lo, hi)
                ids = _walk(start_rating, hi)
                if not ids and start_rating > lo:
                    # Nothing above the random start inside the band: wrap to the
                    # band's floor so a sparse theme is still found.
                    ids = _walk(lo, hi)
                ids = [i for i in ids if i not in exclude and i not in picked]
                if not ids:
                    continue
                marks = ",".join("?" * len(ids))
                sql = f"SELECT * FROM puzzles WHERE id IN ({marks}) AND popularity >= ?"
                params: list = [*ids, min_popularity]
                if opening:
                    sql += " AND opening_tags LIKE ?"
                    params.append(f"%{opening}%")
                for row in conn.execute(sql, params):
                    picked[row["id"]] = dict(row)
                if len(picked) >= count * 3:
                    break
            if picked:
                rows = list(picked.values())
                rng.shuffle(rows)
                return [present_puzzle(r) for r in rows[:count]]
        return []
    finally:
        conn.close()


def stats(db_path: Optional[str] = None) -> dict:
    if not db_available(db_path):
        return {"available": False, "path": db_path or PUZZLES_DB_PATH}
    conn = connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM puzzles").fetchone()[0]
        meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}
    finally:
        conn.close()
    return {"available": True, "puzzles": total, **meta}
