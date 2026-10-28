"""What a tool put on the student's board is what the model is told — one place for every tool.

Two lies came out of the tools' own words (2026-10-09). Under the board lock get_puzzle still
said «the puzzle is already on the student's board» while nothing went up: the /coach chip
«Дай мне тактическую задачу» left the start position and the coach said the puzzle was there
(production). And after a puzzle did go up, the turn's [Engine] line — computed for the board
before it — was read as the puzzle's: «сыграй d4, на Nf6 — c4» about a mate puzzle (stand).

Every chess tool's result passes here (src/tools/__init__._tell_the_board): a new position
under a strict lock is taken out and the model is told nothing went up; any other new position
is named, with the warning that the turn's engine line and facts were about the board before.
"""

import io
import json
from typing import Optional

import chess
import chess.pgn

POSITION_ACTIONS = frozenset({"set_fen", "set_puzzle", "load_pgn", "clear_board"})

GAME_KEPT_NOTE = (
    "A game against the student is on: the position belongs to the game and nothing was put on the board. "
    "The student's moves go through make_game_move, the engine makes yours; board_control may only draw "
    "arrows or highlight squares."
)


def position_after(action: dict) -> Optional[str]:
    """The FEN a position-changing board action leaves on the board, or None."""
    kind = action.get("type")
    if kind in ("set_fen", "set_puzzle"):
        return action.get("fen")
    if kind == "clear_board":
        return "8/8/8/8/8/8/8/8 w - - 0 1"
    if kind == "load_pgn" and action.get("pgn"):
        try:
            game = chess.pgn.read_game(io.StringIO(action["pgn"]))
            return game.end().board().fen() if game is not None else None
        except Exception:  # noqa: BLE001
            return None
    return None


def board_now_note(fen: Optional[str]) -> str:
    where = "the position this tool put up"
    if fen:
        try:
            side = "White" if chess.Board(fen).turn else "Black"
            where = f"{fen} — {side} to move"
        except ValueError:
            where = fen
    return (f"The student's board now shows {where}. Any [Engine] line or board facts in the student's "
            "message are about the board before it: they say nothing about this position.")


# A position the model sets from memory (stand voice run 28.10: to «show» the Légal trap it put up a made-up start
# position with a black pawn on e4 — the engine then analysed nonsense) — an opening-sized army (this many pieces or
# more) goes up only if a verified source of the session had that position; sparse set-ups (an ending the student
# describes) stay the model's to set.
INVENTED_MIN_PIECES = 20
INVENTED_NOTE = (
    "This position is not from any verified source of this conversation (an opening line, a lesson, a puzzle, the "
    "game, the student's board): nothing was put up. Never set an opening position from memory — show a line by its "
    "moves (board_control load_pgn, the moves are checked) or ask lookup_opening for the book line.")
_FEN_IN_TEXT = None


def _key(board: chess.Board) -> str:
    return board.board_fen() + (" w" if board.turn else " b")


def _keys_of(value, out: set) -> None:
    """Every position a tool result names: FENs, and the positions along any PGN line in it."""
    global _FEN_IN_TEXT
    if _FEN_IN_TEXT is None:
        import re

        _FEN_IN_TEXT = re.compile(r"(?:[pnbrqkPNBRQK1-8]{1,8}/){7}[pnbrqkPNBRQK1-8]{1,8} [wb]")
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("pgn", "line", "book_line", "game_pgn") and isinstance(v, str) and v.strip():
                try:
                    game = chess.pgn.read_game(io.StringIO(v))
                    board = game.board() if game is not None else None
                    if board is not None:
                        out.add(_key(board))
                        for move in game.mainline_moves():
                            board.push(move)
                            out.add(_key(board))
                except Exception:  # noqa: BLE001
                    pass
            else:
                _keys_of(v, out)
    elif isinstance(value, list):
        for v in value:
            _keys_of(v, out)
    elif isinstance(value, str):
        for m in _FEN_IN_TEXT.finditer(value):
            try:
                out.add(_key(chess.Board(m.group(0) + " - - 0 1")))
            except ValueError:
                pass


def remember_positions(result, kwargs: Optional[dict]) -> None:
    """The positions a tool result brought, kept on the session as verified (see INVENTED_NOTE)."""
    if not isinstance(result, str) or not ("/" in result or '"pgn"' in result or '"line"' in result):
        return  # nothing positional in it (a FEN has slashes; a line comes as moves)
    try:
        obj = json.loads(result)
    except ValueError:
        return
    from src.sessions import _tool_session

    session = _tool_session(kwargs)
    if session is None:
        return
    keys = getattr(session, "_verified_positions", None)
    if keys is not None and len(keys) < 5000:
        _keys_of(obj, keys)


def _invented(fen: Optional[str], kwargs: Optional[dict]) -> bool:
    """A set_fen of the model's own: an invalid position, or an opening-sized one no verified source had."""
    try:
        board = chess.Board(fen)
    except (ValueError, TypeError):
        return True
    if not board.is_valid():
        return True
    if len(board.piece_map()) < INVENTED_MIN_PIECES:
        return False
    key = _key(board)
    if key == _key(chess.Board()):
        return False
    from src.sessions import _tool_session

    session = _tool_session(kwargs)
    if session is None:
        return False  # no session to know its sources: the old behaviour
    known = set(getattr(session, "_verified_positions", None) or ())
    for rec in getattr(session, "boards", None) or []:
        _keys_of({"pgn": rec.pgn or "", "fen": rec.fen or ""}, known)
    # a FEN the student sent is theirs to have on the board
    _keys_of(str((kwargs or {}).get("student_message") or "") + " " + str((kwargs or {}).get("utterance") or ""), known)
    return key not in known


def board_truth(result, kwargs: Optional[dict]):
    """The tool's result as the model must read it (see the module docstring)."""
    if not isinstance(result, str) or not any(f'"{kind}"' in result for kind in POSITION_ACTIONS):
        return result
    try:
        obj = json.loads(result)
    except ValueError:
        return result
    if not isinstance(obj, dict) or "error" in obj:
        return result
    single = obj.get("type") in POSITION_ACTIONS  # board_control returns the action itself
    actions = [obj] if single else [a for a in obj.get("board_actions") or [] if isinstance(a, dict)]
    moving = [a for a in actions if a.get("type") in POSITION_ACTIONS]
    if not moving:
        return result

    from src.sessions import BOARD_KEPT_NOTE, _tool_session, board_lock_strict_for

    if board_lock_strict_for(kwargs):
        from src.tools.game_play import live_game_board

        session = _tool_session(kwargs)
        note = GAME_KEPT_NOTE if session is not None and live_game_board(session) is not None else BOARD_KEPT_NOTE
        if single:
            return json.dumps({"shown": False, "board_hint": note}, ensure_ascii=False)
        kept = [a for a in actions if a.get("type") not in POSITION_ACTIONS]
        if kept:
            obj["board_actions"] = kept
        else:
            obj.pop("board_actions", None)
        for key in ("how_to_show", "on_board"):  # «already on the student's board» would be a lie
            obj.pop(key, None)
        obj["board_hint"] = note
        return json.dumps(obj, ensure_ascii=False)

    if single and obj.get("type") == "set_fen" and _invented(obj.get("fen"), kwargs):
        return json.dumps({"shown": False, "board_hint": INVENTED_NOTE}, ensure_ascii=False)
    if single:
        obj = {"board_actions": [obj]}
    obj["board_now"] = board_now_note(position_after(moving[-1]))
    return json.dumps(obj, ensure_ascii=False)
