"""The coach points the student at the board while nothing of what it describes is on it.

Alexander's phone, voice, 10.11: with the untouched start position on the board the coach said «Отлично, смотри на
доску. Шах — это когда на твоего короля нападают. Видишь, белого короля атакует чёрная ладья? У тебя есть три…» — a
demonstration that was never put on the board (it was retelling the book's picture, src/lesson_texts.UNSEEN_PICTURE).
The board checks read a claim against the turn's boards and leave the bare start position out of them: a coach talking
theory over it is not describing it. This reads the one case they leave open — and it needs no reading of the claim
itself, only three facts:

  the board is nobody's   the start position or an empty board: no piece attacks a piece, no king is in check and
                          nothing can be taken there, so any such thing told as standing on it is false;
  the coach points at it  «смотри на доску», «видишь», «на диаграмме», "look at the board", «тақтаға қара» — in this
                          sentence or in the two before it in the same answer;
  the sentence tells a    a check, a mate, an attack on a piece, a piece under attack, a pin, a capture there is — in
  contact as standing     the present, not as a definition («шах — это когда…»), a condition («если», «после»), a
                          plan or a denial;
  or says an example      «теперь на доске пример спёртого мата», «вот, посмотри на эту позицию», «я поставил
  is on the board         пример», "the example is on the board" — said of a board that shows the bare start (live
                          run 11.11: «…теперь на доске должен быть пример спёртого мата. Видите, король противника
                          заблокирован…» over the start position).

A game against the coach owns its board from the first move on — its start position is the game's, not nobody's;
with a game loaded on the board or in a tab, or any other position in the turn (a line, the student's idea), the
coach may be telling that — the check stays out.
A position a tool put up during the answer is another board (the site sends the position the student sees; the text
turn marks ctx.board_moved), so a real example is never judged here.

The words of «points at the board» and of «tells a contact» are lists of forms (ru / en / kk) — the fact they are read
against is the server's. Switches: detectors `unshown_board_voice` (the voice check: the coach is told at once and
corrects itself; on) and `unshown_board` (the text turn, where an issue withholds the sentence: shadow until its flags
are reviewed) in src/config.DETECTOR_DEFAULTS — COACH_DETECTORS_OFF / COACH_DETECTORS_SHADOW.
"""

from __future__ import annotations

import re
from typing import Optional

import chess

# The issue's first words: /voice/check tells the site by them that the coach's turn is to be cut now.
ISSUE_PREFIX = "nothing of this is on the student's board"
ISSUE = (ISSUE_PREFIX + ": it shows {what}, no example was put on it, and the student sees none of what you "
         "describe. Do not point at the board for it")

_B = r"(?<![а-яёәіңғүұқөһa-z])"
_E = r"(?![а-яёәіңғүұқөһa-z])"

# The coach points at what the student sees.
POINTER = re.compile(
    _B + r"(?:"
    r"(?:по)?смотри(?:те)?(?:\s+\S+){0,2}\s+на\s+(?:доск|диаграмм|позици|экран|пример|картинк)\w*"
    r"|(?:взгляни|глянь|погляди)(?:те)?(?:\s+\S+){0,2}\s+на\s+(?:доск|диаграмм|позици|экран|пример|картинк)\w*"
    r"|обрати(?:те)?\s+внимание"
    r"|на\s+(?:доске|диаграмме|картинке|рисунке|схеме|экране)"
    r"|в\s+(?:этой|данной|нашей)\s+позиции"
    r"|перед\s+(?:тобой|вами|нами)"
    r"|(?:видишь|видите|видно|заметь|заметьте|замечаешь)"
    r"|(?:(?:по)?смотри(?:те)?|гляди(?:те)?|вот)\s*[,:—–-]"
    r"|(?:здесь|тут)"
    r"|look(?:ing)?\s+at\s+(?:the|this|your)\s+(?:board|diagram|position|screen|example|picture)"
    r"|on\s+(?:the|this|your)\s+(?:board|diagram|screen)"
    r"|in\s+(?:this|the)\s+(?:position|diagram|picture|example)"
    r"|(?:do|can)\s+you\s+see|as\s+you\s+(?:can\s+)?see|you\s+can\s+see|see\s+(?:how|that)|notice"
    r"|in\s+front\s+of\s+you|right\s+here|here"
    r"|тақтаға\s+қара\w*|тақтада|диаграммада|суретте|экранда"
    r"|(?:осы|мына)\s+(?:позицияда|жерде|мысалда)"
    r"|көріп\s+тұр\w*|көрдің\w*|көресің\w*|байқа\w*|қарашы|мұнда|міне"
    r")" + _E, re.IGNORECASE)

_PIECE_RU = r"(?:корол\w*|ферз\w*|лад(?:ь[яиеюё]|ей|ьёй|ьей)\w*|слон\w*|кон(?:ь|я|ю|ём|ем|е|и|ей|ям|ями|ях)|пешк\w*|фигур\w*)"
_PIECE_EN = r"(?:king|queen|rook|bishop|knight|pawn|piece)s?"
_PIECE_KK = r"(?:корол\w*|патша\w*|ферз\w*|уәзір\w*|лад\w*|піл\w*|ат(?:ты|қа|пен|тың)?|пешк\w*|сарбаз\w*|фигура\w*)"
# A contact told as standing on the board: a check, an attack on a piece, a piece under attack, a capture there is.
_CONTACT = (
    r"(?:"
    # ru — a check
    r"(?:стоит|объявлен|объявили|дан|дали|получил\w*|поставлен|поставили)\s+шах"
    r"|шах\s+(?:от|корол\w+|бел\w+|ч[её]рн\w+)"
    r"|(?:да[её]т|дают|объявля\w+|став\w+)\s+шах"
    r"|под\s+шахом|шаху[её]т|шахуют"
    # ru — a mate, a blow, a pin
    r"|(?:стоит|объявлен|поставлен|получил\w*)\s+мат|(?:став\w+|объявля\w+)\s+мат|мату[её]т|корол\w+\s+мат(?![а-яё])"
    r"|нанос\w+\s+(?:\S+\s+){0,2}удар|связан\w*|в\s+связке|под\s+связкой"
    # ru — an attack on a piece, a piece under attack
    r"|<RU>(?:\s+\S+){0,3}\s+(?:атаку[её]т|атакуют|нападает|нападают|напал\w*|бь[её]т|бьют|угрожа\w+)"
    r"|(?:атаку[её]т|атакуют|нападает|нападают|напал\w*|бь[её]т|бьют|угрожа\w+)(?:\s+\S+){0,3}\s+<RU>"
    r"|под\s+(?:ударом|боем|атакой|нападением)"
    # ru — a capture there is
    r"|(?:можешь|может|могут|можно|можем)\s+(?:съесть|взять|побить|забрать|срубить)"
    # en
    r"|(?:is|are|'s|'re)\s+in\s+check|gives?\s+(?:a\s+)?check|giving\s+(?:a\s+)?check"
    r"|checks?\s+(?:the|your|my|white|black)|is\s+checking|delivers?\s+(?:a\s+)?check"
    r"|<EN>(?:\s+\S+){0,3}\s+(?:attacks?|is\s+attacking|are\s+attacking|threatens?|hits?)"
    r"|(?:attacks?|is\s+attacking|attacking|threatens?)(?:\s+\S+){0,3}\s+<EN>"
    r"|(?:is|are)\s+(?:under\s+attack|attacked|hanging|en\s+prise)"
    r"|(?:can|could)\s+(?:take|capture)"
    r"|(?:is|are)\s+(?:check)?mated|delivers?\s+(?:the\s+)?(?:check)?mate|(?:is|are)\s+pinned|forks?\s+(?:the|your|both)"
    # kk
    r"|шах\s+(?:беріп|жариялап|қойып|тұр)\w*|шах\s+астында|шахта\s+тұр\w*"
    r"|<KK>(?:\s+\S+){0,3}\s+шабуыл\w*|шабуыл\s+жаса\w*|шабуылда\w*|соққы\s+астында|қауіп\s+төндір\w*"
    r")"
)
CONTACT = re.compile(
    _B + _CONTACT.replace("<RU>", _PIECE_RU).replace("<EN>", _PIECE_EN).replace("<KK>", _PIECE_KK) + _E, re.IGNORECASE)

# The sentence does not tell the contact as standing now: a denial, a condition, a plan, a definition, a request.
UNREAL = re.compile(
    _B + r"(?:"
    r"не|нет|ни|никто|ничто|ничего|никак\w*|нельзя"
    r"|если|когда|после|пока|допустим|представь\w*|предположим|пусть|вдруг|бы|чтобы"
    r"|будет|будут|буду|будем|станет|станут|пойд[её]\w*|сыгра\w+|сходи\w*|поставь\w*|постав(?:им|лю|ит)|расстав\w+"
    r"|покажу|покажем|давай|найди\w*|попробуй\w*|подумай\w*"
    r"|например|бывает|называ\w+|означает|значит|это\s+когда|то\s+есть"
    r"|not|no|nobody|nothing|never|cannot|can't|isn't|aren't|doesn't|don't|won't"
    r"|if|when|after|once|suppose|imagine|let's|would|will|could|should|for\s+example|means?|is\s+called|is\s+when"
    r"|try|find|think"
    r"|жоқ|емес|егер|кейін|соң|болса|делік|мысалы|деп\s+аталады|дегеніміз|деген"
    r")" + _E + r"|—\s*это|–\s*это|-\s+это|n't", re.IGNORECASE)

# The coach says an example is on the board.
_THING = r"(?:пример\w*|позици\w+|задач\w+|диаграмм\w+|ситуаци\w+)"
_THING_EN = r"(?:example|position|puzzle|diagram|setup)"
_THING_KK = r"(?:мысал\w*|позиция\w*|есеп\w*|диаграмма\w*)"
_SHOWN = (
    r"(?:"
    r"на\s+доске\s+(?:\S+\s+){0,3}<T>"
    r"|<T>\s+(?:\S+\s+){0,2}(?:уже\s+|теперь\s+|сейчас\s+)?на\s+доске"
    r"|(?:поставил|расставил|загрузил|вывел|показал|выставил)\w*\s+(?:\S+\s+){0,3}(?:<T>|на\s+доск\w+)"
    r"|перед\s+(?:тобой|вами|нами)\s+(?:\S+\s+){0,2}<T>"
    r"|вот\s*,?\s+(?:\S+\s+){0,3}(?:позици\w+|диаграмм\w+|задач\w+)"   # «вот пример: …» may be told in words
    r"|(?:по)?смотри(?:те)?\s*,?\s+(?:\S+\s+){0,2}на\s+(?:эт\w+|нов\w+|так\w+)\s+<T>"
    r"|(?:now\s+)?on\s+(?:the|your)\s+board\s+(?:\S+\s+){0,3}<TE>"
    r"|<TE>\s+is\s+(?:now\s+|already\s+)?(?:up\s+)?on\s+(?:the|your)\s+board"
    r"|I(?:'ve|\s+have)?\s+(?:just\s+)?(?:put|set\s+up|placed|loaded)\s+(?:\S+\s+){0,3}(?:<TE>|on\s+the\s+board)"
    r"|here(?:'s|\s+is)\s+(?:an?\s+|the\s+)?(?:\S+\s+){0,2}(?:position|puzzle|diagram)"
    r"|look\s+at\s+(?:this|the\s+new)\s+<TE>"
    r"|тақтада\s+(?:\S+\s+){0,3}<TK>|<TK>\s+тақтада|тақтаға\s+(?:\S+\s+){0,3}қойдым|орналастырдым"
    r")"
)
SHOWN = re.compile(_B + _SHOWN.replace("<TE>", _THING_EN).replace("<TK>", _THING_KK).replace("<T>", _THING) + _E,
                   re.IGNORECASE)
# …not when it speaks of the start position itself, denies, asks, offers or plans.
NOT_SHOWN = re.compile(
    _B + r"(?:"
    r"начальн\w+|исходн\w+|стартов\w+|пуст\w+|starting|initial|start|empty|бастапқы|бос"
    r"|не|нет|ни|нету|пока|нельзя|not|no|n't|isn't|cannot|can't|жоқ|емес"
    r"|поставлю|расставлю|загружу|покажу|найду|подберу|поставим|покажем|давай\w*|хочешь|хотите|могу|можем|если|когда"
    r"|забыл\w*|хотел\w*|собирал\w*|поменять|сменить|заменить|поставить|показать|загрузить|расставить"   # «я забыл поменять позицию на доске»
    r"|forgot|meant|going\s+to|about\s+to|ұмытып"
    r"|will|shall|let|want|would|could|can|if|when|қояйын|көрсетейін|келе\s+ме"
    r")" + _E + r"|n't", re.IGNORECASE)


def says_shown(sentence: str) -> bool:
    """*sentence* says an example or a position is on the board (see the module docstring)."""
    text = (sentence or "").replace("ё", "е")
    return bool(SHOWN.search(text)) and not NOT_SHOWN.search(text)


# How long a pointer holds: the sentence that points and the two after it («Смотри на доску. Шах — это… Видишь, …»).
POINTER_SPAN = 2
_STATE = "_unshown_pointer_age"


def nobodys(board: Optional[chess.Board]) -> Optional[str]:
    """What a board that is nobody's shows — 'the starting position' / 'an empty board' — else None."""
    if board is None:
        return None
    try:
        placement = board.board_fen()
    except Exception:  # noqa: BLE001
        return None
    if placement == chess.STARTING_BOARD_FEN:
        return "the starting position"
    if placement == "8/8/8/8/8/8/8/8":
        return "an empty board"
    return None


def tells_contact(sentence: str) -> bool:
    """*sentence* tells a check, an attack or a capture as standing now (see the module docstring)."""
    text = (sentence or "").replace("ё", "е")
    return bool(CONTACT.search(text)) and not UNREAL.search(text)


def points(sentence: str) -> bool:
    return bool(POINTER.search((sentence or "").replace("ё", "е")))


def issue(sentence: str, board: Optional[chess.Board], pointed_before: bool = False) -> Optional[str]:
    """The issue of *sentence* said over *board*, or None. *pointed_before*: the answer pointed at the board in
    one of the two sentences before."""
    what = nobodys(board)
    if what is None:
        return None
    if says_shown(sentence) or ((pointed_before or points(sentence)) and tells_contact(sentence)):
        return ISSUE.format(what=what)
    return None


def judge(sentence: str, ctx) -> list:
    """The check's hook (src/answer_check.check_sentence): keeps on *ctx* how long ago the answer pointed at the
    board, and returns the issues of *sentence* — [] when the board is somebody's, a tool moved it during the
    answer, or the lesson tutor is the surface. Never raises."""
    try:
        if not (sentence or "").strip():
            return []
        age = getattr(ctx, _STATE, None)
        pointed_before = age is not None and age < POINTER_SPAN
        if points(sentence) or SHOWN.search(sentence.replace("ё", "е")):
            setattr(ctx, _STATE, 0)
        elif age is not None:
            setattr(ctx, _STATE, age + 1)
        if getattr(ctx, "board_moved", False) or getattr(ctx, "relation_surface", "text") == "lesson":
            return []
        if getattr(ctx, "game_moves", None) is not None or getattr(ctx, "game_engine_moves", None) is not None:
            return []  # a game against the coach: the board is the game's
        if getattr(ctx, "games_loaded", False):
            return []  # a game is loaded on the board or in a tab: the coach may be telling it from its first position
        current = getattr(ctx, "current", None)
        others = {b.board_fen() for b in (getattr(ctx, "boards", None) or [])} - ({current.board_fen()} if current else set())
        if others:
            return []  # the turn has other positions (a line, a tool's board, the student's idea): theirs to describe
        found = issue(sentence, getattr(ctx, "current", None), pointed_before)
        return [found] if found else []
    except Exception:  # noqa: BLE001 — a bonus check: the sentence is judged by the others either way
        return []


def is_unshown(issues) -> bool:
    return any(isinstance(i, str) and i.startswith(ISSUE_PREFIX) for i in issues or [])
