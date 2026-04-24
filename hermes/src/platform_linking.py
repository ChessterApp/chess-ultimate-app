"""Platform linking — connect and sync external chess platform accounts."""

import json
import logging
import os

import httpx

from src.tools.player_profiles import get_player_profile
from tools.registry import registry

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
TIMEOUT = 10


def _supabase_headers(key: str = None) -> dict:
    api_key = key or SUPABASE_KEY
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _get_chess_profile(user_id: str, url: str = None, key: str = None) -> dict | None:
    """Fetch user_chess_profiles row for user_id. Returns None if not found."""
    base = url or SUPABASE_URL
    api_key = key or SUPABASE_KEY
    if not base or not api_key:
        return None

    resp = httpx.get(
        f"{base}/rest/v1/user_chess_profiles",
        params={"user_id": f"eq.{user_id}", "select": "*"},
        headers=_supabase_headers(api_key),
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def _upsert_chess_profile(user_id: str, data: dict, url: str = None, key: str = None) -> None:
    """Upsert a row in user_chess_profiles."""
    base = url or SUPABASE_URL
    api_key = key or SUPABASE_KEY
    if not base or not api_key:
        return

    headers = _supabase_headers(api_key)
    headers["Prefer"] = "resolution=merge-duplicates"

    row = {"user_id": user_id, **data}
    httpx.post(
        f"{base}/rest/v1/user_chess_profiles",
        json=row,
        headers=headers,
        timeout=TIMEOUT,
    )


def link_platform(
    user_id: str,
    platform: str,
    username: str,
    supabase_url: str = None,
    supabase_key: str = None,
    client: httpx.Client = None,
) -> dict:
    """Verify a platform account exists, then store the link in user_chess_profiles.

    Args:
        user_id: Internal user ID.
        platform: 'lichess' or 'chesscom'.
        username: Platform username to link.

    Returns:
        dict with status or error.
    """
    if platform not in ("lichess", "chesscom"):
        return {"error": f"Unknown platform: {platform}. Use 'lichess' or 'chesscom'."}

    # Verify the account exists
    profile = get_player_profile(username, platform, client=client)
    if "error" in profile:
        return {"error": f"Cannot verify account: {profile['error']}"}

    # Store the link
    column = f"{platform}_username"
    try:
        _upsert_chess_profile(
            user_id, {column: username}, url=supabase_url, key=supabase_key
        )
    except Exception:
        logger.exception("Failed to store platform link")
        return {"error": "Failed to save platform link to database."}

    return {
        "status": "linked",
        "platform": platform,
        "username": profile.get("username", username),
        "ratings": profile.get("ratings", {}),
    }


def sync_ratings(
    user_id: str,
    supabase_url: str = None,
    supabase_key: str = None,
    client: httpx.Client = None,
) -> dict:
    """Read linked platforms and fetch current ratings, updating the profile.

    Returns:
        dict with updated ratings per platform.
    """
    try:
        chess_profile = _get_chess_profile(user_id, url=supabase_url, key=supabase_key)
    except Exception:
        logger.exception("Failed to read chess profile for sync")
        return {"error": "Failed to read profile from database."}

    if not chess_profile:
        return {"error": "No linked platforms found. Link a platform first."}

    updates = {}
    ratings_result = {}

    lichess_user = chess_profile.get("lichess_username")
    if lichess_user:
        profile = get_player_profile(lichess_user, "lichess", client=client)
        if "error" not in profile:
            rapid = profile.get("ratings", {}).get("rapid", 0)
            updates["lichess_rapid_rating"] = rapid
            ratings_result["lichess"] = {
                "username": lichess_user,
                "rapid": rapid,
                "ratings": profile.get("ratings", {}),
            }

    chesscom_user = chess_profile.get("chesscom_username")
    if chesscom_user:
        profile = get_player_profile(chesscom_user, "chesscom", client=client)
        if "error" not in profile:
            rapid = profile.get("ratings", {}).get("rapid", 0)
            updates["chesscom_rapid_rating"] = rapid
            ratings_result["chesscom"] = {
                "username": chesscom_user,
                "rapid": rapid,
                "ratings": profile.get("ratings", {}),
            }

    if updates:
        try:
            _upsert_chess_profile(user_id, updates, url=supabase_url, key=supabase_key)
        except Exception:
            logger.exception("Failed to update ratings in Supabase")
            return {"error": "Failed to save ratings to database.", "ratings": ratings_result}

    return {"synced": True, "ratings": ratings_result}


# --- Tool registration ---

LINK_PLATFORM_SCHEMA = {
    "type": "function",
    "function": {
        "name": "link_platform",
        "description": "Link a Lichess or Chess.com account to the user's coaching profile.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID."},
                "platform": {
                    "type": "string",
                    "enum": ["lichess", "chesscom"],
                    "description": "Platform: 'lichess' or 'chesscom'.",
                },
                "username": {"type": "string", "description": "Platform username to link."},
            },
            "required": ["user_id", "platform", "username"],
        },
    },
}

SYNC_RATINGS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "sync_ratings",
        "description": "Sync ratings from linked platforms (Lichess, Chess.com) into the coaching profile.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID."},
            },
            "required": ["user_id"],
        },
    },
}


def _handle_link_platform(args: dict) -> str:
    result = link_platform(
        user_id=args.get("user_id", ""),
        platform=args.get("platform", ""),
        username=args.get("username", ""),
    )
    return json.dumps(result, indent=2)


def _handle_sync_ratings(args: dict) -> str:
    result = sync_ratings(user_id=args.get("user_id", ""))
    return json.dumps(result, indent=2)


registry.register(
    name="link_platform",
    toolset="chess",
    schema=LINK_PLATFORM_SCHEMA,
    handler=_handle_link_platform,
    description="Link a Lichess or Chess.com account.",
    emoji="🔗",
)

registry.register(
    name="sync_ratings",
    toolset="chess",
    schema=SYNC_RATINGS_SCHEMA,
    handler=_handle_sync_ratings,
    description="Sync ratings from linked platforms.",
    emoji="📊",
)
