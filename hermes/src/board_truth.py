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

    from src.sessions import BOARD_KEPT_NOTE, board_lock_strict_for

    if board_lock_strict_for(kwargs):
        if single:
            return json.dumps({"shown": False, "board_hint": BOARD_KEPT_NOTE}, ensure_ascii=False)
        kept = [a for a in actions if a.get("type") not in POSITION_ACTIONS]
        if kept:
            obj["board_actions"] = kept
        else:
            obj.pop("board_actions", None)
        for key in ("how_to_show", "on_board"):  # «already on the student's board» would be a lie
            obj.pop(key, None)
        obj["board_hint"] = BOARD_KEPT_NOTE
        return json.dumps(obj, ensure_ascii=False)

    if single:
        obj = {"board_actions": [obj]}
    obj["board_now"] = board_now_note(position_after(moving[-1]))
    return json.dumps(obj, ensure_ascii=False)
