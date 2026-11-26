"""A rule of the game shown on the board: the coach's own example, known to the server (25.11).

«Что такое взятие на проходе, покажи на доске» was answered «Показать пример на доске сейчас не получилось. Для
урока о взятии на проходе сначала нужно пройти курс «Основы шахмат»» (tester 25.11; the stand said «примера этого
правила в базе нет, а строить позицию по памяти я не стану»). The knowledge base has no topic for the rules of the
game — its topics are strategy and endgames — so the only example was the site's lesson, and that lesson's course was
still locked for the student. A lock closes a lesson, not a question: what a rule is and how it looks on the board is
the coach's own to show.

Each rule here has one small position where the rule is the whole point, the move that shows it and the words for
it; ``verify`` proves every one on the board (the tests run it), so nothing is «built from memory». The topic and
lesson tools reach for it when they have no example of their own to give (src/tools/knowledge_topics.get_topic,
src/tools/learning_path.get_lesson's locked answer).
"""

from __future__ import annotations

import re
from typing import Optional

import chess

_W = r"(?<![\w-])"

# key, the words that name the rule, the position, the move just made there (UCI, or None), the move that shows the
# rule (SAN, or None when the position itself is the rule), the title by language, the example in words
EXAMPLES = (
    {
        "key": "en_passant",
        "words": re.compile(_W + r"(?:на\s+проходе|en\s+passant|өтпелі\s+алу|бит\w+\s+пол\w+)", re.IGNORECASE),
        "fen": "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2",
        "last_move": "d7d5",
        "move": "exd6",
        "title": {"ru": "Взятие на проходе", "en": "En passant", "kk": "Өтпелі алу"},
        "note": ("Black's pawn has just gone d7–d5, two squares at once, and stands beside White's pawn on e5. White "
                 "may take it en passant right now: exd6 — the white pawn goes diagonally to d6, the square the black "
                 "pawn jumped over, and the black pawn on d5 leaves the board. Only a pawn takes this way, and only on "
                 "the very next move: after any other move the right is gone."),
    },
    {
        "key": "castling",
        "words": re.compile(_W + r"(?:рокиров\w*|рокир\w+|castl\w+|рокировка|рокирлеу\w*)", re.IGNORECASE),
        "fen": "4k3/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQ - 0 1",
        "last_move": None,
        "move": "O-O",
        "title": {"ru": "Рокировка", "en": "Castling", "kk": "Рокировка"},
        "note": ("White's king and both rooks have not moved and nothing stands between them. Short castling, O-O: "
                 "the king goes two squares to g1 and the h1 rook jumps over it to f1 — one move. Long castling, "
                 "O-O-O, is the same to the other side: the king to c1, the a1 rook to d1. It needs: neither the king "
                 "nor that rook has moved, the squares between them are empty, the king is not in check and does not "
                 "pass through or land on an attacked square."),
    },
    {
        "key": "promotion",
        "words": re.compile(_W + r"(?:превращ\w*|превра[тщ]\w*|promot\w*|айналд\w*)", re.IGNORECASE),
        "fen": "8/4P1k1/8/8/8/8/8/4K3 w - - 0 1",
        "last_move": None,
        "move": "e8=Q",
        "title": {"ru": "Превращение пешки", "en": "Promotion", "kk": "Пешканың айналуы"},
        "note": ("White's pawn on e7 is one step from the last rank. e8=Q: the pawn steps to e8 and becomes a queen "
                 "at once — or a rook, a bishop or a knight, as its player chooses; never a king, never stays a pawn. "
                 "It does not matter which pieces are still on the board: a second queen is fine."),
    },
    {
        "key": "stalemate",
        "words": re.compile(_W + r"(?:пат(?:а|у|ом|е|ов\w*)?|stalemate\w*)(?![\w-])", re.IGNORECASE),
        "fen": "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1",
        "last_move": None,
        "move": None,
        "title": {"ru": "Пат", "en": "Stalemate", "kk": "Пат"},
        "note": ("Black is to move. The king on h8 is NOT in check, but every square it could step to — g8, g7, h7 — "
                 "is covered by the white queen on f7 or the white king on g6, and Black has no other piece. No legal "
                 "move and no check: that is stalemate, and the game is a draw, however much material White has."),
    },
)


def for_words(text: Optional[str]) -> Optional[dict]:
    """The rule *text* names («что такое взятие на проходе», "en passant"), or None."""
    if not text:
        return None
    for example in EXAMPLES:
        if example["words"].search(text):
            return example
    return None


def verify(example: dict) -> bool:
    """The example is what it says: a legal position, its «last move» the pawn's or piece's real way there, its move
    legal and of the rule's kind (an en passant capture, a castling, a promotion), a moveless example a stalemate."""
    try:
        board = chess.Board(example["fen"])
        if not board.is_valid():
            return False
        last = example.get("last_move")
        if last:
            came = chess.Move.from_uci(last)
            if board.piece_at(came.to_square) is None or board.piece_at(came.from_square) is not None:
                return False
        san = example.get("move")
        if not san:
            return example["key"] == "stalemate" and board.is_stalemate()
        move = board.parse_san(san)
        return {
            "en_passant": board.is_en_passant(move),
            "castling": board.is_castling(move),
            "promotion": bool(move.promotion),
        }.get(example["key"], True)
    except (ValueError, KeyError):
        return False


def actions(example: dict) -> list[dict]:
    """The board actions that show the example: the position, the move just made (blue) and the rule's move (green)."""
    board = chess.Board(example["fen"])
    out: list[dict] = [{"type": "set_fen", "fen": example["fen"]}]
    arrows = []
    if example.get("last_move"):
        came = chess.Move.from_uci(example["last_move"])
        arrows.append({"from": chess.square_name(came.from_square), "to": chess.square_name(came.to_square),
                       "brush": "blue"})
    if example.get("move"):
        move = board.parse_san(example["move"])
        arrows.append({"from": chess.square_name(move.from_square), "to": chess.square_name(move.to_square),
                       "brush": "green"})
    if arrows:
        out.append({"type": "draw_arrows", "arrows": arrows})
    return out


BOARD_HINT = (
    "This is your own example of the rule, checked on the board by the server, and it is ON the student's board now "
    "(the position and its arrows). Explain the rule with it, in the student's language and a child's words: say what "
    "stands where, which move shows the rule and what happens on the board when it is played — exactly as "
    "`example.note` tells it. Do not say the example could not be shown, and do not set up another position."
)
WORDS_HINT = (
    "This is your own example of the rule, checked on the board by the server. It was not put on the student's board "
    "this turn: tell it in words from `example.note` and offer to show it."
)


def topic(example: dict, locale: Optional[str] = "ru", show: bool = True) -> dict:
    """The topic tool's answer for a rule: its title, the example (position, move, words) and the board actions."""
    lang = (locale or "ru").lower()
    lang = "kk" if lang in ("kk", "kz") else lang
    board = chess.Board(example["fen"])
    out = {
        "source": "rule_example",
        "slug": example["key"],
        "title": example["title"].get(lang) or example["title"]["ru"],
        "example": {
            "source": "rule_example", "fen": example["fen"], "key_move": example.get("move"),
            "side_to_move": "White" if board.turn == chess.WHITE else "Black", "note": example["note"],
        },
    }
    if show:
        out["board_actions"] = actions(example)
        out["board_hint"] = BOARD_HINT
    else:
        out["board_hint"] = WORDS_HINT
    return out


# ── the rule asked about, and a lesson's diagram that shows something else (26.11) ────────────────────────────────
# «Может ли пешка превратиться в короля?» was answered rightly — over a position with queens, a rook and two kings,
# «на доске показан пример материального перевеса: у белых лишняя ладья» (tester 26.11): the site's lesson
# «Превращение пешки — путь к победе» was open to the student, and its first diagram, which is about the extra rook,
# went on the board. A question about a rule is answered on a board that shows the rule: when the position a tool is
# about to show does not, the coach's own example goes up and the lesson is offered by its name.
_WANTS_LESSON = re.compile(_W + r"(?:урок\w*|lesson\w*|сабақ\w*|курс\w*|course\w*|заняти\w*|программ\w*)", re.IGNORECASE)


def shown_in(example: dict, fen: Optional[str]) -> bool:
    """*fen* is a position where the rule of *example* can be seen: an en passant capture or a castling to play, a
    pawn one step from promoting, a stalemate."""
    try:
        board = chess.Board(fen)
    except (ValueError, TypeError):
        return False
    key = example["key"]
    if key == "stalemate":
        return board.is_stalemate()
    for turn in (board.turn, not board.turn):
        b = board.copy(stack=False)
        if turn != board.turn:
            if b.is_check():
                continue
            b.turn = turn
            b.ep_square = None
        for move in b.legal_moves:
            if (key == "en_passant" and b.is_en_passant(move)) or (key == "castling" and b.is_castling(move)) \
                    or (key == "promotion" and move.promotion):
                return True
    return False


OVER_LESSON_HINT = (
    " The student asked about the rule itself: this example is on the board INSTEAD of the lesson's own diagram, which "
    "shows something else — never describe that other diagram. After the answer you may offer the lesson by its title."
)


def over(result, words: Optional[str], locale: Optional[str] = "ru", show: bool = True):
    """*result* — a lesson's or a topic's, about to show a position — with the rule's own example in its place when
    the student's *words* ask about a rule (not for a lesson) and that position does not show it. Else *result*."""
    if not isinstance(result, dict) or result.get("source") == "rule_example" or result.get("locked"):
        return result
    example = for_words(words)
    if not example or _WANTS_LESSON.search(words or ""):
        return result
    if isinstance(result.get("example"), dict) and result["example"].get("source") in ("knowledge_base", "endgame_theory"):
        return result  # the base's own example for its topic («патовая ловушка») is chosen for that topic
    actions = result.get("board_actions") if isinstance(result.get("board_actions"), list) else []
    fen = next((a.get("fen") for a in actions if isinstance(a, dict) and a.get("type") in ("set_fen", "set_puzzle")
                and a.get("fen")), None)
    if fen is None and isinstance(result.get("example"), dict):
        fen = result["example"].get("fen")
    if not fen or shown_in(example, fen):
        return result
    own = topic(example, locale, show)
    out = dict(result)
    out["example"] = own["example"]
    out["board_hint"] = own["board_hint"] + OVER_LESSON_HINT
    if show:
        out["board_actions"] = own["board_actions"]
    else:
        out.pop("board_actions", None)
    # the lesson's own diagrams stay out of the answer: they are what was told by mistake
    for key in ("diagrams", "diagrams_note", "board_puzzle"):
        out.pop(key, None)
    return out
