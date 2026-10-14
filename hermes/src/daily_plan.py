"""Today's plan for the coach's home screen (coach redesign P3b): the ``daily_plan`` payload.

Composed from what is already stored, with no model call and no engine:

* the student's latest saved game (``user_games``) → «review my last game»; its number of
  key moments is the engine-verified mistakes of that game's review (``coach_game_insights``),
  sent only when such a review exists;
* the engine-measured focus theme (``coach_curriculum``), else the theme with the most
  engine-verified blunders in the reviewed games → «weak spot» puzzles; ``stat`` counts the
  reviewed games that had a blunder there, sent only when there are enough games to say so;
* the opening of the latest game that names one → an opening lesson;
* playing the coach, always.

A student with nothing stored gets the minimal plan: puzzles on any theme and a game with
the coach. The sources are read in parallel under one deadline (``BUDGET_S``); one that is
late or fails is left out. Nothing here is made up: a number is sent only when it was counted.
"""

from __future__ import annotations

import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout, wait
from typing import Any, Callable, Optional

import chess.pgn

logger = logging.getLogger(__name__)

MAX_CARDS = 4
PUZZLES_PER_CARD = 5
# The fewest reviewed games a «missed in k of the last n» line is shown for.
MIN_STAT_GAMES = 3
RECENT_GAMES = 5
RECENT_INSIGHTS = 10
# The fewest plies a game needs for a review (as model_router.extract_game_pgn).
MIN_REVIEW_PLIES = 8
MAX_TITLE = 80
BUDGET_S = 0.8

_ECO_RE = re.compile(r"^[A-E]\d\d$")
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="daily-plan")


def _clip(value: Any) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text[:MAX_TITLE] if text else None


def _plies(pgn: Any) -> int:
    if not isinstance(pgn, str) or not pgn.strip():
        return 0
    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except Exception:  # noqa: BLE001
        return 0
    return sum(1 for _ in game.mainline_moves()) if game is not None and not game.errors else 0


def _blunders(row: Any) -> list[dict]:
    from src.curriculum import _coerce_blunders

    return _coerce_blunders(row) if isinstance(row, dict) else []


def _puzzle_theme(value: Any) -> Optional[str]:
    """A theme the puzzle set knows (a Lichess tag), or None."""
    from src.puzzle_db import resolve_theme

    return resolve_theme(str(value)) if isinstance(value, str) and value.strip() else None


def _review_card(games: list, insights: list) -> Optional[dict]:
    game = next((g for g in games if isinstance(g, dict)), None)
    if not game or game.get("id") in (None, "") or _plies(game.get("pgn")) < MIN_REVIEW_PLIES:
        return None
    white, black = _clip(game.get("white")) or "?", _clip(game.get("black")) or "?"
    card: dict = {"type": "review_last_game", "game_id": str(game["id"]), "title": f"{white} – {black}"[:MAX_TITLE]}
    review = next((r for r in insights if isinstance(r, dict) and str(r.get("game_ref")) == str(game["id"])), None)
    if review is not None:
        card["moments_count"] = len(_blunders(review))
    return card


def _weak_spot_card(focus: list, insights: list) -> dict:
    from src.curriculum import _blunder_theme, aggregate_blunders

    theme = None
    for f in focus:
        theme = _puzzle_theme(f.get("theme")) if isinstance(f, dict) else None
        if theme:
            break
    if theme is None:
        counts = aggregate_blunders([r for r in insights if isinstance(r, dict)])
        for name, _ in sorted(counts.items(), key=lambda kv: (-kv[1]["blunder_count"], kv[0])):
            theme = _puzzle_theme(name)
            if theme:
                break
    card: dict = {"type": "weak_spot", "puzzles": PUZZLES_PER_CARD}
    if theme is None:
        return card  # puzzles on any theme
    card["theme"] = theme
    reviewed = [r for r in insights if isinstance(r, dict)]
    if len(reviewed) >= MIN_STAT_GAMES:
        hit = sum(1 for r in reviewed if any(_puzzle_theme(_blunder_theme(b)) == theme for b in _blunders(r)))
        if hit:
            card["stat"] = {"games_with": hit, "games": len(reviewed)}
    return card


def _opening_card(games: list) -> Optional[dict]:
    for g in games:
        if not isinstance(g, dict):
            continue
        eco, name = _clip(g.get("eco")), _clip(g.get("opening_name"))
        if eco and name and _ECO_RE.match(eco.upper()):
            return {"type": "opening_lesson", "eco": eco.upper(), "name": name}
    return None


def build_daily_plan(
    games: Optional[list] = None,
    insights: Optional[list] = None,
    focus: Optional[list] = None,
) -> dict:
    """The plan from the student's rows (each source may be None: not read in time / failed)."""
    games = games if isinstance(games, list) else []
    insights = insights if isinstance(insights, list) else []
    focus = focus if isinstance(focus, list) else []
    cards: list[dict] = []
    for build in (lambda: _review_card(games, insights), lambda: _weak_spot_card(focus, insights),
                  lambda: _opening_card(games)):
        try:
            card = build()
        except Exception:  # noqa: BLE001 — one bad source never empties the plan
            logger.debug("daily plan card failed", exc_info=True)
            card = None
        if card:
            cards.append(card)
    if not any(c["type"] == "weak_spot" for c in cards):
        cards.append({"type": "weak_spot", "puzzles": PUZZLES_PER_CARD})
    cards.append({"type": "play_coach"})
    return {"kind": "daily_plan", "cards": cards[:MAX_CARDS]}


def _sources(user_id: str) -> dict[str, Callable[[], Any]]:
    from src.curriculum import get_cached_curriculum
    from src.tools.game_insights import get_game_insights
    from src.tools.user_data import _query_user_games

    return {
        "games": lambda: _query_user_games(user_id, limit=RECENT_GAMES),
        "insights": lambda: get_game_insights(user_id, limit=RECENT_INSIGHTS),
        "focus": lambda: get_cached_curriculum(user_id),
    }


def load_daily_plan(user_id: str, budget_s: float = BUDGET_S) -> dict:
    """Read the sources in parallel for at most *budget_s* seconds and build the plan."""
    futures = {}
    for name, read in _sources(user_id).items():
        try:
            futures[name] = _pool.submit(read)
        except Exception:  # noqa: BLE001 — a pool that cannot start still gives the minimal plan
            logger.debug("daily plan source %s not started", name, exc_info=True)
    wait(list(futures.values()), timeout=budget_s)
    rows: dict[str, Any] = {}
    for name, future in futures.items():
        if not future.done():
            logger.info("daily plan: %s late, left out", name)
            continue
        try:
            rows[name] = future.result(timeout=0)
        except (FutureTimeout, Exception):  # noqa: BLE001
            logger.debug("daily plan source %s failed", name, exc_info=True)
    return build_daily_plan(rows.get("games"), rows.get("insights"), rows.get("focus"))
