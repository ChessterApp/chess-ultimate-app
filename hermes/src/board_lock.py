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


def _board_lock_level(message: str, has_fen: bool, live_game: bool, fen: Optional[str]) -> tuple[Optional[str], bool]:
    """(the position to keep on the board this turn or None, whether the lock is strict)."""
    if not fen:
        return None, False
    if live_game:
        return fen, True
    if not has_fen or fen.split()[0] in _DEFAULT_BOARDS:
        return None, False
    text = re.sub(r"«[^»]*»|\"[^\"]*\"|“[^”]*”", " ", message or "")  # «Пример 5» is a lesson's name
    if _ABOUT_POSITION.search(text) and not (_WANTS_NEW_BOARD.search(text) or _WANTS_NEW_PUZZLE.search(text)):
        return fen, bool(_ABOUT_THIS_BOARD.search(text))
    return None, False


def _board_lock_for_turn(message: str, has_fen: bool, live_game: bool, fen: Optional[str]) -> Optional[str]:
    """The position to keep on the board this turn, or None."""
    return _board_lock_level(message, has_fen, live_game, fen)[0]
