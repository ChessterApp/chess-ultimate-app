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
import time
from typing import Optional

import chess
from tools.registry import registry

from src.board_protocol import GAME_ACTION

logger = logging.getLogger(__name__)

from src.game_intent import STRENGTHS  # the site's GAME_STRENGTHS, one list (src/game_intent.py)

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
            "view_ply": {"type": "integer", "description": "Leave empty (the site passes the earlier position the student is looking at)."},
            "view_line": {"type": "array", "items": {"type": "string"}, "description": "Leave empty (the site passes a side line on the board)."},
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
    from src.session_persistence import SessionLoadError

    try:
        return session_store.get(str(sid))
    except SessionLoadError:
        raise  # the game is unknown, not absent: never "no session" (28.10)
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


def _as_move(board: chess.Board, san: Optional[str]) -> Optional[chess.Move]:
    try:
        return board.parse_san(san) if san else None
    except ValueError:
        return None


def _already_played(board_rec, text: str, parse) -> bool:
    from src import game_mode

    return game_mode._just_played(board_rec.game_state or {}, text, parse=parse) is not None


def _already_played_reply(board_rec, text: str, parse) -> str:
    """The first call's result again: the student's move as played and the engine's reply to it."""
    from src import game_mode

    state = board_rec.game_state or {}
    student, engine = game_mode._just_played(state, text, parse=parse)
    board = game_mode._replay(state.get("moves") or [])
    view = game_mode._payload(board_rec, state, board, student=student, engine=engine)
    reply = (engine or {}).get("san")
    words = (engine or {}).get("words") or (game_mode.ply_words(state, len(state.get("moves") or [])) if reply else None)
    return _reply(view, {
        "ok": True, "already_played": True, "student_move": student.get("san"), "verdict": student.get("verdict"),
        "engine_reply": reply, "engine_reply_words": words,
        "note": "This move was already played a moment ago; nothing changed now. "
                + (f"Tell the student the engine's reply {game_mode.told_ply(state, len(state.get('moves') or []))}."
                   if reply and game_mode.told_ply(state, len(state.get("moves") or []))
                   else f"Tell the student the engine's reply {reply} ({words})." if reply and words
                   else f"Tell the student the engine's reply {reply}." if reply
                   else "Wait for the engine's reply." if view.get("status") == "playing"
                   else "The game is over: say the result."),
    })


def _opened_with(state: dict, engine: Optional[str]) -> str:
    """«The engine opened with Nf3 (knight from g1 to f3): …» — its first move in words, as each reply is (28.10)."""
    from src import game_mode

    words = game_mode.ply_words(state, 1) if engine else None
    return f"The engine opened with {engine}" + (f" ({words})" if words else "")


def _record_start(session, view: dict, heard: str) -> None:
    """What started the game: the same words again a moment later are the same request (game_command_step)."""
    board_rec = session.get_board(view.get("board_id")) if view.get("board_id") else None
    if board_rec is not None and board_rec.game_state is not None:
        board_rec.game_state["started_by"] = {"words": _norm_words(heard), "at": time.time()}
        session.save_board(board_rec)


def _handle_start_game(args: dict, **kwargs) -> str:
    from src import game_mode

    session = _session(kwargs)
    if session is None:
        return json.dumps({"error": "No coach session to start the game in."})
    if kwargs.get("turn_game_step"):
        return json.dumps({"error": "The game of this turn is already started: tell the student whose move it is."})
    live = live_game_board(session)
    color = args.get("color") if args.get("color") in ("white", "black", "random") else "white"
    elo = args.get("elo")
    words = str(args.get("said") or "")
    heard = words or str(kwargs.get("student_message") or kwargs.get("utterance") or "")
    if words:
        # The site's call with the student's words (voice): only when they ask for a game.
        from src.game_intent import game_request

        req = game_request(words)
        if req is None:
            from src.game_intent import game_command

            if game_command(words) == "restart":
                if kwargs.get("caller") == "site":
                    # The site's own call (its fallback when voice/intent did not answer: «сыграем по новой» after a
                    # game): the game's «New game», with what the page's [Game] note tells (the colour, the first move).
                    # Only the page marks its calls — the model may pass `said` alone too (review 29.10).
                    out = json.loads(_handle_game_action({"said": words}, **kwargs))
                    now = live_game_board(session)
                    if out.get("ok") and now is not None:
                        ns = now.game_state or {}
                        engine = (ns.get("moves") or [None])[0] if ns.get("student_color") == "black" else None
                        out.update({"student_color": ns.get("student_color"), "engine_elo": ns.get("engine_elo"),
                                    "engine_first_move": engine,
                                    "engine_first_move_words": game_mode.ply_words(ns, 1) if engine else None})
                    return json.dumps(out, ensure_ascii=False)
                # The model's call with «Нет, давай лучше заново, я чёрными»: in voice the site restarts the game for these
                # words itself (voice/intent → game_action), so start_game does not — no second restart. Refused as «not a
                # game request», the coach said «партия уже началась, может продолжишь за белых?» over the new game as
                # Black (prod Live run 29.10). Where no site call comes (text, no intent), game_action does it.
                return json.dumps({"error": "Not done by start_game: these words ask for a NEW game. If a [Game] note says the "
                                            "new game has started, tell the student exactly what it says. Otherwise call "
                                            "game_action with action 'restart' — it starts the new game with the colour the "
                                            "student named. Never say the old game goes on."}, ensure_ascii=False)
            return json.dumps({"error": "The student's words do not ask for a game."})
        color, elo = req["color"], req["elo"] or elo
        asked_color, asked_elo = req["color"], req["elo"]
    else:
        # The model's own call: the colour and strength the student named win over its arguments (prod Live run
        # 28.10: «я белыми» came as color=black, and the site's call for the same words then restarted the game).
        from src.game_intent import game_wish

        named = game_wish(heard)
        color, elo = named.get("color") or color, named.get("elo") or elo
        asked_color, asked_elo = named.get("color") or args.get("color"), named.get("elo") or args.get("elo")
    if live is not None:
        state = live.game_state or {}
        same_game = ((not asked_color or asked_color == "random" or asked_color == state.get("student_color"))
                     and (asked_elo is None or _strength(asked_elo) == state.get("engine_elo")))
        fresh = (same_game and not state.get("annotations") and state.get("status") == "playing"
                 and time.time() - float(state.get("started_at") or 0) < game_mode.SAME_START_WINDOW_S)
        if fresh:
            # The game just started and nobody has moved: a second start for the same request (the site's
            # call and the model's, voice 2026-10-23) is the same game, not a restart.
            board = game_mode._replay(state.get("moves") or [])
            view = game_mode._payload(live, state, board)
            engine = (state.get("moves") or [None])[0] if state.get("student_color") == "black" else None
            return _reply(view, {
                "ok": True, "already_started": True,
                "student_color": view["student_color"], "engine_elo": view["engine_elo"], "engine_first_move": engine,
                "engine_first_move_words": game_mode.ply_words(state, 1) if engine else None,
                "note": "The game is already on (it was started a moment ago for this very request). "
                        + (f"{_opened_with(state, engine)}: tell the student, naming exactly that piece, then wait "
                           "for their move." if engine else "The student moves first: ask for their move.") + " " + game_mode.NO_MOVE_TIP,
            })
        # A new game asked for while one is on («хочу сыграть партию с самым сильным ботом 2500», voice
        # 2026-10-15: the answer was «A game is already on» and the model improvised «давай перезапустим»): the
        # old game is resigned and the new one starts with the named colour and strength, as «New game» does.
        wish = {k: v for k, v in (("color", asked_color), ("elo", elo)) if v} if not words else None
        step = game_command_step(session, live, "restart", words, wish=wish)
        if not step or not step.get("view"):
            return json.dumps({"error": (step or {}).get("block", "The game could not restart.")})
        view = step["view"]
        _record_start(session, view, heard)
        engine = (view.get("engine") or {}).get("san")
        new_state = {"moves": view.get("moves") or []}
        return _reply(view, {
            "ok": True, "restarted": True,
            "student_color": view["student_color"], "engine_elo": view["engine_elo"], "engine_first_move": engine,
            "engine_first_move_words": game_mode.ply_words(new_state, 1) if engine else None,
            "note": "The previous game was still on: it is counted as resigned and a new game has started. "
                    + (f"{_opened_with(new_state, engine)}: tell the student, naming exactly that piece, then wait "
                       "for their move." if engine else "The student moves first: say the new game is on and ask for their move.")
                    + " " + game_mode.NO_MOVE_TIP,
        })
    try:
        _, view = game_mode.start_game(session, color, _strength(elo), "quiet")
    except Exception as exc:  # noqa: BLE001 — the engine may be down
        logger.warning("start_game failed: %s", exc)
        return json.dumps({"error": f"The game could not start: {exc}"})
    _record_start(session, view, heard)
    engine = (view.get("engine") or {}).get("san")
    new_state = {"moves": view.get("moves") or []}
    return _reply(view, {
        "ok": True,
        "student_color": view["student_color"],
        "engine_elo": view["engine_elo"],
        "engine_first_move": engine,
        "engine_first_move_words": game_mode.ply_words(new_state, 1) if engine else None,
        "note": (f"The game is on. {_opened_with(new_state, engine)}: tell the student, naming exactly that piece, "
                 "then wait for their move." if engine else "The game is on and the student moves first: ask for their move.")
                + " " + game_mode.NO_MOVE_TIP,
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
    view_ply = args.get("view_ply")
    if (isinstance(args.get("view_line"), list) and args.get("view_line")) or (
            isinstance(view_ply, (int, float)) and int(view_ply) < len(board_rec.game_state.get("moves") or [])):
        # The board shows another position (an earlier ply or a side line): a move said now is not played in the live
        # game (audit 26.10: the Live mode played it). Ask whether to continue from there or go back.
        return _refused("The board shows an EARLIER position (or a side line) of the game, not the live one: nothing was played. "
                        "Ask whether to continue the game from the shown position («продолжим отсюда») or go back to the game.")
    try:
        game_mode.repair_game(session, board_rec)  # a record broken before the lock (23.10): mended, never raised on
    except Exception:  # noqa: BLE001
        logger.warning("game repair failed", exc_info=True)
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

        text = str(args["said"])
        san = bare_move(text, board)
        if san is None and _already_played(board_rec, text, lambda b, t: _as_move(b, bare_move(t, b))):
            return _already_played_reply(board_rec, text, lambda b, t: _as_move(b, bare_move(t, b)))
        if san is None:
            return _refused("The student's words are not a move to play.")
    else:
        text = str(args.get("move") or "")
        san = _student_move(board, text)
    if san is None:
        # The move is not legal NOW — but it may be the one just played, asked for a second time (the site's
        # call and the model's for one «e4», voice 23.10): then the first call's result, never a refusal that
        # the model turns into «твой ход не прошёл».
        if _already_played(board_rec, text, lambda b, t: _as_move(b, _student_move(b, t))):
            return _already_played_reply(board_rec, text, lambda b, t: _as_move(b, _student_move(b, t)))
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
    # the piece and squares in words: from a bare «c6» the voice coach said «мой конь на c6» (prod Live run 28.10)
    words = (view.get("engine") or {}).get("words")
    told = (game_mode.told_ply(view, len(view.get("moves") or [])) if engine else None) or (
        f"{engine} ({words})" if engine and words else engine)
    summary = {
        "ok": True,
        "student_move": student.get("san"),
        "verdict": student.get("verdict"),
        "engine_reply": engine,
        "engine_reply_words": words,
        "note": (f"Tell the student the engine's reply {told}." if engine
                 else "The game is over: say the result." if view.get("status") != "playing" else ""),
    }
    if view.get("already_played"):
        # The same move came twice (the site's call and the model's for one «e4»): the first one played it.
        summary["already_played"] = True
        summary["note"] = (f"This move was already played a moment ago; nothing changed now. "
                           + (f"Tell the student the engine's reply {told}." if engine
                              else "Wait for the engine's reply." if view.get("status") == "playing"
                              else "The game is over: say the result."))
    if student.get("verdict") in ("mistake", "blunder") and student.get("best"):
        summary["better_was"] = student["best"]
    if view.get("status") != "playing":
        summary.update(game_over=True, result=view.get("result"), termination=view.get("termination"),
                       winner=view.get("winner"))
    return _reply(view, summary)


# A takeback asked for once arrives twice in the voice game: the model's own game_action call and the site's
# (Alexander, 26.10: «попросил вернуть ход, он вернул сразу 2»). The second one within this window, with the
# record unchanged since the first, gets the first result again — like already_played for a move.
SAME_TAKEBACK_WINDOW_S = 12.0
# The undo commands are one family for that guard: the site may read «ты ошибся» as mistake while the model calls
# takeback for the same words (audit 26.10).
UNDO_FAMILY = frozenset({"takeback", "mistake", "correct"})
# The commands that act on a finished game still on the board (a takeback reopens it) — audit 26.10.
POST_GAME_COMMANDS = frozenset({"takeback", "mistake", "correct", "continue_here", "view", "view_live"})


def last_game_board(session):
    """The session's latest game board (playing or finished), or None."""
    return next((b for b in reversed(getattr(session, "boards", None) or []) if b.kind == "game" and b.game_state), None)


def _norm_words(words: str) -> str:
    return re.sub(r"[^\w]+", " ", (words or "").lower().replace("ё", "е")).strip()


def _just_taken_back(state: dict, command: str, words: str = "") -> bool:
    """The same undo request again (the model's call and the site's, a few seconds apart): same family, the record
    unchanged since, and the same words — or no words on one side. Different words are a NEW request («верни ещё
    ход»), done even inside the window (audit 26.10: a real second takeback was swallowed)."""
    last = state.get("last_takeback") or {}
    if command not in UNDO_FAMILY or last.get("command") not in UNDO_FAMILY:
        return False
    if time.time() - float(last.get("at") or 0) >= SAME_TAKEBACK_WINDOW_S:
        return False
    if len(state.get("moves") or []) != int(last.get("plies_after", -1)):
        return False
    a, b = _norm_words(words), _norm_words(last.get("words") or "")
    return not a or not b or a == b


def _remember_undo(session, board_rec, command: str, words: str, view: dict) -> None:
    board_rec.game_state["last_takeback"] = {"command": command, "at": time.time(), "words": words or "",
                                             "plies_after": len(view.get("moves") or [])}
    session.save_board(board_rec)


def game_command_step(session, board_rec, command: str, words: str = "", wish: Optional[dict] = None,
                      view_ply: Optional[int] = None, view_line: Optional[list] = None) -> Optional[dict]:
    """Resign / take back / draw / a new game / the engine's strength, asked for in words: done here as the
    game's buttons do it (src/game_mode.py), and the model is told what happened. {"view", "block"}. A new game
    takes the colour and strength named in *words* («сыграем ещё раз чёрными, посложнее»), else *wish* (the
    model's start_game arguments), else the last game's."""
    from src import game_mode
    from src.game_intent import game_wish, strength_in_words

    state = board_rec.game_state or {}
    try:
        if command == "level":
            elo = strength_in_words(words, state.get("engine_elo"))
            if elo is None:
                return {"view": None, "block": (
                    "## The student asked for a different strength but named no level — nothing changed\n"
                    "Ask which level they want: a number from 600 to 2500, or «посложнее» / «полегче»."
                )}
            view = game_mode.set_strength(session, board_rec, _strength(elo))
            return {"view": view, "block": (
                "## The engine's strength was changed (the system did it)\n"
                f"From its next move the engine plays at about {view['engine_elo']} Elo; the game goes on from the "
                "same position and it is " + ("the student's move. " if view.get("student_to_move") else
                                              "the engine's move. ")
                + "Say the new level in one sentence; the student plays on."
            )}
        if command == "resign":
            view = game_mode.resign(session, board_rec)
            return {"view": view, "block": (
                "## The student resigned — the system ended the game\n"
                f"Result {view.get('result')} (resignation). Say the game is over in one kind sentence, without "
                "talking them out of it, and offer to review it or to play again."
            )}
        if command in UNDO_FAMILY and _just_taken_back(state, command, words):
            board = game_mode._replay(state.get("moves") or [])
            view = game_mode._payload(board_rec, state, board)
            view["already_done"] = True
            return {"view": view, "block": (
                "## The takeback was already done a moment ago (this is the same request again)\n"
                f"Nothing more was undone. The record: {game_mode._moves_text(view.get('moves') or []) or 'the start'}; "
                f"the position is {view.get('fen')}; it is " + ("the student's move." if view.get("student_to_move") else "the engine's move.")
                + " Say the position once and let them move."
            )}
        if command == "coach_move":
            # «Ты не так сходил», «твой ход не тот»: the student objects to the ENGINE's move, not theirs (audit 26.10:
            # it undid the student's move and made the coach apologise for it). The engine's move is a real move of
            # the game; nothing is undone unless they ask «верни ход».
            moves = state.get("moves") or []
            board_now = game_mode._replay(moves)
            last_engine = None
            if moves and not game_mode._student_to_move(state, game_mode._replay(moves[:-1])):
                last_engine = moves[-1]
            return {"view": None, "block": (
                "## The student objects to the engine's (your) last move — nothing was changed\n"
                f"The engine's last move was {last_engine or 'none yet'}; the record is "
                f"{game_mode._moves_text(moves) or 'the start'}, FEN {board_now.fen()}. Say plainly which move you (the engine) "
                "made, on which squares, and that it is a legal move of the game; if they think it was a misreading of "
                "THEIR move, offer «верни ход». Do not apologise for a move that was played correctly."
            )}
        if command == "correct":
            # «Я хотел не конь c6, а c6 пешкой»: the move just played goes back and the one they meant is played.
            from src.game_intent import correction_move

            plies = [a.get("ply") for a in state.get("annotations") or []]
            if not plies:
                return {"view": None, "block": ("## The student corrects a move, but they have not moved yet — nothing to correct\n"
                                                "Ask them to say the move they want to play.")}
            before = game_mode._replay((state.get("moves") or [])[: int(plies[-1]) - 1])
            san = correction_move(words, before)
            if san is None:
                return {"view": None, "block": (
                    "## The student says they meant another move, but which one was not understood — nothing changed\n"
                    f"Their words: «{words.strip()}». Ask them to name the move plainly («пешка c6», «конь f3»); their "
                    "last move stays on the board until then. Never say a move was played.")}
            game_mode.takeback_moves(session, board_rec, 1)
            view = game_mode.play_move(session, board_rec, san)
            engine = (view.get("engine") or {}).get("san")
            _remember_undo(session, board_rec, "correct", words, view)
            n = len(view.get("moves") or [])
            return {"view": view, "block": (
                "## The student's last move was replaced by the one they meant (the system did it)\n"
                f"Their previous move and the engine's reply are undone; {game_mode.told_ply(view, n - 1 if engine else n) or san} "
                "is played instead"
                + (f" and the engine answered {game_mode.told_ply(view, n) or engine}, naming exactly that piece" if engine else "")
                + ". Say it in one sentence"
                + (" and let them move." if view.get("student_to_move") else ".")
            )}
        if command == "takeback":
            # «Верни ход», «верни партию на два хода назад», «до того как я сходил конём», «до 10-го хода»
            # (Alexander's list, 26.10, item 2): the record is cut back to the place the words name.
            from src.game_intent import cut_target

            target = cut_target(words, state)
            moves_before = list(state.get("moves") or [])
            cut_at = max(0, min(int(target["ply"]), len(moves_before)))
            gone = moves_before[cut_at:]
            view = game_mode.truncate(session, board_rec, target["ply"])
            if not gone and not view.get("engine"):
                return {"view": None, "block": (
                    "## Nothing to take back — the game is at its start\n"
                    "Say so in one sentence and let the student move."
                )}
            engine = (view.get("engine") or {}).get("san")
            kept = game_mode._moves_text(view.get("moves") or []) or "the start"
            _remember_undo(session, board_rec, "takeback", words, view)
            return {"view": view, "block": (
                "## The game was taken back (the system did it)\n"
                f"Cut to {target['why']}. UNDONE, exactly these moves: {game_mode.numbered_from(gone, cut_at) or 'none'}. "
                f"The record now: {kept}; the position is {view.get('fen')}"
                + (f"; the engine then moved {engine}" if engine else "")
                + ("; it is the student's move." if view.get("student_to_move") else ".")
                + " Say in one sentence which moves were undone — name them as listed, never other moves — and let them move."
            )}
        if command == "mistake":
            # «Ты ошибся», «это не мой ход», «верни как было» (item 5): the system misread the move or moved wrong —
            # the student's last move and the reply are undone, and they are asked what they meant.
            try:
                view = game_mode.takeback_moves(session, board_rec, 1)
            except game_mode.GameError:
                return {"view": None, "block": (
                    "## The student says something went wrong on the board, but no move of theirs is recorded\n"
                    "Nothing changed. Apologise in a word and ask them to say the move they want."
                )}
            _remember_undo(session, board_rec, "mistake", words, view)
            return {"view": view, "block": (
                "## The student says the last move was not what they meant — it is undone (the system did it)\n"
                f"Their last move and the engine's reply are taken back; the position is {view.get('fen')} and it is "
                "the student's move. Apologise in a word, say the move is undone, and ask which move they want — "
                "the piece and the square. Never argue that the move was right."
            )}
        if command == "continue_here" and view_line:
            # «Продолжим отсюда» on a side line (item 4): the side line becomes the game, the old continuation is kept.
            view = game_mode.continue_from_line(session, board_rec, [str(m) for m in view_line])
            engine = (view.get("engine") or {}).get("san")
            return {"view": view, "block": (
                "## The game now continues from the SIDE LINE the student was looking at (the system made it the main line)\n"
                f"The record now: {game_mode._moves_text(view.get('moves') or [])}; the old continuation is kept in the notation"
                + (f"; the engine moved {engine} from there — say this move aloud in words" if engine else "")
                + ("; it is the student's move." if view.get("student_to_move") else ".")
                + " Say it in one sentence and let them move."
            )}
        if command == "continue_here":
            # «Продолжим отсюда» while looking at an earlier position (item 4): the record is cut there and the game
            # goes on; with the live position on the board there is nothing to do.
            moves = state.get("moves") or []
            if view_ply is None or int(view_ply) >= len(moves):
                return {"view": None, "block": (
                    "## The student asks to continue from here, but the board already shows the game's latest position\n"
                    "Nothing changed. Say the game is at its current position and whose move it is"
                    + (" (the student's)." if game_mode._student_to_move(state, game_mode._replay(moves)) else " (the engine's).")
                )}
            view = game_mode.truncate(session, board_rec, int(view_ply))
            engine = (view.get("engine") or {}).get("san")
            return {"view": view, "block": (
                "## The game now continues from the position the student was looking at (the system cut the record there)\n"
                f"The moves after ply {int(view_ply)} are gone; the position is {view.get('fen')}"
                + (f"; the engine moved {engine} from there — say this move aloud in words" if engine else "")
                + ("; it is the student's move." if view.get("student_to_move") else ".")
                + " Say it in one sentence and let them move."
            )}
        if command in ("view", "view_live"):
            # «Покажи позицию после 10-го хода», «вернись к партии» (items 4 and 8): the board shows an earlier
            # position, or the live one again; the game itself does not change.
            from src.game_intent import view_target

            moves = state.get("moves") or []
            if command == "view_live":
                return {"view": None, "actions": [{"type": "game_view", "board_id": board_rec.id, "ply": None}], "block": (
                    "## The board shows the game's latest position again (the system did it)\n"
                    f"Ply {len(moves)}; it is " + ("the student's move." if game_mode._student_to_move(state, game_mode._replay(moves))
                                                     else "the engine's move.") + " Say so in a few words."
                )}
            target = view_target(words, state)
            ply = max(0, min(int(target["ply"]), len(moves)))
            shown = game_mode.position_at(state, ply)
            return {"view": None, "actions": [{"type": "game_view", "board_id": board_rec.id, "ply": ply, "fen": shown.fen()}], "block": (
                "## The board now shows an EARLIER position of the game (the system did it); the game itself goes on\n"
                f"Shown: {target['why']} — the position after ply {ply} ({game_mode._moves_text(moves[:ply]) or 'the start'}), "
                f"FEN {shown.fen()}, {'White' if shown.turn else 'Black'} to move there. The game stands at ply {len(moves)} and "
                "continues from its live position unless the student says «продолжим отсюда». Describe or answer about the "
                "shown position in a sentence or two; nothing is played by talking."
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
            # The same request again (the site's call and the model's, seconds apart): the game just started, no
            # student move yet, and the words name nothing different — it stays (audit 26.10: doubled restarts).
            # Every start records its words — the model's start_game too (prod Live run 28.10: it recorded none, so the
            # site's call for the same words a second later restarted the game, 1.e4 became 1.Nf3, and the coach
            # announced e4). Other words («давай лучше заново») are a new request even inside the window.
            wish_now = {**dict(wish or {}), **(game_wish(words, state.get("engine_elo")) if words else {})}
            started_by = state.get("started_by") or {}
            fresh = (state.get("status") == "playing" and not state.get("annotations")
                     and time.time() - float(started_by.get("at") or 0) < game_mode.SAME_START_WINDOW_S
                     and (not _norm_words(words) or _norm_words(words) == started_by.get("words"))
                     and (not wish_now.get("color") or wish_now.get("color") in ("random", state.get("student_color")))
                     and (not wish_now.get("elo") or _strength(wish_now["elo"]) == state.get("engine_elo")))
            if fresh:
                board_now = game_mode._replay(state.get("moves") or [])
                view = game_mode._payload(board_rec, state, board_now)
                view["already_started"] = True
                engine = (state.get("moves") or [None])[0] if state.get("student_color") == "black" else None
                return {"view": view, "block": (
                    "## The new game was already started a moment ago (this is the same request again)\n"
                    "It is already on; nothing changed now. "
                    f"The student plays {state.get('student_color')}. "
                    + (f"{_opened_with(state, engine)} — if you named its first move, it must be exactly this one. "
                       if engine else "")
                    + ("It is their move." if view.get("student_to_move") else "It is the engine's move.")
                    + " Say it once."
                )}
            # The site offers «New game» only once a game is over: a game still on is resigned first, so two
            # games are never on at once (the old one would come back as «the game» after the new one ends).
            abandoned = state.get("status") == "playing"
            if abandoned:
                game_mode.resign(session, board_rec)
            wish = wish_now
            new_board, view = game_mode.start_game(session, wish.get("color") or state.get("student_color") or "white",
                                                   _strength(wish.get("elo") or state.get("engine_elo") or 1200),
                                                   state.get("comment_mode") or "quiet")
            # what started it: the same words again a moment later are the same request (the dedupe above)
            if getattr(new_board, "game_state", None) is not None:
                new_board.game_state["started_by"] = {"words": _norm_words(words), "at": time.time()}
                session.save_board(new_board)
            engine = (view.get("engine") or {}).get("san")
            return {"view": view, "block": (
                "## A new game has started on the board (the system started it)\n"
                + ("The previous game was still on: it is counted as resigned. " if abandoned else "")
                + f"The student plays {view['student_color']} again, the engine about {view['engine_elo']} Elo. "
                + (f"{_opened_with({'moves': view.get('moves') or []}, engine)}: say this move aloud in words, naming "
                   "exactly that piece and square. " if engine else "The student moves first. ")
                + "Tell them it is on and whose move it is. " + game_mode.NO_MOVE_TIP
            )}
    except game_mode.GameError as exc:
        return {"view": None, "block": f"## The game could not do that: {exc}\nSay so plainly in one sentence."}
    return None


GAME_ACTION_SCHEMA = {
    "name": "game_action",
    "description": (
        "Do what the game's buttons do, when the student asks for it in words during a game: resign («сдаюсь»), "
        "take back their last move («верни ход»), offer a draw («предлагаю ничью» — the engine decides), start a "
        "new game («давай заново») or change the engine's strength for the rest of the game («играй посложнее», "
        "«уровень 2000» — pass their words in said). Never pretend: no game ends, no move is undone, no new game "
        "starts and no level changes unless this tool did it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["resign", "takeback", "draw", "restart", "level", "correct", "mistake", "continue_here", "view", "view_live", "coach_move"]},
            "view_line": {"type": "array", "items": {"type": "string"}, "description": "The side line on the board (moves from the start), when one is shown."},
            "view_ply": {"type": "integer", "description": "The ply of the game's position the student is looking at, when it is not the live one (continue_here)."},
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
    words = str(args.get("said") or kwargs.get("student_message") or kwargs.get("utterance") or "")
    if not args.get("said") and words:
        # The model's own call: the student's words decide what is meant and how much (audit 26.10: the model's bare
        # «takeback» undid one move where the words said two, and its later call was then swallowed by the guard).
        meant = game_command(words)
        if meant in POST_GAME_COMMANDS and (action in POST_GAME_COMMANDS or action is None):
            action = meant
    if args.get("said"):
        # The site's call with the student's words (voice): only words that ask for it. Words that ask for
        # a game while one is on («давай сыграем, играй как гроссмейстер») are the game's «New game», as
        # the text coach and src/intent.py read them — not a level change the same words also name.
        from src.game_intent import game_request

        action = game_command(str(args["said"]))
        if game_request(str(args["said"])) and live_game_board(session) is not None:
            action = "restart"
        if action is None:
            return json.dumps({"error": "The student's words do not ask the game for anything."})
    if action not in ("resign", "takeback", "draw", "restart", "level", "correct", "mistake", "continue_here", "view", "view_live", "coach_move"):
        return json.dumps({"error": "action must be resign, takeback, draw, restart, level, correct, mistake, continue_here, view, view_live or coach_move."})
    board_rec = live_game_board(session)
    if board_rec is None and (action == "restart" or action in POST_GAME_COMMANDS):
        board_rec = last_game_board(session)   # a finished game: «верни ход» reopens it (audit 26.10)
    if board_rec is None:
        return json.dumps({"error": "No game is on: start_game starts one."})
    view_ply = args.get("view_ply")
    view_line = args.get("view_line") if isinstance(args.get("view_line"), list) else None
    step = game_command_step(session, board_rec, action, words,
                             view_ply=int(view_ply) if isinstance(view_ply, (int, float)) else None, view_line=view_line)
    if not step:
        return json.dumps({"error": "Nothing was done."})
    note = step["block"].split("\n", 1)[-1]
    if step.get("view") is None:
        out = {"ok": action == "draw" or bool(step.get("actions")), "action": action, "done": bool(step.get("actions")), "note": note}
        if step.get("actions"):
            out["board_actions"] = step["actions"]  # the board shows another position of the game (game_view)
        return json.dumps(out, ensure_ascii=False)
    if action == "level":
        return _reply(step["view"], {"ok": True, "action": action, "done": True, "engine_elo": step["view"]["engine_elo"],
                                     "note": note})
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
