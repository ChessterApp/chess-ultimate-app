"""What a coaching session is called in the list (25.11).

The label was the session's first user message, whatever it was. The tester's list (25.11) read «Current chess puzzle
context: This puzzle focuses on: middlegame, advantage, short. themes White to move. The solution i…» — the service
text the puzzle screen's chat put in front of the student's question, the task's solution included; «Подскажи, на
что обратить внимание в этой позиции (без лучшего хода)» — the game's hint button, for a whole game against the
coach; «7k/5Q2/6K1/8/8/8/8/8 b - - 0 1» — a pasted position. A child finds nothing by such names.

The label is the first thing the student said in their own words:
  * a service text in front of a question is not the student's — only what follows it counts;
  * a bare position, game record or link is something put on the board, not said — it names the session only when
    nothing was said at all, and then by what it is, in words: «Позиция: король, ладья и пешка — король и ладья»,
    «Накамура – Карлсен», «Партия с Chess.com» (``paste_label``; the FEN or the link itself named it until 28.11 —
    «1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1», tester 28.11: «ребёнку такое название ничего не скажет»);
  * a session that began as a game against the coach is named by the game (its opening and result, the same in
    every language): what is written during the game — the hint button's request, «оцени позицию» — is about a move
    of it, not about the session.
"""

from __future__ import annotations

import io
import re
from typing import Optional

import chess
import chess.pgn

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
        return (paste_label(pasted, session, _language(session)) or " ".join(pasted.split()))[:LABEL_CHARS]
    last = messages[-1] if messages else None
    return (getattr(last, "content", "") or "")[:LABEL_CHARS] if last is not None else ""


# ── a paste named in words (28.11) ────────────────────────────────────────────────────────────────────────────────
_ORDER = (chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN)
_NAMES = {
    # one, two–four, five and more (Russian); English singular / plural; Kazakh takes no plural after a number
    "ru": {chess.KING: ("король", "короля", "королей"), chess.QUEEN: ("ферзь", "ферзя", "ферзей"),
           chess.ROOK: ("ладья", "ладьи", "ладей"), chess.BISHOP: ("слон", "слона", "слонов"),
           chess.KNIGHT: ("конь", "коня", "коней"), chess.PAWN: ("пешка", "пешки", "пешек")},
    "en": {chess.KING: ("king", "kings"), chess.QUEEN: ("queen", "queens"), chess.ROOK: ("rook", "rooks"),
           chess.BISHOP: ("bishop", "bishops"), chess.KNIGHT: ("knight", "knights"), chess.PAWN: ("pawn", "pawns")},
    "kk": {chess.KING: ("патша",), chess.QUEEN: ("уәзір",), chess.ROOK: ("тура",), chess.BISHOP: ("піл",),
           chess.KNIGHT: ("ат",), chess.PAWN: ("сарбаз",)},
}
_WORDS = {
    "ru": {"and": " и ", "versus": " — ", "position": "Позиция: {}", "to_move": "Позиция, ход {}",
           "white": "белых", "black": "чёрных", "start": "Начальная позиция", "game_from": "Партия с {}",
           "link": "Партия по ссылке"},
    "en": {"and": " and ", "versus": " vs ", "position": "Position: {}", "to_move": "Position, {} to move",
           "white": "White", "black": "Black", "start": "Starting position", "game_from": "Game from {}",
           "link": "Game from a link"},
    "kk": {"and": " және ", "versus": " — ", "position": "Позиция: {}", "to_move": "Позиция, {} жүрісі",
           "white": "ақтардың", "black": "қаралардың", "start": "Бастапқы позиция", "game_from": "{} партиясы",
           "link": "Сілтемедегі партия"},
}
# Up to this many pieces besides the kings the position is named by its pieces; more is a whole game's worth.
NAMED_PIECES = 8
_HOSTS = (("lichess.org", "Lichess"), ("chess.com", "Chess.com"))


def _count_word(lang: str, piece: int, n: int) -> str:
    forms = _NAMES[lang][piece]
    if n == 1:
        return forms[0]
    if lang == "ru":
        form = forms[1] if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else forms[2]
    elif lang == "en":
        form = forms[1]
    else:
        form = forms[0]
    return f"{n} {form}"


def _side_words(board: chess.Board, color: bool, lang: str) -> str:
    parts = [_count_word(lang, piece, len(board.pieces(piece, color))) for piece in _ORDER
             if board.pieces(piece, color)]
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + _WORDS[lang]["and"] + parts[-1]


def position_words(fen: str, lang: str = "ru") -> str:
    """«Позиция: король, ладья и пешка — король и ладья» (White's pieces first) for a position with few pieces,
    «Позиция, ход белых» for a fuller one, «Начальная позиция»; "" for what is not a position."""
    lang = lang if lang in _WORDS else "ru"
    try:
        board = chess.Board(" ".join(fen.split()[:6]) if len(fen.split()) >= 2 else fen.split()[0] + " w - - 0 1")
    except (ValueError, IndexError):
        return ""
    words = _WORDS[lang]
    if board.board_fen() == chess.Board().board_fen():
        return words["start"]
    others = sum(1 for p in board.piece_map().values() if p.piece_type != chess.KING)
    if others <= NAMED_PIECES:
        return words["position"].format(
            _side_words(board, chess.WHITE, lang) + words["versus"] + _side_words(board, chess.BLACK, lang))
    return words["to_move"].format(words["white"] if board.turn == chess.WHITE else words["black"])


def _players(pgn: str) -> str:
    """«Nakamura – Carlsen» from a record's headers, or ""."""
    try:
        game = chess.pgn.read_game(io.StringIO(pgn or ""))
    except Exception:  # noqa: BLE001
        return ""
    if game is None:
        return ""
    white, black = (game.headers.get(k, "").strip() for k in ("White", "Black"))
    if white in ("", "?") or black in ("", "?"):
        return ""
    return f"{white} – {black}"


def paste_label(text: str, session=None, lang: str = "ru") -> str:
    """A pasted position, record or link named in words (see the module's rule), or "" when it is none of them."""
    lang = lang if lang in _WORDS else "ru"
    text = (text or "").strip()
    if _FEN.match(text):
        return position_words(text, lang)
    if _URL.match(text):
        # the game the link brought onto a board of the session, by its players; else the site it is from
        for board in reversed(list(getattr(session, "boards", None) or [])):
            if getattr(board, "kind", None) != "game":
                names = _players(getattr(board, "pgn", "") or "")
                if names:
                    return names
        host = next((name for domain, name in _HOSTS if domain in text.lower()), None)
        return _WORDS[lang]["game_from"].format(host) if host else _WORDS[lang]["link"]
    if is_board_paste(text):
        names = _players(text)
        if names:
            return names
        try:
            game = chess.pgn.read_game(io.StringIO(text))
            result = game.headers.get("Result") if game else None
        except Exception:  # noqa: BLE001
            result = None
        from src.coach_games import title

        return title(text, result)
    return ""


def _language(session) -> str:
    """The session's language for its label: the student's (src/prompt_builder.conversation_language), else the
    coach's own answers' — a session of pastes alone carries none of the student's words."""
    try:
        from src.prompt_builder import _script_language, conversation_language

        messages = list(getattr(session, "messages", None) or [])
        users = [m.content for m in reversed(messages) if getattr(m, "role", "") == "user"]
        code, why = conversation_language(users, None)
        if why != "interface":
            return code
        for m in reversed(messages):
            if getattr(m, "role", "") == "assistant":
                found = _script_language(getattr(m, "content", "") or "")
                if found:
                    return found
    except Exception:  # noqa: BLE001 — a label in Russian is still a label
        pass
    return "ru"
