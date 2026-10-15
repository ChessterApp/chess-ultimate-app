"""What the student wants from their words — decided in one place for text and voice (2026-10-15).

The voice coach's browser kept its own copies of the server's word rules (src/game_intent.py,
src/board_lock.py, the opening book's names) and they drifted: «Дай мне тактическую задачу» was a
puzzle for the text coach and nothing for the voice one, the voice board lock missed the strict level,
the order «opening, then famous game» was reversed (inventory 2026-10-15). Now the browser asks
here (POST /api/coach/voice/intent) and does what the answer says; the server's own steps use the same
readers. Every reader below ends on data — the board, the game, the opening book, the famous games —
where it can; the words only say which question to ask of them.
"""

from __future__ import annotations

import re
from typing import Optional

import chess

# «задачу на вилку», "a puzzle on pins", «реши задачу» with no puzzle on the board, "let's solve"
_PUZZLE_ON = re.compile(r"(?<![\w-])(?:задач(?:у|и|ку|ки)|упражнени[ея]|puzzles?)\s+(?:на|про|по|on|about|for)\s+(?P<theme>[^,.!?]+)",
                        re.IGNORECASE)
_SOLVE = re.compile(r"(?<![\w-])(?:реши\w*\s+(?:мне\s+)?задач\w*|давай\s+решать|solve\s+a\s+puzzle|let'?s\s+solve|"
                    r"есеп\s+шығар\w*)(?![\w-])", re.IGNORECASE)
_REVIEW = re.compile(
    r"(?<![\w-])(?:разбер[иё]\w*|разбор|проанализир\w*\s+(?:мою\s+|эту\s+)?парти\w*|где\s+я\s+ошиб\w*|мои\s+ошибк\w*|"
    r"что\s+я\s+сделал\s+не\s+так|ойынымды\s+талда\w*|review\s+(?:my\s+|the\s+|this\s+)?game|"
    r"analy[sz]e\s+(?:my\s+|the\s+|this\s+)?game|where\s+did\s+i\s+go\s+wrong|my\s+mistakes)", re.IGNORECASE)
_REVIEW_SIDE = re.compile(r"(?P<black>ч[её]рными|за\s+ч[её]рных|as\s+black|with\s+black)|"
                          r"(?P<white>белыми|за\s+белых|as\s+white|with\s+white)", re.IGNORECASE)
REVIEW_MIN_PLIES = 10
# A concept asked about: «что такое связка», «объясни вилку», «покажи пример», "what is a pin"
_CONCEPT = re.compile(
    r"(?:что\s+так(?:ое|ая|ой|ие)|объясни|расскажи\s+(?:мне\s+)?(?:про|о|об)(?![\w-])|покажи\s+(?:мне\s+)?(?:пример|как)|"
    r"пример\w*\s+\w+|что\s+значит|как\s+(?:играть|использовать|работает)|деген\s+не|түсіндір|мысал|what\s+is|"
    r"what's\s+an?(?![\w-])|explain|show\s+me\s+(?:an?\s+)?example|example\s+of)", re.IGNORECASE)


def _plies(pgn: Optional[str]) -> int:
    from src.openings_book import _split_moves

    try:
        return len(_split_moves(re.sub(r"\[[^\]]*\]|\{[^}]*\}", " ", pgn or "")))
    except Exception:  # noqa: BLE001
        return 0


def read_intent(text: str, *, fen: Optional[str] = None, pgn: Optional[str] = None,
                live_game: bool = False, finished_game: bool = False, puzzle_on_board: bool = False) -> dict:
    """{"kind": …, …} — what *text* asks for, in the order a coach would hear it:

    game_command (resign / takeback / draw / restart), game_request (color, elo), move (san) or idea (in a
    game), puzzle (theme), review (side), famous_game (key), opening (name), board (a question about the
    position in front of the student — nothing replaces it), concept (topic), none.
    """
    from src.board_lock import _WANTS_NEW_PUZZLE, _board_lock_level
    from src.game_intent import game_command, game_request, game_wish, is_idea

    t = (text or "").strip()
    if not t:
        return {"kind": "none"}
    command = game_command(t)
    if command and (live_game or (command == "restart" and finished_game)):
        out = {"kind": "game_command", "command": command}
        if command == "restart":
            out.update(game_wish(t))  # «сыграем ещё раз чёрными»
        return out
    if not live_game:
        req = game_request(t)
        if req:
            return {"kind": "game_request", **req}
    if live_game:
        board = None
        try:
            board = chess.Board(fen) if fen else None
        except ValueError:
            board = None
        if board is not None:
            from src.move_text import moves_in, one_move

            if is_idea(t):
                named = moves_in(t, board)
                return {"kind": "idea", "moves": [m["san"] for m in named]} if named else {"kind": "none"}
            if len(t.split()) <= 8:
                san = one_move(t, board)
                if san:
                    return {"kind": "move", "san": san}
        return {"kind": "none"}  # the board is the game's: no example, no puzzle goes up
    theme_m = _PUZZLE_ON.search(t)
    if _WANTS_NEW_PUZZLE.search(t) or theme_m or (_SOLVE.search(t) and not puzzle_on_board):
        return {"kind": "puzzle", "theme": theme_m["theme"].strip() if theme_m else None}
    if _REVIEW.search(t) and _plies(pgn) >= REVIEW_MIN_PLIES:
        side = _REVIEW_SIDE.search(t)
        return {"kind": "review", "side": (None if not side else "black" if side["black"] else "white")}
    from src.famous_games import famous_game

    famous = famous_game(t)
    if famous:
        return {"kind": "famous_game", "key": famous["key"], "name": famous["name"]}
    from src.openings_book import named_opening

    opening = named_opening(t)
    if opening:
        return {"kind": "opening", "name": opening}
    keep, _strict = _board_lock_level(t, bool(fen), False, fen)
    if keep:
        return {"kind": "board"}
    if _CONCEPT.search(t) and len(t.split()) >= 2:
        return {"kind": "concept", "topic": t}
    return {"kind": "none"}
