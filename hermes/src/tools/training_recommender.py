"""Tool: training_recommender — what to train next, pointing at REAL lessons.

Signals, in priority order:

1. Engine-measured focus themes from the offline curriculum (``coach_curriculum``,
   see ``src/curriculum.py``) — where the student actually blunders.
2. Weaknesses recorded on the profile (``user_chess_profiles.weaknesses``:
   ``{category, description, frequency}``).
3. The student's place in the site's programme (``user_progress``): the lesson
   to continue with.

Each theme / weakness is matched against the programme's lesson and module
titles (RU/EN stems), so a recommendation names a lesson that exists, with its
link, plus a puzzle theme the coach can hand to ``get_puzzle``. When the
programme cannot be read (no Supabase), the old generic advice is returned so
the coach still has something to say.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import httpx

from tools.registry import registry

from src.identity import resolve_user_id
from src.tools.learning_path import (
    SITE_URL, _cap, _loc, fetch_programme, fetch_progress, iter_lessons, next_lesson,
    TITLE_CHAR_CAP,
)

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
TIMEOUT = 10

MAX_RECOMMENDATIONS = 5
LESSONS_PER_THEME = 2

TRAINING_SCHEMA = {
    "name": "training_recommender",
    "description": (
        "What the student should train next: concrete lessons from the site's programme "
        "(with links) matched to their engine-measured weak themes and profile weaknesses, "
        "plus puzzle themes for get_puzzle and the lesson to continue with. Use when the "
        "student asks what to study, for a training plan, or how to fix a weakness."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "The student's ID."},
            "locale": {"type": "string", "description": "ru | kz | en — language for titles."},
        },
        "required": ["user_id"],
    },
}

# Profile weakness category → (lesson-title stems RU/EN, puzzle themes for get_puzzle,
# fallback advice). Stems are lowercase prefixes matched against title tokens.
WEAKNESS_MAP = {
    "tactics": {
        "stems": ("тактик", "вилк", "связк", "двойн", "открыт", "сквозн", "комбинац",
                  "tactic", "fork", "pin", "skewer", "discovered"),
        "puzzle_themes": ["fork", "pin", "discoveredAttack"],
        "advice": "Solve puzzles on forks, pins, skewers and discovered attacks.",
    },
    "endgame": {
        "stems": ("эндшпил", "окончан", "пешечн", "ладейн", "король и пешк", "оппозиц",
                  "endgame", "ending", "pawn ending", "rook ending", "opposition"),
        "puzzle_themes": ["endgame", "pawnEndgame", "rookEndgame"],
        "advice": "Study king-and-pawn and rook endings; practise converting won endgames.",
    },
    "opening_theory": {
        "stems": ("дебют", "начал", "принцип", "развит", "центр", "opening", "development",
                  "principle"),
        "puzzle_themes": ["opening"],
        "advice": "Review opening principles: centre, development, king safety.",
    },
    "positional_play": {
        "stems": ("стратег", "позицион", "план", "структур", "слаб", "форпост", "миттельшпил",
                  "positional", "strategy", "structure", "outpost", "middlegame"),
        "puzzle_themes": ["middlegame", "quietMove"],
        "advice": "Study pawn structures, piece placement and planning.",
    },
    "mate": {
        "stems": ("мат", "матов", "mate", "checkmate"),
        "puzzle_themes": ["mateIn2", "backRankMate"],
        "advice": "Drill checkmate patterns.",
    },
    "time_management": {
        "stems": (),
        "puzzle_themes": [],
        "advice": "Play rapid games and decide faster in known positions.",
    },
}

# Lichess puzzle theme (curriculum focus) → lesson-title stems, when they differ
# from the theme id itself.
THEME_STEMS = {
    "fork": ("вилк", "двойн", "fork"),
    "pin": ("связк", "pin"),
    "skewer": ("сквозн", "рентген", "skewer"),
    "discoveredAttack": ("открыт", "вскрыт", "discovered"),
    "backRankMate": ("последн", "горизонтал", "back rank", "мат"),
    "mateIn1": ("мат", "mate"),
    "mateIn2": ("мат", "mate"),
    "mateIn3": ("мат", "mate"),
    "smotheredMate": ("спёрт", "сперт", "smothered", "мат"),
    "hangingPiece": ("висяч", "незащищ", "hanging"),
    "trappedPiece": ("ловл", "запер", "trapped"),
    "promotion": ("превращ", "проходн", "promotion", "passed"),
    "endgame": ("эндшпил", "окончан", "endgame", "ending"),
    "pawnEndgame": ("пешечн", "король и пешк", "pawn ending", "оппозиц"),
    "rookEndgame": ("ладейн", "rook ending"),
    "opening": ("дебют", "opening"),
    "middlegame": ("миттельшпил", "стратег", "план", "middlegame"),
    "sacrifice": ("жертв", "sacrifice"),
    "deflection": ("отвлеч", "deflection"),
    "attraction": ("завлеч", "attraction"),
    "zugzwang": ("цугцванг", "zugzwang"),
    "exposedKing": ("открыт", "корол", "exposed king"),
    "kingsideAttack": ("атак", "королевск", "kingside"),
    "queensideAttack": ("атак", "ферзев", "queenside"),
    "defensiveMove": ("защит", "оборон", "defen"),
}

# Generic advice when nothing is known about the student and no programme.
DEFAULT_RECOMMENDATIONS = [
    {
        "type": "puzzle",
        "title": "Daily Puzzles",
        "description": "Solve daily puzzles to maintain tactical sharpness.",
        "priority": "medium",
        "weakness_addressed": "general",
        "puzzle_themes": ["fork", "pin", "mateIn2"],
    },
    {
        "type": "practice",
        "title": "Analyze Your Games",
        "description": "Review your recent games to identify areas for improvement.",
        "priority": "medium",
        "weakness_addressed": "general",
    },
]


# ── Signals ────────────────────────────────────────────────────────────────


def _fetch_user_weaknesses(user_id: str, supabase_url: str = None, supabase_key: str = None) -> list[dict]:
    base = supabase_url or SUPABASE_URL
    api_key = supabase_key or SUPABASE_KEY
    if not base or not api_key:
        return []
    headers = {"apikey": api_key, "Authorization": f"Bearer {api_key}"}
    try:
        resp = httpx.get(
            f"{base}/rest/v1/user_chess_profiles",
            params={"user_id": f"eq.{user_id}", "select": "weaknesses"},
            headers=headers, timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list):
            return data[0].get("weaknesses", []) or []
    except Exception:
        logger.exception("Failed to fetch weaknesses for user %s", user_id)
    return []


def _fetch_focus_themes(user_id: str) -> list[dict]:
    """Engine-measured focus themes ({theme, rationale, ...}) — fail-open."""
    try:
        from src.curriculum import get_cached_curriculum

        return get_cached_curriculum(user_id) or []
    except Exception:
        return []


# ── Matching lessons ───────────────────────────────────────────────────────


def _title_blob(*rows: dict) -> str:
    parts = []
    for r in rows:
        for f in ("title", "title_ru", "title_kk"):
            v = r.get(f)
            if isinstance(v, str):
                parts.append(v.lower())
    return " ".join(parts)


def match_lessons(programme: dict, stems: tuple, progress: dict, limit: int = LESSONS_PER_THEME) -> list[tuple]:
    """Lessons whose own or module title contains one of *stems*, not-completed
    first, in study order. Multi-word stems match as phrases."""
    if not stems:
        return []
    hits = []
    for c, m, l in iter_lessons(programme):
        own = _title_blob(l)
        blob = own + " " + _title_blob(m)
        score = 0
        for s in stems:
            if s in own:
                score += 2
            elif s in blob:
                score += 1
        if score:
            done = (progress.get(l["id"]) or {}).get("status") == "completed"
            hits.append((done, -score, c, m, l))
    hits.sort(key=lambda t: (t[0], t[1]))
    return [(c, m, l) for _, _, c, m, l in hits[:limit]]


def _lesson_rec(c: dict, m: dict, l: dict, progress: dict, locale: Optional[str], *,
                reason: str, weakness: str, priority: str, puzzle_themes: list[str]) -> dict:
    status = (progress.get(l["id"]) or {}).get("status") or "not_started"
    return {
        "type": "lesson",
        "title": _cap(_loc(l, "title", locale), TITLE_CHAR_CAP),
        "course": _cap(_loc(c, "title", locale), TITLE_CHAR_CAP),
        "module": _cap(_loc(m, "title", locale), TITLE_CHAR_CAP),
        "lesson_slug": l.get("slug"),
        "course_slug": c.get("slug"),
        "url": f"{SITE_URL}/learn/{c.get('slug')}/{l.get('slug')}",
        "status": status,
        "description": reason,
        "priority": priority,
        "weakness_addressed": weakness,
        "puzzle_themes": puzzle_themes,
    }


# ── The recommendation ─────────────────────────────────────────────────────


def training_recommender(
    user_id: str,
    locale: Optional[str] = "ru",
    supabase_url: str = None,
    supabase_key: str = None,
    _weaknesses: list[dict] = None,
    _focus: list[dict] = None,
    _programme: Optional[dict] = None,
    _progress: Optional[dict] = None,
) -> dict:
    """Recommendations grounded in the site's programme (see module docstring).
    The underscore parameters let tests inject the signals directly."""
    weaknesses = _weaknesses if _weaknesses is not None else _fetch_user_weaknesses(
        user_id, supabase_url=supabase_url, supabase_key=supabase_key)
    focus = _focus if _focus is not None else _fetch_focus_themes(user_id)
    programme = _programme if _programme is not None else fetch_programme(url=supabase_url, key=supabase_key)
    if programme is None:
        return _generic(user_id, weaknesses, focus)
    progress = _progress if _progress is not None else (
        fetch_progress(user_id, url=supabase_url, key=supabase_key) or {})

    recs: list[dict] = []
    seen: set = set()

    def _add(rec: dict) -> None:
        key = rec.get("lesson_slug") or rec.get("title")
        if key in seen or len(recs) >= MAX_RECOMMENDATIONS:
            return
        seen.add(key)
        recs.append(rec)

    # 1. Engine-measured focus themes (strongest evidence).
    for f in focus[:3]:
        theme = str(f.get("theme") or "").strip()
        if not theme:
            continue
        stems = THEME_STEMS.get(theme, (theme.lower(),))
        rationale = _cap(str(f.get("rationale") or ""), 200)
        reason = f"Engine-measured weak theme «{theme}»" + (f": {rationale}" if rationale else "")
        matched = match_lessons(programme, stems, progress)
        for c, m, l in matched:
            _add(_lesson_rec(c, m, l, progress, locale, reason=reason, weakness=theme,
                             priority="high", puzzle_themes=[theme]))
        if not matched:
            _add({"type": "puzzle", "title": f"Puzzles: {theme}", "description": reason,
                  "priority": "high", "weakness_addressed": theme, "puzzle_themes": [theme]})

    # 2. Profile weaknesses.
    for w in sorted(weaknesses, key=lambda w: w.get("frequency", 0), reverse=True):
        category = str(w.get("category") or "").strip()
        spec = WEAKNESS_MAP.get(category)
        if not spec:
            continue
        desc = _cap(str(w.get("description") or ""), 160)
        reason = f"Profile weakness «{category}»" + (f": {desc}" if desc else "")
        matched = match_lessons(programme, spec["stems"], progress)
        for c, m, l in matched:
            _add(_lesson_rec(c, m, l, progress, locale, reason=reason, weakness=category,
                             priority="high", puzzle_themes=spec["puzzle_themes"]))
        if not matched:
            _add({"type": "puzzle" if spec["puzzle_themes"] else "practice",
                  "title": spec["advice"], "description": reason, "priority": "medium",
                  "weakness_addressed": category, "puzzle_themes": spec["puzzle_themes"]})

    # 3. Where the student is in the programme.
    nxt = next_lesson(programme, progress)
    continue_with = None
    if nxt:
        c, m, l = nxt
        continue_with = _lesson_rec(c, m, l, progress, locale,
                                    reason="Next lesson in the programme.", weakness="programme",
                                    priority="medium", puzzle_themes=[])
        if not recs:
            _add(continue_with)

    return {
        "user_id": user_id,
        "recommendations": recs or DEFAULT_RECOMMENDATIONS,
        "continue_with": continue_with,
        "signals": {
            "focus_themes": [f.get("theme") for f in focus[:3] if f.get("theme")],
            "weaknesses": [w.get("category") for w in weaknesses if w.get("category")],
        },
        "hint": "Name the lesson and give its url; call get_lesson to teach it on the board; "
                "use puzzle_themes with get_puzzle.",
    }


def _generic(user_id: str, weaknesses: list[dict], focus: list[dict]) -> dict:
    """No programme available: generic advice keyed on the weakness categories."""
    recs = []
    seen = set()
    for f in focus[:3]:
        theme = str(f.get("theme") or "")
        if theme and theme not in seen:
            seen.add(theme)
            recs.append({"type": "puzzle", "title": f"Puzzles: {theme}",
                         "description": _cap(str(f.get("rationale") or "Engine-measured weak theme."), 200),
                         "priority": "high", "weakness_addressed": theme, "puzzle_themes": [theme]})
    for w in sorted(weaknesses, key=lambda w: w.get("frequency", 0), reverse=True):
        category = str(w.get("category") or "")
        spec = WEAKNESS_MAP.get(category)
        if not spec or category in seen:
            continue
        seen.add(category)
        recs.append({"type": "puzzle" if spec["puzzle_themes"] else "practice",
                     "title": spec["advice"], "description": spec["advice"], "priority": "high",
                     "weakness_addressed": category, "puzzle_themes": spec["puzzle_themes"]})
    return {
        "user_id": user_id,
        "recommendations": recs or DEFAULT_RECOMMENDATIONS,
        "continue_with": None,
        "note": "Study programme unavailable — generic advice only.",
    }


def _handle_training_recommender(args: dict, **kwargs) -> str:
    result = training_recommender(user_id=resolve_user_id(args, kwargs), locale=args.get("locale") or "ru")
    return json.dumps(result, ensure_ascii=False)


registry.register(
    name="training_recommender",
    toolset="chess",
    schema=TRAINING_SCHEMA,
    handler=_handle_training_recommender,
    description="What to train next: real lessons matched to weaknesses.",
    emoji="🎓",
)
