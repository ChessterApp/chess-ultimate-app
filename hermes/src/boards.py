"""Boards: the positions a coaching session is working on.

A session used to hold one FEN string (``board_state``) that was persisted
and never restored. A session now owns a list of :class:`Board` records —
the study board, puzzles, master games opened from search, and (later) a
game against the coach — one of which is *active*. Every coach turn talks
about the active board; ``board_control`` actions are applied to it on the
server so the board survives a reload, and the client mirrors the same
records as its tabs.
"""

import io
import time
import uuid
from typing import Any, Optional

import chess
import chess.pgn
from pydantic import BaseModel, Field

BOARD_KINDS = ("study", "puzzle", "game", "master_game")
DEFAULT_TITLE = {"study": "Доска тренера", "puzzle": "Задача", "game": "Партия", "master_game": "Партия мастеров"}


def _fens_from_pgn(pgn: str) -> list[str]:
    """FEN after every ply of a PGN's main line (index 0 = start position)."""
    game = chess.pgn.read_game(io.StringIO(pgn or ""))
    if game is None or game.errors:
        raise ValueError("Could not parse PGN")
    board = game.board()
    fens = [board.fen()]
    for move in game.mainline_moves():
        board.push(move)
        fens.append(board.fen())
    if len(fens) == 1 and (pgn or "").strip():
        raise ValueError("PGN contains no moves")
    return fens


def position_key(fen: str) -> str:
    """Pieces + side + castling: the part of a FEN that identifies a position
    for navigation (en-passant and move clocks differ between sources)."""
    return " ".join((fen or "").split()[:3])


class Board(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    kind: str = "study"
    title: str = ""
    pgn: str = ""
    fen: str = chess.STARTING_FEN
    ply: int = 0
    orientation: str = "white"
    # Last arrows / highlights the coach drew, so a reload shows them again.
    annotations: dict = Field(default_factory=dict)
    # set_puzzle payload (puzzle_id, solution …) when kind == "puzzle".
    puzzle: Optional[dict] = None
    # Play mode state (opponent, strength, clocks, result) when kind == "game".
    game_state: Optional[dict] = None
    # Where the board came from: {"twic_game_id": 123} / {"lichess": "abc"} …
    source: Optional[dict] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    # ── mutation helpers (return True when something changed) ─────────
    def touch(self) -> None:
        self.updated_at = time.time()

    def set_fen(self, fen: str) -> None:
        chess.Board(fen)  # validates
        self.fen = fen
        self.pgn = ""
        self.ply = 0
        self.annotations = {}
        if self.kind == "puzzle":
            self.kind = "study"
            self.puzzle = None
        self.touch()

    def load_pgn(self, pgn: str, ply: Optional[int] = None) -> None:
        fens = _fens_from_pgn(pgn)
        self.pgn = pgn
        self.ply = len(fens) - 1 if ply is None else max(0, min(ply, len(fens) - 1))
        self.fen = fens[self.ply]
        self.annotations = {}
        if self.kind == "puzzle":
            self.kind = "study"
            self.puzzle = None
        self.touch()

    def navigate(self, direction: str) -> None:
        if not self.pgn:
            return
        fens = _fens_from_pgn(self.pgn)
        last = len(fens) - 1
        target = {"first": 0, "last": last, "prev": self.ply - 1, "next": self.ply + 1}.get(direction, self.ply)
        self.ply = max(0, min(target, last))
        self.fen = fens[self.ply]
        self.touch()

    def apply_action(self, action: dict) -> bool:
        """Apply one board_control action (validated dict). Returns True if the board changed."""
        kind = action.get("type")
        try:
            if kind == "set_fen":
                self.set_fen(action["fen"])
            elif kind == "load_pgn":
                self.load_pgn(action["pgn"])
            elif kind == "set_puzzle":
                self.set_fen(action["fen"])
                self.kind = "puzzle"
                self.puzzle = {k: v for k, v in action.items() if k in ("puzzle_id", "solution", "fen")}
                self.title = self.title or DEFAULT_TITLE["puzzle"]
            elif kind == "navigate":
                self.navigate(action.get("direction", ""))
            elif kind == "flip_board":
                self.orientation = "black" if self.orientation == "white" else "white"
                self.touch()
            elif kind == "clear_board":
                self.set_fen(chess.STARTING_FEN)
            elif kind == "draw_arrows":
                self.annotations = {**self.annotations, "arrows": action.get("arrows", [])}
                self.touch()
            elif kind == "highlight_squares":
                self.annotations = {**self.annotations, "highlights": action.get("squares", []),
                                    "highlight_color": action.get("color")}
                self.touch()
            else:
                return False
        except (ValueError, KeyError):
            return False
        return True

    def to_public(self) -> dict:
        return self.model_dump()


def new_board(
    session_id: str,
    kind: str = "study",
    title: str = "",
    pgn: str = "",
    fen: Optional[str] = None,
    orientation: str = "white",
    source: Optional[dict] = None,
    ply: Optional[int] = None,
) -> Board:
    if kind not in BOARD_KINDS:
        raise ValueError(f"Unknown board kind {kind!r}")
    if orientation not in ("white", "black"):
        raise ValueError("orientation must be 'white' or 'black'")
    board = Board(session_id=session_id, kind=kind, title=title or DEFAULT_TITLE[kind],
                  orientation=orientation, source=source)
    if pgn:
        board.load_pgn(pgn, ply=ply)
    elif fen:
        board.set_fen(fen)
    return board


def board_from_row(row: dict[str, Any]) -> Board:
    """Rebuild a Board from a coach_boards row (timestamps are ISO strings there)."""
    data = dict(row)
    for key in ("created_at", "updated_at"):
        value = data.get(key)
        if isinstance(value, str):
            from datetime import datetime

            try:
                data[key] = datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                data[key] = time.time()
    data.setdefault("annotations", {})
    if data.get("annotations") is None:
        data["annotations"] = {}
    return Board(**{k: v for k, v in data.items() if k in Board.model_fields})
