"""The task of the site's lesson that stands on the board, found by its position (2026-10-22).

The programme run of 19.10 (184 lesson tasks asked about on the board, prod): the first move named
matched the site's solution in 170. The 14 misses were turns where the model, with only the engine
line, picked another good-looking move — the solution itself was known to nobody in the turn: the task
had come onto the board as a FEN (the lesson page, a pasted position), not through get_lesson /
get_puzzle, which mark the board as a puzzle and carry the solution (src/server._puzzle_block).

Here every lesson task of the site (``lesson_puzzles`` and the lessons' own ``exercise_fen``) is
indexed by position once in a while, and a board that shows one gets a block with the lesson it is
from and its solution — the same private block a puzzle set by the tools gets.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Optional

import chess

logger = logging.getLogger(__name__)

SITE_PUZZLE_TTL_SECONDS = 600  # the lessons' tasks change rarely; a reread every 10 minutes is plenty
_PAGE = 1000  # PostgREST's default max-rows: the tables are read page by page
_MAX_PAGES = 20

_index_lock = threading.Lock()
_index: dict = {"at": 0.0, "by_key": None}

PUZZLES_SELECT = "id,lesson_id,order_index,fen,solution_move,hint_text"
PUZZLES_SELECT_MIN = "id,lesson_id,order_index,fen,solution_move"
LESSONS_SELECT = "id,exercise_fen,solution_move,exercise_solution"
LESSONS_SELECT_MIN = "id,exercise_fen,exercise_solution"


def position_key(fen: Optional[str]) -> Optional[str]:
    """The pieces and the side to move — castling flags and counters differ between the site's FEN and
    the board's (src/fen_repair drops impossible flags), the position does not."""
    if not fen:
        return None
    try:
        board = chess.Board(fen)
    except ValueError:
        return None
    return board.board_fen() + (" w" if board.turn else " b")


def _paged(table: str, select: str, select_min: str, url=None, key=None) -> Optional[list]:
    """Every row of *table*, page by page (None when the database is unreachable)."""
    from src.tools.learning_path import _query_with_fallback

    rows: list = []
    for page in range(_MAX_PAGES):
        chunk = _query_with_fallback(table, select, select_min, url, key,
                                     limit=str(_PAGE), offset=str(page * _PAGE), order="id.asc")
        if chunk is None:
            return None if not rows else rows
        rows.extend(r for r in chunk if isinstance(r, dict))
        if len(chunk) < _PAGE:
            break
    return rows


def build_index(programme: dict, puzzles: list, lessons: list) -> dict:
    """position key → the tasks standing there (a position may be shared by two lessons)."""
    from src.tools.learning_path import _lesson_url, _loc, _slug, _solution_san, iter_lessons

    where: dict = {}
    for course, module, lesson in iter_lessons(programme):
        where[lesson.get("id")] = (course, module, lesson)
    counts: dict = {}
    for p in puzzles:
        counts[p.get("lesson_id")] = counts.get(p.get("lesson_id"), 0) + 1
    by_key: dict = {}

    def _put(fen, lesson_id, solution_raw, n, total, hint=None):
        key = position_key(fen)
        if not key or lesson_id not in where:
            return
        course, module, lesson = where[lesson_id]
        solution = _solution_san(fen, solution_raw)
        if not solution:
            return
        entry = {
            "lesson_id": lesson_id, "lesson": _loc(lesson, "title", "ru") or lesson.get("title"),
            "course": _loc(course, "title", "ru") or course.get("title"),
            "module": _loc(module, "title", "ru") or module.get("title"),
            "slug": _slug(lesson) or None, "url": _lesson_url(course, lesson),
            "n": n, "total": total, "fen": fen, "solution": solution, "hint": (hint or "")[:300] or None,
        }
        by_key.setdefault(key, []).append(entry)

    ordered = sorted(puzzles, key=lambda p: (p.get("lesson_id") or "", p.get("order_index") or 0))
    seen: dict = {}
    for p in ordered:
        n = seen.get(p.get("lesson_id"), 0) + 1
        seen[p.get("lesson_id")] = n
        _put(p.get("fen"), p.get("lesson_id"), p.get("solution_move"), n, counts.get(p.get("lesson_id"), n),
             p.get("hint_text"))
    for l in lessons:
        if l.get("exercise_fen"):
            _put(l["exercise_fen"], l.get("id"), l.get("solution_move") or l.get("exercise_solution"), 1, 1)
    return by_key


def site_puzzle_index(force: bool = False, url=None, key=None) -> Optional[dict]:
    """The index, read from Supabase at most every SITE_PUZZLE_TTL_SECONDS; None when unreachable.
    SITE_PUZZLE_INDEX_FILE (a JSON dump of the index) stands in for the database on a stand without it."""
    now = time.monotonic()
    with _index_lock:
        if _index["by_key"] is not None and not force and now - _index["at"] < SITE_PUZZLE_TTL_SECONDS:
            return _index["by_key"]
    dump = os.environ.get("SITE_PUZZLE_INDEX_FILE")
    if dump:
        try:
            with open(dump, encoding="utf-8") as fh:
                by_key = json.load(fh)
        except (OSError, ValueError):
            logger.warning("site puzzle index file %s unreadable", dump)
            return None
        with _index_lock:
            _index["by_key"] = by_key
            _index["at"] = time.monotonic()
        return by_key
    from src.tools.learning_path import fetch_programme

    programme = fetch_programme(url=url, key=key)
    if programme is None:
        return None
    puzzles = _paged("lesson_puzzles", PUZZLES_SELECT, PUZZLES_SELECT_MIN, url, key)
    lessons = _paged("lessons", LESSONS_SELECT, LESSONS_SELECT_MIN, url, key)
    if puzzles is None and lessons is None:
        return None
    by_key = build_index(programme, puzzles or [], lessons or [])
    with _index_lock:
        _index["by_key"] = by_key
        _index["at"] = time.monotonic()
    logger.info("site puzzle index: %d positions from %d tasks", len(by_key), len(puzzles or []) + len(lessons or []))
    return by_key


def clear_index() -> None:
    with _index_lock:
        _index["by_key"] = None
        _index["at"] = 0.0


def site_puzzle_at(fen: Optional[str], index: Optional[dict] = None) -> Optional[dict]:
    """The site's task that stands on the board in *fen*, or None. The start position is never a task."""
    key = position_key(fen)
    if not key or key.startswith(chess.STARTING_BOARD_FEN):
        return None
    if index is None:
        try:
            index = site_puzzle_index()
        except Exception:  # noqa: BLE001 — the lookup is best-effort
            logger.debug("site puzzle index failed", exc_info=True)
            return None
    hits = (index or {}).get(key) or []
    if not hits:
        return None
    # The same position in two lessons (114 on the site, 21.10): the one whose solution is a legal move
    # here comes first («Эндшпиль — Набор 21» writes h4 with no h-pawn; «Двойной удар — Набор 17» Ke5).
    hits = sorted(hits, key=lambda h: not _legal_first(fen, h.get("solution")))
    first = dict(hits[0])
    others = [h for h in hits[1:] if h.get("lesson_id") != first.get("lesson_id")]
    if others:
        first["also_in"] = [h.get("lesson") for h in others][:3]
    return first


def _legal_first(fen: str, solution) -> bool:
    try:
        board = chess.Board(fen)
        board.parse_san(str((solution or [None])[0]))
        return True
    except (ValueError, IndexError, TypeError):
        return False


def site_puzzle_block(hit: Optional[dict]) -> str:
    """The private block for the turn: which lesson the task is from and its solution."""
    if not hit:
        return ""
    solution = " ".join(hit.get("solution") or [])
    try:
        solver = "White" if chess.Board(hit["fen"]).turn else "Black"
    except (ValueError, KeyError):
        solver = "The side to move"
    where = f"task {hit.get('n')} of {hit.get('total')} " if hit.get("total") and hit.get("total") > 1 else "the task "
    also = f" (the same position is also in «{'», «'.join(hit['also_in'])}»)" if hit.get("also_in") else ""
    hint = f" The lesson's own hint: {hit['hint']}" if hit.get("hint") else ""
    return (
        "## The board shows a task of the site's lesson (private — its solution)\n"
        f"It is {where}of the lesson «{hit.get('lesson')}» (module «{hit.get('module')}», course "
        f"«{hit.get('course')}»){also}. {solver} to move; the lesson's solution: {solution}.{hint}\n"
        "The answer to «what is the move here» is exactly this solution — name it first, then why it works; "
        "do not offer another move as the answer even if the engine's line differs (the lesson teaches this "
        "idea). A hint leads to THIS solution: the idea, the target or the piece first. You may say which "
        "lesson the task is from" + (f" ({hit['url']})" if hit.get("url") else "") + "."
    )
