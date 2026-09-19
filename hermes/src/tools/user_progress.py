"""Tool: get_user_progress — Fetch user lesson completions and puzzle stats.

Reads the tables the site actually writes (see backend/schema.sql and
backend/migrations/005_add_lesson_puzzles.sql):

- ``user_progress``: one row per (user, lesson) with ``status`` in
  not_started / in_progress / completed, ``score``, ``attempts``,
  ``completed_at``; ``lesson_id`` → ``lessons`` (title, title_ru, module_id).
- ``user_puzzle_progress``: one row per (user, lesson puzzle) with
  ``completed_at`` (NULL until solved) and ``attempts``.
"""

import json
import logging
from datetime import date

from tools.registry import registry

from src.tools.user_data import _supabase_query

logger = logging.getLogger(__name__)

PROGRESS_SCHEMA = {
    "name": "get_user_progress",
    "description": (
        "Fetch the student's learning progress: lessons completed / in progress "
        "(with titles and scores), lesson puzzles solved, solve rate, and the "
        "current daily puzzle streak."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "The user's ID.",
            },
        },
        "required": ["user_id"],
    },
}

RECENT_LESSONS = 10


def _streak(days: list) -> int:
    """Consecutive days (ending today or yesterday) with at least one solve."""
    if not days:
        return 0
    uniq = sorted({d for d in days}, reverse=True)
    prev = date.fromisoformat(uniq[0])
    if (date.today() - prev).days > 1:
        return 0
    streak = 1
    for d_str in uniq[1:]:
        d = date.fromisoformat(d_str)
        if (prev - d).days == 1:
            streak += 1
            prev = d
        else:
            break
    return streak


def get_user_progress(
    user_id: str,
    supabase_url: str = None,
    supabase_key: str = None,
) -> dict:
    """Fetch lesson and puzzle progress for *user_id* from Supabase."""
    lessons = _supabase_query(
        "user_progress",
        {
            "user_id": f"eq.{user_id}",
            "select": (
                "lesson_id,status,score,attempts,time_spent_seconds,completed_at,"
                "updated_at,lessons(title,title_ru,lesson_type,module_id)"
            ),
            "order": "updated_at.desc",
        },
        url=supabase_url,
        key=supabase_key,
    )
    if lessons is None:
        return {"error": "Could not fetch the student's progress (Supabase unavailable)."}

    puzzles = _supabase_query(
        "user_puzzle_progress",
        {
            "user_id": f"eq.{user_id}",
            "select": "puzzle_id,completed_at,attempts",
        },
        url=supabase_url,
        key=supabase_key,
    )
    if puzzles is None:
        return {"error": "Could not fetch the student's puzzle stats (Supabase unavailable)."}

    completed = [lp for lp in lessons if lp.get("status") == "completed"]
    in_progress = [lp for lp in lessons if lp.get("status") == "in_progress"]

    def _lesson_summary(lp: dict) -> dict:
        info = lp.get("lessons") or {}
        return {
            "lesson_id": lp.get("lesson_id"),
            "title": info.get("title_ru") or info.get("title"),
            "type": info.get("lesson_type"),
            "status": lp.get("status"),
            "score": lp.get("score"),
            "attempts": lp.get("attempts"),
            "completed_at": lp.get("completed_at"),
        }

    solved = [p for p in puzzles if p.get("completed_at")]
    solved_days = [p["completed_at"][:10] for p in solved]
    total_attempts = sum(int(p.get("attempts") or 0) for p in puzzles)
    solve_rate_pct = round(len(solved) / total_attempts * 100, 1) if total_attempts else 0.0

    scores = [lp["score"] for lp in completed if isinstance(lp.get("score"), (int, float))]

    return {
        "user_id": user_id,
        "lessons_started": len(lessons),
        "lessons_completed": len(completed),
        "lessons_in_progress": len(in_progress),
        "avg_lesson_score": round(sum(scores) / len(scores), 1) if scores else None,
        "recent_lessons": [_lesson_summary(lp) for lp in lessons[:RECENT_LESSONS]],
        "puzzles_attempted": len(puzzles),
        "puzzles_solved": len(solved),
        "puzzle_attempts_total": total_attempts,
        "solve_rate_pct": solve_rate_pct,
        "current_streak": _streak(solved_days),
        "last_puzzle_solved_at": max((p["completed_at"] for p in solved), default=None),
    }


def _handle_get_user_progress(args: dict, **kwargs) -> str:
    result = get_user_progress(user_id=args.get("user_id", ""))
    return json.dumps(result, indent=2, ensure_ascii=False)


registry.register(
    name="get_user_progress",
    toolset="chess",
    schema=PROGRESS_SCHEMA,
    handler=_handle_get_user_progress,
    description="Fetch user learning progress and puzzle stats.",
    emoji="📈",
)
