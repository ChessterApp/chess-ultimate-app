"""«А если бы на 8-м ходу я взял на g5 вместо Bg3?» — the position of that move.

The student asks about a move of the game on the board, not about the board's
final position. Production, 2026-10-06: the question went to the final
position, where Bxg5 is not even possible, and the coach explained the idea
with an invented capture («пешка g5 сама забирает слона»). Here the move
number (or the game move after «вместо» / "instead of") finds the moment in
the game; the idea is then played and judged there.
"""

from __future__ import annotations

import io
import re
from typing import Optional

import chess
import chess.pgn

_NUMBER = [
    re.compile(r"(?:на|в)\s+(?P<n>\d{1,3})\s*-?\s*(?:м|ом|ой|й)?\s+ход\w*", re.IGNORECASE),
    re.compile(r"(?P<n>\d{1,3})\s*-?\s*(?:м|ом|ой|й)\s+ход\w*", re.IGNORECASE),
    re.compile(r"ход(?:е|у)?\s+(?:номер\s+)?(?P<n>\d{1,3})(?![\d.])", re.IGNORECASE),
    re.compile(r"\b(?:on|at|in)\s+move\s+(?P<n>\d{1,3})\b", re.IGNORECASE),
    re.compile(r"\bmove\s+(?P<n>\d{1,3})\b", re.IGNORECASE),
    re.compile(r"(?P<n>\d{1,3})\s*-?\s*(?:ші|шы|інші|ыншы)\s+жүріс\w*", re.IGNORECASE),
]
_SAN = r"(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?|O-O-O|O-O)[+#]?"
_NUMBERED = re.compile(r"(?<![\d.])(?P<n>\d{1,3})\s*(?P<dots>\.\.\.|…|\.)\s*(?P<san>" + _SAN + ")")
_INSTEAD = re.compile(r"(?:вместо|instead\s+of|орнына)\s+(?:хода\s+|of\s+)?(?:\d{1,3}\s*(?:\.\.\.|…|\.)\s*)?(?P<san>" + _SAN + ")",
                      re.IGNORECASE)


def _plies(pgn: str) -> list[dict]:
    """[{'board': position before, 'san', 'number', 'color'}] along the main line."""
    try:
        game = chess.pgn.read_game(io.StringIO(pgn or ""))
    except Exception:  # noqa: BLE001
        return []
    if game is None:
        return []
    board = game.board()
    out = []
    for move in game.mainline_moves():
        if move not in board.legal_moves:
            break
        out.append({"board": board.copy(stack=False), "san": board.san(move),
                    "number": board.fullmove_number, "color": board.turn})
        board.push(move)
    return out


def _norm(san: str) -> str:
    return re.sub(r"[+#!?]", "", san or "").replace("0-0-0", "O-O-O").replace("0-0", "O-O")


def past_position(message: str, pgn: Optional[str]) -> Optional[dict]:
    """The game moment the question is about: {'fen', 'number', 'color',
    'played', 'label'} — or None when the question names no earlier moment.

    The moment is found by the move after «вместо» / "instead of" when it was
    played in the game (nearest to the named move number), else by the move
    number: the side whose move the student's idea is legal for.
    """
    if not pgn or not message:
        return None
    plies = _plies(pgn)
    if len(plies) < 2:
        return None
    from src.answer_check import _to_san

    text, _ = _to_san(message)
    text = re.sub(r"(?<![0-9A-Za-z-])0-0-0(?![0-9-])", "O-O-O", text)
    text = re.sub(r"(?<![0-9A-Za-z-])0-0(?![0-9-])", "O-O", text)
    number, color = None, None
    for rx in _NUMBER:
        m = rx.search(text)
        if m:
            number = int(m["n"])
            break
    numbered = _NUMBERED.search(text)
    if number is None and numbered:
        number = int(numbered["n"])
        color = chess.BLACK if numbered["dots"] != "." else chess.WHITE
    instead = _INSTEAD.search(text)
    played = _norm(instead["san"]) if instead else None
    if number is None and played is None:
        return None
    # The final position is not "an earlier moment".
    last = plies[-1]

    def pick(cands):
        return min(cands, key=lambda p: abs(p["number"] - number)) if number is not None else cands[0]

    chosen = None
    if played:
        cands = [p for p in plies if _norm(p["san"]) == played]
        if number is not None:
            cands = [p for p in cands if abs(p["number"] - number) <= 1] or cands
        if cands:
            chosen = pick(cands)
    if chosen is None and number is not None:
        at = [p for p in plies if p["number"] == number and (color is None or p["color"] == color)]
        if not at:
            return None
        if len(at) == 1 or color is not None:
            chosen = at[0]
        else:
            # Whose move: the side for which the student's idea is a legal move.
            from src.prompt_builder import question_moves

            legal_for = [p for p in at if any(q.get("legal") for q in question_moves(message, p["board"].fen()))]
            chosen = legal_for[0] if len(legal_for) == 1 else at[0]
    if chosen is None:
        return None
    if chosen is last and number is None and played is None:
        return None
    dots = "." if chosen["color"] == chess.WHITE else "..."
    return {
        "fen": chosen["board"].fen(),
        "number": chosen["number"],
        "color": chosen["color"],
        "played": chosen["san"],
        "label": f"move {chosen['number']}{dots} ({'White' if chosen['color'] else 'Black'} to move; "
                 f"the game went {chosen['number']}{dots}{chosen['san']})",
    }
