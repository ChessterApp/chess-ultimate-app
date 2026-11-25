"""What a coaching session is called in the list (25.11).

The label was the session's first user message, whatever it was. The tester's list (25.11) read «Current chess puzzle
context: This puzzle focuses on: middlegame, advantage, short. themes White to move. The solution i…» — the service
text the puzzle screen's chat put in front of the student's question, the task's solution included; «Подскажи, на
что обратить внимание в этой позиции (без лучшего хода)» — the game's hint button, for a whole game against the
coach; «7k/5Q2/6K1/8/8/8/8/8 b - - 0 1» — a pasted position. A child finds nothing by such names.

The label is the first thing the student said in their own words:
  * a service text in front of a question is not the student's — only what follows it counts;
  * a bare position, game record or link is something put on the board, not said — it names the session only when
    nothing was said at all;
  * a session that began as a game against the coach is named by the game (its opening and result, the same in
    every language): what is written during the game — the hint button's request, «оцени позицию» — is about a move
    of it, not about the session.
"""

from __future__ import annotations

import re
from typing import Optional

LABEL_CHARS = 120

# The puzzle screen's chat (site puzzle/page.tsx createPuzzlePrompt, the app's puzzles.tsx): «Current chess puzzle
# context: <themes> <side> to move. The solution is: …» and then, after an empty line, the student's question.
_SERVICE = re.compile(r"^\s*Current chess puzzle context:.*?(?:\n\s*\n|\Z)", re.IGNORECASE | re.DOTALL)
_FEN = re.compile(r"^\s*(?:[pnbrqkPNBRQK1-8]{1,8}/){7}[pnbrqkPNBRQK1-8]{1,8}(?:\s+[wb](?:\s+\S+){0,4})?\s*$")
_URL = re.compile(r"^\s*https?://\S+\s*$", re.IGNORECASE)
_PGN_HEADER = re.compile(r"\[\s*\w+\s+\"[^\"]*\"\s*\]")
_PGN_TOKEN = re.compile(
    r"\d+\s*\.(?:\s*\.\.)?|…|(?:[KQRBNКФЛСКр]{0,2}[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBNФЛСК])?|O-O-O|O-O|0-0-0|0-0)[+#]?[!?]*"
    r"|1-0|0-1|1/2-1/2|½-½|\*|\{[^}]*\}|\$\d+")


def own_words(text: Optional[str]) -> str:
    """*text* without the service text a screen put in front of it."""
    return _SERVICE.sub("", text or "", count=1).strip()


def is_board_paste(text: str) -> bool:
    """*text* is a position, a game record or a link and nothing else — put on the board, not said."""
    if not text:
        return False
    if _FEN.match(text) or _URL.match(text):
        return True
    rest = _PGN_HEADER.sub(" ", text)
    moves = _PGN_TOKEN.findall(rest)
    return len(moves) >= 4 and not _PGN_TOKEN.sub(" ", rest).strip()


def _game_boards(session) -> list:
    return [b for b in (getattr(session, "boards", None) or []) if getattr(b, "kind", None) == "game"
            and (getattr(b, "pgn", None) or "").strip()]


def game_label(session) -> str:
    """«1.e4 e5 2.Nf3 Nc6 … 1-0» of the session's latest game against the coach, or ""."""
    games = _game_boards(session)
    if not games:
        return ""
    from src.coach_games import title

    board = max(games, key=lambda b: getattr(b, "updated_at", 0) or 0)
    return title(board.pgn, (getattr(board, "game_state", None) or {}).get("result"))[:LABEL_CHARS]


def label(session) -> str:
    """The session's name in the list: see the module's rule. "" for a session with nothing in it."""
    messages = list(getattr(session, "messages", None) or [])
    users = [m for m in messages if getattr(m, "role", "") == "user" and (getattr(m, "content", "") or "").strip()]
    said = [(m, own_words(m.content)) for m in users]
    worded = next(((m, text) for m, text in said if text and not is_board_paste(text)), None)
    game = game_label(session)
    if game:
        began = [getattr(b, "created_at", None) for b in _game_boards(session)]
        began = min([t for t in began if isinstance(t, (int, float)) and t > 0], default=None)
        when = getattr(worded[0], "timestamp", None) if worded else None
        during = began is not None and isinstance(when, (int, float)) and when >= began
        if worded is None or during:
            return game
    if worded is not None:
        return worded[1][:LABEL_CHARS]
    pasted = next((text for _, text in said if text), "")
    if pasted:
        return " ".join(pasted.split())[:LABEL_CHARS]
    last = messages[-1] if messages else None
    return (getattr(last, "content", "") or "")[:LABEL_CHARS] if last is not None else ""
