"""Compact, typed summaries of tool results for the coach's rich cards (coach redesign P3a).

The text loop sends ``{"tool", "ok", "summary"?}`` in each SSE ``tool_result`` frame; the
frontend draws an engine line, a game list, an opening, a puzzle or a game's critical
moments from ``summary`` instead of throwing the tool output away. A game review becomes
``review_moments`` (src/review_moments.py), the steps of the «Моменты» flow; the plain
``critical_moments`` list is the fallback when no moment has a checkable better move. The field is additive:
clients that do not know it ignore it.

``build_summary`` is pure and never raises: an unknown tool, an error result or output it
cannot read gives ``None``. Lists are capped, strings clipped, and nothing is added that
the tool did not already return.

Evaluations are from White's side: ``eval_cp`` in centipawns, ``mate`` in moves (positive =
White mates). Moves are SAN.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import chess

logger = logging.getLogger(__name__)

MAX_ENGINE_LINES = 3
MAX_LINE_PLIES = 8
MAX_GAMES = 10
MAX_OPENING_PLIES = 20
MAX_THEMES = 6
MAX_MOMENTS = 10
MAX_TEXT = 80
# critical_moments reports a forced mate as ±10000 pawns; the card only needs "decided".
MAX_CP = 10000

ENGINE_TOOLS = frozenset({"analyze_position", "compare_variations"})
GAME_LIST_TOOLS = frozenset({
    "search_master_games", "find_games_by_position", "famous_game",
    "lichess_game_import", "chesscom_game_import", "get_user_games",
})
OPENING_TOOLS = frozenset({"identify_opening", "lookup_opening", "get_opening_stats"})
PUZZLE_TOOLS = frozenset({"get_puzzle"})
MOMENT_TOOLS = frozenset({"find_critical_moments", "review_game"})


def build_summary(tool_name: str, args: Any, raw: Any, language: Optional[str] = None) -> Optional[dict]:
    """The card summary of one tool result, or None (unknown tool, error, unreadable).

    *language* is the turn's language, for the texts of ``review_moments``."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data, dict) and "error" in data:
            return None
        args = args if isinstance(args, dict) else {}
        if tool_name in ENGINE_TOOLS:
            return _engine_line(args, data)
        if tool_name in GAME_LIST_TOOLS:
            return _game_list(tool_name, data)
        if tool_name in OPENING_TOOLS:
            return _opening(data)
        if tool_name in PUZZLE_TOOLS:
            return _puzzle(data)
        if tool_name in MOMENT_TOOLS:
            from src.review_moments import build_review_moments

            return build_review_moments(
                data, pgn=args.get("pgn"), side=args.get("side"), language=language,
            ) or _critical_moments(data)
    except Exception:  # noqa: BLE001 — a summary must never break a turn
        logger.debug("tool summary failed for %s", tool_name, exc_info=True)
    return None


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text[:MAX_TEXT] if text else None


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ── engine_line ──────────────────────────────────────────────────────────────


def _board(fen: Any) -> Optional[chess.Board]:
    from src.fen_repair import repair_fen

    if not isinstance(fen, str) or not fen.strip():
        return None
    try:
        return chess.Board(repair_fen(fen))
    except ValueError:
        return None


def _score(entry: dict, white_to_move: bool) -> Optional[dict]:
    """``{"eval_cp": n}`` or ``{"mate": n}`` from White's side; the tools score for the side to move."""
    sign = 1 if white_to_move else -1
    mate = _int(entry.get("mate_in"))
    if mate is not None:
        return {"mate": mate * sign}
    score = entry.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    return {"eval_cp": int(round(score * 100)) * sign}


def _san_line(board: chess.Board, pv: Any) -> list[str]:
    """SAN of a UCI (or SAN) line from *board*, up to the first move that does not fit."""
    tokens = pv.split() if isinstance(pv, str) else pv if isinstance(pv, list) else []
    b = board.copy(stack=False)
    sans: list[str] = []
    for token in tokens[:MAX_LINE_PLIES]:
        try:
            move = chess.Move.from_uci(str(token))
            if move not in b.legal_moves:
                raise ValueError(token)
        except ValueError:
            try:
                move = b.parse_san(str(token))
            except ValueError:
                break
        sans.append(b.san(move))
        b.push(move)
    return sans


def _engine_line(args: dict, data: Any) -> Optional[dict]:
    if not isinstance(data, dict):
        return None
    fen = data.get("fen") or args.get("fen")
    board = _board(fen)
    if board is None:
        return None
    entries = data.get("lines") if "lines" in data else [
        {**v, "pv": v.get("moves")} for v in data.get("variations") or [] if isinstance(v, dict)
    ]
    lines = []
    for entry in (entries or [])[:MAX_ENGINE_LINES]:
        if not isinstance(entry, dict):
            continue
        score = _score(entry, board.turn == chess.WHITE)
        san = _san_line(board, entry.get("pv"))
        if score is None or not san:
            continue
        lines.append({"san": san, **score})
    if not lines:
        return None
    out = {"kind": "engine_line", "fen": board.fen(), **{k: v for k, v in lines[0].items() if k != "san"}}
    first = entries[0] if isinstance(entries[0], dict) else {}
    depth = _int(data.get("depth")) or _int(first.get("depth"))
    if depth:
        out["depth"] = depth
    out["lines"] = lines
    return out


# ── game_list ────────────────────────────────────────────────────────────────


def _pgn_header(pgn: str, tag: str) -> str:
    from src.middleware.response_envelope import _header

    return _header(pgn, tag)


def _year(date: Any) -> Optional[int]:
    text = str(date or "")[:4]
    return int(text) if len(text) == 4 and text.isdigit() else None


def _game(row: dict, white_key: str, black_key: str, game_id: Any = None) -> Optional[dict]:
    pgn = row.get("pgn") if isinstance(row.get("pgn"), str) else ""
    white = _text(row.get(white_key) or _pgn_header(pgn, "White"))
    black = _text(row.get(black_key) or _pgn_header(pgn, "Black"))
    if not white or not black:
        return None
    game: dict = {
        "white": white,
        "black": black,
        "result": _text(row.get("result") or _pgn_header(pgn, "Result")) or "*",
    }
    if isinstance(game_id, (int, str)) and not isinstance(game_id, bool) and str(game_id):
        game["id"] = game_id
    eco = _text(row.get("eco") or _pgn_header(pgn, "ECO"))
    if eco:
        game["eco"] = eco
    year = _year(row.get("date") or _pgn_header(pgn, "UTCDate") or _pgn_header(pgn, "Date"))
    if year:
        game["year"] = year
    for key, tag in (("white_elo", "WhiteElo"), ("black_elo", "BlackElo")):
        elo = _int(row.get(key)) or _int(_pgn_header(pgn, tag))
        if elo:
            game[key] = elo
    return {k: game[k] for k in ("id", "white", "black", "result", "eco", "year", "white_elo", "black_elo") if k in game}


def _game_list(tool_name: str, data: Any) -> Optional[dict]:
    games: list = []
    if isinstance(data, list):  # search_master_games: TWIC rows
        games = [_game(r, "white_name", "black_name", r.get("id")) for r in data[:MAX_GAMES] if isinstance(r, dict)]
    elif isinstance(data, dict) and tool_name == "famous_game":
        if data.get("found"):
            pgn = next((a.get("pgn") for a in data.get("board_actions") or []
                        if isinstance(a, dict) and isinstance(a.get("pgn"), str)), "")
            games = [_game({"pgn": pgn}, "white", "black")]
    elif isinstance(data, dict) and isinstance(data.get("games"), list):  # by position / the student's games
        games = [_game(r, "white", "black", r.get("id")) for r in data["games"][:MAX_GAMES] if isinstance(r, dict)]
    elif isinstance(data, dict) and isinstance(data.get("last_games"), list):  # Lichess / Chess.com import
        # The same ids extract_game_results gives these cards, so a client can match the two.
        source = "chesscom" if tool_name == "chesscom_game_import" else "lichess"
        games = [
            _game(r, "white", "black", r.get("id") or f"{source}-{i}")
            for i, r in enumerate(data["last_games"][:MAX_GAMES]) if isinstance(r, dict)
        ]
    games = [g for g in games if g]
    return {"kind": "game_list", "games": games} if games else None


# ── opening ──────────────────────────────────────────────────────────────────


def _moves_san(line: Any) -> list[str]:
    from src.openings_book import _split_moves

    return list(_split_moves(line))[:MAX_OPENING_PLIES] if isinstance(line, str) else []


def _opening(data: Any) -> Optional[dict]:
    if not isinstance(data, dict) or data.get("found") is False:
        return None
    name, eco = _text(data.get("name")), _text(data.get("eco"))
    if not name or not eco:
        return None
    out: dict = {"kind": "opening", "name": name, "eco": eco}
    moves = _moves_san(data.get("book_line") or data.get("main_line") or data.get("line"))
    if moves:
        out["moves_san"] = moves
    games = _int(data.get("games_count"))
    if games:
        out["stats"] = {
            "white": float(data.get("white_win_pct") or 0),
            "draw": float(data.get("draw_pct") or 0),
            "black": float(data.get("black_win_pct") or 0),
            "games": games,
        }
    return out


# ── puzzle ───────────────────────────────────────────────────────────────────


def _puzzle(data: Any) -> Optional[dict]:
    if not isinstance(data, dict):
        return None
    puzzles = [p for p in data.get("puzzles") or [] if isinstance(p, dict)]
    on_board = data.get("on_board")
    shown = next((p for p in puzzles if p.get("puzzle_id") == on_board), puzzles[0] if puzzles else None)
    if not shown:
        return None
    puzzle_id, board = shown.get("puzzle_id"), _board(shown.get("fen"))
    if puzzle_id in (None, "") or isinstance(puzzle_id, bool) or board is None:
        return None
    out: dict = {"kind": "puzzle", "puzzle_id": str(puzzle_id), "fen": board.fen()}
    rating = _int(shown.get("rating"))
    if rating:
        out["rating"] = rating
    themes = [t for t in (_text(t) for t in shown.get("themes") or []) if t][:MAX_THEMES]
    if themes:
        out["themes"] = themes
    return out


# ── critical_moments ─────────────────────────────────────────────────────────


def _cp(pawns: Any) -> Optional[int]:
    if isinstance(pawns, bool) or not isinstance(pawns, (int, float)):
        return None
    return max(-MAX_CP, min(MAX_CP, int(round(pawns * 100))))


def _critical_moments(data: Any) -> Optional[dict]:
    if not isinstance(data, dict):
        return None
    rows = data.get("critical_moments") if "critical_moments" in data else data.get("moments")
    moments = []
    for row in (rows or [])[:MAX_MOMENTS]:
        if not isinstance(row, dict):
            continue
        number, san = _int(row.get("move_number")), _text(row.get("move"))
        before, after = _cp(row.get("eval_before")), _cp(row.get("eval_after"))
        if not number or not san or before is None or after is None:
            continue
        moments.append({
            "ply": (number - 1) * 2 + (2 if row.get("side") == "black" else 1),
            "san": san,
            "eval_before": before,
            "eval_after": after,
            "label": _text(row.get("type")) or "mistake",
        })
    return {"kind": "critical_moments", "moments": moments} if moments else None
