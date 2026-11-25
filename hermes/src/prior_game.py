"""The game the student has just finished against the coach, asked about from the next one (25.11).

After «Реванш» the student asked «а что было бы, если бы я в прошлой партии взял конём на d5» and the coach answered
«чтобы сказать… нужна позиция после восьмого хода белых. Можешь прислать запись партии или эту позицию?» — with its own
review of that game («сильнее было 8...Nxd5») just above in the chat (tester 25.11; «Главная ошибка» after a rematch
was the same in the report of 20.11). The turn's context is the board in front of the student — the new game — and
the finished game lives on another board of the same session, which the server holds whole.

So when the words name the previous game, the server gives the turn that game's record and, when the question is
about a move («если бы я взял конём на d5»), the moment it belongs to: the student's turn where that move could be
played — the one the engine itself named as the better move if there is one. The idea is then played and looked at by
the engine THERE (src/hypothetical), exactly as for a moment of the game on the board (src/past_move).
"""

from __future__ import annotations

import re
from typing import Optional

import chess

_B = r"(?<![а-яёa-zәғқңөұүһі])"
_E = r"(?![а-яёa-zәғқңөұүһі])"
# «в прошлой / предыдущей / той партии», «прошлую партию», "the last / previous game", «өткен партияда»
_PRIOR = re.compile(
    _B + r"(?:(?:прошл|предыдущ|прежн|минувш)\w*\s+(?:наш\w+\s+)?(?:парти\w+|игр\w+)"
    r"|(?:парти\w+|игр\w+)\s+(?:до\s+этой|перед\s+этой)"
    r"|(?:в|из)\s+той\s+(?:парти\w+|игр\w+)"
    r"|(?:last|previous|prior|earlier)\s+game"
    r"|(?:the\s+)?game\s+(?:before|we\s+just\s+played)"
    r"|(?:өткен|алдыңғы)\s+(?:парти\w+|ойын\w*))" + _E,
    re.IGNORECASE)

HEADER = "## The previous game of this session"


def names_prior_game(message: Optional[str]) -> bool:
    """The words point at the game before the one on the board («в прошлой партии», "in the previous game")."""
    return bool(message) and bool(_PRIOR.search(message))


def prior_board(session, active_board=None):
    """The session's latest finished game against the coach that is not *active_board*, or None."""
    boards = [
        b for b in (getattr(session, "boards", None) or [])
        if getattr(b, "kind", None) == "game" and getattr(b, "id", None) != getattr(active_board, "id", None)
        and (getattr(b, "game_state", None) or {}).get("status") == "finished"
        and (getattr(b, "game_state", None) or {}).get("moves")
    ]
    if not boards:
        return None
    return max(boards, key=lambda b: (getattr(b, "game_state", None) or {}).get("finished_at")
               or getattr(b, "updated_at", 0) or 0)


def _label(ply: int, san: str) -> str:
    number = (ply + 1) // 2
    return f"{number}.{san}" if ply % 2 == 1 else f"{number}...{san}"


def moment(message: str, state: dict) -> Optional[dict]:
    """The moment of the finished game *state* the question's move belongs to — {'fen', 'number', 'color', 'played',
    'label', 'prior': True} as src/past_move.past_position gives it — or None when the words name no move the student
    could have played in that game, or more than one moment fits and nothing tells them apart.

    Tried in order: a move number or «вместо …» in the words (past_position's own reading of the record); the
    student's turn where a move the words name is the better move the engine gave for it; the only student's turn
    where such a move was legal and was not the move played."""
    moves = list(state.get("moves") or [])
    if not moves or not message:
        return None
    student = chess.WHITE if state.get("student_color") == "white" else chess.BLACK
    try:
        from src.game_mode import _pgn, _replay
        from src.past_move import past_position

        found = past_position(message, _pgn(state, _replay(moves)))
        if found:
            return {**found, "prior": True}
    except Exception:  # noqa: BLE001 — the other readings still stand
        pass
    from src.prompt_builder import question_moves

    best_at = {int(a.get("ply") or 0): str(a.get("best") or "") for a in (state.get("annotations") or [])}
    board = chess.Board()
    fits: list[dict] = []
    for i, san in enumerate(moves):
        ply = i + 1
        if board.turn == student:
            try:
                named = [q for q in question_moves(message, board.fen()) if q.get("legal")]
            except Exception:  # noqa: BLE001
                named = []
            ideas = [q for q in named if q["san"].rstrip("+#") != san.rstrip("+#")]
            if ideas:
                better = best_at.get(ply, "").rstrip("+#")
                fits.append({
                    "fen": board.fen(), "number": board.fullmove_number, "color": board.turn, "played": san,
                    "ply": ply, "engine_named": any(q["san"].rstrip("+#") == better for q in ideas) if better else False,
                })
        try:
            board.push_san(san)
        except ValueError:
            break
    if not fits:
        return None
    named_by_engine = [f for f in fits if f["engine_named"]]
    chosen = named_by_engine[-1] if named_by_engine else (fits[0] if len(fits) == 1 else None)
    if chosen is None:
        return None
    side = "White" if chosen["color"] == chess.WHITE else "Black"
    return {
        "fen": chosen["fen"], "number": chosen["number"], "color": chosen["color"], "played": chosen["played"],
        "prior": True,
        "label": f"the PREVIOUS game, before {_label(chosen['ply'], chosen['played'])} ({side} — the student — to "
                 f"move there; that game went {_label(chosen['ply'], chosen['played'])})",
    }


MISTAKES = 5  # the student's latest mistakes told with their positions


def _fen_before(moves: list, annotation: dict) -> str:
    try:
        from src.game_mode import _replay

        return _replay(moves[: max(0, int(annotation.get("ply") or 1) - 1)]).fen()
    except Exception:  # noqa: BLE001
        return "?"


def block(state: dict, at: Optional[dict] = None) -> str:
    """The turn's block for the finished game *state*: whose it was, how it ended, every move numbered, the student's
    mistakes with the engine's better moves, and — when the question is about one of its moments — that moment."""
    moves = list(state.get("moves") or [])
    if not moves:
        return ""
    from src.game_mode import _mistake_text, _moves_text, decisive_moment

    lines = [
        HEADER,
        "The game the student played against you before the one on the board now — finished, and NOT the position "
        "in front of them. They ask about it: answer from this record, never ask them for its moves or its position.",
        f"The student played {state.get('student_color')}. Result: {state.get('result')} ({state.get('termination')}), "
        f"winner: {state.get('winner') or 'nobody'}.",
        f"The record, exact: {_moves_text(moves)}",
    ]
    bad = [a for a in (state.get("annotations") or []) if a.get("verdict") in ("mistake", "blunder")]
    if bad:
        lines.append("The student's mistakes in it, each with the position BEFORE the move (a FEN the engine tools "
                     "take): " + "; ".join(f"{_mistake_text(a, with_cp=True)} [before it: {_fen_before(moves, a)}]"
                                           for a in bad[-MISTAKES:]))
    try:
        lines.append(decisive_moment(state))
    except Exception:  # noqa: BLE001
        pass
    if at:
        lines.append(f"The question is about this moment of it: {at['label']}. Position there: {at['fen']}. The "
                     "student's idea is played and judged on THAT position (the blocks below) — say so, and do not mix "
                     "it with the game on the board now.")
    else:
        lines.append("If it is not clear which moment of it they mean, ask which move — never for the record.")
    return "\n".join(lines)
