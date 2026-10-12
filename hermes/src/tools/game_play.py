"""Tools: start_game, make_game_move — the game against the coach, asked for in words.

The game existed only behind the site's «Сыграть с тренером» button. Asked in words — «давай
сыграем», «спорим, я тебя обыграю» — the coach played by talking: «играю e5» with nothing on the
board and no engine, and a move typed in the chat during a game was talked about, not played
(chesster.io, text and voice alike; Alexander's voice game of 2026-10-10 lost a pawn to a FEN the
model wrote itself). Now both coaches start the same game (src/game_mode.py) and play the
student's move in it; the engine makes the coach's moves. The result carries a ``game`` board
action with the game's state, which the page shows the way it shows a game started by the button.
"""

import json
import logging
from typing import Optional

import chess
from tools.registry import registry

from src.board_protocol import GAME_ACTION

logger = logging.getLogger(__name__)

STRENGTHS = (600, 800, 1000, 1200, 1500, 1800, 2000, 2200, 2500)  # the site's GAME_STRENGTHS

START_GAME_SCHEMA = {
    "name": "start_game",
    "description": (
        "Start a game against the student on the board — the same game as the site's «Play the coach» "
        "button; an engine makes your moves at the chosen strength. Call it whenever the student wants to "
        "play a game with you, in any words. Never play a game by talking: no move of yours exists unless "
        "this tool or make_game_move returned it. The result says the student's colour, whose move it is "
        "and, when the student plays Black, the engine's first move."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "color": {"type": "string", "enum": ["white", "black", "random"],
                      "description": "The student's colour (default white)."},
            "elo": {"type": "integer", "description": "Engine strength, 600-2500 (default 1200)."},
            "said": {"type": "string", "description": "Leave empty (the site passes the student's words here)."},
        },
    },
}

MAKE_GAME_MOVE_SCHEMA = {
    "name": "make_game_move",
    "description": (
        "Play the student's move in the game on the board (they wrote or said it: «е4», «конь f3», "
        "«беру на d5», \"knight f3\"). Pass it in SAN (e4, Nf3, exd5, O-O, e8=Q). The result gives the "
        "verdict on the move and the engine's reply — tell the student that reply."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "move": {"type": "string", "description": "The student's move in SAN."},
            "said": {"type": "string", "description": "Leave empty (the site passes the student's words here)."},
        },
    },
}


def _strength(elo) -> int:
    try:
        n = int(elo)
    except (TypeError, ValueError):
        n = 1200
    return min(STRENGTHS, key=lambda s: abs(s - n))


def _session(kwargs: Optional[dict]):
    from src.sessions import session_store

    sid = (kwargs or {}).get("session_id")
    if not sid:
        return None
    try:
        return session_store.get(str(sid))
    except Exception:  # noqa: BLE001
        return None


def live_game_board(session):
    """The session's game in progress (a board of kind game, status playing), or None."""
    for board in reversed(getattr(session, "boards", None) or []):
        state = board.game_state or {}
        if board.kind == "game" and state.get("status") == "playing":
            return board
    return None


def _to_move(view: dict) -> str:
    if view.get("status") != "playing":
        return "the game is over"
    return "the student's move" if view.get("student_to_move") else "the engine's move"


def _reply(view: dict, summary: dict) -> str:
    return json.dumps({**summary, "fen": view.get("fen"), "to_move": _to_move(view),
                       "board_actions": [{"type": GAME_ACTION, "game": view}]}, ensure_ascii=False)


def _student_move(board: chess.Board, text: str) -> Optional[str]:
    """*text* as a legal move of *board* (SAN, UCI, Russian notation, words), in SAN; None if not one."""
    from src.move_matcher import named_moves
    from src.notation import russian_to_san

    raw = (text or "").strip()
    for candidate in (raw, raw.rstrip("+#!?"), russian_to_san(raw)):
        try:
            return board.san(board.parse_san(candidate))
        except ValueError:
            pass
        try:
            move = chess.Move.from_uci(candidate.replace("-", "").lower())
            if move in board.legal_moves:
                return board.san(move)
        except ValueError:
            pass
    found = named_moves(raw, board)
    return found[0]["san"] if len(found) == 1 else None


def _handle_start_game(args: dict, **kwargs) -> str:
    from src import game_mode

    session = _session(kwargs)
    if session is None:
        return json.dumps({"error": "No coach session to start the game in."})
    if kwargs.get("turn_game_step"):
        return json.dumps({"error": "The game of this turn is already started: tell the student whose move it is."})
    live = live_game_board(session)
    if live is not None:
        view = game_mode._payload(live, live.game_state, game_mode._replay(live.game_state["moves"]))
        return json.dumps({"error": "A game is already on: play the student's move with make_game_move.",
                           "fen": view["fen"], "to_move": _to_move(view)}, ensure_ascii=False)
    color = args.get("color") if args.get("color") in ("white", "black", "random") else "white"
    elo = args.get("elo")
    if args.get("said"):
        # The site's call with the student's words (voice): only when they ask for a game.
        from src.game_intent import game_request

        req = game_request(str(args["said"]))
        if req is None:
            return json.dumps({"error": "The student's words do not ask for a game."})
        color, elo = req["color"], req["elo"] or elo
    try:
        _, view = game_mode.start_game(session, color, _strength(elo), "quiet")
    except Exception as exc:  # noqa: BLE001 — the engine may be down
        logger.warning("start_game failed: %s", exc)
        return json.dumps({"error": f"The game could not start: {exc}"})
    engine = (view.get("engine") or {}).get("san")
    return _reply(view, {
        "ok": True,
        "student_color": view["student_color"],
        "engine_elo": view["engine_elo"],
        "engine_first_move": engine,
        "note": (f"The game is on. The engine opened with {engine}: tell the student, then wait for their move."
                 if engine else "The game is on and the student moves first: ask for their move."),
    })


def _handle_make_game_move(args: dict, **kwargs) -> str:
    from src import game_mode

    session = _session(kwargs)
    board_rec = live_game_board(session) if session is not None else None
    if board_rec is None:
        return json.dumps({"error": "No game is on: call start_game first."})
    if kwargs.get("turn_game_step"):
        # The server already played the move the student wrote this turn (src/server._game_prestep).
        return json.dumps({"error": "The student's move of this turn is already played: tell them the engine's reply."})
    board = game_mode._replay(board_rec.game_state["moves"])
    student_message = str(kwargs.get("student_message") or kwargs.get("utterance") or "")
    if student_message and not args.get("said"):
        from src.game_intent import _QUESTION, bare_move

        if _QUESTION.search(student_message) and bare_move(student_message, board) is None:
            # «А если Кf3?» was played as a move (stand, 2026-10-12): a question is answered, not played.
            return json.dumps({"error": "The student asked about a move, they did not play it: answer the question "
                                        "as a hint and do not play it — they play a move by writing it."})
    if args.get("said") and not args.get("move"):
        # The site's call with the student's words (voice): only a move said on its own is played.
        from src.game_intent import bare_move

        san = bare_move(str(args["said"]), board)
        if san is None:
            return json.dumps({"error": "The student's words are not a move to play."})
    else:
        san = _student_move(board, str(args.get("move") or ""))
    if san is None:
        legal = sorted(board.san(m) for m in board.legal_moves)
        return json.dumps({"error": f"{args.get('move')!r} is not a legal move here.", "legal_moves": legal[:40]},
                          ensure_ascii=False)
    try:
        view = game_mode.play_move(session, board_rec, san)
    except game_mode.GameError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        logger.warning("make_game_move failed: %s", exc)
        return json.dumps({"error": f"The move could not be played: {exc}"})
    student = view.get("student") or {}
    engine = (view.get("engine") or {}).get("san")
    summary = {
        "ok": True,
        "student_move": student.get("san"),
        "verdict": student.get("verdict"),
        "engine_reply": engine,
        "note": (f"Tell the student the engine's reply {engine}." if engine
                 else "The game is over: say the result." if view.get("status") != "playing" else ""),
    }
    if student.get("verdict") in ("mistake", "blunder") and student.get("best"):
        summary["better_was"] = student["best"]
    if view.get("status") != "playing":
        summary.update(game_over=True, result=view.get("result"), termination=view.get("termination"),
                       winner=view.get("winner"))
    return _reply(view, summary)


registry.register(
    name="start_game",
    toolset="chess",
    schema=START_GAME_SCHEMA,
    handler=_handle_start_game,
    description="Start a game against the student on the board (the engine plays the coach's moves).",
    emoji="♟️",
)

registry.register(
    name="make_game_move",
    toolset="chess",
    schema=MAKE_GAME_MOVE_SCHEMA,
    handler=_handle_make_game_move,
    description="Play the student's move in the game on the board; returns the engine's reply.",
    emoji="♟️",
)
