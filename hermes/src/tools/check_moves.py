"""Tool: check_moves — verify candidate move legality (engine-free).

Pure python-chess legality check for the coach. Lets the model (especially the
voice coach, which can *speak* a move nothing validated) confirm a move is legal
before recommending it, and returns the full legal-move list so it can
self-correct in one round-trip. No Stockfish, no network, no DB.
"""

import json
import logging
import re

import chess

from tools.registry import registry

logger = logging.getLogger(__name__)

# Coordinate/UCI notation, e.g. "g1f3" or "e7e8q". Dispatched to the UCI path;
# everything else is treated as SAN. (python-chess's parse_san also accepts
# coordinate notation, so shape-based dispatch keeps the two paths distinct and
# lets us give precise per-notation reasons instead of a redundant fallback.)
_UCI_RE = re.compile(r"^[a-h][1-8][a-h][1-8][qrbnQRBN]?$")

# Cap the legal-move list so freak positions can't bloat the tool result.
MAX_LEGAL_MOVES = 60
# Bounds on the candidate move batch (mirrors the input schema).
MIN_MOVES = 1
MAX_MOVES = 10

CHECK_MOVES_SCHEMA = {
    "name": "check_moves",
    "description": (
        "Verify whether candidate moves are legal in a given position. "
        "ALWAYS use this before recommending a specific move that did not come "
        "from analyze_position/compare_variations output. Returns legality per "
        "move plus the full legal move list."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fen": {
                "type": "string",
                "description": "FEN string of the position to check against.",
            },
            "moves": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": MIN_MOVES,
                "maxItems": MAX_MOVES,
                "description": (
                    "1-10 candidate moves in SAN (e.g. \"Nf3\", \"O-O\", "
                    "\"exd5\") or UCI (e.g. \"g1f3\"). Both notations accepted."
                ),
            },
        },
        "required": ["fen", "moves"],
    },
}

_PIECE_LETTER_NAMES = {
    "N": "knight",
    "B": "bishop",
    "R": "rook",
    "Q": "queen",
    "K": "king",
}


def _dest_square(san_core: str) -> str:
    """Extract the destination square (e.g. 'e5') from a SAN move, or ''."""
    # Promotions (e8=Q) and the like: scan for the last file+rank pair.
    for i in range(len(san_core) - 1, 0, -1):
        pair = san_core[i - 1 : i + 1]
        if len(pair) == 2 and pair[0] in "abcdefgh" and pair[1] in "12345678":
            return pair
    return ""


def _reason_illegal_san(san: str) -> str:
    """Best-effort explanation for a SAN move that parsed but is illegal."""
    core = san.rstrip("+#!?")
    if core in ("O-O", "0-0", "O-O-O", "0-0-0"):
        return "castling is not legal in this position"
    piece = _PIECE_LETTER_NAMES.get(core[0], "pawn") if core else "pawn"
    dest = _dest_square(core)
    if dest:
        return f"no legal {piece} move to {dest}"
    return f"no legal {piece} move"


def _reason_illegal_uci(board: chess.Board, move: chess.Move) -> str:
    """Best-effort explanation for a well-formed UCI move that is illegal."""
    from_sq = chess.square_name(move.from_square)
    to_sq = chess.square_name(move.to_square)
    piece = board.piece_at(move.from_square)
    side = "white" if board.turn == chess.WHITE else "black"
    if piece is None:
        return f"no piece on {from_sq}"
    if piece.color != board.turn:
        return f"the piece on {from_sq} is not {side}'s to move"
    # Pseudo-legal but not legal ⇒ the move leaves the king in check.
    if move in board.pseudo_legal_moves:
        return f"{from_sq}-{to_sq} leaves the king in check"
    return f"the {chess.piece_name(piece.piece_type)} on {from_sq} cannot legally reach {to_sq}"


def _legal_result(board: chess.Board, move_str: str, move: chess.Move) -> dict:
    return {"move": move_str, "legal": True, "san": board.san(move), "uci": move.uci()}


def _check_one(board: chess.Board, raw_move: str) -> dict:
    """Classify a single candidate move as legal or illegal (with a reason)."""
    move_str = str(raw_move).strip()
    if not move_str:
        return {"move": raw_move, "legal": False, "reason": "empty move string"}

    # Coordinate/UCI notation (e.g. "g1f3") — parse to a Move for a precise reason.
    if _UCI_RE.match(move_str):
        move = chess.Move.from_uci(move_str.lower())
        if move in board.legal_moves:
            return _legal_result(board, move_str, move)
        return {"move": move_str, "legal": False, "reason": _reason_illegal_uci(board, move)}

    # Otherwise treat as SAN — the coach mostly speaks SAN.
    try:
        move = board.parse_san(move_str)
        return _legal_result(board, move_str, move)
    except chess.AmbiguousMoveError:
        return {
            "move": move_str,
            "legal": False,
            "reason": f"ambiguous SAN '{move_str}' — matches multiple legal moves",
        }
    except chess.IllegalMoveError:
        return {"move": move_str, "legal": False, "reason": _reason_illegal_san(move_str)}
    except (chess.InvalidMoveError, ValueError):
        return {
            "move": move_str,
            "legal": False,
            "reason": f"unparseable move '{move_str}' — not valid SAN or UCI",
        }


def check_moves(fen: str, moves: list) -> dict:
    """Check the legality of candidate moves in a position (pure python-chess)."""
    try:
        board = chess.Board(fen)
        if not board.is_valid():
            return {"error": f"Invalid FEN: {fen}"}
    except (ValueError, IndexError):
        return {"error": f"Invalid FEN: {fen}"}

    if not isinstance(moves, list):
        return {"error": "moves must be an array of move strings"}
    if len(moves) < MIN_MOVES:
        return {"error": "moves must contain at least 1 move"}
    if len(moves) > MAX_MOVES:
        return {"error": f"moves must contain at most {MAX_MOVES} moves"}

    results = [_check_one(board, m) for m in moves]

    legal_moves = [board.san(m) for m in board.legal_moves]
    truncated = len(legal_moves) > MAX_LEGAL_MOVES

    out = {
        "fen": fen,
        "side_to_move": "white" if board.turn == chess.WHITE else "black",
        "results": results,
        "legal_moves": legal_moves[:MAX_LEGAL_MOVES] if truncated else legal_moves,
    }
    if truncated:
        out["legal_moves_truncated"] = True
    return out


def _handle_check_moves(args: dict, **kwargs) -> str:
    result = check_moves(fen=args.get("fen", ""), moves=args.get("moves", []))
    return json.dumps(result, indent=2)


registry.register(
    name="check_moves",
    toolset="chess",
    schema=CHECK_MOVES_SCHEMA,
    handler=_handle_check_moves,
    description="Verify candidate move legality in a position (engine-free, python-chess).",
    emoji="✅",
)
