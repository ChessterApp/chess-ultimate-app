"""Game mode: the student plays a game against the coach on a session board.

The game lives on a board of kind ``game`` (migration 018 reserved
``game_state`` for it), so it survives reloads and appears in the session
like any other board. Moves are made by the engine at a chosen strength
(``src/game_engine.py``); the model never plays — it only comments.

Per student move the engine also evaluates the position before and after
(depth 12, a fraction of a second), so every move gets a verdict — ok /
inaccuracy / mistake / blunder — and the better move when there was one.
The client decides, from ``comment_wanted`` and the game's comment mode,
whether to ask for a coach comment (a separate, tool-free streamed call:
see ``comment_prompt``). When the student asks the coach something during
the game, ``game_context`` puts the game into that turn's prompt so hints
stay hints and the coach never moves for the student.
"""

from __future__ import annotations

import io
import random
import time
from typing import Optional

import chess
import chess.pgn

from src.boards import Board
from src.game_engine import clamp_elo, get_engine

COMMENT_MODES = ("quiet", "mistakes", "every")
DEFAULT_COMMENT_MODE = "mistakes"

# cp lost by the student's move (from their point of view) → verdict
BLUNDER_CP = 300
MISTAKE_CP = 100
INACCURACY_CP = 50

MAX_GAME_PLIES = 400


class GameError(ValueError):
    """A request the rules do not allow (not your turn, illegal move, game over)."""


# ── state ──────────────────────────────────────────────────────────────────


def new_game_state(student_color: str, elo: int, comment_mode: str) -> dict:
    return {
        "student_color": student_color,
        "engine_elo": clamp_elo(elo),
        "comment_mode": comment_mode if comment_mode in COMMENT_MODES else DEFAULT_COMMENT_MODE,
        "status": "playing",          # playing | finished
        "result": None,               # 1-0 | 0-1 | 1/2-1/2
        "termination": None,          # checkmate | stalemate | insufficient | repetition | fifty_moves | resign | move_limit
        "winner": None,               # student | engine | None
        "moves": [],                  # SAN, from the start
        "annotations": [],            # one per student move: {ply, san, verdict, cp_loss, best, eval_after}
        "started_at": time.time(),
        "finished_at": None,
    }


def _replay(moves: list[str]) -> chess.Board:
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    return board


def _pgn(state: dict, board: chess.Board) -> str:
    game = chess.pgn.Game()
    game.headers["Event"] = "Game with the coach"
    game.headers["Site"] = "chesster.io"
    game.headers["Date"] = time.strftime("%Y.%m.%d", time.gmtime(state.get("started_at") or time.time()))
    student = "Student"
    engine = f"Coach (Stockfish {state['engine_elo']})"
    game.headers["White"] = student if state["student_color"] == "white" else engine
    game.headers["Black"] = engine if state["student_color"] == "white" else student
    game.headers["Result"] = state.get("result") or "*"
    node = game
    replay = chess.Board()
    for san in state["moves"]:
        move = replay.parse_san(san)
        node = node.add_variation(move)
        replay.push(move)
    return game.accept(chess.pgn.StringExporter(headers=True, variations=False, comments=False))


def _student_to_move(state: dict, board: chess.Board) -> bool:
    return (board.turn == chess.WHITE) == (state["student_color"] == "white")


def _finish(state: dict, board: chess.Board) -> bool:
    """Record the outcome if the game is over. Returns True when finished."""
    if state["status"] == "finished":
        return True
    outcome = board.outcome(claim_draw=True)
    if outcome is None and len(state["moves"]) >= MAX_GAME_PLIES:
        state.update({"status": "finished", "result": "1/2-1/2", "termination": "move_limit",
                      "winner": None, "finished_at": time.time()})
        return True
    if outcome is None:
        return False
    term = {
        chess.Termination.CHECKMATE: "checkmate",
        chess.Termination.STALEMATE: "stalemate",
        chess.Termination.INSUFFICIENT_MATERIAL: "insufficient",
        chess.Termination.THREEFOLD_REPETITION: "repetition",
        chess.Termination.FIVEFOLD_REPETITION: "repetition",
        chess.Termination.FIFTY_MOVES: "fifty_moves",
        chess.Termination.SEVENTYFIVE_MOVES: "fifty_moves",
    }.get(outcome.termination, "draw")
    winner = None
    if outcome.winner is not None:
        winner = "student" if (outcome.winner == chess.WHITE) == (state["student_color"] == "white") else "engine"
    state.update({"status": "finished", "result": outcome.result(), "termination": term,
                  "winner": winner, "finished_at": time.time()})
    return True


def _sync_board(board_rec: Board, state: dict, board: chess.Board) -> None:
    board_rec.game_state = state
    board_rec.pgn = _pgn(state, board) if state["moves"] else ""
    board_rec.fen = board.fen()
    board_rec.ply = len(state["moves"])
    board_rec.annotations = {}
    board_rec.touch()


# ── engine helpers (patched in tests) ──────────────────────────────────────


def _engine_move(fen: str, elo: int) -> str:
    return get_engine().choose_move(fen, elo)


def _evaluate(fen: str, pov: chess.Color) -> tuple[int, Optional[str]]:
    return get_engine().evaluate(fen, pov)


def _verdict(cp_loss: int) -> str:
    if cp_loss >= BLUNDER_CP:
        return "blunder"
    if cp_loss >= MISTAKE_CP:
        return "mistake"
    if cp_loss >= INACCURACY_CP:
        return "inaccuracy"
    return "ok"


# ── operations ─────────────────────────────────────────────────────────────


def start_game(session, color: str = "white", elo: int = 1500,
               comment_mode: str = DEFAULT_COMMENT_MODE) -> tuple[Board, dict]:
    """Create the game board (active) and, if the student is Black, make the
    engine's first move. Returns (board record, the reply payload)."""
    color = (color or "white").lower()
    if color == "random":
        color = random.choice(("white", "black"))
    if color not in ("white", "black"):
        raise GameError("color must be white, black or random")
    state = new_game_state(color, elo, comment_mode)
    board_rec = session.add_board(activate=True, kind="game", title="", orientation=color)
    board = chess.Board()
    engine_move = None
    if color == "black":
        engine_move = _push_engine_move(state, board)
    _sync_board(board_rec, state, board)
    session.save_board(board_rec)
    return board_rec, _payload(board_rec, state, board, student=None, engine=engine_move)


def _push_engine_move(state: dict, board: chess.Board) -> dict:
    uci = _engine_move(board.fen(), state["engine_elo"])
    move = chess.Move.from_uci(uci)
    if move not in board.legal_moves:
        raise RuntimeError(f"engine proposed an illegal move {uci}")
    san = board.san(move)
    board.push(move)
    state["moves"].append(san)
    return {"san": san, "uci": uci}


def _parse_student_move(board: chess.Board, move_str: str) -> chess.Move:
    text = (move_str or "").strip()
    if not text:
        raise GameError("Empty move.")
    looks_uci = len(text) in (4, 5) and text[0] in "abcdefgh" and text[1].isdigit() and text[2] in "abcdefgh"
    move = None
    if looks_uci:
        try:
            move = chess.Move.from_uci(text)
        except ValueError:
            move = None
    if move is None:
        try:
            move = board.parse_san(text)
        except (chess.IllegalMoveError, chess.AmbiguousMoveError) as exc:
            raise GameError(f"{text} is not a legal move here.") from exc
        except ValueError as exc:
            raise GameError(f"Cannot read the move {text!r}.") from exc
    if move not in board.legal_moves:
        raise GameError(f"{text} is not a legal move here.")
    return move


def play_move(session, board_rec: Board, move_str: str) -> dict:
    """The student's move, its verdict, and the engine's reply."""
    state = board_rec.game_state
    if board_rec.kind != "game" or not state:
        raise GameError("This board is not a game.")
    if state["status"] != "playing":
        raise GameError("The game is over.")
    board = _replay(state["moves"])
    if not _student_to_move(state, board):
        raise GameError("It is not your move.")
    student_color = chess.WHITE if state["student_color"] == "white" else chess.BLACK

    move = _parse_student_move(board, move_str)
    cp_before, best = _evaluate(board.fen(), student_color)
    san = board.san(move)
    board.push(move)
    state["moves"].append(san)
    cp_after, _ = _evaluate(board.fen(), student_color)
    cp_loss = max(0, cp_before - cp_after)
    verdict = _verdict(cp_loss)
    annotation = {
        "ply": len(state["moves"]),
        "san": san,
        "verdict": verdict,
        "cp_loss": cp_loss,
        "eval_after": cp_after,
        "best": best if (verdict != "ok" and best and best != san) else None,
    }
    state["annotations"].append(annotation)

    engine_move = None
    if not _finish(state, board):
        engine_move = _push_engine_move(state, board)
        _finish(state, board)

    _sync_board(board_rec, state, board)
    session.save_board(board_rec)
    return _payload(board_rec, state, board, student={**annotation, "uci": move.uci()}, engine=engine_move)


def resign(session, board_rec: Board) -> dict:
    state = board_rec.game_state
    if board_rec.kind != "game" or not state:
        raise GameError("This board is not a game.")
    if state["status"] != "playing":
        raise GameError("The game is over.")
    board = _replay(state["moves"])
    state.update({
        "status": "finished",
        "result": "0-1" if state["student_color"] == "white" else "1-0",
        "termination": "resign", "winner": "engine", "finished_at": time.time(),
    })
    _sync_board(board_rec, state, board)
    session.save_board(board_rec)
    return _payload(board_rec, state, board)


def takeback(session, board_rec: Board) -> dict:
    """Undo the student's last move (and the engine's reply to it)."""
    state = board_rec.game_state
    if board_rec.kind != "game" or not state:
        raise GameError("This board is not a game.")
    if state["status"] != "playing":
        raise GameError("The game is over.")
    board = _replay(state["moves"])
    student_plies = [a["ply"] for a in state["annotations"]]
    if not student_plies:
        raise GameError("Nothing to take back.")
    last_student_ply = student_plies[-1]
    state["moves"] = state["moves"][: last_student_ply - 1]
    state["annotations"] = [a for a in state["annotations"] if a["ply"] < last_student_ply]
    board = _replay(state["moves"])
    _sync_board(board_rec, state, board)
    session.save_board(board_rec)
    return _payload(board_rec, state, board)


def _payload(board_rec: Board, state: dict, board: chess.Board, student: Optional[dict] = None,
             engine: Optional[dict] = None) -> dict:
    mode = state.get("comment_mode", DEFAULT_COMMENT_MODE)
    finished = state["status"] == "finished"
    verdict = (student or {}).get("verdict")
    comment_wanted = finished or (
        mode == "every" and student is not None
    ) or (
        mode == "mistakes" and verdict in ("mistake", "blunder")
    )
    return {
        "board_id": board_rec.id,
        "student_color": state["student_color"],
        "engine_elo": state["engine_elo"],
        "comment_mode": mode,
        "status": state["status"],
        "result": state["result"],
        "termination": state["termination"],
        "winner": state["winner"],
        "fen": board.fen(),
        "pgn": board_rec.pgn,
        "ply": len(state["moves"]),
        "moves": list(state["moves"]),
        "student_to_move": (not finished) and _student_to_move(state, board),
        "student": student,
        "engine": engine,
        "comment_wanted": bool(comment_wanted),
        "in_check": board.is_check(),
    }


# ── prompts ────────────────────────────────────────────────────────────────

_LANG = {"ru": "Russian", "kz": "Kazakh", "kk": "Kazakh", "en": "English"}


def _moves_text(moves: list[str], last_n: Optional[int] = None) -> str:
    items = moves if last_n is None else moves[-last_n:]
    start_ply = len(moves) - len(items)
    out = []
    for i, san in enumerate(items):
        ply = start_ply + i
        if ply % 2 == 0:
            out.append(f"{ply // 2 + 1}.{san}")
        else:
            out.append(san if out and not out[-1].endswith("...") else f"{ply // 2 + 1}...{san}")
    return " ".join(out)


def game_context(board_rec: Board) -> str:
    """The live game as text for a chat turn (goes into the turn context)."""
    state = board_rec.game_state or {}
    if board_rec.kind != "game" or not state:
        return ""
    board = _replay(state.get("moves", []))
    who = "the student" if _student_to_move(state, board) else "you (the engine)"
    lines = [
        "## Live game (the student is playing against you)",
        f"Student plays {state['student_color']}; your moves are made by an engine at about {state['engine_elo']} Elo.",
        f"Moves so far: {_moves_text(state.get('moves', [])) or '(none yet)'}",
        f"Current FEN: {board.fen()}",
    ]
    if state.get("status") == "finished":
        lines.append(f"The game is over: {state.get('result')} ({state.get('termination')}); "
                     f"winner: {state.get('winner') or 'nobody'}. A full review is welcome now.")
    else:
        lines.append(f"It is {who} to move." + (" The student is in check." if board.is_check() else ""))
        lines.append("Rules for this turn: if the student asks for a hint, give a HINT (a theme, a piece to look at, "
                     "a question) — not the best move, unless they insist twice. Never make a move for the student "
                     "and never change the board position with board_control while the game is on; arrows and "
                     "highlights are fine.")
    annotations = state.get("annotations") or []
    bad = [a for a in annotations if a.get("verdict") in ("mistake", "blunder")]
    if bad:
        lines.append("Student's mistakes so far: " + "; ".join(
            f"{a['ply']}. {a['san']} ({a['verdict']}, -{a['cp_loss']} cp" + (f", better {a['best']}" if a.get("best") else "") + ")"
            for a in bad[-5:]
        ))
    return "\n".join(lines)


COMMENT_SYSTEM = (
    "You are Chesster, a chess coach playing a training game against your student. "
    "Speak in {language}, in the second person, like a coach sitting beside the board. "
    "Reply with at most {max_sentences} short sentences, no markdown, no lists, no move numbers "
    "you are not given. Never invent moves: mention only the moves and the better move listed in "
    "the facts. Do not reveal your own plan for the next move."
)

COMMENT_RULES = {
    "blunder": ("The student just blundered. Say what the move gave up in one sentence, name the better "
                "move from the facts, and end with one question that points at the idea."),
    "mistake": ("The student made a mistake. Point at what the move overlooked and ask one guiding "
                "question; you may name the better move."),
    "inaccuracy": "A small inaccuracy: one sentence, gently, and one question about the plan.",
    "ok": "The move was fine. One short encouraging sentence about the idea behind it, or about the plan ahead.",
    "finished": ("The game is over. Give the result in one sentence, name the moment that decided it "
                 "(from the mistakes listed, if any), and offer a full review in one sentence."),
}


def comment_prompt(board_rec: Board, locale: Optional[str], event: str = "move") -> list[dict]:
    """Messages for the tool-free comment call after a student's move or at the end."""
    state = board_rec.game_state or {}
    board = _replay(state.get("moves", []))
    language = _LANG.get((locale or "ru").lower(), "the student's language")
    finished = state.get("status") == "finished" or event == "end"
    last = (state.get("annotations") or [{}])[-1] if state.get("annotations") else {}
    verdict = "finished" if finished else (last.get("verdict") or "ok")
    max_sentences = 3 if verdict in ("blunder", "mistake", "finished") else 2
    facts = [
        f"Student plays {state.get('student_color')}; engine strength about {state.get('engine_elo')} Elo.",
        f"Last moves: {_moves_text(state.get('moves', []), last_n=8) or '(none)'}",
    ]
    if not finished and last:
        facts.append(f"Student's move: {last.get('san')} — verdict {last.get('verdict')}, "
                     f"lost {last.get('cp_loss', 0)} centipawns; evaluation now {last.get('eval_after', 0) / 100:+.1f} "
                     f"for the student.")
        if last.get("best"):
            facts.append(f"Better move was: {last['best']}.")
        if state.get("moves"):
            facts.append(f"Your reply on the board: {state['moves'][-1]}.")
    if finished:
        facts.append(f"Result: {state.get('result')} ({state.get('termination')}), winner: {state.get('winner') or 'nobody'}.")
        bad = [a for a in (state.get("annotations") or []) if a.get("verdict") in ("mistake", "blunder")]
        if bad:
            facts.append("Student's mistakes: " + "; ".join(
                f"{a['ply']}. {a['san']} ({a['verdict']}" + (f", better {a['best']}" if a.get("best") else "") + ")"
                for a in bad[-5:]))
    facts.append(f"FEN: {board.fen()}")
    return [
        {"role": "system", "content": COMMENT_SYSTEM.format(language=language, max_sentences=max_sentences)
                                       + "\n" + COMMENT_RULES[verdict]},
        {"role": "user", "content": "\n".join(facts)},
    ]
