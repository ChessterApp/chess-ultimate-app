"""Board protocol — Pydantic models for frontend board actions.

Defines the BoardAction base and 8 subtypes that the AI emits
to control the chess board UI. Includes FEN validation via python-chess
and coordinate validation for arrows/highlights.
"""

import re
from enum import Enum
from typing import Optional, Union

import chess
import chess.pgn
from pydantic import BaseModel, Field, field_validator

# Valid algebraic squares a1–h8
_SQUARE_RE = re.compile(r"^[a-h][1-8]$")


class ActionType(str, Enum):
    SET_FEN = "set_fen"
    LOAD_PGN = "load_pgn"
    SET_PUZZLE = "set_puzzle"
    DRAW_ARROWS = "draw_arrows"
    HIGHLIGHT_SQUARES = "highlight_squares"
    NAVIGATE = "navigate"
    FLIP_BOARD = "flip_board"
    CLEAR_BOARD = "clear_board"


class NavigateDirection(str, Enum):
    FIRST = "first"
    PREV = "prev"
    NEXT = "next"
    LAST = "last"


class Arrow(BaseModel):
    from_sq: str = Field(..., alias="from")
    to_sq: str = Field(..., alias="to")
    brush: str = "green"

    model_config = {"populate_by_name": True}

    @field_validator("from_sq", "to_sq")
    @classmethod
    def validate_square(cls, v: str) -> str:
        v = v.lower()
        if not _SQUARE_RE.match(v):
            raise ValueError(f"Invalid square: {v!r} — must be a1-h8")
        return v


def validate_fen(fen: str) -> str:
    """Validate a FEN string using python-chess. Returns the FEN if valid."""
    try:
        board = chess.Board(fen)
        # Ensure the FEN round-trips cleanly
        return board.fen()
    except (ValueError, Exception) as exc:
        raise ValueError(f"Invalid FEN: {exc}") from exc


def parse_pgn_moves(pgn_text: str) -> list[str]:
    """Parse a PGN string and return a list of SAN moves."""
    import io
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Could not parse PGN")
    return [move.san() for move in game.mainline()]


# --- BoardAction subtypes ---

class SetFen(BaseModel):
    action: ActionType = Field(ActionType.SET_FEN, alias="type")
    fen: str

    model_config = {"populate_by_name": True}

    @field_validator("fen")
    @classmethod
    def validate_fen_field(cls, v: str) -> str:
        return validate_fen(v)


class LoadPgn(BaseModel):
    action: ActionType = Field(ActionType.LOAD_PGN, alias="type")
    pgn: str
    moves: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @field_validator("pgn")
    @classmethod
    def validate_and_parse_pgn(cls, v: str) -> str:
        # Just validate it parses — moves populated in model_post_init
        parse_pgn_moves(v)
        return v

    def model_post_init(self, _context) -> None:
        if not self.moves:
            self.moves = parse_pgn_moves(self.pgn)


class SetPuzzle(BaseModel):
    action: ActionType = Field(ActionType.SET_PUZZLE, alias="type")
    fen: str
    solution: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @field_validator("fen")
    @classmethod
    def validate_fen_field(cls, v: str) -> str:
        return validate_fen(v)


class DrawArrows(BaseModel):
    action: ActionType = Field(ActionType.DRAW_ARROWS, alias="type")
    arrows: list[Arrow]

    model_config = {"populate_by_name": True}


class HighlightSquares(BaseModel):
    action: ActionType = Field(ActionType.HIGHLIGHT_SQUARES, alias="type")
    squares: list[str]
    color: str = "yellow"

    model_config = {"populate_by_name": True}

    @field_validator("squares")
    @classmethod
    def validate_squares(cls, v: list[str]) -> list[str]:
        result = []
        for sq in v:
            sq = sq.lower()
            if not _SQUARE_RE.match(sq):
                raise ValueError(f"Invalid square: {sq!r} — must be a1-h8")
            result.append(sq)
        return result


class Navigate(BaseModel):
    action: ActionType = Field(ActionType.NAVIGATE, alias="type")
    direction: NavigateDirection

    model_config = {"populate_by_name": True}


class FlipBoard(BaseModel):
    action: ActionType = Field(ActionType.FLIP_BOARD, alias="type")

    model_config = {"populate_by_name": True}


class ClearBoard(BaseModel):
    action: ActionType = Field(ActionType.CLEAR_BOARD, alias="type")

    model_config = {"populate_by_name": True}


# Union type for all board actions
BoardAction = Union[
    SetFen, LoadPgn, SetPuzzle, DrawArrows,
    HighlightSquares, Navigate, FlipBoard, ClearBoard,
]


class ResponseEnvelope(BaseModel):
    """Response wrapper: text message + optional board actions."""
    message: str
    board_actions: list[BoardAction] = Field(default_factory=list)

    def model_dump(self, **kwargs) -> dict:
        kwargs.setdefault("by_alias", True)
        return super().model_dump(**kwargs)
