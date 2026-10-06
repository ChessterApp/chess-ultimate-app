"""Tool: get_puzzle — a verified tactical puzzle from the Lichess puzzle set.

Before this tool the coach had no puzzle source: ``set_puzzle`` took a FEN and
a solution the model made up, and the student could not solve them. Now the
coach asks for a puzzle by theme and rating and gets a real position with a
verified solution. The first puzzle goes on the board with the result itself
(2026-09-30): the model used to spend a second step — about 1.5 s — calling
``board_control set_puzzle`` for it.
"""

import json
import logging
import random
from typing import Optional

from tools.registry import registry

from src.board_protocol import SetPuzzle
from src.puzzle_db import THEME_ALIASES, db_available, find_puzzles, resolve_theme, stats

logger = logging.getLogger(__name__)

_THEME_LIST = ", ".join(sorted(THEME_ALIASES))

GET_PUZZLE_SCHEMA = {
    "name": "get_puzzle",
    "description": (
        "Get a verified tactical puzzle by theme and rating — from the site's own sets of tasks on the "
        "theme first (the student's programme, with the set's address), else the Lichess puzzle set. "
        "Returns the position the student must solve (FEN, side to move), the "
        "solution in SAN, rating and themes. ALWAYS use this instead of inventing "
        "a puzzle. The first returned puzzle is put on the student's board "
        "automatically — do not call board_control for it. "
        f"Themes (English tags, RU/KK phrases like «вилка», «связка», «мат в 2» are accepted): {_THEME_LIST}."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "theme": {
                "type": "string",
                "description": "Theme tag or phrase, e.g. 'fork', 'pin', 'mateIn2', 'endgame', «связка». Omit for any theme.",
            },
            "rating": {
                "type": "integer",
                "description": "Target puzzle rating (Lichess scale, ~600–2800). Use the student's rating; omit for any.",
            },
            "opening": {
                "type": "string",
                "description": "Optional opening tag filter, e.g. 'Sicilian_Defense', 'Italian_Game'.",
            },
            "count": {
                "type": "integer",
                "description": "How many puzzles to return (1–10, default 1).",
            },
            "exclude_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Puzzle ids already shown in this session, to avoid repeats.",
            },
        },
    },
}


# The site's sets of tasks by the theme's words: «Связка — Набор 1», «Двойной удар —
# Набор 3», «Мат в 3 хода — Набор 2», «Эндшпиль — Набор 6» (course titles, 2026-10-04).
_SITE_STEMS = {
    "fork": ("двойной удар", "вилк"), "pin": ("связк",), "skewer": ("сквозн",), "mate": ("мат",),
    "mateIn1": ("мат в 1",), "mateIn2": ("мат в 2",), "mateIn3": ("мат в 3",), "mateIn4": ("мат в 4",),
    "backRankMate": ("ладейн", "мат"), "deflection": ("отвлеч",), "attraction": ("завлеч",),
    "capturingDefender": ("уничтожение защит",), "xRayAttack": ("рентген",), "endgame": ("эндшпил",),
    "discoveredAttack": ("открыт",), "hangingPiece": ("выигрыш",), "sacrifice": ("жертв",),
}


def site_puzzle(theme: Optional[str], resolved: Optional[str], user_id: Optional[str] = None,
                locale: Optional[str] = "ru", exclude_ids: Optional[list] = None) -> Optional[dict]:
    """A task from the site's own sets on the theme — the student's programme —
    shaped like a Lichess puzzle, with the set's title and address. The first
    not-completed set whose title matches, its first task not shown yet. None
    when the site has no set for the theme (fail-open: Lichess then)."""
    try:
        from src.tools.learning_path import _loc, fetch_programme, fetch_progress, get_lesson
        from src.tools.training_recommender import match_lessons

        stems = tuple(_SITE_STEMS.get(resolved or "", ())) + tuple(
            THEME_ALIASES.get(resolved, ()) if resolved else ()) + ((theme.strip().lower(),) if theme else ())
        stems = tuple(dict.fromkeys(s for s in stems if s and len(s) >= 3))
        if not stems:
            return None
        programme = fetch_programme()
        if not programme:
            return None
        progress = (fetch_progress(user_id) or {}) if user_id else {}
        excluded = set(exclude_ids or [])
        for c, m, l in match_lessons(programme, stems, progress, limit=6):
            if (l.get("lesson_type") or "") not in ("", "exercise", "puzzle", "practice"):
                continue
            full = get_lesson(l.get("id") or "", user_id=user_id, locale=locale, show=False)
            if "error" in full or full.get("ambiguous"):
                continue
            tasks = [p for p in full.get("puzzles") or [] if p.get("fen") and p.get("solution")]
            if not tasks:
                continue
            for p in tasks:
                pid = f"site:{full.get('lesson_id')}:{p.get('n')}"
                if pid in excluded:
                    continue
                try:
                    import chess

                    side = "white" if chess.Board(p["fen"]).turn else "black"
                except Exception:  # noqa: BLE001
                    continue
                course = full.get("course") or {}
                return {
                    "puzzle_id": pid, "fen": p["fen"], "side_to_move": side, "solution": list(p["solution"]),
                    "rating": None, "themes": [resolved or theme], "hint": p.get("hint") or "",
                    "source": "site_lesson", "lesson": full.get("title"),
                    "course": course.get("title") if isinstance(course, dict) else course,
                    "url": full.get("url"), "n": p.get("n"), "of": len(tasks),
                }
        return None
    except Exception:  # noqa: BLE001
        logger.debug("site puzzle lookup failed", exc_info=True)
        return None


def get_puzzle(
    theme: str = None,
    rating: int = None,
    opening: str = None,
    count: int = 1,
    exclude_ids: list = None,
    db_path: str = None,
    rng: random.Random = None,
    user_id: str = None,
    locale: str = "ru",
) -> dict:
    from src import config

    resolved_early = resolve_theme(theme) if theme else None
    if config.COACH_PUZZLES_FROM_SITE and theme and not opening:
        site = site_puzzle(theme, resolved_early, user_id=user_id, locale=locale, exclude_ids=exclude_ids)
        if site:
            shown = SetPuzzle(fen=site["fen"], solution=site["solution"], puzzle_id=site["puzzle_id"])
            where = f"the site's set «{site['lesson']}»" + (f" (course «{site['course']}»)" if site.get("course") else "")
            return {
                "theme": resolved_early or theme,
                "rating": None,
                "count": 1,
                "source": "site_lesson",
                "puzzles": [site],
                "on_board": site["puzzle_id"],
                "how_to_show": (
                    f"The puzzle is already on the student's board — do not call board_control for it. It is task "
                    f"{site.get('n')} of {site.get('of')} of {where}, the student's own programme: say so, say whose "
                    "move it is and what to look for, never the solution, and give the set's address at the end"
                    + (f": {site['url']}" if site.get("url") else "") + ". For the next task call get_puzzle again "
                    "with this puzzle_id in exclude_ids."
                ),
                "board_actions": [shown.model_dump(by_alias=True)],
            }
    if not db_available(db_path):
        return {
            "error": "Puzzle database is not installed on this server "
                     "(scripts/import_puzzles.py builds it from the Lichess puzzle set).",
        }
    resolved = resolve_theme(theme) if theme else None
    if theme and not resolved:
        return {
            "error": f"Unknown theme {theme!r}.",
            "known_themes": sorted(THEME_ALIASES),
        }
    try:
        rating_int = int(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating_int = None

    puzzles = find_puzzles(
        theme=resolved,
        rating=rating_int,
        opening=opening,
        exclude_ids=exclude_ids,
        count=count,
        db_path=db_path,
        rng=rng,
    )
    if not puzzles:
        return {
            "error": "No puzzle matched.",
            "theme": resolved,
            "rating": rating_int,
            "hint": "Try another theme or drop the opening filter.",
        }
    first = puzzles[0]
    shown = SetPuzzle(fen=first["fen"], solution=first["solution"], puzzle_id=first["puzzle_id"])
    return {
        "theme": resolved,
        "rating": rating_int,
        "count": len(puzzles),
        "puzzles": puzzles,
        "on_board": first["puzzle_id"],
        "how_to_show": (
            "The first puzzle is already on the student's board — do not call board_control "
            "for it. Say whose move it is and what to look for, never the solution. Another "
            "puzzle from this list: board_control set_puzzle with its puzzle_id."
        ),
        "board_actions": [shown.model_dump(by_alias=True)],
    }


def _handle_get_puzzle(args: dict, **kwargs) -> str:
    from src.identity import resolve_user_id

    try:
        user_id = resolve_user_id(args, kwargs)
    except Exception:  # noqa: BLE001
        user_id = None
    result = get_puzzle(
        theme=args.get("theme"),
        rating=args.get("rating"),
        opening=args.get("opening"),
        count=args.get("count", 1),
        exclude_ids=args.get("exclude_ids"),
        user_id=user_id,
        locale=args.get("locale") or "ru",
    )
    from src.sessions import BOARD_KEPT_NOTE, board_lock_for

    if board_lock_for(kwargs) and isinstance(result, dict):
        result.pop("board_actions", None)
        result["board_hint"] = BOARD_KEPT_NOTE
    return json.dumps(result, indent=2, ensure_ascii=False)


registry.register(
    name="get_puzzle",
    toolset="chess",
    schema=GET_PUZZLE_SCHEMA,
    handler=_handle_get_puzzle,
    description="Get a verified tactical puzzle by theme and rating.",
    emoji="🧩",
)


def puzzle_db_stats() -> dict:
    """Health-check helper: is the puzzle DB installed and how big is it."""
    return stats()
