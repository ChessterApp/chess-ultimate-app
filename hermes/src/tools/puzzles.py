"""Tool: get_puzzle — a verified tactical puzzle from the Lichess puzzle set.

Before this tool the coach had no puzzle source: ``set_puzzle`` took a FEN and
a solution the model made up, and the student could not solve them. Now the
coach asks for a puzzle by theme and rating and gets a real position with a
verified solution. The first puzzle goes on the board with the result itself
(2026-09-30): the model used to spend a second step — about 1.5 s — calling
``board_control set_puzzle`` for it.
"""

import json
import re
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
                "description": "How many puzzles to return (1–10, default 1): «дай три задачи», «несколько задач» → 3; "
                               "the first goes on the board, the rest are lined up in the result.",
            },
            "any": {
                "type": "boolean",
                "description": "True when the student asked for any puzzle («любую задачу», «случайную»), not the next set of their programme.",
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


MAX_COUNT = 10
_COUNT_WORDS = {"два": 2, "две": 2, "пару": 2, "пара": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "несколько": 3,
                "нескольк": 3, "two": 2, "couple": 2, "three": 3, "four": 4, "five": 5, "several": 3, "a few": 3,
                "екі": 2, "үш": 3, "төрт": 4, "бес": 5, "бірнеше": 3}
_COUNT_RE = re.compile(
    r"(?<![\w-])(?P<n>\d{1,2}|два|две|пару|пара|три|четыре|пять|шесть|несколько|нескольк\w*|two|couple(?:\s+of)?|three|four|"
    r"five|several|a\s+few|екі|үш|төрт|бес|бірнеше)\s+(?:[\w-]+\s+){0,2}?(?:задач\w*|задани\w*|упражнени\w*|пазл\w*|"
    r"головоломк\w*|puzzles?|tasks?|exercises?|есеп\w*|жаттығу\w*)(?![\w-])", re.IGNORECASE)


def count_in_words(text: str) -> Optional[int]:
    """The number of puzzles the student's words ask for — «дай три задачи», «пару задач на вилку»,
    "two puzzles" — or None (one, or no number)."""
    m = _COUNT_RE.search((text or "").replace("ё", "е"))
    if not m:
        return None
    raw = m.group("n").lower()
    if raw.isdigit():
        n = int(raw)
    else:
        n = next((v for k, v in _COUNT_WORDS.items() if raw.startswith(k.split()[0])), None)
        if n is None:
            return None
    return max(1, min(n, MAX_COUNT)) if n > 1 else None


# «Ещё», «другую», «следующую» without a theme: the student goes on with what they asked for last.
_MORE = re.compile(r"(?<![\w-])(?:ещ[её]|еще|друг\w+|следующ\w+|дальше|another|next|more|тағы|келесі)(?![\w-])", re.IGNORECASE)
# «Дальше», «следующую», «сдаюсь, давай следующую»: the next task of the queue (no noun needed).
NEXT_IN_QUEUE = re.compile(r"(?<![\w-])(?:следующ\w*|дальше|далее|next|келесі)(?![\w-])", re.IGNORECASE)


def queued_puzzle_result(puzzle: dict, left: int) -> dict:
    """A get_puzzle-shaped result for the next task of the student's queue («дай три задачи» → «дальше»)."""
    shown = SetPuzzle(fen=puzzle["fen"], solution=puzzle.get("solution") or [], puzzle_id=puzzle.get("puzzle_id"))
    where = (f"the site's set «{puzzle.get('lesson')}»" + (f" (course «{puzzle.get('course')}»)" if puzzle.get("course") else "")
             if puzzle.get("lesson") else "the puzzles asked for")
    return {
        "theme": (puzzle.get("themes") or [None])[0],
        "rating": puzzle.get("rating"),
        "count": 1,
        "source": puzzle.get("source") or "queue",
        "from_queue": True,
        "left_in_queue": left,
        "puzzles": [puzzle],
        "on_board": puzzle.get("puzzle_id"),
        "how_to_show": (
            f"The next task of what the student asked for is already on the board — do not call board_control for it. "
            + (f"It is task {puzzle.get('n')} of {puzzle.get('of')} of {where}. " if puzzle.get("n") else "")
            + f"{left} more {'is' if left == 1 else 'are'} lined up after it. Say whose move it is and what to look for, "
            "never the solution" + (f"; the set's address: {puzzle['url']}" if puzzle.get("url") else "") + "."
        ),
        "board_actions": [shown.model_dump(by_alias=True)],
    }


def site_puzzle(theme: Optional[str], resolved: Optional[str], user_id: Optional[str] = None,
                locale: Optional[str] = "ru", exclude_ids: Optional[list] = None) -> Optional[dict]:
    """A task from the site's own sets on the theme — the student's programme —
    shaped like a Lichess puzzle, with the set's title and address. The first
    not-completed set whose title matches, its first task not shown yet. None
    when the site has no set for the theme (fail-open: Lichess then)."""
    found = site_puzzles(theme, resolved, user_id=user_id, locale=locale, exclude_ids=exclude_ids, count=1)
    return found[0] if found else None


def site_puzzles(theme: Optional[str], resolved: Optional[str], user_id: Optional[str] = None,
                 locale: Optional[str] = "ru", exclude_ids: Optional[list] = None, count: int = 1) -> list:
    """Up to *count* tasks from the site's sets on the theme, in the programme's order — the rest of the
    set the student is on, then the next matching set («дай три задачи на связку», 20.10)."""
    out: list = []
    try:
        from src.tools.learning_path import _loc, fetch_programme, fetch_progress, get_lesson
        from src.tools.training_recommender import match_lessons

        stems = tuple(_SITE_STEMS.get(resolved or "", ())) + tuple(
            THEME_ALIASES.get(resolved, ()) if resolved else ()) + ((theme.strip().lower(),) if theme else ())
        stems = tuple(dict.fromkeys(s for s in stems if s and len(s) >= 3))
        if not stems:
            return out
        programme = fetch_programme()
        if not programme:
            return out
        progress = (fetch_progress(user_id) or {}) if user_id else {}
        excluded = set(exclude_ids or [])
        for c, m, l in match_lessons(programme, stems, progress, limit=6):
            if len(out) >= count:
                break
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
                out.append({
                    "puzzle_id": pid, "fen": p["fen"], "side_to_move": side, "solution": list(p["solution"]),
                    "rating": None, "themes": [resolved or theme], "hint": p.get("hint") or "",
                    "source": "site_lesson", "lesson": full.get("title"),
                    "course": course.get("title") if isinstance(course, dict) else course,
                    "url": full.get("url"), "n": p.get("n"), "of": len(tasks),
                })
                if len(out) >= count:
                    break
        return out
    except Exception:  # noqa: BLE001
        logger.debug("site puzzle lookup failed", exc_info=True)
        return out


def site_next_puzzle(user_id: Optional[str], locale: Optional[str] = "ru",
                     exclude_ids: Optional[list] = None) -> Optional[dict]:
    """«Дай задачу» with no theme: the next task of the student's own programme — the set they are on
    (or the first not completed), its first task not shown yet; the sets after it when that one has
    none (2026-10-16: a themeless request went to Lichess, past the programme). None when the
    programme is unavailable or every set is done (fail-open: Lichess then)."""
    found = site_next_puzzles(user_id, locale=locale, exclude_ids=exclude_ids, count=1)
    return found[0] if found else None


def site_next_puzzles(user_id: Optional[str], locale: Optional[str] = "ru",
                      exclude_ids: Optional[list] = None, count: int = 1) -> list:
    """Up to *count* next tasks of the student's programme, in order (the rest of the set, then the next sets)."""
    out: list = []
    try:
        from src.tools.learning_path import fetch_programme, fetch_progress, get_lesson, iter_lessons, next_lesson

        programme = fetch_programme()
        if not programme:
            return out
        progress = (fetch_progress(user_id) or {}) if user_id else {}
        lessons = list(iter_lessons(programme))
        start = next_lesson(programme, progress)
        idx = next((i for i, t in enumerate(lessons) if start and t[2].get("id") == start[2].get("id")), 0)
        excluded = set(exclude_ids or [])
        for c, m, l in lessons[idx: idx + 12]:
            if len(out) >= count:
                break
            if (progress.get(l.get("id")) or {}).get("status") == "completed":
                continue
            full = get_lesson(l.get("id") or "", user_id=user_id, locale=locale, show=False)
            if "error" in full or full.get("ambiguous"):
                continue
            tasks = [p for p in full.get("puzzles") or [] if p.get("fen") and p.get("solution")]
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
                out.append({
                    "puzzle_id": pid, "fen": p["fen"], "side_to_move": side, "solution": list(p["solution"]),
                    "rating": None, "themes": [], "hint": p.get("hint") or "",
                    "source": "site_lesson", "next_in_programme": True, "lesson": full.get("title"),
                    "course": course.get("title") if isinstance(course, dict) else course,
                    "url": full.get("url"), "n": p.get("n"), "of": len(tasks),
                })
                if len(out) >= count:
                    break
        return out
    except Exception:  # noqa: BLE001
        logger.debug("site next puzzle lookup failed", exc_info=True)
        return out


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
    any: bool = False,  # noqa: A002 — the tool argument's name
) -> dict:
    from src import config

    resolved_early = resolve_theme(theme) if theme else None
    try:
        count = max(1, min(int(count or 1), MAX_COUNT))
    except (TypeError, ValueError):
        count = 1
    sites: list = []
    if config.COACH_PUZZLES_FROM_SITE and theme and not opening:
        sites = site_puzzles(theme, resolved_early, user_id=user_id, locale=locale, exclude_ids=exclude_ids, count=count)
    elif config.COACH_PUZZLES_FROM_SITE and not theme and not opening and not rating and not any and user_id:
        sites = site_next_puzzles(user_id, locale=locale, exclude_ids=exclude_ids, count=count)
    if sites:
        site = sites[0]
        shown = SetPuzzle(fen=site["fen"], solution=site["solution"], puzzle_id=site["puzzle_id"])
        where = f"the site's set «{site['lesson']}»" + (f" (course «{site['course']}»)" if site.get("course") else "")
        # «Дай три задачи»: the first goes on the board, the rest are lined up in the result — the model puts
        # the next one up itself when the student solves or gives up (no new get_puzzle needed).
        queued = ("" if len(sites) == 1 else
                  f" The student asked for several: {len(sites)} tasks are in this result, in the programme's order "
                  f"({', '.join(f'task {q.get('n')} of «{q.get('lesson')}»' for q in sites[1:])}); tell them how many "
                  "are lined up, and when they solve the one on the board or give up, put the next one up with "
                  "board_control set_puzzle (its fen, solution and puzzle_id are below) — do not call get_puzzle again "
                  "for them.")
        return {
            "theme": resolved_early or theme,
            "rating": None,
            "count": len(sites),
            "source": "site_lesson",
            "puzzles": sites,
            "on_board": site["puzzle_id"],
            "how_to_show": (
                f"The puzzle is already on the student's board — do not call board_control for it. It is task "
                f"{site.get('n')} of {site.get('of')} of {where}, "
                + ("the next set of the student's own programme (they asked for a puzzle, not a theme: say it is "
                   "where their programme continues; a random one — get_puzzle(any=true) — only if they ask)"
                   if site.get("next_in_programme") else "the student's own programme")
                + ": say so, say whose move it is and what to look for, never the solution, and give the set's "
                "address at the end"
                + (f": {site['url']}" if site.get("url") else "") + ". For the next task simply call get_puzzle "
                "again (the same theme, or none): the server remembers the tasks already shown in this session."
                + queued
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
    # The session remembers every puzzle it has put up: «ещё задачу» moves on to the next task even when
    # the model forgets exclude_ids (production, 20.10: task 1 of the same set again and again).
    session = None
    exclude = {str(x) for x in (args.get("exclude_ids") or []) if x}
    try:
        from src.sessions import session_for

        session = session_for(kwargs)
        if session is not None:
            exclude |= session.puzzles_shown
    except Exception:  # noqa: BLE001 — without a session the model's own list is all there is
        session = None
    words = str(kwargs.get("student_message") or kwargs.get("utterance") or "")
    count = args.get("count") or 1
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 1
    if count <= 1:
        # «Дай три задачи на связку», «несколько задач»: the words name the number when the model does not.
        count = count_in_words(words) or 1
    theme = args.get("theme")
    # «Дальше», «ещё задачу» after «дай три задачи»: the next one of those, from the session's queue — no
    # new lookup, no repeat (21.10).
    if session is not None and session.puzzle_queue and not theme and not args.get("any") and not args.get("opening"):
        nxt = session.pop_puzzle()
        if nxt:
            session.note_puzzles_shown([str(nxt.get("puzzle_id"))])
            return json.dumps(queued_puzzle_result(nxt, len(session.puzzle_queue)), indent=2, ensure_ascii=False)
    if not theme and session is not None and session.last_puzzle_theme and _MORE.search(words):
        theme = session.last_puzzle_theme  # «ещё задачу» after «задачу на вилку»: the same theme
    result = get_puzzle(
        theme=theme,
        rating=args.get("rating"),
        opening=args.get("opening"),
        count=count,
        exclude_ids=sorted(exclude),
        any=bool(args.get("any")),
        user_id=user_id,
        locale=args.get("locale") or "ru",
    )
    if session is not None and isinstance(result, dict):
        puzzles = result.get("puzzles") or []
        session.note_puzzles_shown([str(p.get("puzzle_id")) for p in puzzles if p.get("puzzle_id")])
        if puzzles:
            session.set_puzzle_queue(puzzles[1:], theme=theme or "")
    # A puzzle is what the student asked for: only a strict board lock keeps it off the board,
    # and the model then hears so (src/board_truth.py, for every tool).
    return json.dumps(result, indent=2, ensure_ascii=False)


registry.register(
    name="get_puzzle",
    toolset="chess",
    schema=GET_PUZZLE_SCHEMA,
    handler=_handle_get_puzzle,
    description="Get a verified tactical puzzle by theme and rating.",
    emoji="🧩",
)


# ── The solution of the puzzle on the board, shown by the system (23.10) ────────────────────────────
# «Сдаюсь, покажи решение» on the mate-in-two puzzle: the solution Qf3+ Kg1 Nh3# was in the model's private
# block and it still told «Qf3+ Kg1 и Qh1#» (prod, 23.10). The solution is a fact of the puzzle, so the system
# shows it (arrows) and tells the model the exact line; the model only explains why.
ASKS_SOLUTION = re.compile(
    r"(?<![\w-])(?:сда[юё]сь|сдаться|сдалс\w*|не\s+знаю|не\s+вижу|не\s+могу\s+(?:найти|решить)|"
    r"(?:покажи|скажи|дай|назови|какое|открой|раскрой)\s+(?:мне\s+|уже\s+|тогда\s+)?(?:решени\w*|ответ\w*|правильн\w+\s+ход\w*)|"
    r"решени[ея]\s*\?|ответ\s*\?|реши\s+(?:её|ее|сам|за\s+меня)|"
    r"i\s+give\s+up|give\s+up|(?:show|tell)\s+(?:me\s+)?the\s+(?:solution|answer)|what(?:'s|\s+is)\s+the\s+(?:solution|answer)|"
    r"i\s+don'?t\s+know|берілемін|шешімін\s+(?:көрсет|айт)\w*|жауабы\w*\s+(?:қандай|не))(?![\w-])", re.IGNORECASE)
# «сдаюсь, давай следующую», «не знаю, дай другую задачу»: the next task, not this one's solution.
_NOT_SOLUTION = re.compile(r"(?<![\w-])(?:следующ\w*|дальше|далее|друг(?:ую|ой)|ещ[её]|нов(?:ую|ая)|next|another|"
                           r"подсказк\w*|намёк\w*|hint\w*)(?![\w-])", re.IGNORECASE)


def asks_solution(text: str) -> bool:
    """The student gives up or asks for the solution of the puzzle in front of them."""
    t = text or ""
    return bool(ASKS_SOLUTION.search(t)) and not _NOT_SOLUTION.search(t)


def solution_line(board_rec) -> Optional[dict]:
    """The puzzle on *board_rec* and its solution in SAN from its start: {"fen", "sans", "reached", "next"} —
    *reached* half-moves of it are already on the board; None when the board is not a puzzle or has left the line."""
    import chess

    pz = getattr(board_rec, "puzzle", None) or {}
    solution = [str(m) for m in (pz.get("solution") or [])]
    if getattr(board_rec, "kind", None) != "puzzle" or not pz.get("fen") or not solution:
        return None
    try:
        line = chess.Board(pz["fen"])
        now = chess.Board(board_rec.fen)
    except (ValueError, IndexError):
        return None

    def key(b):
        return b.board_fen() + (" w" if b.turn else " b")

    sans, ucis, reached = [], [], None
    for i in range(len(solution) + 1):
        if reached is None and key(line) == key(now):
            reached = i
        if i == len(solution):
            break
        try:
            mv = line.parse_san(solution[i])
        except ValueError:
            try:
                mv = chess.Move.from_uci(solution[i])
                if mv not in line.legal_moves:
                    return None
            except ValueError:
                return None
        sans.append(line.san(mv))
        ucis.append(mv.uci())
        line.push(mv)
    if reached is None:
        return None
    return {"fen": pz["fen"], "sans": sans, "ucis": ucis, "reached": reached, "next": sans[reached:]}


def numbered_line(fen: str, sans: list) -> str:
    """«1...Qf3+ 2.Kg1 Nh3#» from *fen*."""
    import chess

    b = chess.Board(fen)
    out = []
    for san in sans:
        if b.turn == chess.WHITE:
            out.append(f"{b.fullmove_number}.{san}")
        elif not out:
            out.append(f"{b.fullmove_number}...{san}")
        else:
            out.append(san)
        b.push_san(san)
    return " ".join(out)


def _handle_puzzle_solution(args: dict, **kwargs) -> str:
    from src.sessions import session_for

    session = session_for(kwargs)
    board_rec = None
    try:
        board_rec = session.get_board(session.active_board_id) if session is not None else None
    except Exception:  # noqa: BLE001
        board_rec = None
    sol = solution_line(board_rec) if board_rec is not None else None
    if not sol:
        return json.dumps({"error": "No puzzle is on the board (or the board has left its line): nothing to show. "
                                    "Offer a puzzle with get_puzzle."})
    if not sol["next"]:
        return json.dumps({"ok": True, "solved": True, "line": numbered_line(sol["fen"], sol["sans"]),
                           "note": "The puzzle is already solved on the board: say so and offer the next one."})
    whole = numbered_line(sol["fen"], sol["sans"])
    arrows = [{"from": u[:2], "to": u[2:4], "brush": "green" if i % 2 == 0 else "blue"}
              for i, u in enumerate(sol["ucis"][sol["reached"]:])]
    return json.dumps({
        "ok": True, "line": whole, "moves": sol["sans"], "from_here": sol["next"], "reached": sol["reached"],
        "board_actions": [{"type": "draw_arrows", "arrows": arrows[:6]}],
        "note": (f"The solution is SHOWN on the board with arrows. Say it EXACTLY, move by move: {whole}"
                 + (f" (from the position on the board: {' '.join(sol['next'])})" if sol["reached"] else "")
                 + ". Then why each move works. Never substitute another move or another finish — this line is the "
                   "puzzle's verified solution."),
    }, ensure_ascii=False)


registry.register(
    name="puzzle_solution",
    toolset="chess",
    schema={"name": "puzzle_solution", "description": "Show the verified solution of the puzzle on the board "
            "(the student gave up or asked for it): arrows on the board and the exact line to say.",
            "parameters": {"type": "object", "properties": {}}},
    handler=_handle_puzzle_solution,
    description="The verified solution of the puzzle on the board, shown with arrows.",
    emoji="💡",
)


def puzzle_db_stats() -> dict:
    """Health-check helper: is the puzzle DB installed and how big is it."""
    return stats()
