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
        from src.tools.learning_path import SITE_URL, _loc, fetch_programme, fetch_progress
        from src.tools.training_recommender import match_lessons

        programme = fetch_programme()
        if not programme:
            return []
        progress = (fetch_progress(user_id) or {}) if user_id else {}
        out = []
        for c, m, l in match_lessons(programme, stems, progress, limit=MAX_RELATED_LESSONS):
            out.append({
                "title": _loc(l, "title", locale), "course": _loc(c, "title", locale),
                "slug": l.get("slug"), "url": f"{SITE_URL}/learn/{c.get('slug')}/{l.get('slug')}",
                "status": (progress.get(l["id"]) or {}).get("status") or "not_started",
            })
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
        try:
            full = get_lesson(brief.get("slug") or brief.get("title") or "", user_id=user_id, locale=locale)
        except Exception:  # noqa: BLE001
            logger.debug("lesson fetch for the topic example failed", exc_info=True)
            continue
        if "error" in full or full.get("ambiguous"):
            continue
        candidates = []
        ex = full.get("exercise") or {}
        if ex.get("fen"):
            candidates.append((ex["fen"], (ex.get("solution") or [None])[0], ex.get("hint") or ""))
        for pz in full.get("puzzles") or []:
            candidates.append((pz.get("fen"), (pz.get("solution") or [None])[0], pz.get("hint") or ""))
        for fen, key_move, note in candidates:
            if _legal_fen(fen):
                return {
                    "source": "site_lesson",
                    "title": full.get("title"),
                    "url": full.get("url"),
                    "fen": fen,
                    "key_move": key_move,
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
                "note": p.get("plan_ru") or "",
            }
    return None


def _example_actions(example: dict) -> list[dict]:
    actions = [{"type": "set_fen", "fen": example["fen"]}]
    arrow = _arrow(example["fen"], example.get("key_move"))
    if arrow:
        actions.append({"type": "draw_arrows", "arrows": [arrow]})
    return actions


def get_topic(topic: str, locale: Optional[str] = "ru", user_id: Optional[str] = None,
              topics: Optional[dict] = None, with_lessons: bool = True, show: bool = True) -> dict:
    topics = topics if topics is not None else kb.load_topics()
    if not topics:
        return {"error": "The knowledge base is empty on this server (hermes/content/topics)."}
    matches = kb.find_topics(topic, topics)
    if not matches:
        return {"error": f"No topic matches {topic!r}. Call list_topics to see them."}
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
