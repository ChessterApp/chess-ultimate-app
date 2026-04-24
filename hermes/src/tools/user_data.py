"""Tools 6 & 7: get_user_repertoire and get_user_games — Supabase user data."""

import json
import logging
import os

import httpx

from tools.registry import registry

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
TIMEOUT = 10


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


# --- Tool 6: get_user_repertoire ---

REPERTOIRE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_user_repertoire",
        "description": "Get a user's opening repertoire from their profile.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID."},
                "color": {"type": "string", "description": "Filter by color: 'white' or 'black'. If omitted, returns both."},
            },
            "required": ["user_id"],
        },
    },
}


def get_user_repertoire(
    user_id: str,
    color: str = None,
    supabase_url: str = None,
    supabase_key: str = None,
) -> list[dict]:
    """Fetch user's opening repertoire from Supabase."""
    params = {"user_id": f"eq.{user_id}", "select": "*"}
    if color:
        params["color"] = f"eq.{color.lower()}"

    return _supabase_get(
        "repertoire",
        params,
        url=supabase_url,
        key=supabase_key,
    )


def _handle_get_user_repertoire(args: dict, **kwargs) -> str:
    result = get_user_repertoire(
        user_id=args.get("user_id", ""),
        color=args.get("color"),
    )
    return json.dumps(result, indent=2)


registry.register(
    name="get_user_repertoire",
    toolset="chess",
    schema=REPERTOIRE_SCHEMA,
    handler=_handle_get_user_repertoire,
    description="Get a user's opening repertoire.",
    emoji="📚",
)


# --- Tool 7: get_user_games ---

USER_GAMES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_user_games",
        "description": "Get a user's recent games from their profile.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID."},
                "limit": {"type": "integer", "description": "Max games to return (default 20)."},
            },
            "required": ["user_id"],
        },
    },
}


def get_user_games(
    user_id: str,
    limit: int = 20,
    supabase_url: str = None,
    supabase_key: str = None,
) -> list[dict]:
    """Fetch user's games from Supabase."""
    limit = min(max(1, limit), 100)
    params = {
        "user_id": f"eq.{user_id}",
        "select": "*",
        "order": "played_at.desc",
        "limit": str(limit),
    }

    return _supabase_get(
        "user_games",
        params,
        url=supabase_url,
        key=supabase_key,
    )


def _handle_get_user_games(args: dict, **kwargs) -> str:
    result = get_user_games(
        user_id=args.get("user_id", ""),
        limit=args.get("limit", 20),
    )
    return json.dumps(result, indent=2)


registry.register(
    name="get_user_games",
    toolset="chess",
    schema=USER_GAMES_SCHEMA,
    handler=_handle_get_user_games,
    description="Get a user's recent games.",
    emoji="🎮",
)
