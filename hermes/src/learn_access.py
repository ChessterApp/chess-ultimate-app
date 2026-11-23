"""Which lessons of the programme are open to the student — the same locks as the site's /learn (tester 20.11).

The coach offered the lesson «Двойной удар» of the course «Шахматная тактика» and opened it on «да, открой», while
/learn showed that course under a lock (Ступень 2). Asan, 22.11: «только те, которые ему открыты, чтобы не лез; а так
тренер говорит: вот начни проходить те уроки, чтобы дойти до этого».

The locks are the site's ``computeLockStates`` (frontend src/lib/learn-gating.ts), over the courses in their order:
- the first course is open;
- a course is open when the one before it is complete, or when it is complete itself;
- a Chess Empire student's courses up to their school level are open (``floor``, the site's ``coachLearnFloor``:
  the site's proxy sends it as the ``x-learn-floor`` header and the direct path's pass carries it — never the page).
A course is complete when every one of its lessons is (the backend's ``compute_progress_by_course``).

Unread programme or progress: everything stays open, as before — a lookup that fails never hides a lesson.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_S = 60.0
_floors: dict[str, int] = {}
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def floor_from_header(value) -> Optional[int]:
    """``x-learn-floor`` as a level (1…99), else None."""
    try:
        level = int(str(value or "").strip())
    except ValueError:
        return None
    return level if 1 <= level <= 99 else None


def note_floor(user_id: Optional[str], floor) -> None:
    """The student's school level, as the site sent it with this turn (None / not a level: none)."""
    if not user_id:
        return
    with _lock:
        if isinstance(floor, int) and not isinstance(floor, bool) and floor >= 1:
            _floors[user_id] = floor
        else:
            _floors.pop(user_id, None)


def course_states(programme: dict, progress: dict, floor: Optional[int] = None) -> dict:
    """course_id → {"locked", "complete", "position", "left": [lessons not completed, in order]}."""
    states: dict = {}
    courses = [c for c in programme.get("courses") or [] if isinstance(c, dict) and c.get("id")]
    previous_complete = True
    for i, course in enumerate(courses):
        lessons = [l for m in course.get("modules") or [] for l in m.get("lessons") or [] if l.get("id")]
        left = [l for l in lessons if (progress.get(l["id"]) or {}).get("status") != "completed"]
        complete = bool(lessons) and not left
        unlocked = i == 0 or previous_complete or complete or (floor is not None and i + 1 <= floor)
        states[course["id"]] = {"locked": not unlocked, "complete": complete, "position": i + 1, "left": left,
                                "course": course}
        previous_complete = complete
    return states


def _states(user_id: str) -> Optional[dict]:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(user_id)
        floor = _floors.get(user_id)
        if hit and now - hit[0] < CACHE_S and hit[1].get("_floor") == floor:
            return hit[1]
    try:
        from src.tools.learning_path import fetch_programme, fetch_progress

        programme = fetch_programme()
        progress = fetch_progress(user_id)
    except Exception:  # noqa: BLE001 — nothing is hidden when the programme cannot be read
        logger.debug("learn access: programme or progress not read", exc_info=True)
        return None
    if not programme or progress is None:
        return None
    states = course_states(programme, progress, floor)
    states["_floor"] = floor
    with _lock:
        _cache[user_id] = (now, states)
    return states


def states_for(user_id: Optional[str], programme: dict, progress: dict) -> dict:
    """The locks over a programme and progress the caller already read (get_learning_path), with the student's floor."""
    with _lock:
        floor = _floors.get(user_id or "")
    return course_states(programme, progress, floor)


def forget(user_id: Optional[str]) -> None:
    """Drop the kept states (a lesson completed this turn)."""
    with _lock:
        _cache.pop(user_id or "", None)


def lesson_course_id(programme_states: dict, lesson_id) -> Optional[str]:
    for cid, st in programme_states.items():
        if cid == "_floor":
            continue
        for m in st["course"].get("modules") or []:
            if any(str(l.get("id")) == str(lesson_id) for l in m.get("lessons") or []):
                return cid
    return None


def locked_course(user_id: Optional[str], lesson_id=None, course_id=None) -> Optional[dict]:
    """The state of the locked course the lesson (or course) belongs to, or None when it is open / not known."""
    if not user_id or (lesson_id is None and course_id is None):
        return None
    states = _states(user_id)
    if not states:
        return None
    cid = course_id if course_id is not None else lesson_course_id(states, lesson_id)
    st = states.get(cid) if cid is not None else None
    return st if st and st["locked"] else None


def unlock_path(user_id: str, course_state: dict, locale: Optional[str] = "ru", max_lessons: int = 3,
                states: Optional[dict] = None) -> list:
    """What to pass to open *course_state*'s course: every course before it not complete yet, in order —
    [{"course", "url", "lessons_left", "next": [{"title", "url"}]}]; the first is where to start (its first lessons)."""
    states = states if states is not None else (_states(user_id) or {})
    from src.tools.learning_path import _course_url, _lesson_url, _loc

    # A course opens when the one before it is complete: walk back from the target through the courses not complete
    # yet, down to the first that is open — that is where to start (a school level may open it; the site's rule).
    by_position = {st["position"]: st for cid, st in states.items() if cid != "_floor"}
    chain = []
    k = course_state["position"] - 1
    while k >= 1 and k in by_position and not by_position[k]["complete"]:
        chain.insert(0, by_position[k])
        if not by_position[k]["locked"]:
            break
        k -= 1
    out = []
    for st in chain:
        course = st["course"]
        item = {"course": _loc(course, "title", locale), "url": _course_url(course), "lessons_left": len(st["left"])}
        if not out:
            item["next"] = [{"title": _loc(l, "title", locale), "url": _lesson_url(course, l)}
                            for l in st["left"][:max_lessons]]
        out.append(item)
    return out


LOCKED_NOTE = (
    "This lesson is LOCKED for the student: its course is closed in their /learn programme until the courses before it "
    "are passed. Do not open, show, teach or link it, and do not offer it. Tell them, warmly and in one or two sentences, "
    "which course to finish to get there (unlock_path — the first one is where to start) and offer its next lesson "
    "(unlock_path[0].next[0], as a link)."
)


LOCKED_COURSE_NOTE = (
    "This course is LOCKED for the student: closed in their /learn programme until the courses before it are passed. "
    "You may say what it teaches (the titles above), but do not open, teach or link its lessons. Tell them which "
    "course to finish to get there (unlock_path — the first one is where to start) and offer its next lesson."
)
LOCKED_COURSES_NOTE = (
    "Courses with locked: true are closed in the student's /learn programme: each opens once the course before it is "
    "passed. Asked about their courses, list them all — the open ones with their links, the locked ones by name, "
    "saying they open after the course before them. Never offer, open or link a locked course's lessons."
)


def gate_lesson(result: dict, user_id: Optional[str], locale: Optional[str] = "ru") -> dict:
    """get_lesson's result for the student: a lesson of a locked course becomes the way to it — nothing of the lesson
    goes to the model, its board actions neither."""
    if not isinstance(result, dict) or not result.get("lesson_id"):
        return result
    st = locked_course(user_id, lesson_id=result["lesson_id"])
    if not st:
        return result
    course = result.get("course") if isinstance(result.get("course"), dict) else {}
    return {"locked": True, "title": result.get("title"), "course": course.get("title"),
            "unlock_path": unlock_path(user_id, st, locale), "note": LOCKED_NOTE}


def gate_topic(result: dict, user_id: Optional[str], locale: Optional[str] = "ru") -> dict:
    """get_topic's result for the student: the site lessons of locked courses are not offered — dropped from
    ``site_lessons``; an example taken from one keeps its position but loses the lesson's link and name."""
    if not isinstance(result, dict) or not user_id:
        return result
    lessons = result.get("site_lessons")
    hidden = []
    if isinstance(lessons, list):
        kept = []
        for lesson in lessons:
            st = locked_course(user_id, lesson_id=lesson.get("lesson_id")) if isinstance(lesson, dict) else None
            (hidden if st else kept).append((lesson, st))
        result["site_lessons"] = [l for l, _ in kept]
    example = result.get("example")
    if isinstance(example, dict) and example.get("source") == "site_lesson" and example.get("lesson_id"):
        st = locked_course(user_id, lesson_id=example["lesson_id"])
        if st:
            hidden.append((example, st))
            for key in ("url", "title", "course", "lesson_id"):
                example.pop(key, None)
            example["source"] = "site_lesson_locked"
    if hidden:
        first_state = hidden[0][1]
        result["locked_lessons"] = [{"title": l.get("title"), "course": l.get("course")} for l, _ in hidden
                                    if isinstance(l, dict) and l.get("title")]
        result["unlock_path"] = unlock_path(user_id, first_state, locale)
        result["locked_note"] = (
            "The lessons in locked_lessons are LOCKED for the student (their /learn courses are closed): never offer, "
            "open or link them. If the student wants that topic's lesson, say which course to finish first "
            "(unlock_path — start with its first entry and its next lesson)."
        )
    return result
