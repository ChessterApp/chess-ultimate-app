"""Tool: get_game_insights — retrieval over a student's own reviewed games.

Reads the ``coach_game_insights`` table (populated by the backend Game Review
pipeline / backfill CLI) so the coach can reason over a student's recent games:
opening, result, accuracy, and the worst blunders/mistakes per game. Read-only.
"""

import json
import logging

from tools.registry import registry
from src.tools.user_data import _supabase_get

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 5
MAX_LIMIT = 20

# Columns returned to the coach — compact on purpose (no per-move dump).
_SELECT = "game_ref,source,color,opening,result,accuracy,blunders,summary,played_at,created_at"


GAME_INSIGHTS_SCHEMA = {
    "name": "get_game_insights",
    "description": (
        "Get distilled insights from a student's own recently reviewed games "
        "(opening, result, accuracy, worst blunders). Use to ground coaching in "
        "the student's actual games."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "The student's ID."},
            "opening": {
                "type": "string",
                "description": "Optional opening-name filter (case-insensitive substring match).",
            },
            "limit": {
                "type": "integer",
                "description": f"Max games to return (default {DEFAULT_LIMIT}, max {MAX_LIMIT}).",
            },
        },
        "required": ["user_id"],
    },
}


def get_game_insights(
    user_id: str,
    opening: str = None,
    limit: int = DEFAULT_LIMIT,
    supabase_url: str = None,
    supabase_key: str = None,
) -> list[dict]:
    """Fetch a student's most recent game insights, newest first."""
    limit = min(max(1, int(limit or DEFAULT_LIMIT)), MAX_LIMIT)
    params = {
        "user_id": f"eq.{user_id}",
        "select": _SELECT,
        "order": "created_at.desc",
        "limit": str(limit),
    }
    if opening:
        params["opening"] = f"ilike.*{opening}*"

    return _supabase_get(
        "coach_game_insights",
        params,
        url=supabase_url,
        key=supabase_key,
    )


def _handle_get_game_insights(args: dict, **kwargs) -> str:
    result = get_game_insights(
        user_id=args.get("user_id", ""),
        opening=args.get("opening"),
        limit=args.get("limit", DEFAULT_LIMIT),
    )
    return json.dumps(result, indent=2)


registry.register(
    name="get_game_insights",
    toolset="chess",
    schema=GAME_INSIGHTS_SCHEMA,
    handler=_handle_get_game_insights,
    description="Get insights from a student's own reviewed games.",
    emoji="🔎",
)


# ── Prompt digest (CL Phase 1, Slice 2) ─────────────────────────────────
# Mirrors memory_writer.load_active_corrections / render_corrections_block: a
# fail-open loader + a hard-capped renderer, injected in prompt_builder behind
# COACH_GAME_RAG (default OFF). Context injection only — never writes anywhere.

GAMES_BLOCK_CAP = 700  # total chars of the injected prompt block
DIGEST_LIMIT = 3       # most-recent games to summarize


def load_recent_insights(user_id: str, limit: int = DIGEST_LIMIT) -> list[dict]:
    """Load a student's most recent game insights for the prompt digest.
    Fail-open → [] (get_game_insights already swallows Supabase errors)."""
    try:
        return get_game_insights(user_id, limit=limit)
    except Exception:
        logger.debug("load_recent_insights failed for %s", user_id, exc_info=True)
        return []


def _worst_blunder_theme(row: dict) -> str:
    """Extract the worst blunder's theme/classification from an insight row."""
    blunders = (row or {}).get("blunders")
    if isinstance(blunders, str):
        try:
            blunders = json.loads(blunders)
        except (json.JSONDecodeError, ValueError):
            blunders = None
    if not isinstance(blunders, list) or not blunders:
        return ""
    worst = blunders[0]
    if not isinstance(worst, dict):
        return ""
    theme = str(worst.get("theme") or "").strip()
    cls = str(worst.get("classification") or "").strip()
    if theme and cls:
        return f"{cls} in {theme}"
    return theme or cls


def render_games_block(insights: list[dict], cap: int = GAMES_BLOCK_CAP) -> str:
    """Render the 'Recent games' prompt block, hard-capped. Returns an empty
    string when there is nothing to render. Malformed rows are skipped."""
    lines: list[str] = []
    for row in insights or []:
        if not isinstance(row, dict):
            continue
        opening = str(row.get("opening") or "Unknown opening").strip()
        result = str(row.get("result") or "").strip()
        parts = [opening]
        if result:
            parts.append(f"result {result}")
        theme = _worst_blunder_theme(row)
        if theme:
            parts.append(f"worst: {theme}")
        line = "- " + "; ".join(parts)
        if line.strip("- "):
            lines.append(line)
    if not lines:
        return ""
    block = "## Recent games (the student's own, most recent first)\n" + "\n".join(lines)
    return block[:cap]
