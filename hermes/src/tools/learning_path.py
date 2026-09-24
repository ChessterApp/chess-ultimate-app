"""Tools: get_learning_path / get_lesson — the site's own study programme.

The site already has a programme (``/learn``): courses → modules → lessons, with
theory text, one-move exercises and sets of lesson puzzles, and it records the
student's progress per lesson. Until now the coach only saw a list of completed
lesson titles and recommended made-up "courses". These tools read the real
tables the site writes (``backend/schema.sql`` + migrations 001/003/005/010/014):

- ``courses``  (slug, title/title_ru/title_kk, level, order_index)
- ``modules``  (course_id, title/title_ru, order_index)
- ``lessons``  (module_id, slug, title/title_ru, lesson_type, content/content_ru,
               exercise_fen, solution_move, solution_line, exercise_solution,
               hint_text/hint_text_ru, order_index)
- ``lesson_puzzles`` (lesson_id, fen, solution_move UCI, hint_text, order_index)
- ``user_progress``  (user_id, lesson_id, status, score, updated_at)

The programme itself changes rarely, so it is cached in-process for a few
minutes; the student's progress is read fresh on every call. Everything from
the database is data for the coach, never an instruction: strings are
length-capped and returned as JSON fields.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Optional

import chess

from tools.registry import registry

from src.identity import resolve_user_id
from src.tools.user_data import _supabase_query

logger = logging.getLogger(__name__)

SITE_URL = os.environ.get("SITE_URL", "https://chesster.io").rstrip("/")

PROGRAMME_TTL_SECONDS = 300
CONTENT_CHAR_CAP = 6000       # lesson text handed to the model per call
TITLE_CHAR_CAP = 120
MAX_LESSON_MATCHES = 5

_programme_lock = threading.Lock()
_programme_cache: dict = {"at": 0.0, "value": None}


# ── Localisation ───────────────────────────────────────────────────────────


def _loc(row: dict, field: str, locale: Optional[str]) -> str:
    """Pick the localised column: ``<field>_ru`` for ru, ``<field>_kk`` for kz/kk,
    falling back to the base column (which on this site is usually Russian too)."""
    loc = (locale or "ru").lower()
    candidates = []
    if loc in ("kz", "kk"):
        candidates = [f"{field}_kk", f"{field}_ru"]
    elif loc == "ru":
        candidates = [f"{field}_ru"]
    for c in candidates:
        v = row.get(c)
        if isinstance(v, str) and v.strip():
            return v.strip()
    v = row.get(field)
    return v.strip() if isinstance(v, str) else ""


def _cap(text: Optional[str], limit: int) -> str:
    if not isinstance(text, str):
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ── Programme (courses → modules → lessons) ────────────────────────────────

COURSE_SELECT = "id,slug,title,title_ru,title_kk,description,description_ru,level,order_index"
MODULE_SELECT = "id,course_id,title,title_ru,description,description_ru,order_index"
LESSON_LIST_SELECT = "id,slug,module_id,title,title_ru,lesson_type,exercise_type,order_index"

# PostgREST rejects the whole query when one selected column is missing, and the
# optional columns above come from later migrations (003 slug, 010 *_ru, 001
# exercise_type). If the rich select fails, retry with the base schema so the
# tool degrades to English titles instead of failing outright.
COURSE_SELECT_MIN = "id,slug,title,level,order_index"
MODULE_SELECT_MIN = "id,course_id,title,order_index"
LESSON_LIST_SELECT_MIN = "id,slug,module_id,title,lesson_type,order_index"


def _query_with_fallback(table: str, select: str, select_min: str, url: str, key: str, **extra) -> Optional[list]:
    rows = _supabase_query(table, {"select": select, **extra}, url=url, key=key)
    if rows is None and select_min != select:
        logger.warning("%s: rich select failed, retrying with base columns", table)
        rows = _supabase_query(table, {"select": select_min, **extra}, url=url, key=key)
    return rows


def fetch_programme(url: str = None, key: str = None, force: bool = False) -> Optional[dict]:
    """Courses with their modules and lessons, in site order. ``None`` when the
    database is unreachable (callers turn that into a tool error, not silence)."""
    now = time.monotonic()
    with _programme_lock:
        cached = _programme_cache["value"]
        if cached is not None and not force and now - _programme_cache["at"] < PROGRAMME_TTL_SECONDS:
            return cached

    order = {"order": "order_index.asc"}
    courses = _query_with_fallback("courses", COURSE_SELECT, COURSE_SELECT_MIN, url, key, **order)
    modules = _query_with_fallback("modules", MODULE_SELECT, MODULE_SELECT_MIN, url, key, **order)
    lessons = _query_with_fallback("lessons", LESSON_LIST_SELECT, LESSON_LIST_SELECT_MIN, url, key, **order)
    if courses is None or modules is None or lessons is None:
        return None
    courses = [r for r in courses if isinstance(r, dict) and r.get("id")]
    modules = [r for r in modules if isinstance(r, dict) and r.get("id")]
    lessons = [r for r in lessons if isinstance(r, dict) and r.get("id")]

    modules_by_course: dict[str, list] = {}
    for m in modules:
        modules_by_course.setdefault(m.get("course_id"), []).append(m)
    lessons_by_module: dict[str, list] = {}
    for l in lessons:
        lessons_by_module.setdefault(l.get("module_id"), []).append(l)

    ordered_courses = []
    for c in sorted(courses, key=lambda r: (r.get("order_index") or 0)):
        c = dict(c)
        c["modules"] = []
        for m in sorted(modules_by_course.get(c["id"], []), key=lambda r: (r.get("order_index") or 0)):
            m = dict(m)
            m["lessons"] = sorted(lessons_by_module.get(m["id"], []), key=lambda r: (r.get("order_index") or 0))
            c["modules"].append(m)
        ordered_courses.append(c)

    programme = {"courses": ordered_courses}
    with _programme_lock:
        _programme_cache["value"] = programme
        _programme_cache["at"] = now
    return programme


def clear_programme_cache() -> None:
    with _programme_lock:
        _programme_cache["value"] = None
        _programme_cache["at"] = 0.0


def iter_lessons(programme: dict):
    """Yield (course, module, lesson) in study order."""
    for c in programme.get("courses", []):
        for m in c.get("modules", []):
            for l in m.get("lessons", []):
                yield c, m, l


# ── Student progress ───────────────────────────────────────────────────────


def fetch_progress(user_id: str, url: str = None, key: str = None) -> Optional[dict]:
    """lesson_id → {status, score, updated_at}. ``None`` when the query failed."""
    rows = _supabase_query(
        "user_progress",
        {"user_id": f"eq.{user_id}", "select": "lesson_id,status,score,updated_at,completed_at",
         "order": "updated_at.desc"},
        url=url, key=key,
    )
    if rows is None:
        return None
    return {r["lesson_id"]: r for r in rows if r.get("lesson_id")}


def _lesson_view(course: dict, module: dict, lesson: dict, progress: dict, locale: Optional[str]) -> dict:
    p = progress.get(lesson["id"]) or {}
    view = {
        "lesson_id": lesson["id"],
        "slug": lesson.get("slug"),
        "title": _cap(_loc(lesson, "title", locale), TITLE_CHAR_CAP),
        "type": lesson.get("lesson_type"),
        "status": p.get("status") or "not_started",
        "url": f"{SITE_URL}/learn/{course.get('slug')}/{lesson.get('slug')}",
    }
    if p.get("score") is not None:
        view["score"] = p.get("score")
    return view


def next_lesson(programme: dict, progress: dict) -> Optional[tuple]:
    """The lesson to continue with: the most recently touched in-progress lesson,
    else the first not-completed lesson in study order."""
    in_progress = [
        (c, m, l) for c, m, l in iter_lessons(programme)
        if (progress.get(l["id"]) or {}).get("status") == "in_progress"
    ]
    if in_progress:
        return max(in_progress, key=lambda t: (progress[t[2]["id"]].get("updated_at") or ""))
    for c, m, l in iter_lessons(programme):
        if (progress.get(l["id"]) or {}).get("status") != "completed":
            return c, m, l
    return None


def _match_course(programme: dict, needle: str) -> Optional[dict]:
    n = needle.strip().lower()
    if not n:
        return None
    for c in programme.get("courses", []):
        if n in (c.get("slug") or "").lower() or n == (c.get("id") or "").lower():
            return c
    for c in programme.get("courses", []):
        for field in ("title", "title_ru", "title_kk"):
            if n in (c.get(field) or "").lower():
                return c
    return None


def get_learning_path(
    user_id: str,
    locale: Optional[str] = "ru",
    course: Optional[str] = None,
    supabase_url: str = None,
    supabase_key: str = None,
) -> dict:
    """The site's programme with the student's progress.

    Without ``course``: every course with lesson counts and the lesson to
    continue with. With ``course`` (slug or part of a title): that course
    expanded to modules and lessons, each with its status.
    """
    programme = fetch_programme(url=supabase_url, key=supabase_key)
    if programme is None:
        return {"error": "Could not read the study programme (Supabase unavailable)."}
    progress = fetch_progress(user_id, url=supabase_url, key=supabase_key)
    if progress is None:
        progress = {}
        progress_note = "Progress unavailable — statuses below assume nothing completed."
    else:
        progress_note = None

    if course:
        c = _match_course(programme, course)
        if c is None:
            return {
                "error": f"No course matches {course!r}.",
                "courses": [
                    {"slug": x.get("slug"), "title": _loc(x, "title", locale)} for x in programme["courses"]
                ],
            }
        modules = []
        for m in c.get("modules", []):
            modules.append({
                "module_id": m["id"],
                "title": _cap(_loc(m, "title", locale), TITLE_CHAR_CAP),
                "lessons": [_lesson_view(c, m, l, progress, locale) for l in m.get("lessons", [])],
            })
        out = {
            "course": {
                "slug": c.get("slug"),
                "title": _cap(_loc(c, "title", locale), TITLE_CHAR_CAP),
                "level": c.get("level"),
                "description": _cap(_loc(c, "description", locale), 400),
                "url": f"{SITE_URL}/learn/{c.get('slug')}",
            },
            "modules": modules,
        }
        if progress_note:
            out["note"] = progress_note
        return out

    courses_out = []
    total = completed = 0
    for c in programme["courses"]:
        lessons = [l for m in c.get("modules", []) for l in m.get("lessons", [])]
        done = sum(1 for l in lessons if (progress.get(l["id"]) or {}).get("status") == "completed")
        total += len(lessons)
        completed += done
        courses_out.append({
            "slug": c.get("slug"),
            "title": _cap(_loc(c, "title", locale), TITLE_CHAR_CAP),
            "level": c.get("level"),
            "lessons_total": len(lessons),
            "lessons_completed": done,
            "url": f"{SITE_URL}/learn/{c.get('slug')}",
        })

    nxt = next_lesson(programme, progress)
    out = {
        "user_id": user_id,
        "lessons_total": total,
        "lessons_completed": completed,
        "courses": courses_out,
        "continue_with": (
            {**_lesson_view(nxt[0], nxt[1], nxt[2], progress, locale),
             "course": _cap(_loc(nxt[0], "title", locale), TITLE_CHAR_CAP),
             "module": _cap(_loc(nxt[1], "title", locale), TITLE_CHAR_CAP)}
            if nxt else None
        ),
        "hint": "Call get_learning_path with course=<slug> to see its modules and lessons; "
                "get_lesson with lesson=<slug> to read a lesson and put its exercise on the board.",
    }
    if progress_note:
        out["note"] = progress_note
    return out


# ── One lesson ─────────────────────────────────────────────────────────────

LESSON_FULL_SELECT = (
    "id,slug,module_id,title,title_ru,lesson_type,exercise_type,order_index,"
    "content,content_ru,exercise_fen,solution_move,solution_line,exercise_solution,"
    "hint_text,hint_text_ru,success_message,success_message_ru,"
    "lesson_puzzles(id,order_index,fen,solution_move,hint_text,success_message)"
)
LESSON_FULL_SELECT_MIN = (
    "id,slug,module_id,title,lesson_type,order_index,content,exercise_fen,exercise_solution,"
    "lesson_puzzles(id,order_index,fen,solution_move,hint_text,success_message)"
)


def _norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", (text or "").lower(), flags=re.UNICODE).strip()


# Words that carry no signal when the student names a lesson ("урок про пешку").
_LESSON_STOPWORDS = frozenset({
    "урок", "уроки", "про", "и", "в", "на", "о", "об", "по", "с", "для", "тема", "тему",
    "открой", "объясни", "разбери", "покажи", "the", "a", "an", "lesson", "about", "on",
    "of", "and", "сабақ", "туралы", "және",
})


def _stem_match(a: str, b: str) -> bool:
    """Inflection-tolerant token match: one is a prefix of the other and the
    shared prefix is at least four characters ("пешку" ~ "пешка", "короля" ~ "король")."""
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and long_.startswith(short[: max(4, len(short) - 1)])


def find_lessons(programme: dict, needle: str) -> list[tuple]:
    """Lessons matching a slug, an id, or a fragment of a title (any language).
    Exact slug/id first, then substring matches, then token overlap."""
    n = (needle or "").strip().lower()
    if not n:
        return []
    exact, contains, overlap = [], [], []
    n_tokens = [t for t in _norm(n).split() if t not in _LESSON_STOPWORDS]
    for c, m, l in iter_lessons(programme):
        slug = (l.get("slug") or "").lower()
        if n == slug or n == (l.get("id") or "").lower():
            exact.append((c, m, l))
            continue
        titles = [(l.get(f) or "").lower() for f in ("title", "title_ru")]
        if any(n in t for t in titles if t):
            contains.append((c, m, l))
            continue
        if n_tokens:
            toks = set(_norm(" ".join(titles)).split())
            hit = sum(1 for q in n_tokens if any(_stem_match(q, t) for t in toks))
            if hit and hit >= max(1, (len(n_tokens) + 1) // 2):
                overlap.append((hit, c, m, l))
    overlap.sort(key=lambda t: -t[0])
    if overlap and n_tokens and overlap[0][0] == len(n_tokens):
        # A lesson matched every word the student used: partial matches are noise.
        overlap = [t for t in overlap if t[0] == len(n_tokens)]
    return exact + contains + [(c, m, l) for _, c, m, l in overlap]


def _uci_to_san(fen: Optional[str], uci: Optional[str]) -> Optional[str]:
    if not fen or not uci:
        return None
    try:
        board = chess.Board(fen)
        return board.san(chess.Move.from_uci(uci.strip()))
    except Exception:
        return None


def _solution_san(fen: Optional[str], raw) -> list[str]:
    """Best-effort SAN list from ``solution_move`` (UCI or SAN) or ``solution_line``."""
    moves: list[str] = []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            raw = [raw]
    if isinstance(raw, dict):
        raw = raw.get("moves") or raw.get("line") or [raw.get("move")]
    if not isinstance(raw, list):
        return moves
    try:
        board = chess.Board(fen) if fen else None
    except Exception:
        board = None
    for item in raw:
        mv = item.get("move") if isinstance(item, dict) else item
        if not isinstance(mv, str) or not mv.strip():
            continue
        mv = mv.strip()
        if board is not None:
            try:
                move = chess.Move.from_uci(mv) if re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", mv) else board.parse_san(mv)
                moves.append(board.san(move))
                board.push(move)
                continue
            except Exception:
                board = None  # stop converting, keep raw from here
        moves.append(mv)
    return moves


def get_lesson(
    lesson: str,
    user_id: Optional[str] = None,
    locale: Optional[str] = "ru",
    supabase_url: str = None,
    supabase_key: str = None,
) -> dict:
    """One lesson in full: text, exercise (FEN + solution in SAN), its puzzles
    (FEN + solution in SAN + hint), link, and the student's status."""
    programme = fetch_programme(url=supabase_url, key=supabase_key)
    if programme is None:
        return {"error": "Could not read the study programme (Supabase unavailable)."}
    matches = find_lessons(programme, lesson)
    if not matches:
        return {"error": f"No lesson matches {lesson!r}. Use get_learning_path to see the lesson titles."}
    if len(matches) > 1 and not any((l.get("slug") or "").lower() == lesson.strip().lower() for _, _, l in matches):
        return {
            "ambiguous": True,
            "lessons": [
                {"slug": l.get("slug"), "title": _loc(l, "title", locale),
                 "course": _loc(c, "title", locale), "module": _loc(m, "title", locale)}
                for c, m, l in matches[:MAX_LESSON_MATCHES]
            ],
            "hint": "Call get_lesson again with the exact slug.",
        }
    course, module, brief = matches[0]

    rows = _query_with_fallback(
        "lessons", LESSON_FULL_SELECT, LESSON_FULL_SELECT_MIN, supabase_url, supabase_key,
        id=f"eq.{brief['id']}", limit="1",
    )
    if not rows:
        return {"error": "Could not read the lesson (Supabase unavailable)."}
    row = rows[0]

    status = None
    if user_id:
        progress = fetch_progress(user_id, url=supabase_url, key=supabase_key) or {}
        status = (progress.get(row["id"]) or {}).get("status") or "not_started"

    content = _loc(row, "content", locale)
    out = {
        "lesson_id": row["id"],
        "slug": row.get("slug"),
        "title": _cap(_loc(row, "title", locale), TITLE_CHAR_CAP),
        "course": {"slug": course.get("slug"), "title": _cap(_loc(course, "title", locale), TITLE_CHAR_CAP)},
        "module": _cap(_loc(module, "title", locale), TITLE_CHAR_CAP),
        "type": row.get("lesson_type"),
        "url": f"{SITE_URL}/learn/{course.get('slug')}/{row.get('slug')}",
        "content": _cap(content, CONTENT_CHAR_CAP),
        "content_truncated": len(content) > CONTENT_CHAR_CAP,
    }
    if status:
        out["student_status"] = status

    fen = row.get("exercise_fen")
    if fen:
        solution = _solution_san(fen, row.get("solution_line")) or _solution_san(fen, row.get("solution_move")) \
            or _solution_san(fen, row.get("exercise_solution"))
        exercise = {
            "fen": fen,
            "type": row.get("exercise_type"),
            "solution": solution,
            "hint": _cap(_loc(row, "hint_text", locale), 400),
            "success_message": _cap(_loc(row, "success_message", locale), 400),
        }
        if isinstance(row.get("exercise_solution"), list):
            exercise["explanations"] = [
                {"move": e.get("move"), "explanation": _cap(e.get("explanation"), 300)}
                for e in row["exercise_solution"] if isinstance(e, dict)
            ][:6]
        out["exercise"] = exercise
        if solution:
            out["board_puzzle"] = {"fen": fen, "solution": solution}

    puzzles = sorted(row.get("lesson_puzzles") or [], key=lambda p: p.get("order_index") or 0)
    if puzzles:
        out["puzzles"] = [
            {
                "n": i + 1,
                "fen": p.get("fen"),
                "solution": [s for s in [_uci_to_san(p.get("fen"), p.get("solution_move")) or p.get("solution_move")] if s],
                "hint": _cap(p.get("hint_text"), 300),
            }
            for i, p in enumerate(puzzles)
        ]
        out["puzzles_hint"] = ("To put a puzzle on the student's board call board_control with "
                               "action_type=set_puzzle, fen=<fen> and solution=<solution>.")
    return out


# ── Registration ───────────────────────────────────────────────────────────

LEARNING_PATH_SCHEMA = {
    "name": "get_learning_path",
    "description": (
        "The site's study programme (courses → modules → lessons) with the student's "
        "progress and the lesson to continue with. Use it whenever the student asks what "
        "to study next, about their courses/lessons, or which lesson covers a topic. "
        "Pass course=<slug or title> to expand one course into its lessons."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "The student's ID."},
            "locale": {"type": "string", "description": "ru | kz | en — language for titles."},
            "course": {"type": "string", "description": "Course slug or part of its title to expand."},
        },
        "required": ["user_id"],
    },
}

LESSON_SCHEMA = {
    "name": "get_lesson",
    "description": (
        "Read one lesson of the site's programme: its text, exercise (FEN + solution), "
        "puzzles (FEN + solution + hint) and link. Use it to teach or explain a lesson, "
        "to put its exercise on the board (board_control set_puzzle with the returned fen "
        "and solution), or to check what a lesson covers. Identify the lesson by slug, id or "
        "part of its title."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "lesson": {"type": "string", "description": "Lesson slug, id, or part of its title."},
            "user_id": {"type": "string", "description": "The student's ID (for their status)."},
            "locale": {"type": "string", "description": "ru | kz | en — language for the text."},
        },
        "required": ["lesson"],
    },
}


def _handle_get_learning_path(args: dict, **kwargs) -> str:
    result = get_learning_path(
        user_id=resolve_user_id(args, kwargs),
        locale=args.get("locale") or "ru",
        course=args.get("course"),
    )
    return json.dumps(result, ensure_ascii=False)


def _handle_get_lesson(args: dict, **kwargs) -> str:
    try:
        user_id = resolve_user_id(args, kwargs)
    except Exception:
        user_id = None
    result = get_lesson(
        lesson=str(args.get("lesson") or ""),
        user_id=user_id,
        locale=args.get("locale") or "ru",
    )
    return json.dumps(result, ensure_ascii=False)


registry.register(
    name="get_learning_path",
    toolset="chess",
    schema=LEARNING_PATH_SCHEMA,
    handler=_handle_get_learning_path,
    description="The site's study programme with the student's progress.",
    emoji="🗺️",
)

registry.register(
    name="get_lesson",
    toolset="chess",
    schema=LESSON_SCHEMA,
    handler=_handle_get_lesson,
    description="Read one lesson: text, exercise, puzzles, link.",
    emoji="📖",
)
