"""Tool: import_game_from_url — a game by its Lichess or Chess.com link.

The student pastes a link ("https://lichess.org/kAdOQKeh/black",
"https://www.chess.com/game/live/184239477800") and the coach loads the game
on the board. Lichess exports a PGN directly. Chess.com has no per-game PGN
endpoint: the game page's JSON callback carries the headers and the move list
in Chess.com's compact "TCN" encoding, which is decoded here and verified move
by move with python-chess; if that fails, the public monthly archive of the
white player is searched for the game's URL as a fallback.

``fetch_game_by_url`` is shared by the tool and the ``/api/coach/import-url``
endpoint (the web page calls the endpoint straight from a pasted link, without
a model round-trip).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional
from urllib.parse import urlparse

import chess
import chess.pgn
import httpx

from tools.registry import registry

logger = logging.getLogger(__name__)

TIMEOUT = 20.0
USER_AGENT = "ChessterCoach/1.0 (+https://chesster.io)"

_LICHESS_ID = re.compile(r"^/([A-Za-z0-9]{8})(?:[A-Za-z0-9]{4})?(?:/|$)")
_CHESSCOM_ID = re.compile(r"/game/(?:live|daily|computer)/(\d+)|/(?:analysis/)?game/(?:live|daily)/(\d+)|/live/game/(\d+)|/game/(\d+)")

# Chess.com TCN: two characters per move, each an index into this alphabet
# (0..63 = squares a1..h8 rank by rank; a destination > 63 encodes a promotion).
_TCN = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?{~}(^)[_]@#$,./&-*++="
_TCN_PROMO = "qnrbkp"


class GameUrlError(ValueError):
    """A link that is not a supported game URL, or a game that could not be fetched."""


def parse_game_url(url: str) -> tuple[str, str]:
    """('lichess' | 'chesscom', game id) for a supported link; raises GameUrlError."""
    raw = (url or "").strip()
    if not raw:
        raise GameUrlError("Empty link.")
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    if host in ("lichess.org", "www.lichess.org", "lichess.com"):
        # /kAdOQKeh, /kAdOQKeh/black, /kAdOQKehXXXX (12-char player-side id), /game/export/kAdOQKeh
        m = re.match(r"^/(?:game/export/|embed/game/|study/[^/]+/)?([A-Za-z0-9]{8})(?:[A-Za-z0-9]{4})?(?:/|$)", path)
        if m:
            return "lichess", m.group(1)
        raise GameUrlError("This Lichess link does not point to a game.")
    if host.endswith("chess.com"):
        m = _CHESSCOM_ID.search(path)
        if m:
            return "chesscom", next(g for g in m.groups() if g)
        raise GameUrlError("This Chess.com link does not point to a game.")
    raise GameUrlError("Only Lichess and Chess.com game links are supported.")


def looks_like_game_url(text: str) -> bool:
    try:
        parse_game_url(text)
        return True
    except GameUrlError:
        return False


# ── Lichess ────────────────────────────────────────────────────────────────


def _lichess_pgn(game_id: str, client: httpx.Client) -> str:
    resp = client.get(
        f"https://lichess.org/game/export/{game_id}",
        params={"clocks": "false", "evals": "false", "literate": "false"},
        headers={"Accept": "application/x-chess-pgn", "User-Agent": USER_AGENT},
    )
    if resp.status_code == 404:
        raise GameUrlError("Lichess does not know this game (private or wrong id).")
    if resp.status_code == 429:
        raise GameUrlError("Lichess rate limit — try again in a minute.")
    resp.raise_for_status()
    return resp.text.strip()


# ── Chess.com ──────────────────────────────────────────────────────────────


def decode_tcn(tcn: str) -> list[str]:
    """Chess.com move list → UCI moves (without legality check)."""
    moves: list[str] = []
    if len(tcn) % 2:
        raise GameUrlError("Odd-length Chess.com move list.")
    for i in range(0, len(tcn), 2):
        try:
            a = _TCN.index(tcn[i])
            b = _TCN.index(tcn[i + 1])
        except ValueError as exc:
            raise GameUrlError("Unknown character in Chess.com move list.") from exc
        promo = ""
        if b > 63:
            promo = _TCN_PROMO[(b - 64) // 3]
            b = a + (-8 if a < 16 else 8) + ((b - 64) % 3) - 1
        moves.append(_sq(a) + _sq(b) + promo)
    return moves


def _sq(index: int) -> str:
    return "abcdefgh"[index % 8] + str(index // 8 + 1)


def _pgn_from_moves(headers: dict, uci_moves: list[str]) -> str:
    """Build a PGN from headers + UCI moves, verifying every move is legal."""
    start_fen = headers.get("FEN") if headers.get("SetUp") in ("1", 1, True) else None
    board = chess.Board(start_fen) if start_fen else chess.Board()
    game = chess.pgn.Game()
    for tag in ("Event", "Site", "Date", "Round", "White", "Black", "Result", "ECO",
                "WhiteElo", "BlackElo", "TimeControl", "Termination", "Opening"):
        if headers.get(tag) not in (None, ""):
            game.headers[tag] = str(headers[tag])
    if start_fen and start_fen != chess.STARTING_FEN:
        game.headers["SetUp"] = "1"
        game.headers["FEN"] = start_fen
        game.setup(board)
    node = game
    for uci in uci_moves:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as exc:  # chess.InvalidMoveError is a ValueError
            raise GameUrlError(f"Decoded move {uci} is not a move — move list not understood.") from exc
        if move not in board.legal_moves:
            raise GameUrlError(f"Decoded move {uci} is illegal — move list not understood.")
        node = node.add_variation(move)
        board.push(move)
    game.headers["Result"] = str(headers.get("Result") or "*")
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    return game.accept(exporter)


def _chesscom_archive_pgn(headers: dict, game_id: str, client: httpx.Client) -> Optional[str]:
    """Fallback: the white player's monthly archive on the public API."""
    white = str(headers.get("White") or "").strip()
    date = str(headers.get("Date") or "")
    m = re.match(r"(\d{4})\.(\d{2})", date)
    if not white or not m:
        return None
    resp = client.get(
        f"https://api.chess.com/pub/player/{white.lower()}/games/{m.group(1)}/{m.group(2)}",
        headers={"User-Agent": USER_AGENT},
    )
    if resp.status_code != 200:
        return None
    for g in resp.json().get("games", []):
        if str(g.get("url", "")).rstrip("/").endswith(f"/{game_id}") and g.get("pgn"):
            return g["pgn"]
    return None


def _chesscom_pgn(game_id: str, client: httpx.Client) -> str:
    resp = client.get(
        f"https://www.chess.com/callback/live/game/{game_id}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    if resp.status_code == 404:
        raise GameUrlError("Chess.com does not know this game.")
    if resp.status_code == 429:
        raise GameUrlError("Chess.com rate limit — try again in a minute.")
    resp.raise_for_status()
    data = resp.json()
    game = data.get("game") or {}
    headers = game.get("pgnHeaders") or {}
    if not headers.get("White") or not headers.get("Black"):
        raise GameUrlError("Chess.com returned no game data for this link.")
    tcn = game.get("moveList") or ""
    if tcn:
        try:
            return _pgn_from_moves(headers, decode_tcn(tcn))
        except GameUrlError as exc:
            logger.info("chess.com TCN decode failed for %s (%s); trying the archive", game_id, exc)
    pgn = _chesscom_archive_pgn(headers, game_id, client)
    if not pgn:
        raise GameUrlError("Could not read the moves of this Chess.com game.")
    return pgn


# ── Shared ─────────────────────────────────────────────────────────────────


def _header(pgn: str, tag: str) -> str:
    m = re.search(rf'^\[{tag} "([^"]*)"\]', pgn, re.M)
    return m.group(1) if m else ""


def _int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fetch_game_by_url(url: str, client: httpx.Client = None) -> dict:
    """PGN and headers of the game behind a Lichess / Chess.com link.

    Raises GameUrlError with a student-readable message on anything expected
    (bad link, unknown game, rate limit); network errors propagate as httpx
    exceptions for the caller to report.
    """
    provider, game_id = parse_game_url(url)
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT, follow_redirects=True)
    try:
        pgn = _lichess_pgn(game_id, client) if provider == "lichess" else _chesscom_pgn(game_id, client)
    finally:
        if own:
            client.close()
    if not pgn or "1." not in pgn and "1-0" not in pgn:
        raise GameUrlError("The game has no moves.")
    plies = len(re.sub(r"\{[^}]*\}", "", pgn.split("\n\n", 1)[-1]).replace("\n", " ").split()) if "\n\n" in pgn else 0
    return {
        "source": provider,
        "game_id": game_id,
        "url": url.strip(),
        "pgn": pgn,
        "white": _header(pgn, "White") or "?",
        "black": _header(pgn, "Black") or "?",
        "white_elo": _int(_header(pgn, "WhiteElo")),
        "black_elo": _int(_header(pgn, "BlackElo")),
        "result": _header(pgn, "Result") or "*",
        "date": _header(pgn, "UTCDate") or _header(pgn, "Date"),
        "event": _header(pgn, "Event"),
        "eco": _header(pgn, "ECO"),
        "opening": _header(pgn, "Opening"),
        "plies_hint": plies,
    }


IMPORT_URL_SCHEMA = {
    "name": "import_game_from_url",
    "description": (
        "Fetch a game by its Lichess or Chess.com link (e.g. https://lichess.org/kAdOQKeh or "
        "https://www.chess.com/game/live/184239477800). Returns the PGN and headers. "
        "Then call board_control with action_type=load_pgn and the returned pgn to show it, "
        "and use find_critical_moments to review it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The game link the student pasted."},
        },
        "required": ["url"],
    },
}


def _handle_import_game_from_url(args: dict, **kwargs) -> str:
    url = str(args.get("url") or "").strip()
    try:
        result = fetch_game_by_url(url)
        result["hint"] = "Call board_control(action_type='load_pgn', pgn=<pgn>) to put the game on the board."
    except GameUrlError as exc:
        result = {"error": str(exc), "url": url}
    except httpx.HTTPError as exc:
        result = {"error": f"Could not reach the site: {exc}", "url": url}
    return json.dumps(result, ensure_ascii=False)


registry.register(
    name="import_game_from_url",
    toolset="chess",
    schema=IMPORT_URL_SCHEMA,
    handler=_handle_import_game_from_url,
    description="Fetch a game by its Lichess / Chess.com link.",
    emoji="🔗",
)
