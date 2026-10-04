"""Tools: list_topics / get_topic — the thematic knowledge base (brief, section 1д).

``list_topics`` gives the map: seven sections, each topic with level and one-line
summary. ``get_topic`` gives one topic in full — summary, key ideas, typical
mistakes, verified positions (FEN + plan), puzzle themes for get_puzzle, ECO
codes for get_opening_stats, model games for search_master_games, and the site's
lessons that cover the topic (matched through the programme by title stems).

It also puts one example on the board itself: a position from the site's lesson
on the topic when there is one, else the base's first verified position. The
model used to copy (or invent) a FEN into board_control — the customer saw a
"knight on c3 is pinned" with no knight on c3 (2026-09-25).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import chess

from tools.registry import registry

from src import knowledge_base as kb
from src.identity import resolve_user_id

logger = logging.getLogger(__name__)

MAX_RELATED_LESSONS = 4
# Lessons fetched in full while looking for one with a position to show.
MAX_EXAMPLE_LESSONS = 2


def _phase_title(phase: str, locale: Optional[str]) -> str:
    if (locale or "ru").lower() == "en":
        return kb.PHASE_TITLES_EN.get(phase, phase)
    return kb.PHASE_TITLES_RU.get(phase, phase)


def list_topics(phase: Optional[str] = None, level: Optional[int] = None,
                locale: Optional[str] = "ru", topics: Optional[dict] = None) -> dict:
    topics = topics if topics is not None else kb.load_topics()
    if not topics:
        return {"error": "The knowledge base is empty on this server (hermes/content/topics)."}
    if phase and phase not in kb.PHASES:
        return {"error": f"Unknown phase {phase!r}.", "phases": list(kb.PHASES)}
    sections = []
    for ph in kb.PHASES:
        if phase and ph != phase:
            continue
        items = [
            {
                "slug": t["slug"], "level": t["level"], "title": kb.title(t, locale),
                "summary": kb.summary(t, locale)[:160],
                "positions": len(t["positions"]),
            }
            for t in topics.values()
            if t["phase"] == ph and (level is None or t["level"] == int(level))
        ]
        if items:
            sections.append({"phase": ph, "title": _phase_title(ph, locale), "topics": items})
    return {
        "sections": sections,
        "total": sum(len(s["topics"]) for s in sections),
        "hint": "Call get_topic with a slug to teach a topic: it returns positions for the board and puzzle themes.",
    }


def _related_lessons(topic: dict, user_id: Optional[str], locale: Optional[str]) -> list[dict]:
    """Lessons of the site's programme whose titles match the topic's stems (fail-open)."""
    stems = tuple(topic.get("lesson_stems") or ())
    if not stems:
        return []
    try:
        from src.tools.learning_path import _loc, fetch_programme, fetch_progress
        from src.tools.training_recommender import match_lessons

        from src.tools.learning_path import _lesson_view

        programme = fetch_programme()
        if not programme:
            return []
        progress = (fetch_progress(user_id) or {}) if user_id else {}
        out = []
        for c, m, l in match_lessons(programme, stems, progress, limit=MAX_RELATED_LESSONS):
            # The same view as get_learning_path: the site keeps no slug in the
            # rows (production: every lesson came back as «/learn/None/None» and
            # the example was looked up by title, 2026-10-03), the address is
            # derived from the English title as the site itself does.
            view = _lesson_view(c, m, l, progress, locale)
            view["course"] = _loc(c, "title", locale)
            view["module"] = _loc(m, "title", locale)
            view.pop("type", None)
            if not view.get("url"):
                view.pop("url", None)
            out.append(view)
        return out
    except Exception:  # noqa: BLE001 — the programme is a bonus, never a blocker
        logger.debug("related lessons lookup failed", exc_info=True)
        return []


def _legal_fen(fen: Optional[str]) -> bool:
    try:
        return bool(fen) and chess.Board(fen).is_valid()
    except (ValueError, IndexError):
        return False


def _arrow(fen: str, move: Optional[str]) -> Optional[dict]:
    """Green arrow for a SAN or UCI move in *fen*; None if it is not legal there."""
    if not move:
        return None
    try:
        board = chess.Board(fen)
        mv = (chess.Move.from_uci(move) if re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", move)
              else board.parse_san(move))
    except ValueError:
        return None
    if mv not in board.legal_moves:
        return None
    return {"from": chess.square_name(mv.from_square), "to": chess.square_name(mv.to_square), "brush": "green"}


def _example_from_lessons(lessons: list[dict], user_id: Optional[str], locale: Optional[str]) -> Optional[dict]:
    """A position from the site's own lessons on the topic: the lesson's exercise,
    else its first puzzle (fail-open — the programme is optional)."""
    try:
        from src.tools.learning_path import get_lesson
    except Exception:  # noqa: BLE001
        return None
    for brief in lessons[:MAX_EXAMPLE_LESSONS]:
        # By id: a title («Связка») fits several lessons and came back ambiguous.
        key = brief.get("lesson_id") or brief.get("slug") or brief.get("title") or ""
        try:
            full = get_lesson(key, user_id=user_id, locale=locale, show=False)
        except Exception:  # noqa: BLE001
            logger.debug("lesson fetch for the topic example failed", exc_info=True)
            continue
        if "error" in full or full.get("ambiguous"):
            continue
        candidates = []
        ex = full.get("exercise") or {}
        if ex.get("fen"):
            candidates.append((ex["fen"], ex.get("solution") or [], ex.get("hint") or "", "exercise"))
        for pz in full.get("puzzles") or []:
            candidates.append((pz.get("fen"), pz.get("solution") or [], pz.get("hint") or "", "task"))
        tasks = len([c for c in candidates if _legal_fen(c[0])])
        for fen, solution, note, kind in candidates:
            if _legal_fen(fen):
                course = full.get("course") or {}
                return {
                    "source": "site_lesson",
                    "title": full.get("title"),
                    "course": course.get("title") if isinstance(course, dict) else course,
                    "lesson_id": full.get("lesson_id"),
                    "url": full.get("url"),
                    "fen": fen,
                    "key_move": (solution or [None])[0],
                    "solution": list(solution),
                    "kind": kind,
                    "tasks": tasks,
                    "note": note or (full.get("content") or "")[:300],
                }
    return None


def _example_from_base(t: dict) -> Optional[dict]:
    for p in t["positions"]:
        if _legal_fen(p.get("fen")):
            return {
                "source": "knowledge_base",
                "title": p["title_ru"],
                "fen": p["fen"],
                "key_move": p.get("best_move"),
                "arrows": p.get("arrows") or [],
                "note": p.get("plan_ru") or "",
            }
    return None


# A move as the plans write it: «1...Kd6», «2.Kf5», «Qb3», «...Ne4», «O-O», «b4–b5».
# A bare square («слон на c4», «поле d5») is a move only after a move number or
# «...», or as the first half of a «b4–b5» range.
_PLAN_MOVE = re.compile(
    r"(?<![\w-])(?P<prefix>\d+\.+\s*|\.\.\.\s*|…\s*)?"
    r"(?P<move>O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8]|[a-h][1-8])"
    r"(?P<range>\s*[–—-]\s*[a-h][1-8])?(?P<mistake>\?)?(?![\w])"
)
_SIDE_WORD = re.compile(r"\b(бел\w*|ч[её]рн\w*|white|black)", re.IGNORECASE)
MAX_PLAN_ARROWS = 3


def _plan_side(plan: str, m: "re.Match") -> Optional[bool]:
    """Whose move a plan token is: «1...»/«...» Black, «1.» White, else the side named
    last in the same sentence («Белые: h4–h5, Bh6»); None when the text does not say."""
    prefix = m.group("prefix") or ""
    if "..." in prefix or "…" in prefix:
        return chess.BLACK
    if prefix.strip().endswith("."):
        return chess.WHITE
    sentence = re.split(r"[.;!?]\s", plan[: m.start()])[-1]
    words = _SIDE_WORD.findall(sentence)
    if not words:
        return None
    return chess.WHITE if words[-1].lower().startswith(("бел", "white")) else chess.BLACK


def _plan_arrows(fen: str, plan: str) -> list[dict]:
    """Arrows for the moves a plan names that are playable in *fen*.

    Most examples of the base are about a plan, not one best move (36 of 49 had
    no key move, so a shown example came with no arrow at all — the voice coach
    does not draw them itself). The side to move's moves are green, the other
    side's (tried on the board with the turn passed) blue; a move that is not
    legal where the example stands is skipped, so nothing false is drawn.
    """
    try:
        board = chess.Board(fen)
    except ValueError:
        return []
    other = board.copy(stack=False)
    other.push(chess.Move.null())
    arrows: list[dict] = []
    plan = plan or ""
    for m in _PLAN_MOVE.finditer(plan):
        token = m.group("move")
        if token[0] in "abcdefgh" and not (m.group("prefix") or m.group("range")):
            continue  # a square named in the text, not a move
        if m.group("mistake"):
            continue  # «9...cxd4?» is the mistake the text warns about
        side = _plan_side(plan, m)
        boards = [(board, "green"), (other, "blue")]
        if side is not None:
            boards = [pair for pair in boards if pair[0].turn == side]
        for b, brush in boards:
            try:
                mv = b.parse_san(token)
            except ValueError:
                continue
            arrow = {"from": chess.square_name(mv.from_square), "to": chess.square_name(mv.to_square), "brush": brush}
            # One arrow per piece: in «1...Kd6 2.Kf5 Ke7» the later king moves start
            # from another square, so from here they would show a different move.
            if all(a["from"] != arrow["from"] for a in arrows):
                arrows.append(arrow)
            break
        if len(arrows) >= MAX_PLAN_ARROWS:
            break
    return arrows


def _example_actions(example: dict) -> list[dict]:
    if example.get("source") == "site_lesson" and example.get("solution"):
        # A task of the site's lesson goes on as a puzzle the student solves
        # there — an arrow for the key move would give the answer away.
        return [{"type": "set_puzzle", "fen": example["fen"], "solution": example["solution"]}]
    actions = [{"type": "set_fen", "fen": example["fen"]}]
    arrow = _arrow(example["fen"], example.get("key_move"))
    # The base's own arrows first (the idea of the position), then the key move,
    # then the moves its plan names.
    arrows = (example.get("arrows") or ([arrow] if arrow else None)
              or _plan_arrows(example["fen"], example.get("note") or ""))
    if arrows:
        actions.append({"type": "draw_arrows", "arrows": arrows})
    return actions


def get_topic(topic: str, locale: Optional[str] = "ru", user_id: Optional[str] = None,
              topics: Optional[dict] = None, with_lessons: bool = True, show: bool = True) -> dict:
    topics = topics if topics is not None else kb.load_topics()
    if not topics:
        return {"error": "The knowledge base is empty on this server (hermes/content/topics)."}
    matches = kb.find_topics(topic, topics)
    if not matches:
        # The whole map in one go: with only "call list_topics" the model guessed
        # names — five get_topic calls for "the Italian game" (bench 2026-09-28).
        return {
            "error": f"No topic matches {topic!r}.",
            "topics": [{"slug": slug, "title": kb.title(t, locale)} for slug, t in topics.items()],
            "hint": ("Call get_topic with one of these slugs only if it really is the subject. "
                     "If none fits, answer without the knowledge base — do not call get_topic "
                     "again for this question."),
        }
    if len(matches) > 1 and matches[0]["slug"] != (topic or "").strip().lower():
        return {
            "ambiguous": True,
            "topics": [{"slug": t["slug"], "title": kb.title(t, locale), "phase": t["phase"]} for t in matches],
            "hint": "Call get_topic again with the exact slug.",
        }
    t = matches[0]
    out = {
        "slug": t["slug"],
        "phase": t["phase"],
        "phase_title": _phase_title(t["phase"], locale),
        "level": t["level"],
        "title": kb.title(t, locale),
        "summary": kb.summary(t, locale),
        "key_ideas": t["key_ideas_ru"],
        "typical_mistakes": t["typical_mistakes_ru"],
        "positions": [
            {
                "title": p["title_ru"], "fen": p["fen"], "side_to_move": p["side_to_move"],
                "moves": p["moves"], "plan": p["plan_ru"], "best_move": p["best_move"],
            }
            for p in t["positions"]
        ],
        "puzzle_themes": t["lichess_themes"],
        "eco_codes": t["eco_codes"],
        "model_games": t["model_games"],
        "related_topics": t["related"],
    }
    lessons = _related_lessons(t, user_id, locale) if with_lessons else []
    if lessons:
        out["site_lessons"] = lessons
    if show:
        # The site's own lesson first — it is the customer's curriculum — then the base.
        example = _example_from_lessons(lessons, user_id, locale) or _example_from_base(t)
        if example:
            side = "White" if chess.Board(example["fen"]).turn == chess.WHITE else "Black"
            out["example"] = {**example, "side_to_move": side}
            out["board_actions"] = _example_actions(example)
            if example.get("source") == "site_lesson":
                # The customer's own programme: the lesson is the authority, and
                # the answer ends by sending the student to it (2026-10-03).
                where = f"the site's lesson «{example.get('title')}»"
                if example.get("course"):
                    where += f" (course «{example.get('course')}»)"
                tasks = example.get("tasks") or 0
                link = f" Its address: {example['url']}." if example.get("url") else ""
                out["board_hint"] = (
                    f"The position on the student's board is {'the first task' if example.get('kind') == 'task' else 'the exercise'} "
                    f"of {where}{f', which has {tasks} tasks' if tasks > 1 else ''}, set as a puzzle the student can "
                    f"solve right there ({side} to move; the solution is {' '.join(example.get('solution') or []) or 'not given'} — "
                    "do NOT reveal it unless the student asks or fails twice). Explain the concept with this very "
                    "position — read the pieces from its FEN — and END the answer by inviting the student to go "
                    f"through the whole lesson and solve its tasks, naming the lesson and course exactly as here.{link} "
                    "Do not set up any other example in the same answer; offer get_puzzle only after the lesson's tasks."
                )
            else:
                out["board_hint"] = (
                    "The example is ALREADY on the student's board (with an arrow for its key move when "
                    "it has one). "
                    "Explain exactly that position — read the pieces from its FEN, use its note. "
                    "Do not set up any other example yourself and do not replace this one in the same "
                    "answer: OFFER a puzzle (get_puzzle(theme=<puzzle_themes>)) and put it on the board "
                    "only when the student asks for it."
                )
    if "board_hint" not in out:
        out["board_hint"] = ("No example position for this topic: explain it on the student's current board "
                             "or offer a puzzle with get_puzzle(theme=<puzzle_themes>) — never invent a position.")
    return out


LIST_TOPICS_SCHEMA = {
    "name": "list_topics",
    "description": (
        "Map of the coach's thematic knowledge base: strategy, tactics, pawn structures, "
        "typical positions, opening, middlegame, endgame — each topic with level and a one-line "
        "summary. Use it when the student asks what they could learn, or to find the right topic slug."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "phase": {"type": "string", "description": "One of: " + ", ".join(kb.PHASES)},
            "level": {"type": "integer", "description": "1–4, like course levels."},
            "locale": {"type": "string", "description": "ru | kz | en."},
        },
    },
}

GET_TOPIC_SCHEMA = {
    "name": "get_topic",
    "description": (
        "One topic of the knowledge base in full: summary, key ideas, typical mistakes, verified "
        "positions, puzzle themes for get_puzzle, ECO codes, model games and the site's lessons on "
        "the topic — and it PUTS ONE EXAMPLE ON THE BOARD itself (from the site's lesson when there "
        "is one, else the base), returned as `example`. Call it BEFORE explaining or showing a "
        "concept (pin, fork, IQP, Lucena, minority attack…): the example must come from here, never "
        "from memory. show=false only to read the topic without touching the board. Identify by "
        "slug, title, Lichess theme or ECO code."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Slug, title fragment, Lichess theme or ECO code."},
            "locale": {"type": "string", "description": "ru | kz | en."},
            "user_id": {"type": "string", "description": "The student's ID (for lesson statuses)."},
            "show": {"type": "boolean", "description": "Put the example on the board (default true)."},
        },
        "required": ["topic"],
    },
}


def _handle_list_topics(args: dict, **kwargs) -> str:
    level = args.get("level")
    try:
        level = int(level) if level not in (None, "") else None
    except (TypeError, ValueError):
        level = None
    return json.dumps(list_topics(phase=args.get("phase") or None, level=level,
                                  locale=args.get("locale") or "ru"), ensure_ascii=False)


def _handle_get_topic(args: dict, **kwargs) -> str:
    try:
        user_id = resolve_user_id(args, kwargs) or None
    except Exception:
        user_id = None
    return json.dumps(get_topic(str(args.get("topic") or ""), locale=args.get("locale") or "ru",
                                user_id=user_id, show=args.get("show") is not False), ensure_ascii=False)


registry.register(
    name="list_topics",
    toolset="chess",
    schema=LIST_TOPICS_SCHEMA,
    handler=_handle_list_topics,
    description="Map of the thematic knowledge base.",
    emoji="🧭",
)

registry.register(
    name="get_topic",
    toolset="chess",
    schema=GET_TOPIC_SCHEMA,
    handler=_handle_get_topic,
    description="One knowledge-base topic: ideas, positions, puzzles, lessons.",
    emoji="🧠",
)
