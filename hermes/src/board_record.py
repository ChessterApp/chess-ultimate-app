"""The record of the game on the student's board, for the model (24.11).

A game the student puts on the study board — a pasted PGN, a .pgn file, a link — reached the model as the position the
board shows and nothing else: the turn's context held the position's analysis, and the game's moves only inside the
review step's list of moments. That step runs when its scan fits in the turn's wait (the background has usually
scanned the game by then); on a game that arrived with the question itself it does not fit on the production server,
so «Review this game» was answered from the final position — «the rook on d8 mates… send me the moves» (prod 24.11,
the Opera Game from a file) — and «which sacrifice decided the game?» could never be answered from the board at all.
The day before the same game was told from memory: «решающая жертва ферзя на d8» for 16.Qb8+ (tester 23.11).

The server knows the record exactly, so it says it: ``block`` is the turn's «## The game on the board» — the players
and the result when the record names them, every move numbered, and the move the board shows. ``finished`` tells a
game that ended from a line still open (an opening's moves the coach put up, a game in progress): only a finished
game's moves are a record an answer is checked against (src/answer_check_db.sacrifice_issues).
"""

from __future__ import annotations

import io
from typing import Optional

import chess
import chess.pgn

HEADER = "## The game on the board"
MAX_PLIES = 600


def _read(pgn: str):
    try:
        game = chess.pgn.read_game(io.StringIO(pgn or ""))
    except Exception:  # noqa: BLE001
        return None, []
    if game is None:
        return None, []
    board = game.board()
    line = []
    for move in game.mainline_moves():
        if move not in board.legal_moves or len(line) >= MAX_PLIES:
            break
        line.append((board.copy(stack=False), move))
        board.push(move)
    return game, line


def _label(board: chess.Board, move: chess.Move) -> str:
    return f"{board.fullmove_number}{'.' if board.turn == chess.WHITE else '...'}{board.san(move)}"


def record(line: list) -> str:
    """«1.e4 e5 2.Nf3 d6 …» of *line* [(board before, move)], Black's first move of a line written «5...Nf6»."""
    out = []
    for i, (board, move) in enumerate(line):
        san = board.san(move)
        if board.turn == chess.WHITE:
            out.append(f"{board.fullmove_number}.{san}")
        else:
            out.append(f"{board.fullmove_number}...{san}" if i == 0 else san)
    return " ".join(out)


def finished(pgn: str) -> bool:
    """The record is of a game that ended: its last position is mate or a draw by the rules, or its result is told."""
    game, line = _read(pgn)
    if game is None or not line:
        return False
    last, move = line[-1]
    end = last.copy(stack=False)
    end.push(move)
    if end.is_checkmate() or end.is_stalemate() or end.is_insufficient_material():
        return True
    return str(game.headers.get("Result") or "").strip() in ("1-0", "0-1", "1/2-1/2")


def block(pgn: str, ply: Optional[int] = None) -> str:
    """The turn's block for the game (or the line) of *pgn* on the board showing its *ply* — "" when it has no moves."""
    game, line = _read(pgn)
    if game is None or not line:
        return ""
    heads = game.headers
    who = [f"{side} {heads.get(side)}" for side in ("White", "Black")
           if str(heads.get(side) or "").strip() not in ("", "?")]
    result = str(heads.get("Result") or "").strip()
    told = ", ".join(who + ([f"result {result}"] if result in ("1-0", "0-1", "1/2-1/2") else []))
    total = len(line)
    at = total if ply is None else max(0, min(int(ply), total))
    shown = ("the start position, before the first move" if at == 0
             else f"the position after {_label(*line[at - 1])}" + (" — the game's last move" if at == total else ""))
    return (
        f"{HEADER}\n"
        "The moves on the student's board — a game or a line put there (a pasted PGN, a file, a link, or shown by "
        f"you). The record, exact{': ' + told if told else ''}:\n"
        f"{record(line)}\n"
        f"{total} plies. The board shows {shown} (ply {at} of {total}).\n"
        "Tell these moves only from this record — which piece went where, what was taken, sacrificed or traded, on "
        "which move — never from memory of a similar or famous game. Asked to review the game with no list of the "
        "engine's moments in this turn, call find_critical_moments with this record as its PGN."
    )
