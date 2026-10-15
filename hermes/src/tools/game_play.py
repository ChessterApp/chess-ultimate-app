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
import re
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
    """*text* as a legal move of *board* (any notation or words, src/move_text.py), in SAN; None if not one."""
    from src.move_text import one_move

    return one_move(text, board)


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


def _refused(error: str, **extra) -> str:
    """A move not played, said so the model cannot take it for one: after «система почему-то не принимает ход»
    the voice coach drew an arrow, «будем считать, что слон c4 сыграно», and answered «конь на c6» — a move of
    its own the engine never made (voice, 2026-10-14)."""
    return json.dumps({"error": error, **extra,
                       "board": "Nothing was played and the game did not change. Never say the move was played, "
                                "never draw it as if it were, and never answer with a move of yours — the engine "
                                "makes your moves only through make_game_move."}, ensure_ascii=False)


def _handle_make_game_move(args: dict, **kwargs) -> str:
    from src import game_mode

    session = _session(kwargs)
    board_rec = live_game_board(session) if session is not None else None
    if board_rec is None:
        return _refused("No game is on: call start_game first.")
    if kwargs.get("turn_game_step"):
        # The server already played the move the student wrote this turn (src/server._game_prestep).
        return json.dumps({"error": "The student's move of this turn is already played: tell them the engine's reply."})
    board = game_mode._replay(board_rec.game_state["moves"])
    student_message = str(kwargs.get("student_message") or kwargs.get("utterance") or "")
    if student_message and not args.get("said"):
        from src.game_intent import is_idea

        if is_idea(student_message):
            # «А если Кf3?» was played as a move (stand, 2026-10-12): an idea is answered, not played. Only an
            # «if» makes it one — «Хорошо, слон c4» and «Слон c4?» are moves (voice, 2026-10-14).
            return _refused("The student asked what a move would do, they did not play it: answer as a hint. "
                            "They play a move by saying or writing it on its own.")
    if args.get("said") and not args.get("move"):
        # The site's call with the student's words (voice): only a move said on its own is played.
        from src.game_intent import bare_move

        san = bare_move(str(args["said"]), board)
        if san is None:
            return _refused("The student's words are not a move to play.")
    else:
        san = _student_move(board, str(args.get("move") or ""))
    if san is None:
        legal = sorted(board.san(m) for m in board.legal_moves)
        return _refused(f"{args.get('move')!r} is not a legal move here.", legal_moves=legal[:40])
    try:
        view = game_mode.play_move(session, board_rec, san)
    except game_mode.GameError as exc:
        return _refused(str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("make_game_move failed: %s", exc)
        return _refused(f"The move could not be played: {exc}")
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


def game_command_step(session, board_rec, command: str, words: str = "") -> Optional[dict]:
    """Resign / take back / draw / a new game, asked for in words: done here as the game's buttons do it
    (src/game_mode.py), and the model is told what happened. {"view", "block"}. A new game takes the colour
    and strength named in *words* («сыграем ещё раз чёрными»), else the last game's."""
    from src import game_mode
    from src.game_intent import game_wish

    state = board_rec.game_state or {}
    try:
        if command == "resign":
            view = game_mode.resign(session, board_rec)
            return {"view": view, "block": (
                "## The student resigned — the system ended the game\n"
                f"Result {view.get('result')} (resignation). Say the game is over in one kind sentence, without "
                "talking them out of it, and offer to review it or to play again."
            )}
        if command == "takeback":
            view = game_mode.takeback(session, board_rec)
            return {"view": view, "block": (
                "## The student's last move was taken back (the system did it)\n"
                f"Their move and the engine's reply to it are undone; the position is {view.get('fen')} and it is "
                "the student's move again. Say it in one sentence and let them move."
            )}
        if command == "draw":
            accepted, cp = game_mode.draw_decision(board_rec)
            if accepted:
                view = game_mode.agree_draw(session, board_rec)
                return {"view": view, "block": (
                    "## The student offered a draw and the engine accepted — the game is over, ½–½\n"
                    "Say the draw is agreed and offer a review or a new game."
                )}
            why = ("it is too early — the game has barely begun" if len(state.get("moves") or []) < game_mode.DRAW_MIN_PLIES
                   else f"the engine judges its position better ({cp / 100:+.1f} for it)")
            return {"view": None, "block": (
                "## The student offered a draw — the engine declined, the game goes on\n"
                f"Declined because {why}. Say so honestly in a sentence; the game is still on and it is their move."
            )}
        if command == "restart":
            # The site offers «New game» only once a game is over: a game still on is resigned first, so two
            # games are never on at once (the old one would come back as «the game» after the new one ends).
            abandoned = state.get("status") == "playing"
            if abandoned:
                game_mode.resign(session, board_rec)
            wish = game_wish(words)
            _, view = game_mode.start_game(session, wish.get("color") or state.get("student_color") or "white",
                                           _strength(wish.get("elo") or state.get("engine_elo") or 1200),
                                           state.get("comment_mode") or "quiet")
            engine = (view.get("engine") or {}).get("san")
            return {"view": view, "block": (
                "## A new game has started on the board (the system started it)\n"
                + ("The previous game was still on: it is counted as resigned. " if abandoned else "")
                + f"The student plays {view['student_color']} again, the engine about {view['engine_elo']} Elo. "
                + (f"The engine opened with {engine}. " if engine else "The student moves first. ")
                + "Tell them it is on and whose move it is."
            )}
    except game_mode.GameError as exc:
        return {"view": None, "block": f"## The game could not do that: {exc}\nSay so plainly in one sentence."}
    return None


GAME_ACTION_SCHEMA = {
    "name": "game_action",
    "description": (
        "Do what the game's buttons do, when the student asks for it in words during a game: resign («сдаюсь»), "
        "take back their last move («верни ход»), offer a draw («предлагаю ничью» — the engine decides) or start a "
        "new game («давай заново»). Never pretend: no game ends, no move is undone and no new game starts unless "
        "this tool did it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["resign", "takeback", "draw", "restart"]},
            "said": {"type": "string", "description": "Leave empty (the site passes the student's words here)."},
        },
    },
}


def _handle_game_action(args: dict, **kwargs) -> str:
    from src.game_intent import game_command
    session = _session(kwargs)
    if session is None:
        return json.dumps({"error": "No coach session."})
    if kwargs.get("turn_game_step"):
        return json.dumps({"error": "The game already did what the student asked this turn: tell them."})
    action = args.get("action")
    if args.get("said"):
        # The site's call with the student's words (voice): only words that ask for it.
        action = game_command(str(args["said"]))
        if action is None:
            return json.dumps({"error": "The student's words do not ask the game for anything."})
    if action not in ("resign", "takeback", "draw", "restart"):
        return json.dumps({"error": "action must be resign, takeback, draw or restart."})
    board_rec = live_game_board(session)
    if board_rec is None and action == "restart":
        board_rec = next((b for b in reversed(session.boards or []) if b.kind == "game" and b.game_state), None)
    if board_rec is None:
        return json.dumps({"error": "No game is on: start_game starts one."})
    step = game_command_step(session, board_rec, action, str(args.get("said") or ""))
    if not step:
        return json.dumps({"error": "Nothing was done."})
    note = step["block"].split("\n", 1)[-1]
    if step.get("view") is None:
        return json.dumps({"ok": action == "draw", "action": action, "done": False, "note": note}, ensure_ascii=False)
    return _reply(step["view"], {"ok": True, "action": action, "done": True, "note": note})


registry.register(
    name="game_action",
    toolset="chess",
    schema=GAME_ACTION_SCHEMA,
    handler=_handle_game_action,
    description="Resign, take back, offer a draw or start a new game — the game's buttons, in words.",
    emoji="♟️",
)

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
