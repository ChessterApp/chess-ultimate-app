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

# The engine's strength, in the site's steps (the «Play the coach» panel's choices), and how the student names
# it in words (voice, 2026-10-15: «с самым сильным ботом», «играй сильнее», «сделай посложнее», «уровень 2500»
# were nothing — only a number in a request for a game was read). A number wins; then a step up or down from
# the current level («посложнее», «полегче»); then a named level («самый сильный», «как новичок»).
STRENGTHS = (600, 800, 1000, 1200, 1500, 1800, 2000, 2200, 2500)
DEFAULT_STRENGTH = 1200
_STRENGTH_UP = re.compile(
    r"(?<![\w-])(?:(?:по)?сильнее|(?:по)?сложнее|(?:по)?трудне\w*|труднее|повыше|выше|покрепче|stronger|harder|tougher|higher"
    r"|күштірек|қиынырақ)(?![\w-])", re.IGNORECASE)
_STRENGTH_DOWN = re.compile(
    r"(?<![\w-])(?:(?:по)?слабее|(?:по)?легче|(?:по)?проще|пониже|ниже|помягче|weaker|easier|lower|softer|әлсізірек|оңайырақ"
    r"|жеңілірек)(?![\w-])", re.IGNORECASE)
_STRENGTH_NAMED = (
    (2500, re.compile(r"(?<![\w-])(?:сам\w*\s+сильн\w*|максимальн\w*|на\s+максимум\w*|максимум|гроссмейстер\w*"
                      r"|как\s+чемпион\w*|в\s+полную\s+силу|strongest|max(?:imum)?|grandmaster|full\s+strength"
                      r"|ең\s+күшті)(?![\w-])", re.IGNORECASE)),
    (600, re.compile(r"(?<![\w-])(?:сам\w*\s+(?:слаб\w*|легк\w*|прост\w*)|совсем\s+(?:слаб\w*|легк\w*|прост\w*)"
                     r"|как\s+(?:ребен\w*|новичок|новичк\w*)|на\s+минимум\w*|минимальн\w*|weakest|easiest"
                     r"|ең\s+(?:әлсіз|оңай))(?![\w-])", re.IGNORECASE)),
    (2200, re.compile(r"(?<![\w-])(?:мастер\w*|очень\s+сильн\w*|very\s+strong|master|expert)(?![\w-])",
                      re.IGNORECASE)),
    (800, re.compile(r"(?<![\w-])(?:слаб\w*|легк\w*|прост\w*|новичк\w*|новичок|начинающ\w*|поддавайся|не\s+сильно"
                     r"|easy|weak|beginner|novice|әлсіз|оңай)(?![\w-])", re.IGNORECASE)),
    (2000, re.compile(r"(?<![\w-])(?:сильн\w*|серьезн\w*|strong|hard|difficult|күшті)(?![\w-])", re.IGNORECASE)),
    (1500, re.compile(r"(?<![\w-])(?:средн\w*|нормальн\w*|обычн\w*|клубн\w*|medium|average|normal|орташа)(?![\w-])",
                      re.IGNORECASE)),
)


def strength_in_words(text: str, current: Optional[int] = None) -> Optional[int]:
    """The engine strength the words ask for, in the site's steps: a number, a step up or down from *current*
    («посложнее», «полегче»), or a named level («самый сильный», «как новичок»); None when they name none."""
    t = (text or "").replace("ё", "е").replace("Ё", "Е")
    m = _ELO.search(t)
    if m:
        return min(STRENGTHS, key=lambda s: abs(s - int(m.group(1))))
    up, down = bool(_STRENGTH_UP.search(t)), bool(_STRENGTH_DOWN.search(t))
    if up != down:
        base = current or DEFAULT_STRENGTH
        i = min(range(len(STRENGTHS)), key=lambda k: abs(STRENGTHS[k] - base)) + (1 if up else -1)
        return STRENGTHS[max(0, min(len(STRENGTHS) - 1, i))]
    for elo, rx in _STRENGTH_NAMED:
        if rx.search(t):
            return elo
    return None
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


def game_wish(text: str, current_elo: Optional[int] = None) -> dict:
    """The colour and strength the words name, whatever they ask for: {"color"?, "elo"?}. A relative strength
    («посложнее») is a step from *current_elo* (the game's, when one is on)."""
    t = (text or "").replace("ё", "е").replace("Ё", "Е")
    out = {}
    if _BLACK.search(t):
        out["color"] = "black"
    elif _WHITE.search(t):
        out["color"] = "white"
    elo = strength_in_words(t, current_elo)
    if elo is not None:
        out["elo"] = elo
    return out


def game_request(text: str) -> Optional[dict]:
    """{"color", "elo"} when *text* asks the coach for a game, else None."""
    t = (text or "").replace("ё", "е").replace("Ё", "Е")
    if not _PLAY.search(t):
        return None
    color = "black" if _BLACK.search(t) else "white"
    return {"color": color, "elo": strength_in_words(t)}


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
# The commands a long sentence may carry (up to _LONG_COMMAND_WORDS words): «Верни партию на два хода назад, до
# того как я сходил конём» (Alexander's list, 26.10). The short ones below keep their 8-word limit: «предлагаю
# ничью» inside a 13-word question is a question, not an offer.
_LONG_COMMANDS = (
    # «ты ошибся», «это не мой ход», «верни как было»: the system misread the student's move, or moved wrong —
    # the last move is undone and the student is asked what they meant (item 5 of the list).
    ("mistake", re.compile(
        r"(?<![\w-])(?:ты\s+(?:ошиб\w*|не\s+тот\s+ход|неправильно|не\s+так\s+(?:понял\w*|сходил\w*|поставил\w*))"
        r"|(?:ты|вы)\s+сделал\w*\s+не\s+тот|это\s+не\s+мой\s+ход|я\s+так\s+не\s+ходил\w*|я\s+не\s+это\s+(?:сказал|говорил)\w*"
        r"|верни\s+(?:вс[её]\s+)?как\s+было|not\s+my\s+move|you\s+(?:made\s+a\s+mistake|got\s+it\s+wrong|misheard)"
        r"|that(?:'s|\s+is)\s+(?:the\s+)?wrong\s+move|қате\s+жүрді\w*)(?![\w-])", re.IGNORECASE)),
    # «продолжим отсюда», «давай играть с этой позиции»: the game goes on from the position the student is
    # looking at (its record cut there) — only when they say so (item 4).
    ("continue_here", re.compile(
        r"(?<![\w-])(?:(?:продолж\w*|игра\w*|сыграем|давай|поиграем)\s+(?:партию\s+|играть\s+|играем\s+)?"
        r"(?:отсюда|с\s+этого\s+места|с\s+этой\s+позиции|с\s+текущей\s+позиции|с\s+этого\s+хода|с\s+этой\s+точки)"
        r"|(?:continue|play|go\s+on)\s+from\s+here|осы\s+жерден\s+жалғаст\w*)(?![\w-])", re.IGNORECASE)),
    # «вернись к партии», «покажи текущую позицию»: the board shows the game's latest position again (item 8).
    ("view_live", re.compile(
        r"(?<![\w-])(?:(?:верн\w*|вернемся|назад|покажи|обратно)\s+(?:к\s+партии|к\s+игре|в\s+партию|в\s+игру|(?:к\s+|на\s+)?текущ\w+\s+позици\w*"
        r"|(?:к\s+|на\s+)?последн\w+\s+позици\w*|(?:к\s+|в\s+)?конц\w*\s+партии|(?:к\s+|на\s+)?живую\s+позицию)|back\s+to\s+the\s+game"
        r"|(?:the\s+)?current\s+position|ойынға\s+қайт\w*)(?![\w-])", re.IGNORECASE)),
    # «покажи позицию после 10-го хода», «отмотай на три хода назад посмотреть», «покажи, как было до моего хода
    # конём»: the board shows an earlier position; the game itself goes on (items 4 and 8).
    ("view", re.compile(
        r"(?<![\w-])(?:покажи|посмотрим|посмотреть|открой|перемотай|отмотай|промотай|пролистай|хочу\s+посмотреть|давай\s+посмотрим"
        r"|show\s+(?:me\s+)?|rewind|go\s+back\s+to)\w*\s*(?:мне\s+)?(?:позици\w*|как\s+было|партию|the\s+position|move)?"
        r"[^.!?]{0,40}?(?:после|до|на|к|перед|after|before|to)\s+[^.!?]{0,30}?(?:ход\w*|move\w*|начал\w*|start)(?![\w-])",
        re.IGNORECASE)),
    ("takeback", re.compile(
        r"(?<![\w-])(?:верн\w*\s+(?:мой\s+|мне\s+|пожалуйста\s+)?(?:ход|назад)|отмен\w*\s+(?:[\w-]+\s+){0,3}?ход\w*"
        r"|верн\w*\s+(?:партию|позицию|игру|все|всё)\s+(?:на\s+)?[^.!?]{0,20}?(?:ход\w*|назад)|(?:на\s+)?(?:\d+|\w+)\s+ход\w*\s+назад"
        r"|верн\w*[^.!?]{0,25}?\d+\s*-?\s*(?:го|му|й|ому)?\s*ход\w*|^(?:до|перед)\s+(?:того\s+как\s+)?(?:я\s+)?(?:сходил|пошел|походил|сыграл)\w*"
        r"|верн\w*[^.!?]{0,20}?(?:в\s+начало|к\s+началу|на\s+начало)"
        r"|(?:можно|дай(?:те)?|давай)\s+переход\w*|перехожу|переходить|ход\s+назад|откат\w*|отмотай\s+(?:партию\s+)?назад"
        r"|take\s*(?:it\s+)?back|undo(?:\s+(?:my\s+|the\s+|last\s+)?(?:\w+\s+)?moves?)?"
        r"|жүрісті\s+қайтар\w*|қайтар\w*\s+жүріс\w*)", re.IGNORECASE)),
)
_LONG_COMMAND_WORDS = 16

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
    # «играй сильнее», «сделай посложнее», «поставь уровень 2500», «полегче» — the engine's strength changed for the
    # rest of the game (2026-10-15: nothing understood, the student could not change the level by voice). Last in
    # the list: «сыграем ещё раз, посложнее» is a restart (with the strength), not a level change.
    ("resign", re.compile(
        r"(?<![\w-])(?:(?:я\s+)?сда[юё]\w*|сдаться|сдалс\w*|i\s+resign|resign|i\s+give\s+up"
        r"|берілемін|жеңілдім)(?![\w-])", re.IGNORECASE)),
    ("draw", re.compile(
        r"(?<![\w-])(?:предлага\w*\s+ничь\w*|(?:давай|согласен\s+на|согласишься\s+на|может)\s+ничь\w*|^ничью\s*[?!.]?$"
        r"|(?:i\s+)?offer\s+(?:you\s+)?(?:a\s+)?draw|let'?s\s+(?:call\s+it\s+a\s+)?draw|тең\s+ойын\w*\s+ұсын\w*)",
        re.IGNORECASE)),
    ("level", re.compile(
        r"(?<![\w-])(?:(?:играй|сыграй|поставь|ставь|сделай|давай|можно|можешь|хочу|включи|выстави|поменяй|смени)\s+"
        r"(?:бота\s+|бот\s+|уровень\s+|сложность\s+|силу\s+|чуть\s+|немного\s+|пожалуйста\s+|мне\s+|играть\s+"
        r"|сыграть\s+|ты\s+)*"
        r"(?:(?:по)?сильнее|(?:по)?слабее|(?:по)?сложнее|(?:по)?легче|(?:по)?проще|сильно|слабо|сложнее|легче|проще|на\s+максимум\w*"
        r"|максимально|на\s+минимум\w*|на\s+\d{3,4}|уровень|уровня|рейтинг|силу|сложность|как\s+гроссмейстер\w*"
        r"|как\s+новичок|как\s+мастер\w*)"
        r"|(?:уровень|сила|сложность|рейтинг)\s*(?:бота\s*|движка\s*|соперника\s*)?(?:\d{3,4}|(?:по)?сложнее|(?:по)?легче"
        r"|выше|ниже|сильнее|слабее|максимум\w*|минимум\w*)"
        r"|^(?:(?:по)?сложнее|(?:по)?легче|(?:по)?проще|(?:по)?сильнее|(?:по)?слабее|сильнее|слабее)\s*[.!,]?\s*(?:пожалуйста\s*[.!]?)?$"
        r"|play\s+(?:a\s+bit\s+|much\s+|more\s+)?(?:stronger|weaker|harder|easier)|(?:set|change|make\s+it)\s+"
        r"(?:the\s+)?(?:level|strength|rating|difficulty|harder|easier)|^(?:harder|easier|stronger|weaker)\s*[.!]?$"
        r"|level\s+\d{3,4}"
        r"|(?:күштірек|әлсізірек|қиынырақ|оңайырақ)\s+ойна\w*|деңгей\w*\s+\d{3,4})", re.IGNORECASE)),
)


# «Я хотел не конь за шесть, а с шесть пойти пешкой», «не тот ход, я имел в виду пешку на c6», «вместо
# этого слон c4»: the student corrects the move just played (Alexander's phone, 25.10 — nobody could do
# that by voice: it is a takeback and the move they meant).
_CORRECT = re.compile(
    r"(?<![\w-])(?:я\s+хотел\w*\s+не(?![\w-])|не\s+(?:кон|слон|лад|ферз|корол|пешк)\w*,?\s+а(?![\w-])|имел\w*\s+в\s+виду|"
    r"не\s+тот\s+ход|не\s+т[ауою]\s+(?:фигур|ход)\w*|вместо\s+(?:этого|него|не[её])|i\s+meant|not\s+that\s+move|"
    r"instead\s+of\s+that|wrong\s+piece)(?![\w-])", re.IGNORECASE)
_CORRECT_SPLIT = re.compile(r",?\s+а\s+(?!не\b)|имел\w*\s+в\s+виду\s+|хотел\w*\s+(?:сказать\s+|пойти\s+|сыграть\s+|ходить\s+)?|"
                            r"вместо\s+(?:этого|него|не[её])\s+|i\s+meant\s+|instead\s+of\s+that\s+", re.IGNORECASE)
_TAKEBACK_WORD = re.compile(r"верн[иу]|отмен|назад|take\s*back|undo", re.IGNORECASE)
_MEANT = re.compile(r"(?<![\w-])(?:хотел\w*|имел\w*\s+в\s+виду|meant)(?![\w-])", re.IGNORECASE)


def corrects_move(text: str) -> bool:
    """«Не конь, а пешка на c6», «я хотел не …, а …», «верни ход, я хотел пешкой на c6», «имел в виду …»."""
    t = (text or "").replace("ё", "е")
    if len(t.split()) > 14:
        return False
    return bool(_CORRECT.search(t)) or bool(_TAKEBACK_WORD.search(t) and _MEANT.search(t))


def correction_move(text: str, board: chess.Board) -> Optional[str]:
    """The move the student meant, read from the words after «а» / «хотел» / «имел в виду» on *board* (the
    position before the move being corrected), in SAN; None when no single legal move is named there."""
    from src.tools.game_play import _student_move

    t = spoken_squares((text or "").replace("ё", "е").strip().rstrip(".!"))
    parts = _CORRECT_SPLIT.split(t)
    tail = parts[-1].strip() if len(parts) > 1 else t
    tail = re.sub(r"(?<![\w-])(?:пойти|сыграть|ходить|походить|сходить|пешкой|конем|слоном|ладьей|ферзем|королем|на)(?![\w-])", " ", tail)
    tail = re.sub(r"\s+", " ", tail).strip()
    if not tail:
        return None
    san = bare_move(tail, board)
    if san:
        return san
    # «с шесть пойти пешкой» → c6: a square alone, when exactly one legal move goes there — a pawn's when a pawn is named
    squares = re.findall(r"(?<![\w-])([a-h][1-8])(?![\w-])", tail)
    pawn = bool(re.search(r"пешк\w*|pawn", (text or ""), re.IGNORECASE))
    if len(squares) == 1:
        to = chess.parse_square(squares[0])
        fits = [mv for mv in board.legal_moves if mv.to_square == to and (not pawn or board.piece_type_at(mv.from_square) == chess.PAWN)]
        if len(fits) == 1:
            return board.san(fits[0])
    return _student_move(board, tail)


def game_command(text: str) -> Optional[str]:
    """«resign» | «takeback» | «restart» | «draw» | «correct» when a short message asks the game for that, else None."""
    t = (text or "").replace("ё", "е").replace("Ё", "Е").strip()
    if corrects_move(t):
        return "correct"
    if t and len(t.split()) <= _LONG_COMMAND_WORDS:
        for name, rx in _LONG_COMMANDS:
            if rx.search(t):
                return name
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


# ── where to cut the game back to, or which position to look at, in words (26.10) ──────────
_NUM_WORDS = {"один": 1, "одного": 1, "одна": 1, "два": 2, "две": 2, "двух": 2, "три": 3, "трех": 3, "четыре": 4, "четырех": 4,
              "пять": 5, "пяти": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "one": 1, "two": 2,
              "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
_COUNT_BACK = re.compile(r"(?<![\w-])(?:на\s+)?(\d{1,2}|один|одного|одну|два|две|двух|три|трех|четыре|четырех|пять|пяти|шесть|семь|восемь|девять|десять"
                         r"|one|two|three|four|five|six|seven|eight)\s+(?:последн\w+\s+|моих\s+|своих\s+)?(?:ход\w*|moves?)(?![\w-])", re.IGNORECASE)
_MOVE_NUMBER = re.compile(r"(?<![\w-])(после|до|к|на|перед|after|before|to)\s+(\d{1,3})\s*-?\s*(?:го|й|му|ому|ого|ый|th|st|nd|rd)?\s*(?:ход\w*|move\w*)(?![\w-])",
                          re.IGNORECASE)
_MY_MOVE = re.compile(r"(?<![\w-])(после|до|перед|after|before)\s+(?:того\s+как\s+)?(?:я\s+|мо\w+\s+)?(?:сходил\w*|пошел|пошла|походил\w*|ход\w*|сыграл\w*|поставил\w*|played|moved|move)?"
                      r"\s*(?:мо\w+\s+)?(кон\w*|слон\w*|ладь\w*|ферз\w*|корол\w*|пешк\w*|knight|bishop|rook|queen|king|pawn)?\s*(?:на\s+|to\s+|on\s+)?([a-h][1-8])?(?![\w-])",
                      re.IGNORECASE)
_TO_START = re.compile(r"(?<![\w-])(?:(?:до|в|к|на)\s+(?:самого\s+|самое\s+)?начал\w*|с\s+начала|с\s+самого\s+начала|to\s+the\s+start|from\s+the\s+start)(?![\w-])",
                       re.IGNORECASE)
_PIECE_LETTER = {"кон": "N", "слон": "B", "ладь": "R", "ферз": "Q", "корол": "K", "пешк": "P", "knight": "N", "bishop": "B", "rook": "R",
                 "queen": "Q", "king": "K", "pawn": "P"}


def _student_ply_of(state: dict, piece: Optional[str], square: Optional[str]) -> Optional[tuple[int, str]]:
    """The ply and SAN of the student's last move by *piece* and/or to *square*, from the record's annotations."""
    letter = None
    if piece:
        key = next((k for k in _PIECE_LETTER if piece.lower().startswith(k)), None)
        letter = _PIECE_LETTER.get(key) if key else None
    for a in reversed(state.get("annotations") or []):
        san = (a.get("san") or "").rstrip("+#!?")
        if square and not san.replace("=", "").endswith(square) and not re.search(rf"{square}(?:=[QRBN])?$", san):
            continue
        if letter == "P" and not re.match(r"^[a-h]", san):
            continue
        if letter and letter != "P" and not san.startswith(letter):
            if not (letter == "K" and san.startswith("O-O")):
                continue
        return int(a["ply"]), a.get("san") or ""
    return None


def cut_target(text: str, state: dict, *, default_count: int = 1) -> dict:
    """{"ply": int, "why": str}: the ply to cut the game back to for a takeback — «на два хода назад» (the student's
    last two moves), «до 10-го хода» (before White's 10th), «до того как я сходил конём» / «до хода на e4», «до
    начала»; with none of those, the last *default_count* student moves."""
    t = spoken_squares((text or "").replace("ё", "е"))
    moves = state.get("moves") or []
    student_plies = [int(a["ply"]) for a in state.get("annotations") or []]
    if _TO_START.search(t):
        return {"ply": 0, "why": "the start of the game"}
    m = _MOVE_NUMBER.search(t)
    if m:
        n = int(m.group(2))
        if m.group(1).lower() in ("после", "after"):
            return {"ply": min(len(moves), 2 * n), "why": f"after move {n}"}
        return {"ply": max(0, min(len(moves), 2 * (n - 1))), "why": f"before move {n}"}
    m = _MY_MOVE.search(t)
    if m and (m.group(2) or m.group(3)):
        found = _student_ply_of(state, m.group(2), m.group(3))
        if found is not None:
            ply, san = found
            if m.group(1).lower() in ("после", "after"):
                return {"ply": ply, "why": f"after the student's move {san} (ply {ply})"}
            return {"ply": ply - 1, "why": f"before the student's move {san} (ply {ply})"}
    m = _COUNT_BACK.search(t)
    count = default_count
    if m:
        raw = m.group(1).lower()
        count = int(raw) if raw.isdigit() else _NUM_WORDS.get(raw, default_count)
    if not student_plies:
        return {"ply": 0, "why": "the start of the game"}
    count = max(1, min(count, len(student_plies)))
    return {"ply": student_plies[-count] - 1, "why": f"the student's last {count} move(s)"}


def view_target(text: str, state: dict) -> dict:
    """{"ply": int, "why": str}: the position to show — the same words as cut_target, but «на N ходов назад» counts
    whole moves of both sides back from the end, and «покажи, как было после моего хода конём» lands after it."""
    t = spoken_squares((text or "").replace("ё", "е"))
    moves = state.get("moves") or []
    m = _COUNT_BACK.search(t)
    if m and not _MOVE_NUMBER.search(t) and not _MY_MOVE.search(t) and not _TO_START.search(t):
        raw = m.group(1).lower()
        count = int(raw) if raw.isdigit() else _NUM_WORDS.get(raw, 1)
        return {"ply": max(0, len(moves) - 2 * count), "why": f"{count} move(s) back from the end"}
    return cut_target(text, state, default_count=1)
