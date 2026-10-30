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
# The default board is nothing of the student's to keep: the start position, an empty board.
_DEFAULT_BOARDS = frozenset({chess.STARTING_BOARD_FEN, "8/8/8/8/8/8/8/8"})
# The question points at the board in front of the student — then nothing replaces it, not even a
# puzzle: the coach answered «Задача из урока … Какой здесь первый ход?» with get_puzzle in 3 of
# 1620 production turns. Words that only touch on a move or a puzzle («Есть задачка на мат в два?»,
# «как ходит конь») lock out the examples of get_topic/get_lesson, not a puzzle (2026-10-09).
_ABOUT_THIS_BOARD = re.compile(
    r"(?<![\w-])(?:здесь|тут|сейчас|эт(?:а|у|ой|от|ом|и|их|им)\s+(?:[\w-]+\s+)?(?:позици\w*|задач\w*|ход\w*|доск\w*|"
    r"парти\w*|вариант\w*)|в\s+этой\s+позиции|из\s+этой\s+позиции|на\s+доске|перв\w+\s+ход\w*|лучш\w+\s+ход\w*|"
    r"следующ\w+\s+ход\w*|чей\s+ход|как(?:ой|ую|им)\s+(?:[\w-]+\s+)?ход\w*|which\s+move|what\s+move|жүріс\w*|"
    r"как\s+(?:мне\s+|белым\s+|ч[её]рным\s+)?(?:выиграть|решить|спастись|защититься)|"
    r"что\s+(?:мне\s+|белым\s+|ч[её]рным\s+)?(?:делать|играть|сыграть)|here|this\s+(?:position|puzzle|move|board)|"
    r"on\s+the\s+board|best\s+move|first\s+move|what\s+should\s+i\s+play|оцени\w*|осы|бұл|мұнда|қазір|бағала\w*)(?![\w-])"
    r"|(?<![\w-])(?:[KQRBNКФЛС]?[a-hасе][1-8]|[KQRBNКФЛС][a-h]?x?[a-h][1-8]|O-O(?:-O)?|0-0(?:-0)?)(?![\w-])",
    re.IGNORECASE)

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
    if _asks_result(text) and not (_WANTS_NEW_BOARD.search(text) or _WANTS_NEW_PUZZLE.search(text)):
        return fen, True, "asked"
    if _ABOUT_POSITION.search(text) and not (_WANTS_NEW_BOARD.search(text) or _WANTS_NEW_PUZZLE.search(text)):
        return fen, bool(_ABOUT_THIS_BOARD.search(text)), "asked"
    if owned and not _WANTS_NEW_PUZZLE.search(text):
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
