"""Tools 6 & 7: get_user_repertoire and get_user_games — Supabase user data.

Table shapes follow the backend migrations, not an idealised schema:

- ``opening_repertoires`` (backend/migrations/005_debut_openings.sql): one row per
  repertoire, ``color`` is ``'w'`` / ``'b'``; the actual lines live in
  ``opening_nodes`` (``repertoire_id`` FK, one row per move).
- ``user_games`` (backend/migrations/011_create_user_games.sql): soft-deleted via
  ``deleted_at``; there is no ``played_at`` column, ordering is by ``created_at``.
"""

import json
import logging
import os
from typing import Optional

import httpx

from tools.registry import registry

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
TIMEOUT = 10

# Full PGNs are what the coach analyses, but 20 of them swamp the context.
DEFAULT_GAMES_LIMIT = 10
MAX_GAMES_LIMIT = 50
MAX_REPERTOIRE_NODES = 300

_COLOR_TO_DB = {"white": "w", "black": "b", "w": "w", "b": "b"}
_DB_TO_COLOR = {"w": "white", "b": "black"}


def _supabase_query(
    table: str, params: dict, url: str = None, key: str = None
) -> Optional[list]:
    """GET rows from Supabase PostgREST. Returns ``None`` (not ``[]``) on failure
    so callers can tell "no rows" from "the query broke"."""
    base = url or SUPABASE_URL
    api_key = key or SUPABASE_KEY

    if not base or not api_key:
        logger.warning("Supabase not configured")
        return None

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
        return None


def _supabase_get(table: str, params: dict, url: str = None, key: str = None) -> list:
    """Fail-open variant (``[]`` on failure) kept for game_insights, the backfill
    script and other callers that only need rows."""
    return _supabase_query(table, params, url=url, key=key) or []


# --- Tool 6: get_user_repertoire ---

REPERTOIRE_SCHEMA = {
    "name": "get_user_repertoire",
    "description": (
        "Get the student's own opening repertoire (the openings and lines they "
        "have saved in the Debut trainer), with the move tree of each repertoire."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "The user's ID."},
            "color": {"type": "string", "description": "Filter by color: 'white' or 'black'. If omitted, returns both."},
        },
        "required": ["user_id"],
    },
}


def get_user_repertoire(
    user_id: str,
    color: str = None,
    supabase_url: str = None,
    supabase_key: str = None,
) -> dict:
    """Fetch the user's repertoires and their move lines from Supabase.

    Returns ``{"repertoires": [...]}`` where each repertoire carries its
    ``lines`` (opening_nodes ordered by move number), or ``{"error": ...}``.
    """
    params = {
        "user_id": f"eq.{user_id}",
        "select": "id,name,color,description,is_primary,starting_fen,starting_move_line,updated_at",
        "order": "is_primary.desc,updated_at.desc",
    }
    if color:
        db_color = _COLOR_TO_DB.get(color.lower())
        if db_color is None:
            return {"error": f"Unknown color {color!r}; use 'white' or 'black'."}
        params["color"] = f"eq.{db_color}"

    repertoires = _supabase_query(
        "opening_repertoires", params, url=supabase_url, key=supabase_key
    )
    if repertoires is None:
        return {"error": "Could not fetch the repertoire (Supabase unavailable)."}

    for rep in repertoires:
        rep["color"] = _DB_TO_COLOR.get(rep.get("color"), rep.get("color"))
        rep["lines"] = []

    if repertoires:
        ids = ",".join(str(r["id"]) for r in repertoires)
        nodes = _supabase_get(
            "opening_nodes",
            {
                "repertoire_id": f"in.({ids})",
                "select": "repertoire_id,move_number,is_white_move,move_san,opening_name,eco_code,notes,is_critical",
                "order": "repertoire_id.asc,move_number.asc,is_white_move.desc",
                "limit": str(MAX_REPERTOIRE_NODES),
            },
            url=supabase_url,
            key=supabase_key,
        )
        by_rep = {str(r["id"]): r for r in repertoires}
        for node in nodes or []:
            rep = by_rep.get(str(node.pop("repertoire_id", "")))
            if rep is not None and node.get("move_san"):
                rep["lines"].append(node)

    return {"user_id": user_id, "repertoires": repertoires}


def _handle_get_user_repertoire(args: dict, **kwargs) -> str:
    result = get_user_repertoire(
        user_id=args.get("user_id", ""),
        color=args.get("color"),
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


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
    "name": "get_user_games",
    "description": (
        "Get the student's saved games (My Games): the most recently added first, "
        "with PGN, players, result, ECO and opening name."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "The user's ID."},
            "limit": {"type": "integer", "description": f"Max games to return (default {DEFAULT_GAMES_LIMIT}, max {MAX_GAMES_LIMIT})."},
        },
        "required": ["user_id"],
    },
}


def _query_user_games(
    user_id: str,
    limit: int = DEFAULT_GAMES_LIMIT,
    supabase_url: str = None,
    supabase_key: str = None,
) -> Optional[list]:
    """Rows of the user's saved (not soft-deleted) games, or ``None`` on failure."""
    limit = min(max(1, int(limit or DEFAULT_GAMES_LIMIT)), MAX_GAMES_LIMIT)
    params = {
        "user_id": f"eq.{user_id}",
        "deleted_at": "is.null",
        "select": (
            "id,title,white,black,white_elo,black_elo,result,date,event,eco,"
            "opening_name,source,is_favorite,tags,created_at,pgn"
        ),
        "order": "created_at.desc",
        "limit": str(limit),
    }

    return _supabase_query("user_games", params, url=supabase_url, key=supabase_key)


def get_user_games(
    user_id: str,
    limit: int = DEFAULT_GAMES_LIMIT,
    supabase_url: str = None,
    supabase_key: str = None,
) -> list:
    """Fetch the user's saved games as a list (``[]`` on failure).

    Kept list-shaped because weakness_tracker consumes it directly; the tool
    handler below reports failures explicitly instead.
    """
    return _query_user_games(user_id, limit, supabase_url, supabase_key) or []


def _handle_get_user_games(args: dict, **kwargs) -> str:
    games = _query_user_games(
        user_id=args.get("user_id", ""),
        limit=args.get("limit", DEFAULT_GAMES_LIMIT),
    )
    if games is None:
        result = {"error": "Could not fetch the student's games (Supabase unavailable)."}
    else:
        result = {"user_id": args.get("user_id", ""), "count": len(games), "games": games}
    return json.dumps(result, indent=2, ensure_ascii=False)


registry.register(
    name="get_user_games",
    toolset="chess",
    schema=USER_GAMES_SCHEMA,
    handler=_handle_get_user_games,
    description="Get a user's recent games.",
    emoji="🎮",
)
