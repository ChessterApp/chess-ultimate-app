"""A game review as guided «Моменты» (coach redesign P3b): the ``review_moments`` summary.

The critical-moments scan (``find_critical_moments``; ``review_game`` and the server's review
pre-step run it too) already holds, for every turning point, the position before the move, the
move played, the engine's better move and the evaluations. This module turns that into at most
``MAX_MOMENTS`` steps the student replays on the board: the position with the mover to move, a
question, the move to find (SAN + UCI), a motif and a short explanation.

Everything is deterministic: the moves are checked against the position with python-chess (a
moment whose played or best move does not fit is dropped), the motif comes from the board
(src/motifs.py), the question and explanation from templates. ``build_review_moments`` never
raises; it returns ``None`` when no moment survives.
"""

from __future__ import annotations

import io
import logging
from typing import Any, Optional

import chess
import chess.pgn

logger = logging.getLogger(__name__)

MAX_MOMENTS = 10
MAX_NAME = 80
MAX_TEXT = 240
# critical_moments reports a forced mate as ±10000 pawns; centipawns are clamped to this.
MAX_CP = 10000

# Short motif slugs the client translates; a moment the board does not explain has none.
MOTIFS = ("mate", "fork", "discovered_attack", "pin", "skewer", "hanging_piece")

_TEXT = {
    "ru": {
        "question_mate": "{side} могут поставить мат. Найдите ход!",
        "question": "В партии было {played}. Найдите ход сильнее за {side_gen}.",
        "white": "Белые", "black": "Чёрные", "white_gen": "белых", "black_gen": "чёрных",
        "better": "Сильнее {best}",
        "swing": "После {played} оценка изменилась: {before} → {after}.",
        "mate": "мат",
        "motif": {
            "mate": "ведёт к мату", "fork": "вилка", "discovered_attack": "вскрытое нападение",
            "pin": "связка", "skewer": "линейный удар", "hanging_piece": "фигура без защиты",
        },
    },
    "en": {
        "question_mate": "{side} can force mate here. Find the move!",
        "question": "The game went {played}. Find a stronger move for {side_gen}.",
        "white": "White", "black": "Black", "white_gen": "White", "black_gen": "Black",
        "better": "Better was {best}",
        "swing": "After {played} the evaluation went {before} → {after}.",
        "mate": "mate",
        "motif": {
            "mate": "leads to mate", "fork": "a fork", "discovered_attack": "a discovered attack",
            "pin": "a pin", "skewer": "a skewer", "hanging_piece": "an undefended piece",
        },
    },
}


def build_review_moments(
    data: Any,
    *,
    pgn: Optional[str] = None,
    side: Optional[str] = None,
    language: Optional[str] = None,
    game_id: Any = None,
) -> Optional[dict]:
    """The ``review_moments`` summary of a critical-moments result, or None.

    *data* is ``find_critical_moments``' result (``critical_moments``) or ``review_game``'s
    (``moments``). *pgn* gives the players and the result; *side* ("white"/"black") keeps only
    that side's moments; *language* picks the templates (English for "en", Russian otherwise).
    """
    try:
        return _build(data, pgn=pgn, side=side, language=language, game_id=game_id)
    except Exception:  # noqa: BLE001 — a summary must never break a turn
        logger.debug("review_moments build failed", exc_info=True)
        return None


def _build(data: Any, *, pgn, side, language, game_id) -> Optional[dict]:
    if not isinstance(data, dict):
        return None
    rows = data.get("critical_moments") if "critical_moments" in data else data.get("moments")
    if not isinstance(rows, list):
        return None
    text = _TEXT["en" if (language or "").lower().startswith("en") else "ru"]
    want = side.lower() if isinstance(side, str) and side.lower() in ("white", "black") else None
    moments = []
    for row in rows:
        moment = _moment(row, text, want)
        if moment:
            moments.append(moment)
    if not moments:
        return None
    moments.sort(key=lambda m: m["ply"])
    return {"kind": "review_moments", "game": _game(pgn, game_id), "moments": moments[:MAX_MOMENTS]}


def _clip(value: Any, limit: int = MAX_NAME) -> Optional[str]:
    if value is None:
        return None
    out = str(value).strip()
    return out[:limit] if out else None


def _game(pgn: Optional[str], game_id: Any) -> dict:
    headers: dict = {}
    if isinstance(pgn, str) and pgn.strip():
        try:
            game = chess.pgn.read_headers(io.StringIO(pgn))
            headers = dict(game) if game is not None else {}
        except Exception:  # noqa: BLE001 — the players are cosmetic
            headers = {}
    game = {"white": _clip(headers.get("White")) or "?", "black": _clip(headers.get("Black")) or "?"}
    result = _clip(headers.get("Result"))
    if result and result != "*":
        game["result"] = result
    if isinstance(game_id, (int, str)) and not isinstance(game_id, bool) and str(game_id):
        game["id"] = game_id
    return game


def _cp(pawns: Any) -> Optional[int]:
    if isinstance(pawns, bool) or not isinstance(pawns, (int, float)):
        return None
    return max(-MAX_CP, min(MAX_CP, int(round(pawns * 100))))


def _parse(board: chess.Board, token: Any) -> Optional[chess.Move]:
    """A legal move of *board* from SAN (or UCI), else None."""
    if not isinstance(token, str) or not token.strip():
        return None
    token = token.strip()
    try:
        return board.parse_san(token)
    except ValueError:
        pass
    try:
        move = chess.Move.from_uci(token)
    except ValueError:
        return None
    return move if move in board.legal_moves else None


def _numbered(board: chess.Board, san: str) -> str:
    dots = "." if board.turn == chess.WHITE else "..."
    return f"{board.fullmove_number}{dots}{san}"


def _moment(row: Any, text: dict, want: Optional[str]) -> Optional[dict]:
    if not isinstance(row, dict):
        return None
    try:
        board = chess.Board(row.get("fen_before"))
    except (TypeError, ValueError):
        return None
    if not board.is_valid():
        return None
    mover = "white" if board.turn == chess.WHITE else "black"
    if row.get("side") in ("white", "black") and row["side"] != mover:
        return None  # the row and its position disagree on who moved
    if want and mover != want:
        return None
    played, best = _parse(board, row.get("move")), _parse(board, row.get("best_move"))
    if played is None or best is None or played == best:
        return None
    played_san, best_san = board.san(played), board.san(best)
    motif = _motif(board, best, played, row.get("type"))
    moment: dict = {
        "ply": (board.fullmove_number - 1) * 2 + (1 if board.turn == chess.WHITE else 2),
        "fen": board.fen(),
        "played": played_san,
        "best": best_san,
        "best_uci": best.uci(),
    }
    if motif:
        moment["motif"] = motif
    before, after = _cp(row.get("eval_before")), _cp(row.get("eval_after"))
    moment["question"] = _question(board, played_san, motif, text)
    moment["explanation"] = _explanation(board, played_san, best_san, motif, before, after, text)
    if before is not None:
        moment["eval_before"] = before
    if after is not None:
        moment["eval_after"] = after
    return moment


def _question(board: chess.Board, played_san: str, motif: Optional[str], text: dict) -> str:
    white = board.turn == chess.WHITE
    if motif == "mate":
        return text["question_mate"].format(side=text["white" if white else "black"])
    return text["question"].format(
        played=_numbered(board, played_san), side_gen=text["white_gen" if white else "black_gen"])


def _score(cp: int, text: dict) -> str:
    if abs(cp) >= MAX_CP:
        return f"{'+' if cp > 0 else '−'}{text['mate']}"
    pawns = cp / 100
    return f"{'+' if pawns >= 0 else '−'}{abs(pawns):.1f}"


def _explanation(board, played_san, best_san, motif, before, after, text) -> str:
    out = text["better"].format(best=_numbered(board, best_san))
    out += f" — {text['motif'][motif]}." if motif else "."
    if before is not None and after is not None:
        out += " " + text["swing"].format(
            played=_numbered(board, played_san), before=_score(before, text), after=_score(after, text))
    return out[:MAX_TEXT]


# ── motif ────────────────────────────────────────────────────────────────────


def _undefended(board: chess.Board, square: int) -> bool:
    """The piece on *square* can be taken for free: attacked and not defended."""
    piece = board.piece_at(square)
    if piece is None or piece.piece_type == chess.KING:
        return False
    return board.is_attacked_by(not piece.color, square) and not board.is_attacked_by(piece.color, square)


def _motif(board: chess.Board, best: chess.Move, played: chess.Move, kind: Any) -> Optional[str]:
    """What the better move does (or what the played one gave away), when the board shows it."""
    from src.motifs import _discovers, _forks, _pins, _skewers

    us = board.turn
    after = board.copy(stack=False)
    after.push(best)
    if after.is_checkmate() or kind == "missed_mate":
        return "mate"
    if _forks(after, best.to_square):
        return "fork"
    if _discovers(board, best):
        return "discovered_attack"
    if _pins(after, us) and not _pins(board, us):
        return "pin"
    if _skewers(after, us) and not _skewers(board, us):
        return "skewer"
    victim = board.piece_at(best.to_square)
    if victim is not None and victim.piece_type != chess.PAWN and _undefended(board, best.to_square):
        return "hanging_piece"  # the better move took a piece left without defence
    played_after = board.copy(stack=False)
    played_after.push(played)
    moved = played_after.piece_at(played.to_square)
    if moved is not None and moved.piece_type != chess.PAWN and _undefended(played_after, played.to_square):
        return "hanging_piece"  # the move played left the piece en prise
    return None
