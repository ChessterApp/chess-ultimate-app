"""A game asked for, or a move played, in the student's words — decided by the server.

The tools start_game / make_game_move (src/tools/game_play.py) were left to the model, and the
model did not always call them: on «Спорим, я тебя обыграю? Давай сыграем партию» it played by
talking, «я отвечаю e5», with nothing on the board (stand, 2026-10-12, 1 of 2 runs). The words
that ask for a game, and a move written on its own while a game is on, are read here; the text
coach's turn acts on them before the model answers (src/server.py), the voice coach's browser calls
the same tools with the student's words (``said``), and the model is told what happened.
"""

import re
from typing import Optional

import chess

# «давай сыграем», «сыграем партию?», «спорим, я тебя обыграю», «хочу сыграть с тобой», «давай
# поиграем», "let's play", «ойнайық». Not «как сыграть против сицилианки», «хочу сыграть Qb6»,
# «что мне сыграть», «спорим, это ничья».
_PLAY = re.compile(
    r"(?<![\w-])(?:"
    r"давай(?:те)?\s+(?:с\s+тобой\s+|со\s+мной\s+)?(?:сыгра(?:ем|ть)|поигра(?:ем|ть)|партию|партейку)"
    r"|сыгра(?:ем|ешь)(?:\s+(?:партию|партейку|со\s+мной|с\s+тобой|в\s+шахматы))?\s*[?!.]?\s*$"
    r"|сыгра(?:ем|ешь|ть)\s+(?:партию|партейку|со\s+мной|с\s+тобой|в\s+шахматы|против\s+тебя)"
    r"|(?:хочу|можем|можно)\s+(?:с\s+тобой\s+)?(?:сыграть|поиграть)\s+(?:с\s+тобой|со\s+мной|партию|партейку|в\s+шахматы|против\s+тебя)"
    r"|поигра(?:ем|ть\s+(?:с\s+тобой|со\s+мной))"
    r"|спорим[\s,]+(?:что\s+)?я\s+тебя\s+(?:обыгра\w*|побе\w*|надую|разгромл\w*)"
    r"|(?:обыгра\w*|побежу)\s+тебя"
    r"|let'?s\s+play|play\s+(?:a\s+game|with\s+me|against\s+you|me)|(?:want|wanna)\s+(?:to\s+)?play\s+(?:a\s+game|you|with\s+you)"
    r"|ойнайық|ойнайыкшы|ойна(?:йық)?\s+менімен"
    r")",
    re.IGNORECASE,
)
_BLACK = re.compile(r"(?<![\w-])(?:за\s+ч[её]рн\w*|ч[её]рными|black|қаралар\w*мен|қарамен)(?![\w-])", re.IGNORECASE)
_WHITE = re.compile(r"(?<![\w-])(?:за\s+бел\w*|белыми|white|ақтар\w*мен|ақпен)(?![\w-])", re.IGNORECASE)
_ELO = re.compile(r"(?<!\d)([5-9]\d\d|1\d\d\d|2[0-5]\d\d)(?!\d)")
# One rule for «is this a move to play or a question about one», on every path — the server's own
# play of the student's words (text pre-step, voice), and the move the model passes to make_game_move.
# Two rules disagreed: the server would not play «Слон c4?» while the model's call of it was played;
# «Хорошо, слон c4» was refused as a question (voice, 2026-10-14; inventory 2026-10-15). An idea is a
# move asked about: «а если Кf3?», «стоит ли брать?», "what if Nf3", "why not Bc4?". A move said with a
# rising voice («Слон c4?»), with «хорошо», «давай лучше», «можно слон c4» is a move.
_IDEA = re.compile(
    r"(?<![\w-])(?:если|а\s+вдруг|что\s+будет|а\s+что|что\s+если|можно\s+ли|стоит\s+ли|лучше\s+ли|хорош\w*\s+ли|"
    r"плох\w*\s+ли|почему|зачем|как\s+(?:насч[её]т|думаешь|считаешь)|what\s+if|what\s+about|how\s+about|why|"
    r"should|could|would|if|егер|қалай|неге)(?![\w-])"
    # «e4 хорош?», "Bc4 good?" — asked how good a move is
    r"|(?<![\w-])(?:хорош\w*|плох\w*|нормальн\w*|сильн\w*|слаб\w*|good|bad|ok|okay|strong|weak)\s*\?",
    re.IGNORECASE,
)
# Kept for older imports: both names now mean the one rule.
_QUESTION = HYPOTHETICAL = _IDEA


def is_idea(text: str) -> bool:
    """*text* asks what a move would do rather than plays it."""
    return bool(_IDEA.search(text or ""))


# Squares said aloud («си четыре») and every other spelling of a move: one reading for all paths.
from src.move_text import FILES, spoken_squares  # noqa: E402,F401 — spoken_squares re-exported


def game_wish(text: str) -> dict:
    """The colour and strength the words name, whatever they ask for: {"color"?, "elo"?}."""
    t = (text or "").replace("ё", "е").replace("Ё", "Е")
    out = {}
    if _BLACK.search(t):
        out["color"] = "black"
    elif _WHITE.search(t):
        out["color"] = "white"
    elo = _ELO.search(t)
    if elo:
        out["elo"] = int(elo.group(1))
    return out


def game_request(text: str) -> Optional[dict]:
    """{"color", "elo"} when *text* asks the coach for a game, else None."""
    t = (text or "").replace("ё", "е").replace("Ё", "Е")
    if not _PLAY.search(t):
        return None
    color = "black" if _BLACK.search(t) else "white"
    elo = _ELO.search(t)
    return {"color": color, "elo": int(elo.group(1)) if elo else None}


# «конь f3», «ферзём h5», "knight f3": a piece word and a square, said as the move to play (the move
# reader takes «конь f3» for a description of the board — «конь f3 висит» — in a question).
_PIECE_WORDS = {"кон": chess.KNIGHT, "слон": chess.BISHOP, "лад": chess.ROOK, "ферз": chess.QUEEN,
                "корол": chess.KING, "knight": chess.KNIGHT, "bishop": chess.BISHOP, "rook": chess.ROOK,
                "queen": chess.QUEEN, "king": chess.KING, "ат": chess.KNIGHT, "піл": chess.BISHOP,
                "тура": chess.ROOK, "уәзір": chess.QUEEN, "патша": chess.KING}
_PIECE_TO = re.compile(r"(?<![\w-])(кон\w*|слон\w*|лад\w*|ферз\w*|корол\w*|knight|bishop|rook|queen|king|"
                       r"ат|піл\w*|тура\w*|уәзір\w*|патша\w*),?\s+(?:на\s+|to\s+)?([a-hабвсцдеэфгх])\s*([1-8])(?![\w-])",
                       re.IGNORECASE)
_LATIN = FILES


def bare_move(text: str, board: chess.Board) -> Optional[str]:
    """The student's move written on its own («е4», «конь f3», «беру на d5»), in SAN — None for a
    question about a move or for words that are not one legal move."""
    from src.tools.game_play import _student_move

    t = spoken_squares((text or "").strip().rstrip(".!"))
    if not t or is_idea(t) or len(t.split()) > 6:
        return None
    m = _PIECE_TO.search(t)
    if m:
        word = m.group(1).lower()
        ptype = next((v for k, v in _PIECE_WORDS.items() if word.startswith(k)), None)
        to = chess.parse_square(_LATIN.get(m.group(2).lower(), m.group(2).lower()) + m.group(3))
        fits = [mv for mv in board.legal_moves if mv.to_square == to and board.piece_type_at(mv.from_square) == ptype]
        if len(fits) == 1:
            return board.san(fits[0])
    return _student_move(board, t)


# What the game's buttons do, said in words (2026-10-13: «Сдаюсь» was talked out of, «Ой, верни ход назад» got
# «в партии отмены не бывает», «Давай начнём заново» got «считай, что предыдущая аннулирована» with the old
# game still on the board). Short messages only: «сдаюсь, покажи решение» on a puzzle is no game command.
_COMMANDS = (
    ("takeback", re.compile(
        r"(?<![\w-])(?:верн\w*\s+(?:мой\s+|мне\s+|пожалуйста\s+)?(?:ход|назад)|отмен\w*\s+(?:мой\s+|последний\s+)?ход"
        r"|(?:можно|дай(?:те)?|давай)\s+переход\w*|перехожу|переходить|ход\s+назад"
        r"|take\s*(?:it\s+)?back|undo(?:\s+(?:my\s+|the\s+|last\s+)?move)?"
        r"|жүрісті\s+қайтар\w*|қайтар\w*\s+жүріс\w*)", re.IGNORECASE)),
    ("restart", re.compile(
        r"(?<![\w-])(?:(?:начн\w*|начать|давай)\s+(?:лучше\s+)?(?:вс[её]\s+)?(?:заново|сначала|с\s+начала)"
        r"|(?:давай|начн\w*|начать|сыгра\w*|хочу)\s+(?:лучше\s+|ещ[её]\s+)?нов\w+\s+парти\w*|^нов\w+\s+парти\w*\s*[.!]?$"
        r"|(?:сыгра\w*|ещ[её])\s+(?:ещ[её]\s+)?(?:раз|одну|партию)|ещ[её]\s+партию|реванш"
        r"|new\s+game|start\s+(?:over|again|a\s+new\s+game)|play\s+again|rematch"
        r"|жаңа\s+ойын|қайта\s+бастай\w*)", re.IGNORECASE)),
    ("resign", re.compile(
        r"(?<![\w-])(?:(?:я\s+)?сда[юё]\w*|сдаться|сдалс\w*|i\s+resign|resign|i\s+give\s+up"
        r"|берілемін|жеңілдім)(?![\w-])", re.IGNORECASE)),
    ("draw", re.compile(
        r"(?<![\w-])(?:предлага\w*\s+ничь\w*|(?:давай|согласен\s+на|согласишься\s+на|может)\s+ничь\w*|^ничью\s*[?!.]?$"
        r"|(?:i\s+)?offer\s+(?:you\s+)?(?:a\s+)?draw|let'?s\s+(?:call\s+it\s+a\s+)?draw|тең\s+ойын\w*\s+ұсын\w*)",
        re.IGNORECASE)),
)


def game_command(text: str) -> Optional[str]:
    """«resign» | «takeback» | «restart» | «draw» when a short message asks the game for that, else None."""
    t = (text or "").replace("ё", "е").replace("Ё", "Е").strip()
    if not t or len(t.split()) > 8:
        return None
    for name, rx in _COMMANDS:
        if rx.search(t):
            return name
    return None


# A move written to be played that is no legal move: «Кe5» from the start, «конь d5» with no knight there.
_MOVE_LIKE = re.compile(
    r"^(?:[КСЛФKQRBN]р?|кр)?[a-hасе]?[1-8]?[x:-]?[a-hасе][1-8](?:=?[QRBNФЛСК])?[+#!?]*$"
    r"|^(?:кон\w*|слон\w*|лад\w*|ферз\w*|корол\w*|пешк\w*|knight|bishop|rook|queen|king|pawn)\s+(?:на\s+|to\s+)?[a-hасе][1-8]$",
    re.IGNORECASE,
)


def move_attempt(text: str) -> bool:
    """*text* is written as one move to play (legal or not)."""
    return bool(_MOVE_LIKE.match((text or "").strip().rstrip(".!")))
