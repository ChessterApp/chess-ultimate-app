"""The board lock: when a tool may not replace the position in front of the student.

One rule for the text coach's turn (src/server.py) and for the voice coach's tool calls
(src/tool_bridge.py, from the student's last words): before 2026-10-12 the voice calls had no
lock, and a «почему здесь связка?» could put the knowledge base's example over the student's
position — the text coach's bug of 2026-10-06, fixed there only.
"""

import re
from typing import Optional

import chess

# The student asks about the position in front of them…
_ABOUT_POSITION = re.compile(
    r"(?<![а-яa-z])(?:ход\w*|реши\w*|решени\w*|задач\w*|лучш\w*|играть|сыграть|сыграю|оцени\w*|позици(?!онн)\w*|"
    r"здесь|тут|в\s+этой\s+позиции|move|moves|solve|solution|puzzle|best|play|position|here|жүріс\w*|есеп\w*|осы\s+жерде)"
    r"(?![а-яa-z])", re.IGNORECASE)
# …unless they ask for something new on the board (an example, a puzzle, a line).
_WANTS_NEW_BOARD = re.compile(
    r"(?<![а-яa-z])(?:покажи|пример\w*|что\s+такое|объясни\s+тем\w*|загрузи|поставь|расставь|дай\s+(?:мне\s+)?(?:ещё\s+|новую\s+)?задач\w*|"
    r"другую\s+задач\w*|следующ\w+\s+задач\w*|show\s+me|example|load|set\s+up|give\s+me\s+a(?:nother)?\s+puzzle|"
    r"what\s+is\s+an?\b)(?![а-яa-z])", re.IGNORECASE)
# …or a new puzzle in their own words: «Дай мне тактическую задачу», «можно ещё одну задачу?»,
# «Give me a tactical puzzle», «Маған тактикалық есеп бер» (the site's own chips, production
# 2026-10-09: the adjective kept _WANTS_NEW_BOARD from matching, the board stayed as it was and
# the coach said «задача уже на доске»). Not «дай подсказку к задаче», not «эту задачу».
_NEW_PUZZLE_NOUN = (r"(?:задач(?:у|и|ку|ки)|задани[еяй]|упражнени[еяй]|пазл\w*|головоломк[уи]|"
                    r"puzzles?|exercises?|tasks?|есеп\w*|жаттығу\w*)")
_PUZZLE_SKIP_WORD = (r"(?!(?:эт\w*|тот|ту|this|that|the|осы|подсказк\w*|намёк\w*|hint\w*|решени\w*|"
                     r"ответ\w*|к|по|в|о|об|для|про)(?![\w-]))[\w-]+")
_WANTS_NEW_PUZZLE = re.compile(
    r"(?<![\w-])(?:дай\w*|давай(?:те)?|хочу|хотел\w*|подбери\w*|предложи\w*|найди\w*|пришли\w*|загадай\w*|"
    r"покажи\w*|ещё|еще|нов(?:ую|ые|ое|ая)|друг(?:ую|ие|ое|ая)|следующ\w+|какую-нибудь|любую|"
    r"give|want|find|send|show|another|new|next|тағы|жаңа|басқа)"
    rf"(?:\s+{_PUZZLE_SKIP_WORD}){{0,3}}?\s+{_NEW_PUZZLE_NOUN}(?![\w-])"
    rf"|(?<![\w-]){_NEW_PUZZLE_NOUN}(?:\s+{_PUZZLE_SKIP_WORD}){{0,2}}?\s+бер\w*",
    re.IGNORECASE)
# The daily plan's warm-up card (17.11): «Разминка: дай мне 5 разных тактических задач по моему уровню.», "Warm-up:
# give me 5 different tactical puzzles at my level.", «Жаттығу: маған деңгейіме сай 5 түрлі тактикалық есеп бер.» —
# a warm-up word, a word that asks and the puzzles themselves, in any order. The card used to send the generic
# «Дай мне тактическую задачу», which is the next task of the student's programme: a beginner got five near-identical
# rook mates of one set (tester, 16.11). The warm-up is a mixed set at the student's level instead
# (src/tools/puzzles.warmup_puzzles). «Жаттығу» is also Kazakh for an exercise, so here the puzzle word is another
# one («есеп»): «маған жаттығу бер» stays the plain request. Not a hint or the solution of the puzzle in front of
# the student («дай подсказку к этой задаче из разминки»).
_WARMUP_WORD = re.compile(r"(?<![\w-])(?:разминк\w*|warm[\s-]?ups?|жаттығу\w*)(?![\w-])", re.IGNORECASE)
_WARMUP_PUZZLES = re.compile(r"(?<![\w-])(?:задач\w*|задани\w*|упражнени\w*|пазл\w*|головоломк\w*|puzzles?|exercises?|"
                             r"tasks?|есеп\w*)(?![\w-])", re.IGNORECASE)
_WARMUP_ASKS = re.compile(r"(?<![\w-])(?:дай\w*|давай(?:те)?|хочу|хотел\w*|подбери\w*|предложи\w*|найди\w*|пришли\w*|"
                          r"покажи\w*|нужн\w+|можно|give|want|find|send|show|need|let'?s|бер\w*|керек)(?![\w-])",
                          re.IGNORECASE)
_WARMUP_NOT = re.compile(r"(?<![\w-])(?:подсказк\w*|нам[её]к\w*|hints?|решени\w*|ответ\w*|solutions?|answers?|шешім\w*|"
                         r"жауа\w*|(?:эт\w*|ту|той|this|that|осы)\s+(?:задач\w*|задани\w*|упражнени\w*|puzzle|task|"
                         r"exercise|есеп\w*))(?![\w-])", re.IGNORECASE)


# «Ещё разминку», «давай новую разминку», "another warm-up, please" (18.11): the coach offers it when a warm-up ends
# (src/warmup.py), so the answer to the offer is read as one. The word that says «one more» stands right by the
# warm-up word and is the request itself: «разминка — это полезно, дай ещё совет» asks for none. Not in Kazakh:
# «тағы бір жаттығу бер» is «one more exercise» — the plain request, as «маған жаттығу бер».
_WARMUP_AGAIN = re.compile(
    r"(?<![\w-])(?:(?:ещ[её]|снова|опять|нов(?:ую|ая)|втор(?:ую|ая)|повтори\w*|another|new|one\s+more)"
    r"(?:\s+(?:одн[ау]|раз|a))?\s+(?:разминк\w*|warm[\s-]?ups?)"
    r"|(?:разминк\w*|warm[\s-]?ups?)\s+(?:ещ[её]\s+раз|снова|заново|again))(?![\w-])", re.IGNORECASE)


def asks_warmup(text: str) -> bool:
    """The student asks for a warm-up of puzzles — the daily plan's card, or the same in their own words; or for one
    more warm-up («ещё разминку»)."""
    t = text or ""
    if not _WARMUP_WORD.search(t) or _WARMUP_NOT.search(t):
        return False
    return bool(_WARMUP_PUZZLES.search(t) and _WARMUP_ASKS.search(t)) or bool(_WARMUP_AGAIN.search(t))


def wants_new_puzzle(text: str) -> bool:
    """The words ask for a puzzle that is not on the board yet: a new one (``_WANTS_NEW_PUZZLE``) or a warm-up of
    them. One reading for the intent, the board lock and the turn's puzzle step."""
    t = text or ""
    return bool(_WANTS_NEW_PUZZLE.search(t)) or asks_warmup(t)


# The default board is nothing of the student's to keep: the start position, an empty board.
_DEFAULT_BOARDS = frozenset({chess.STARTING_BOARD_FEN, "8/8/8/8/8/8/8/8"})
# The question points at the board in front of the student — then nothing replaces it, not even a
# puzzle: the coach answered «Задача из урока … Какой здесь первый ход?» with get_puzzle in 3 of
# 1620 production turns. Words that only touch on a move or a puzzle («Есть задачка на мат в два?»,
# «как ходит конь») lock out the examples of get_topic/get_lesson, not a puzzle (2026-10-09).
_BOARD_WORDS = (
    r"(?<![\w-])(?:здесь|тут|сейчас|эт(?:а|у|ой|от|ом|и|их|им)\s+(?:[\w-]+\s+)?(?:позици\w*|задач\w*|ход\w*|доск\w*|"
    r"парти\w*|вариант\w*)|в\s+этой\s+позиции|из\s+этой\s+позиции|на\s+доске|перв\w+\s+ход\w*|лучш\w+\s+ход\w*|"
    r"следующ\w+\s+ход\w*|чей\s+ход|как(?:ой|ую|им)\s+(?:[\w-]+\s+)?ход\w*|which\s+move|what\s+move|жүріс\w*|"
    r"как\s+(?:мне\s+|белым\s+|ч[её]рным\s+)?(?:выиграть|решить|спастись|защититься)|"
    r"что\s+(?:мне\s+|белым\s+|ч[её]рным\s+)?(?:делать|играть|сыграть)|here|this\s+(?:position|puzzle|move|board)|"
    r"on\s+the\s+board|best\s+move|first\s+move|what\s+should\s+i\s+play|оцени\w*|осы|бұл|мұнда|қазір|бағала\w*)(?![\w-])"
)
_BOARD_SQUARE = (
    r"(?<![\w-])(?:[KQRBNКФЛС]?[a-hасе][1-8]|[KQRBNКФЛС][a-h]?x?[a-h][1-8]|O-O(?:-O)?|0-0(?:-0)?)(?![\w-])"
)
_ABOUT_THIS_BOARD = re.compile(_BOARD_WORDS + "|" + _BOARD_SQUARE, re.IGNORECASE)
_POINTS_WORDS = re.compile(_BOARD_WORDS, re.IGNORECASE)


# The result of the position in front of the student: «Это выигрыш?», «Это ничья?», «Кто выигрывает?», «Белые
# выигрывают?», "Is this a win?", «Мұнда ұтыс па?» (09.10: «Это выигрыш?» had none of the words above, the board
# was free, and the coach answered about a position of its own). The student's position stays, strictly. A
# textbook ending named by its material («ферзь против ладьи — это выигрыш?») is not this board's: it has its own
# position (src/question_position.endgame_theory).
_RESULT_NOUN = (r"(?:выигрыш\w*|выигран\w*|ничь\w*|ничейн\w*|проигрыш\w*|проигран\w*|"
                r"wins?|won|winning|draws?|drawn|lost|losing|ұтыс\w*|жеңіс\w*|тең\s+ойын\w*|ұтылыс\w*)")
_ASKS_RESULT = re.compile(
    r"(?<![\w-])(?:это|здесь|тут|сейчас|позиция|эта\s+позиция|такая\s+позиция|this|it|here|the\s+position|"
    r"мұнда|бұл|осы)(?:\s+(?:is|'s|a|an|ли|уже|всё-таки|все-таки|теоретическ\w+|чист\w+|просто|точно|—|-))*"
    r"\s+" + _RESULT_NOUN + r"(?![\w-])[^.!]*\?"
    r"|(?:^|[.!?]\s*)(?:а\s+|и\s+|так\s+)?(?:кто|белые|ч[её]рные|я|мы|who|white|black|can\s+(?:white|black|i|we))\s+"
    r"(?:(?:тут|здесь|сейчас|here|now|тогда)\s+)?(?:выигрыва\w*|выиграет|выиграют|выиграю|выиграем|проигрыва\w*|"
    r"спас[её]тся|спасутся|спасусь|удерж\w*\s+ничь\w*|wins?|winning|hold\s+(?:the\s+)?draw|draw)"
    r"(?![\w-])[^.!]*\?"
    r"|(?<![\w-])" + _RESULT_NOUN + r"\s+ли\s+(?:это|здесь|тут)(?![\w-])[^.!]*\?",  # «Ничья ли это?»
    re.IGNORECASE)
_OPENING_TALK = re.compile(r"(?<![\w-])(?:дебют\w*|защит\w*|гамбит\w*|вариант\w*|партии|в\s+целом|обычно|opening|defen[cs]e|"
                           r"gambit|variation|in\s+general|usually)(?![\w-])", re.IGNORECASE)


def points_at_board(message: str, squares: bool = True) -> bool:
    """*message* points at the board in front of the student: «тут», «сейчас», «лучший ход» — and, with
    *squares*, a square or a move named on it («ладья на d8?»)."""
    text = re.sub(r"«[^»]*»|\"[^\"]*\"|“[^”]*”", " ", message or "")
    return bool((_ABOUT_THIS_BOARD if squares else _POINTS_WORDS).search(text))


def _asks_result(text: str) -> bool:
    """*text* asks how the position in front of the student ends (see _ASKS_RESULT)."""
    m = _ASKS_RESULT.search(text or "")
    if m is None or _OPENING_TALK.search(text):
        return False
    try:
        from src.question_position import material_in

        if material_in(text):
            return False  # «ферзь против ладьи — это выигрыш?»: the textbook ending, not this board
    except Exception:  # noqa: BLE001 — without the table the question is still about the board
        pass
    return True


def _board_lock_level(message: str, has_fen: bool, live_game: bool, fen: Optional[str],
                      owned: bool = False) -> tuple[Optional[str], bool, str]:
    """(the position to keep on the board this turn or None, whether the lock is strict, why).

    *owned*: the position is the student's own (src/question_position.student_owns). Then it stays
    unless they ask to see something else («покажи», «поставь») — a topic's example or an opening line
    is analysed on a hidden board instead (2026-10-20); a new puzzle still goes up (a plain lock).
    """
    if not fen:
        return None, False, ""
    if live_game:
        return fen, True, "asked"
    if not has_fen or fen.split()[0] in _DEFAULT_BOARDS:
        return None, False, ""
    text = re.sub(r"«[^»]*»|\"[^\"]*\"|“[^”]*”", " ", message or "")  # «Пример 5» is a lesson's name
    if _asks_result(text) and not (_WANTS_NEW_BOARD.search(text) or wants_new_puzzle(text)):
        return fen, True, "asked"
    if _ABOUT_POSITION.search(text) and not (_WANTS_NEW_BOARD.search(text) or wants_new_puzzle(text)):
        return fen, bool(_ABOUT_THIS_BOARD.search(text)), "asked"
    if owned and not wants_new_puzzle(text):
        from src.question_position import wants_shown

        if not wants_shown(text):
            return fen, False, "owned"
    return None, False, ""


def _board_lock_for_turn(message: str, has_fen: bool, live_game: bool, fen: Optional[str]) -> Optional[str]:
    """The position to keep on the board this turn, or None."""
    return _board_lock_level(message, has_fen, live_game, fen)[0]


def board_lock_with_owner(message: str, has_fen: bool, live_game: bool, session) -> tuple[Optional[str], bool, str]:
    """``_board_lock_level`` for a coach session: its active board says whether the position is the student's own."""
    from src.question_position import student_owns

    board = None
    try:
        board = session.get_board(session.active_board_id) if session is not None else None
    except Exception:  # noqa: BLE001
        board = None
    fen = getattr(session, "board_state", None) if session is not None else None
    return _board_lock_level(message, has_fen, live_game, fen, owned=student_owns(board))
