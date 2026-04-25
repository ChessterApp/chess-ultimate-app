"""Tools: lichess_game_import and chesscom_game_import — import games from external platforms."""

import json
import logging
import os
from datetime import datetime, timezone

import httpx

from tools.registry import registry

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
TIMEOUT = 30


def _supabase_post(table: str, rows: list[dict], url: str = None, key: str = None) -> int:
    """POST rows to a Supabase PostgREST table. Returns count of inserted rows."""
    base = url or SUPABASE_URL
    api_key = key or SUPABASE_KEY

    if not base or not api_key:
        logger.warning("Supabase not configured")
        return 0

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    resp = httpx.post(
        f"{base}/rest/v1/{table}",
        json=rows,
        headers=headers,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return len(rows)


def _parse_pgn_stream(pgn_text: str) -> list[dict]:
    """Parse a PGN stream (multiple games) into a list of game dicts.

    Each game dict has: pgn, white, black, result, date, event, platform_game_id.
    """
    games = []
    current_headers = {}
    current_moves = []
    in_moves = False

    for line in pgn_text.strip().split("\n"):
        line = line.strip()
        if not line:
            if in_moves and current_moves:
                pgn_str = "\n".join(
                    f'[{k} "{v}"]' for k, v in current_headers.items()
                ) + "\n\n" + " ".join(current_moves)
                games.append({
                    "pgn": pgn_str,
                    "white": current_headers.get("White", "?"),
                    "black": current_headers.get("Black", "?"),
                    "result": current_headers.get("Result", "*"),
                    "date": current_headers.get("UTCDate", current_headers.get("Date", "")),
                    "event": current_headers.get("Event", ""),
                    "platform_game_id": current_headers.get("Site", "").split("/")[-1] if current_headers.get("Site") else "",
                })
                current_headers = {}
                current_moves = []
                in_moves = False
            continue

        if line.startswith("["):
            # Header tag
            in_moves = False
            tag = line.strip("[]")
            parts = tag.split(" ", 1)
            if len(parts) == 2:
                key = parts[0]
                val = parts[1].strip('"')
                current_headers[key] = val
        else:
            in_moves = True
            current_moves.append(line)

    # Handle last game if file doesn't end with blank line
    if current_moves:
        pgn_str = "\n".join(
            f'[{k} "{v}"]' for k, v in current_headers.items()
        ) + "\n\n" + " ".join(current_moves)
        games.append({
            "pgn": pgn_str,
            "white": current_headers.get("White", "?"),
            "black": current_headers.get("Black", "?"),
            "result": current_headers.get("Result", "*"),
            "date": current_headers.get("UTCDate", current_headers.get("Date", "")),
            "event": current_headers.get("Event", ""),
            "platform_game_id": current_headers.get("Site", "").split("/")[-1] if current_headers.get("Site") else "",
        })

    return games


# --- lichess_game_import ---

LICHESS_IMPORT_SCHEMA = {
    "name": "lichess_game_import",
    "description": "Import a user's recent games from Lichess into the coaching database.",
    "parameters": {
        "type": "object",
        "properties": {
            "username": {"type": "string", "description": "Lichess username."},
            "max_games": {"type": "integer", "description": "Max games to import (default 50)."},
            "time_control": {
                "type": "string",
                "description": "Filter by time control: bullet, blitz, rapid, classical. Optional.",
            },
        },
        "required": ["username"],
    },
}


def lichess_game_import(
    username: str,
    max_games: int = 50,
    time_control: str = None,
    user_id: str = None,
    supabase_url: str = None,
    supabase_key: str = None,
    client: httpx.Client = None,
) -> dict:
    """Fetch games from Lichess API and store in Supabase."""
    max_games = min(max(1, max_games), 200)

    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=TIMEOUT)

    try:
        params = {"max": max_games}
        if time_control:
            params["perfType"] = time_control

        resp = client.get(
            f"https://lichess.org/api/games/user/{username}",
            params=params,
            headers={"Accept": "application/x-chess-pgn"},
        )
        resp.raise_for_status()
        pgn_text = resp.text
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"User '{username}' not found on Lichess."}
        if e.response.status_code == 429:
            return {"error": "Lichess rate limit exceeded. Please try again later."}
        return {"error": f"Lichess API error: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Lichess API error: {e}"}
    finally:
        if own_client:
            client.close()

    if not pgn_text.strip():
        return {"imported": 0, "summary": f"No games found for {username}."}

    games = _parse_pgn_stream(pgn_text)

    if user_id:
        rows = [
            {
                "user_id": user_id,
                "pgn": g["pgn"],
                "white": g["white"],
                "black": g["black"],
                "result": g["result"],
                "date": g["date"],
                "event": g["event"],
                "source": "lichess",
                "platform_game_id": g["platform_game_id"],
            }
            for g in games
        ]
        try:
            _supabase_post("user_games", rows, url=supabase_url, key=supabase_key)
        except Exception:
            logger.exception("Failed to store Lichess games in Supabase")
            return {"error": "Failed to store games in database.", "parsed": len(games)}

    results_summary = {}
    for g in games:
        r = g["result"]
        results_summary[r] = results_summary.get(r, 0) + 1

    return {
        "imported": len(games),
        "source": "lichess",
        "username": username,
        "results": results_summary,
        "summary": f"Imported {len(games)} games from Lichess for {username}.",
    }


def _handle_lichess_game_import(args: dict, **kwargs) -> str:
    result = lichess_game_import(
        username=args.get("username", ""),
        max_games=args.get("max_games", 50),
        time_control=args.get("time_control"),
        user_id=args.get("user_id"),
    )
    return json.dumps(result, indent=2)


registry.register(
    name="lichess_game_import",
    toolset="chess",
    schema=LICHESS_IMPORT_SCHEMA,
    handler=_handle_lichess_game_import,
    description="Import games from Lichess.",
    emoji="🔄",
)


# --- chesscom_game_import ---

CHESSCOM_IMPORT_SCHEMA = {
    "name": "chesscom_game_import",
    "description": "Import a user's recent games from Chess.com into the coaching database.",
    "parameters": {
        "type": "object",
        "properties": {
            "username": {"type": "string", "description": "Chess.com username."},
            "max_games": {"type": "integer", "description": "Max games to import (default 50)."},
        },
        "required": ["username"],
    },
}


def chesscom_game_import(
    username: str,
    max_games: int = 50,
    user_id: str = None,
    supabase_url: str = None,
    supabase_key: str = None,
    client: httpx.Client = None,
) -> dict:
    """Fetch games from Chess.com API and store in Supabase."""
    max_games = min(max(1, max_games), 200)

    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=TIMEOUT)

    now = datetime.now(tz=timezone.utc)
    months = [
        (now.year, now.month),
    ]
    # Previous month
    if now.month == 1:
        months.append((now.year - 1, 12))
    else:
        months.append((now.year, now.month - 1))

    all_games = []
    try:
        for year, month in months:
            resp = client.get(
                f"https://api.chess.com/pub/player/{username}/games/{year}/{month:02d}",
                headers={"User-Agent": "HermesChessCoach/1.0"},
            )
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            data = resp.json()

            for game in data.get("games", []):
                pgn = game.get("pgn", "")
                if not pgn:
                    continue
                all_games.append({
                    "pgn": pgn,
                    "white": game.get("white", {}).get("username", "?"),
                    "black": game.get("black", {}).get("username", "?"),
                    "result": _chesscom_result(game),
                    "date": _chesscom_date(game),
                    "event": game.get("rules", "chess"),
                    "platform_game_id": game.get("url", "").split("/")[-1] if game.get("url") else "",
                })

            if len(all_games) >= max_games:
                break
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            return {"error": "Chess.com rate limit exceeded. Please try again later."}
        return {"error": f"Chess.com API error: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Chess.com API error: {e}"}
    finally:
        if own_client:
            client.close()

    all_games = all_games[:max_games]

    if not all_games:
        return {"imported": 0, "summary": f"No games found for {username}."}

    if user_id:
        rows = [
            {
                "user_id": user_id,
                "pgn": g["pgn"],
                "white": g["white"],
                "black": g["black"],
                "result": g["result"],
                "date": g["date"],
                "event": g["event"],
                "source": "chesscom",
                "platform_game_id": g["platform_game_id"],
            }
            for g in all_games
        ]
        try:
            _supabase_post("user_games", rows, url=supabase_url, key=supabase_key)
        except Exception:
            logger.exception("Failed to store Chess.com games in Supabase")
            return {"error": "Failed to store games in database.", "parsed": len(all_games)}

    results_summary = {}
    for g in all_games:
        r = g["result"]
        results_summary[r] = results_summary.get(r, 0) + 1

    return {
        "imported": len(all_games),
        "source": "chesscom",
        "username": username,
        "results": results_summary,
        "summary": f"Imported {len(all_games)} games from Chess.com for {username}.",
    }


def _chesscom_result(game: dict) -> str:
    """Extract result string from Chess.com game object."""
    white = game.get("white", {})
    black = game.get("black", {})
    if white.get("result") == "win":
        return "1-0"
    if black.get("result") == "win":
        return "0-1"
    return "1/2-1/2"


def _chesscom_date(game: dict) -> str:
    """Extract date from Chess.com game object."""
    end_time = game.get("end_time")
    if end_time:
        return datetime.fromtimestamp(end_time, tz=timezone.utc).strftime("%Y-%m-%d")
    return ""


def _handle_chesscom_game_import(args: dict, **kwargs) -> str:
    result = chesscom_game_import(
        username=args.get("username", ""),
        max_games=args.get("max_games", 50),
        user_id=args.get("user_id"),
    )
    return json.dumps(result, indent=2)


registry.register(
    name="chesscom_game_import",
    toolset="chess",
    schema=CHESSCOM_IMPORT_SCHEMA,
    handler=_handle_chesscom_game_import,
    description="Import games from Chess.com.",
    emoji="🔄",
)
