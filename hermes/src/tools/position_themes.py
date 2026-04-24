"""Tool: score_position_themes — Evaluate position for thematic elements."""

import json
import logging

import chess

from tools.registry import registry

logger = logging.getLogger(__name__)

THEMES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "score_position_themes",
        "description": (
            "Evaluate a chess position for thematic elements: material balance, "
            "mobility, space control, and king safety. Uses python-chess, no engine needed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fen": {
                    "type": "string",
                    "description": "FEN string of the position to evaluate.",
                },
            },
            "required": ["fen"],
        },
    },
}

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}

CENTER_SQUARES = [chess.D4, chess.D5, chess.E4, chess.E5]
EXTENDED_CENTER = [
    chess.C3, chess.C4, chess.C5, chess.C6,
    chess.D3, chess.D6,
    chess.E3, chess.E6,
    chess.F3, chess.F4, chess.F5, chess.F6,
]


def _material_balance(board: chess.Board) -> dict:
    """Compute material balance from white's perspective."""
    white_material = 0
    black_material = 0
    for piece_type, value in PIECE_VALUES.items():
        white_material += len(board.pieces(piece_type, chess.WHITE)) * value
        black_material += len(board.pieces(piece_type, chess.BLACK)) * value
    return {
        "white_material": white_material,
        "black_material": black_material,
        "balance": white_material - black_material,
    }


def _mobility(board: chess.Board) -> dict:
    """Count legal moves for each side."""
    white_moves = len(list(board.legal_moves))
    board.push(chess.Move.null())
    black_moves = len(list(board.legal_moves))
    board.pop()
    return {
        "white_moves": white_moves,
        "black_moves": black_moves,
        "balance": white_moves - black_moves,
    }


def _space_control(board: chess.Board) -> dict:
    """Count center and extended center control by attack squares."""
    white_center = 0
    black_center = 0
    for sq in CENTER_SQUARES:
        if board.is_attacked_by(chess.WHITE, sq):
            white_center += 1
        if board.is_attacked_by(chess.BLACK, sq):
            black_center += 1

    white_extended = 0
    black_extended = 0
    for sq in EXTENDED_CENTER:
        if board.is_attacked_by(chess.WHITE, sq):
            white_extended += 1
        if board.is_attacked_by(chess.BLACK, sq):
            black_extended += 1

    return {
        "white_center": white_center,
        "black_center": black_center,
        "white_extended_center": white_extended,
        "black_extended_center": black_extended,
        "center_balance": white_center - black_center,
    }


def _king_safety(board: chess.Board) -> dict:
    """Evaluate king safety: pawn shield and open files near king."""
    result = {}
    for color, name in [(chess.WHITE, "white"), (chess.BLACK, "black")]:
        king_sq = board.king(color)
        if king_sq is None:
            result[f"{name}_pawn_shield"] = 0
            result[f"{name}_open_files_near_king"] = 0
            continue

        king_file = chess.square_file(king_sq)
        king_rank = chess.square_rank(king_sq)

        # Count pawn shield: pawns on adjacent files in front of king
        shield_count = 0
        shield_files = [f for f in [king_file - 1, king_file, king_file + 1] if 0 <= f <= 7]
        for f in shield_files:
            for r_offset in [1, 2]:
                r = king_rank + (r_offset if color == chess.WHITE else -r_offset)
                if 0 <= r <= 7:
                    sq = chess.square(f, r)
                    piece = board.piece_at(sq)
                    if piece and piece.piece_type == chess.PAWN and piece.color == color:
                        shield_count += 1
                        break

        # Count open files near king (no pawns of either color)
        open_files = 0
        for f in shield_files:
            has_pawn = False
            for r in range(8):
                sq = chess.square(f, r)
                piece = board.piece_at(sq)
                if piece and piece.piece_type == chess.PAWN:
                    has_pawn = True
                    break
            if not has_pawn:
                open_files += 1

        result[f"{name}_pawn_shield"] = shield_count
        result[f"{name}_open_files_near_king"] = open_files

    return result


def score_position_themes(fen: str) -> dict:
    """Evaluate a chess position for thematic elements."""
    try:
        board = chess.Board(fen)
        if not board.is_valid():
            return {"error": f"Invalid FEN: {fen}"}
    except (ValueError, IndexError):
        return {"error": f"Invalid FEN: {fen}"}

    return {
        "fen": fen,
        "material": _material_balance(board),
        "mobility": _mobility(board),
        "space_control": _space_control(board),
        "king_safety": _king_safety(board),
    }


def _handle_score_position_themes(args: dict, **kwargs) -> str:
    result = score_position_themes(fen=args.get("fen", ""))
    return json.dumps(result, indent=2)


registry.register(
    name="score_position_themes",
    toolset="chess",
    schema=THEMES_SCHEMA,
    handler=_handle_score_position_themes,
    description="Evaluate position themes: material, mobility, space, king safety.",
    emoji="🎯",
)
