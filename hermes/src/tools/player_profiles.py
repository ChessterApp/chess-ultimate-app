"""Tool 8: get_player_profile — Lichess and Chess.com public API lookup."""

import json
import logging

import httpx

from tools.registry import registry

logger = logging.getLogger(__name__)

TIMEOUT = 10

PROFILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_player_profile",
        "description": "Get a player's profile from Lichess or Chess.com, including ratings and game counts.",
        "parameters": {
            "type": "object",
            "properties": {
                "username": {"type": "string", "description": "The player's username."},
                "platform": {
                    "type": "string",
                    "enum": ["lichess", "chesscom"],
                    "description": "Platform: 'lichess' or 'chesscom'.",
                },
            },
            "required": ["username", "platform"],
        },
    },
}


def _fetch_lichess_profile(username: str, client: httpx.Client = None) -> dict:
    """Fetch profile from Lichess public API."""
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=TIMEOUT)

    try:
        resp = client.get(
            f"https://lichess.org/api/user/{username}",
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"User '{username}' not found on Lichess."}
        return {"error": f"Lichess API error: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Lichess API error: {e}"}
    finally:
        if own_client:
            client.close()

    # Extract ratings
    perfs = data.get("perfs", {})
    ratings = {}
    for mode in ("bullet", "blitz", "rapid", "classical", "puzzle"):
        if mode in perfs:
            ratings[mode] = perfs[mode].get("rating", 0)

    games_played = data.get("count", {}).get("all", 0)
    created = data.get("createdAt")
    member_since = ""
    if created:
        from datetime import datetime, timezone
        member_since = datetime.fromtimestamp(created / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

    return {
        "username": data.get("username", username),
        "platform": "lichess",
        "ratings": ratings,
        "games_played": games_played,
        "member_since": member_since,
    }


def _fetch_chesscom_profile(username: str, client: httpx.Client = None) -> dict:
    """Fetch profile from Chess.com public API."""
    username = username.lower()
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=TIMEOUT, follow_redirects=True)

    try:
        resp = client.get(
            f"https://api.chess.com/pub/player/{username}",
            headers={"User-Agent": "HermesChessCoach/1.0"},
        )
        resp.raise_for_status()
        profile = resp.json()

        # Fetch stats (same client, before closing)
        ratings = {}
        try:
            stats_resp = client.get(
                f"https://api.chess.com/pub/player/{username}/stats",
                headers={"User-Agent": "HermesChessCoach/1.0"},
            )
            stats_resp.raise_for_status()
            stats = stats_resp.json()

            for mode in ("chess_bullet", "chess_blitz", "chess_rapid"):
                if mode in stats:
                    short = mode.replace("chess_", "")
                    last = stats[mode].get("last", {})
                    ratings[short] = last.get("rating", 0)
        except Exception:
            logger.debug("Could not fetch Chess.com stats for %s", username)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"User '{username}' not found on Chess.com."}
        return {"error": f"Chess.com API error: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Chess.com API error: {e}"}
    finally:
        if own_client:
            client.close()

    joined = profile.get("joined")
    member_since = ""
    if joined:
        from datetime import datetime, timezone
        member_since = datetime.fromtimestamp(joined, tz=timezone.utc).strftime("%Y-%m-%d")

    return {
        "username": profile.get("username", username),
        "platform": "chesscom",
        "ratings": ratings,
        "games_played": profile.get("total_games", 0),
        "member_since": member_since,
    }


def get_player_profile(username: str, platform: str, client: httpx.Client = None) -> dict:
    """Get player profile from the specified platform."""
    if platform == "lichess":
        return _fetch_lichess_profile(username, client=client)
    elif platform == "chesscom":
        return _fetch_chesscom_profile(username, client=client)
    else:
        return {"error": f"Unknown platform: {platform}. Use 'lichess' or 'chesscom'."}


def _handle_get_player_profile(args: dict, **kwargs) -> str:
    result = get_player_profile(
        username=args.get("username", ""),
        platform=args.get("platform", "lichess"),
    )
    return json.dumps(result, indent=2)


registry.register(
    name="get_player_profile",
    toolset="chess",
    schema=PROFILE_SCHEMA,
    handler=_handle_get_player_profile,
    description="Get player profile from Lichess or Chess.com.",
    emoji="👤",
)
