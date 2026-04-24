"""Tool: get_user_progress — Fetch user course completions and puzzle stats."""

import json
import logging
import os

import httpx

from tools.registry import registry

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
TIMEOUT = 10

PROGRESS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_user_progress",
        "description": (
            "Fetch a user's learning progress: course completions, lesson progress, "
            "puzzle stats, accuracy, and current streak."
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
    },
}


def _supabase_get(table: str, params: dict, url: str = None, key: str = None) -> list[dict]:
    """Make a GET request to Supabase PostgREST API."""
    base = url or SUPABASE_URL
    api_key = key or SUPABASE_KEY

    if not base or not api_key:
        logger.warning("Supabase not configured")
        return []

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
    }

    try:
        resp = httpx.get(
            f"{base}/rest/v1/{table}",
            params=params,
            headers=headers,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception("Supabase query failed for table: %s", table)
        return []


def get_user_progress(
    user_id: str,
    supabase_url: str = None,
    supabase_key: str = None,
) -> dict:
    """Fetch user course completions and puzzle stats from Supabase."""
    url = supabase_url if supabase_url is not None else SUPABASE_URL
    key = supabase_key if supabase_key is not None else SUPABASE_KEY

    if not url or not key:
        return {"error": "Supabase not configured."}

    # Fetch lesson progress
    lessons = _supabase_get(
        "lesson_progress",
        {"user_id": f"eq.{user_id}", "select": "*"},
        url=url, key=key,
    )

    # Fetch puzzle attempts
    puzzles = _supabase_get(
        "puzzle_attempts",
        {"user_id": f"eq.{user_id}", "select": "*"},
        url=url, key=key,
    )

    # Compute stats
    courses_completed = len({
        lp["course_id"] for lp in lessons
        if lp.get("completed") and lp.get("course_id")
    })
    lessons_completed = sum(1 for lp in lessons if lp.get("completed"))

    puzzles_attempted = len(puzzles)
    puzzles_solved = sum(1 for p in puzzles if p.get("solved"))
    accuracy_pct = round(
        (puzzles_solved / puzzles_attempted * 100) if puzzles_attempted else 0, 1
    )

    # Calculate streak (consecutive days with solved puzzles)
    solved_dates = sorted({
        p["solved_at"][:10] for p in puzzles
        if p.get("solved") and p.get("solved_at")
    }, reverse=True)

    current_streak = 0
    if solved_dates:
        from datetime import date, timedelta
        prev = date.fromisoformat(solved_dates[0])
        today = date.today()
        if (today - prev).days <= 1:
            current_streak = 1
            for d_str in solved_dates[1:]:
                d = date.fromisoformat(d_str)
                if (prev - d).days == 1:
                    current_streak += 1
                    prev = d
                elif (prev - d).days == 0:
                    continue
                else:
                    break

    return {
        "user_id": user_id,
        "courses_completed": courses_completed,
        "lessons_completed": lessons_completed,
        "puzzles_attempted": puzzles_attempted,
        "puzzles_solved": puzzles_solved,
        "accuracy_pct": accuracy_pct,
        "current_streak": current_streak,
    }


def _handle_get_user_progress(args: dict, **kwargs) -> str:
    result = get_user_progress(user_id=args.get("user_id", ""))
    return json.dumps(result, indent=2)


registry.register(
    name="get_user_progress",
    toolset="chess",
    schema=PROGRESS_SCHEMA,
    handler=_handle_get_user_progress,
    description="Fetch user learning progress and puzzle stats.",
    emoji="📈",
)
