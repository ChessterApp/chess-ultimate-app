"""Tools: list_topics / get_topic — the thematic knowledge base (brief, section 1д).

``list_topics`` gives the map: seven sections, each topic with level and one-line
summary. ``get_topic`` gives one topic in full — summary, key ideas, typical
mistakes, verified positions (FEN + plan) the coach can put on the board with
board_control set_fen, puzzle themes for get_puzzle, ECO codes for
get_opening_stats, model games for search_master_games, and the site's lessons
that cover the topic (matched through the programme by title stems).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from tools.registry import registry

from src import knowledge_base as kb
from src.identity import resolve_user_id

logger = logging.getLogger(__name__)

MAX_RELATED_LESSONS = 4


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


def get_topic(topic: str, locale: Optional[str] = "ru", user_id: Optional[str] = None,
              topics: Optional[dict] = None, with_lessons: bool = True) -> dict:
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
        "board_hint": "Show a position with board_control set_fen (fen above); draw the plan with draw_arrows; "
                      "offer a puzzle with get_puzzle(theme=<puzzle_themes>).",
    }
    if with_lessons:
        lessons = _related_lessons(t, user_id, locale)
        if lessons:
            out["site_lessons"] = lessons
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
        "example positions (FEN + plan — put them on the board with board_control set_fen), puzzle "
        "themes for get_puzzle, ECO codes, model games and the site's lessons on the topic. Use it "
        "BEFORE explaining a concept (fork, IQP, Lucena, minority attack…) so the explanation and "
        "the board example come from the base, not from memory. Identify by slug, title, Lichess "
        "theme or ECO code."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Slug, title fragment, Lichess theme or ECO code."},
            "locale": {"type": "string", "description": "ru | kz | en."},
            "user_id": {"type": "string", "description": "The student's ID (for lesson statuses)."},
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
                                user_id=user_id), ensure_ascii=False)


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
