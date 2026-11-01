"""The parser of the relation checker (WP-A): the words of one sentence → the claims it makes about who attacks,
defends, pins, holds or locks what, each with the position its words point at (a textual ``Pos``).

    text ─normalize─► ─tokenize─► mentions: PIECE(kind, case, square, owner) SQ MOVE(SAN, told in words, castling)
                                            PRON REL(relation word) NEG OWNER SIDE SEP
         ─bind──────► raw claims (relation, agent, patients, negation, tense, question): the case of each noun picks
                      its role (nominative agent, accusative patient, «под ударом коня» — genitive agent …)
         ─position──► Pos: the moves the sentence tells before the claim (alternatives for «X или Y»), «тогда» →
                      'then', a plan with a set-up cue → 'plan', a hypothetical, rule, modal, future without a move,
                      unresolvable pronoun → 'skip'
         ─────────────► claim_types.Claim

No board work happens here: a move told in words is a ``MoveRef(piece, frm, to, told)``; claim_scene (WP-B) plays it.
Precision first: an idiom («Сицилианская защита», «держит ничью», «связан защитой»), a generic statement or a slot
the words do not fill gives no claim, or a claim whose position is 'skip'.

``state`` is ``ctx.relation_state``: this module keeps in it, under its own keys and as immutable values only, the
pieces the sentences before named (pronoun antecedents by gender) and the squares they named (for «туда», «это
место»). ``check_sentence`` restores a shallow copy when a sentence is cut, so a cut sentence leaves nothing behind.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import chess

from src.answer_check import _EN_PIECES, _RU_PIECES
from src.claim_types import Claim, MoveRef, Pos, Ref

L = r"[а-яёa-z]"
W = rf"(?<!{L})"
E = rf"(?!{L})"
SQ = r"[a-h][1-8]"

FOCUS_KEY = "grammar.focus"  # ((gender, piece letter|'', square|'', owner|'', nominative), …) of the sentences before
SQUARES_KEY = "grammar.squares"  # (square, …): the free squares the sentence before named («туда», «это поле»)

# ───────────────────────────── lexicon ─────────────────────────────
# Piece nouns come from the answer check's tables (one copy of the word list); the case of each form comes from its
# ending.  N nom, A acc, G gen, D dat, I ins, P prep (ё folded to е).  Chess pieces are animate: acc = gen.
_ENDINGS_SOFT_M = {"ь": "N", "я": "AG", "ю": "D", "ем": "I", "е": "P", "и": "N", "ей": "AG", "ям": "D", "ями": "I",
                   "ях": "P"}
_ENDINGS_HARD_M = {"": "N", "а": "AG", "у": "D", "ом": "I", "е": "P", "ы": "N", "ов": "AG", "ам": "D", "ами": "I",
                   "ах": "P"}
_ENDINGS = {
    chess.KNIGHT: _ENDINGS_SOFT_M, chess.QUEEN: _ENDINGS_SOFT_M, chess.KING: _ENDINGS_SOFT_M,
    chess.BISHOP: _ENDINGS_HARD_M,
    chess.ROOK: {"ья": "N", "ьи": "GN", "ье": "DP", "ью": "A", "ьей": "I", "ей": "AG", "ьям": "D", "ьями": "I",
                 "ьях": "P"},
    chess.PAWN: {"ка": "N", "ки": "GNA", "ке": "DP", "ку": "A", "кой": "I", "ек": "AG", "кам": "D", "ками": "I",
                 "ках": "P"},
}
_FEMININE = {chess.ROOK, chess.PAWN, 0}
_P: dict = {}  # word → (piece type, 0 = «фигура» any piece, cases)


def _pattern_words(pat: str) -> list:
    """'кон(?:ь|я|ю)' → ['конь', 'коня', 'коню']; 'слон(?:а|у)?' → [..., 'слон']; 'knights?' → ['knight', 'knights']."""
    m = re.fullmatch(r"(\w+)\(\?:([^)]*)\)(\?)?", pat)
    if m:
        stem, alts, opt = m.groups()
        return [(stem + a, a) for a in alts.split("|")] + ([(stem, "")] if opt else [])
    m = re.fullmatch(r"(\w+)s\?", pat)
    if m:
        return [(m.group(1), ""), (m.group(1) + "s", "s")]
    return []


for _pt, _pat in _RU_PIECES:
    for _w, _end in _pattern_words(_pat):
        _cases = _ENDINGS[_pt].get(_end)
        if _cases:
            _P.setdefault(_w, (_pt, set()))[1].update(_cases)
for _pt, _pat in _EN_PIECES:
    for _w, _end in _pattern_words(_pat):
        _P.setdefault(_w, (_pt, set()))[1].update("NA")
for _cases, _words in (("N", "фигура"), ("A", "фигуру"), ("GNA", "фигуры"), ("I", "фигурой фигурами"), ("AG", "фигур"),
                       ("DP", "фигуре"), ("NA", "piece pieces")):
    for _w in _words.split():
        _P.setdefault(_w, (0, set()))[1].update(_cases)
_LETTER = {chess.KNIGHT: "N", chess.BISHOP: "B", chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K", chess.PAWN: "P"}
_PTYPE = {v: k for k, v in _LETTER.items()}
_PIECE_ALT = "|".join(sorted(_P, key=len, reverse=True))


_WORD = re.compile(rf"{W}({L}+){E}")
# moves told in words, matched at a piece word: «конь с g8 на f6 вышел», «пешка идёт на g3», «конь на e2 сыгран»
_TOLD_FROM_TO = re.compile(rf"(?P<p>{_PIECE_ALT}){E}\s+(?:с|со|из|from)\s+(?:пол[яе]\s+)?(?P<a>{SQ})\s+"
                           rf"(?P<gap>(?:\S+\s+){{0,3}}?)(?:на|to)\s+(?P<b>{SQ})(?![0-9])")
_TOLD_PLAYED = re.compile(rf"(?P<p>{_PIECE_ALT}){E}\s+(?:на\s+)?(?P<b>{SQ})\s+(?:сыгран\w*|поставлен\w*|played)" + E)
_POSS_NEXT = re.compile(r"\s+(?:\w+(?:ый|ий|ой|ая|яя|ую|юю|ого|его|ее|ые|ие|ых|их)\s+)?(?:" + _PIECE_ALT + r")" + E)


def _gender(word: str) -> str:
    return "f" if _P[word][0] in _FEMININE else "m"


_PRON = {"он": ("N", "m"), "она": ("N", "f"), "они": ("N", "p"), "его": ("AG", "m"), "него": ("AG", "m"),
         "ее": ("AG", "f"), "нее": ("AG", "f"), "ей": ("DI", "f"), "ней": ("DIP", "f"), "ему": ("D", "m"),
         "нему": ("D", "m"), "им": ("I", "m"), "ним": ("I", "m"), "их": ("AG", "p"), "it": ("NA", "x"),
         "he": ("N", "m"), "she": ("N", "f"), "him": ("A", "m")}
# «пешку b2, которая прикрывала поле c2»: the relative pronoun stands for the noun right before it
_WHICH = {"который": ("N", "m"), "которая": ("N", "f"), "которое": ("N", "n"), "которые": ("N", "p"),
          "которого": ("AG", "m"), "которую": ("A", "f"), "которым": ("I", "m"), "которой": ("GDIP", "f"),
          "which": ("NA", "x"), "who": ("NA", "x")}

# Nouns a pronoun may stand for that are not pieces («это уязвимый пункт, ведь его прикрывает король»): one of them
# between a piece and the pronoun makes the pronoun ambiguous.
_NOUNS = {}
for _g, _ws in (("m", "пункт пункта пункту пунктом ход хода ходу центр центра фланг фланга план плана размен шах удар "
                      "удара темп темпа вариант варианта дебют дебюта эндшпиль эндшпиля"),
                ("f", "диагональ диагонали линия линию линии вертикаль вертикали горизонталь горизонтали слабость "
                      "слабости позиция позицию позиции угроза угрозу угрозы связка связку связки вилка вилку вилки "
                      "атака атаку атаки защита защиту защиты комбинация комбинацию идея идею жертва жертву клетка "
                      "клетку клетки точка точку"),
                ("n", "поле поля полю место места")):
    for _w in _ws.split():
        _NOUNS[_w] = _g
_OWNER = [(re.compile(W + r"(?:тво(?:й|я|е|его|ю|ей|ему|им|их|ими)|your)" + E), "you"),
          (re.compile(W + r"(?:мо(?:й|я|е|его|ю|ей|ему|им|их|ими)|my)" + E), "me"),
          (re.compile(W + r"(?:сво(?:й|я|е|его|ю|ей|ему|им|их|ими)|own)" + E), "own"),
          (re.compile(W + r"бел(?:ый|ая|ое|ого|ую|ой|ым|ых|ыми|ые)" + E), chess.WHITE),
          (re.compile(W + r"черн(?:ый|ая|ое|ого|ую|ой|ым|ых|ыми|ые)" + E), chess.BLACK),
          (re.compile(W + r"white'?s?" + E), chess.WHITE), (re.compile(W + r"black'?s?" + E), chess.BLACK)]
_OWNER_BEFORE = [(re.compile("(?:" + rx.pattern + r")(?:\s+же)?\s*(?:\w+\s+)?$"), v) for rx, v in _OWNER]
_SIDE = [(re.compile(W + r"(?:белые|white)" + E), chess.WHITE), (re.compile(W + r"(?:черные|black)" + E), chess.BLACK),
         (re.compile(W + r"(?:ты|вы|you)" + E), "you"), (re.compile(W + r"(?:соперник|противник)" + E), "opp")]

# Relation words (order matters: the first alternative wins at a position).
_REL = [
    ("UNDEF", r"(?:ничем\s+|никем\s+)?не\s+(?:защищ[её]н[аоы]?|прикрыт[аоы]?|поддержан[аоы]?)" + E
     + r"|незащищ[её]нн?(?:ый|ая|ое|ые|а|о|ы)?" + E + r"|беззащитн\w*|без\s+(?:защиты|прикрытия)"
     + r"|undefended|unprotected|(?:is|are)\s+not\s+(?:defended|protected)"),
    ("HANG", r"вис(?:ит|ят|ел[аио]?)" + E + r"|(?:is|are)\s+hanging|hangs|en\s+prise"),
    ("UNDEF_A", r"(?:никто|ничто|ничего|ничем|nothing|nobody)\s+(?:(?:ее|его|их|it)\s+)?(?:не\s+)?"
     r"(?:защища\w*|прикрыва\w*|defends|protects)"),
    ("HOLD", r"держ(?:ит|ат|ал\w*)\s+под\s+(?:ударом|боем|прицелом|контролем)|бер(?:ет|ут)\s+под\s+контроль|"
     r"брал\w*\s+под\s+контроль|взял\w*\s+под\s+контроль"),
    ("PASS_ATT", r"под\s+(?:ударом|боем|атакой|прицелом)|в\s+зоне\s+(?:удара|атаки|поражения)|атакован[аоы]?" + E +
     r"|(?:is|are)\s+(?:not\s+)?attacked|(?:is|are)\s+(?:not\s+)?under\s+attack|under\s+attack"),
    ("CTRL_G", r"под\s+контролем"),
    ("CTRL_I", r"прострелен[аоы]?" + E + r"|простреливаем\w*"),
    ("PASS_DEF", r"защищ[её]н[аоы]?" + E + r"|прикрыт[аоы]?" + E + r"|под\s+защитой|поддержан[аоы]?" + E
     + r"|(?:is|are)\s+(?:defended|protected)"),
    ("PASS_PIN", r"связан[аоы]?" + E + r"|(?:is|are)\s+(?:not\s+)?pinned"),
    ("PIN", r"связыва\w*|связал\w*|связав\w*|pins|pinning"),
    ("PIN_N", r"связк\w*|pin" + E),
    ("LOCK", r"заперт\w*|запер(?:ла|ли|л)?" + E + r"|запира\w*|перекры\w*|загород\w*|загоражива\w*"),
    ("SOFT", r"смотр(?:ит|ят|ел\w*)\s+(?:на|в)|целит\w*|целя\w*|нацел\w*|дав(?:ит|ят|ил\w*|ить)\s+(?:на|по)|"
             r"мет(?:ит|ят|ил\w*)\s+в|"
             r"давлени\w*\s+на|eyes|aims?\s+at|press(?:es|ing)?\s+on"),
    ("CHASE", r"отгоня\w*|отгон(?:ит|ишь|ят|я|ять)|отогна\w*|прогоня\w*|прогна\w*|выгоня\w*|kicks?|chases?|chasing"),
    ("THREAT", r"гроз(?:ит|ят|ил\w*)|угрожа\w*|threatens?"),
    ("CAPW", r"возьм\w*|заберут|забирают|бьют|бьет|бьешь|берут|берет|берешь|забирает|забираешь"),
    ("ATT", r"бь[её]т|бьют|бил[аи]?|бить|атаку(?:ет|ют|ешь|ете|ем|я|ющ\w*)|атакова(?:л|в|ть)\w*|напада\w*|напал\w*|напав|"
            r"удар(?:ил|ит|яет|яют)\w*\s+по|"
            r"нападет|нападут|с\s+ударом\s+по|с\s+(?:нападением|атакой)\s+на|attacks?|attacking|hits"),
    ("DEF", r"защища\w*|защитит\w*|защитил\w*|защитить|защитив\w*|прикрыва\w*|прикрыл\w*|прикрыв(?:ш\w*)?|"
            r"поддержива\w*|поддерж(?:ит|ал\w*|ать|ав)|подкреп\w*|укреп(?:ил|ля)\w*|охраня\w*|стереж\w*|стерег\w*|"
            r"оберега\w*|страху\w*|бер(?:ет|ут|[её]т)\s+под\s+защиту|взял\w*\s+под\s+защиту|"
            r"defends?|defending|protects?|guards?|(?:вста[её]т|встал\w*)\s+на\s+защиту|"
            r"прикрыти\w*\s+пол[яюе]"),
    ("HOLD", r"держ(?:ит|ат|ал\w*|ать)|удержива\w*|контролиру\w*|простреливает|простреливают|holds|controls|covers"),
]
_REL_RE = re.compile("|".join(f"(?P<{k}__{i}>{W}(?:{p}){E})" for i, (k, p) in enumerate(_REL)))
# «не просто нападаешь, а …», «не только защищает»: not a negation
_NEG = re.compile(W + r"(?:не(?!\s+(?:просто|только|столько|зря|случайно)" + E + r")|ни|нет|никак|нечем|некому|больше\s+не|"
                  r"уже\s+не|not(?!\s+only)|no\s+longer|n't)" + E)
# outside the board: counterfactual, rule, plan in general, lesson/example
_HYPO = re.compile(W + r"(?:бы|если\s+бы|будто|словно|обычно|всегда|как\s+правило|в\s+общем|по\s+правилам|в\s+уроке|"
                   r"например|пример\w*|классик\w*|типичн\w*|представь\w*|поищи|найди|ищи|ищем|правил[оау]|"
                   r"это\s+(?:при[её]м|правило|когда)|называ\w+|означа\w+|исключительно|вспомни\w*|"
                   r"в\s+(?:таком|таких|подобн\w+)\s+(?:эндшпил\w*|позици\w*|положени\w*|структур\w*)|"
                   r"в\s+продолжени\w+\s+(?:урок|парти|вариант|задач)\w*|"
                   r"would|usually|always|in\s+general|for\s+example|imagine)" + E)
# idioms (the trap list): opening names, «связан с идеей», «держит ничью», «упорная защита», «связан защитой» …
# A relation word inside one is no claim; the other claims of the sentence stand («Белый слон связан — он прикрывает
# ферзя e2»: «связан» there means overloaded, «прикрывает ферзя e2» is a claim).
_IDIOM = re.compile(
    W + r"(?:связан\w*\s+(?:с\s+(?:иде\w*|тем|этим|ним|ней|планом|темой)|задачей|обязанност\w*)|чем\s+связан\w*|"
    r"связан\w*(?=\s+(?:защитой|прикрытием|охраной)" + E + r")|"
    r"связаны\s+между|защит\w*\s+(?:позици\w*|центр\w*|фланг\w*)|"
    r"держ\w*\s+(?:ничью|оппозици\w*|удар|позици\w*|оборону|баланс|центр)|"
    r"упорн\w*\s+защит\w*|нет\s+защиты|вис\w*\s+в\s+воздухе|"
    r"связан\w*(?=\s*[:—–]\s*(?:\w+\s+){0,2}(?:должн\w*|обязан\w*|прикрыва\w*|защища\w*|держ\w*))|"
    r"закрыт\w*\s+(?:позици\w*|центр\w*|систем\w*|вариант\w*)|"
    r"(?:сицилианск|французск|скандинавск|голландск|славянск|индийск|английск|испанск|итальянск|русск|шотландск|"
    r"венск|берлинск|каро|алехин|пирц|филидор|петров|нимцович|грюнфельд|бенони|защит\w*\s+[А-Яа-я]+-)\w*\s*"
    r"(?:\w+\s+)?защит\w*|защит\w*\s+(?:каро|алехин|пирц|филидор|петров|нимцович|грюнфельд|двух\s+коней|чигорин)\w*|"
    r"(?:давит|давят|давил\w*|давлени\w*)\s+(?:на|по)\s+(?:центр|фланг|позици)\w*)" + E)
_FUTURE = re.compile(W + r"(?:будет|будут|станет|станут|сможет|смогут|сможешь|will|going\s+to)" + E)
_COND = re.compile(W + r"(?:если|когда|после|в\s+ответ\s+на|after|if|when|once)" + E)
_THEN = re.compile(r"^\W*(?:тогда|после\s+этого|в\s+ответ|там|дальше|далее|затем|потом|следующим\s+ходом|then|"
                   r"and\s+then|next)" + E)
# «Но подумай, что дальше: …»: the position the line before reached
_NEXT = re.compile(W + r"(?:что|а)\s+(?:будет\s+)?дальше" + E)
_ROUTES = re.compile(W + r"(?:через|via|through)\s+[a-h][1-8]\s*(?:,|и|или|либо|and|or)\s*[a-h][1-8]" + E)
_MOVE_CUE = re.compile(W + r"(?:(?:лучше|сильнее|точнее|над[её]жнее|правильнее)(?:\s+всего)?|ход\w*|сыграй\w*|сыграл\w*|играй\w*|играем|ответили|ответил[аи]?|ответ|ответь|после|через|"
                       r"продолжени\w*|начни\s+с|начинай\s+с|начинаем\s+с|идея|отвечай|пошли|пош[её]л|пошла|сделали|сделал\w*|play|played|after|move|"
                       r"(?:move|reply|answer|idea|continuation|choice)\s+(?:is|was|would\s+be)|(?:best|strongest)\s+is)"
                       r"\s*[:—–-]?\s*$")
_SEP = re.compile(r"[.;:!?()\n]|\s[—–]\s|,\s*(?:но|а|зато|поэтому|потому\s+что|так\s+что|чтобы|хотя|что|если|когда|"
                  r"but|so|because|while|if|when)" + E + r"|" + W + r"потому,?\s+что" + E + r"|" + W + r"так\s+как" + E)
_UNPARSED_MOVE = re.compile(
    W + r"(?:ид[её]т|идти|пойд[её]т|вста[её]т|встанет|уходит|уйти|уйд[её]т|уш[её]л|ушла|отходит|отойти|отойд[её]т|"
    r"отступа\w*|отступит|прыгает|прыгнет|переходит|перейд[её]т|выходит|выйдет|входит|войд[её]т|заходит|зайд[её]т|"
    r"берет|берут|взять|возьм[её]т|забирает|забрать|заберет|съест|бь[её]т\s+(?:с\s+шахом\s+)?на|бить\s+на|ходит|"
    r"сделает\s+ход|пойдет|врыва\w+|ворвал\w*|ворв[её]тся|вторга\w+|вторгнет\w*|переводит\w*|перевед[её]т\w*|"
    r"приходит|прид[её]т|подходит|подойд[её]т|бросается|бросит\w*|goes|moves|takes|captures|retreats|jumps|"
    # the past of a move the sentence tells without its square («мой конь на c6 отступил и прикрыл d5», «вышел мой слон
    # и напал на f2»): the board after it is not the one before
    r"вышел|вышла|вышли|отступил[аи]?|отош[её]л|отошла|отошли|вернул(?:ся|ась|ись)|прыгнул[аи]?|ушли|"
    r"переш[её]л|перешла|перешли|went|moved|retreated|jumped)" + E)
_THREAT_GOV = re.compile(W + r"(?:гроз\w*|угро\w*|threat\w*|иде[яюи]|хоч\w*|хотят|готов\w*|планиру\w*|собира\w*|"
                         r"мечта\w*)\s*[:—–-]?\s*$")
_GENERIC_EN = re.compile(r"\b(?:a|an|any|every|each)\s+(?:\w+\s+)?(?:knight|bishop|rook|queen|king|pawn|piece)s?\b", re.I)
_MOTION = (r"(?:ид[её]т|пойд[её]т|вста[её]т|встал[аи]?|уходит|уш[её]л|ушла|отходит|отош[её]л|отошла|отступает|"
           r"отступил[аи]?|прыгает|прыгнул[аи]?|переходит|перешел|перешла|выходит|вышел|вышла|заходит|заш[её]л|зашла|"
           r"прыгнет|встанет|поднимается|поднял(?:ся|ась)|спускается|спустил(?:ся|ась)|возвращается|вернул(?:ся|ась)|"
           r"врывается|ворвал(?:ся|ась)|вторгается|вторгся|вторглась|приходит|пришел|пришла|подходит|подошел|подошла|"
           r"lands|goes|jumps|moves)")
_STRIKE_TO = re.compile(W + rf"(?:удар\w*|жертв\w*|прыж\w*|вторжени\w*)\s+(?P<p>{_PIECE_ALT}){E}\s+(?:на|в)\s+(?P<b>{SQ})(?![0-9])")
_MOTION_TO = re.compile(rf"(?P<p>{_PIECE_ALT}|он|она){E}\s+(?:(?P<mid>\S+)\s+)?(?P<v>{_MOTION})\s+(?:на|в|to|on)\s+"
                        rf"(?P<b>{SQ})(?![0-9])")
# «пешка с d7 пошла вперёд»: a motion verb right after a «с sq» piece — it left the square
_LEFT = re.compile(r"[^.;:!?]{0,12}?(?:пол[яе]\s+[a-h][1-8]\s+)?" + W + r"(?:пош[её]л|пошла|пошли|двинул\w*|продвинул\w*|"
                   r"уш[её]л|ушла|вышел|вышла|отступил\w*|отош[её]л|отошла|прыгнул\w*|поднял\w*|переш[её]л|перешла|"
                   r"ид[её]т|уходит|выходит|отходит|прыгает|переходит|поднимается|went|moved|goes|moves)" + E)
# a move narrated as already made: «чёрные ответили Nc6», «только что сыграли 135...Qg1», «мой последний ход — Nf6»
_TOLD_CUE = re.compile(W + r"(?:ответил[аи]?|сыграл[аи]?|сделал[аи]?|пошел|пошла|пошли|только\s+что|последний\s+ход|"
                       r"предыдущий\s+ход|played|replied|answered)" + E)
# a set-up the sentence plans («фианкетто», «поставить слона на g2», «план»): its geometry is checkable on any board
_PLAN_CUE = re.compile(W + r"(?:фианкетто|fianchetto|постав\w+|расстав\w+|план\w*|plan|с\s+последующим)" + E)
# A verb of playing right before a bare square: «сыграть d5», «пойти d5», «ответить e5», «толкнуть g4», "play d5".
_PLAY_VERB_BEFORE = re.compile(W + r"(?:сыгра\w*|игра\w*|пойти|пойд\w*|ходить|ход(?:ом)?|ответ\w*|продвин\w*|продвига\w*|"
                               r"толкн\w*|толка\w*|двин\w*|play\w*|push\w*|answer\w*)\s+(?:\w+\s+)?$")
# A plan or an idea announced as a head of the sentence («План за белых: …», «Идея — …», «Цель: …», "The plan: …"), or
# an infinitive of placing that opens it («Поставить ладьи на c1 и d1 и …»): what follows is the set-up aimed at.
_PLAN_HEAD = re.compile(r"(?:^|[.!?;]\s*)[\s*_«\"-]*(?:(?:\w+\s+){0,2}(?:план|идея|задача|цель|замысел|схема|расстановка|plan|idea|goal|aim)"
                        r"(?:\s+(?:за|для|у|of|for)\s+\w+)?(?:\s+\w+){0,2}\s*[:—–]|(?:поставить|расставить|перевести|"
                        r"перебросить|переставить)" + E + r")")
_NOW_AGAIN = re.compile(W + r"(?:сейчас|теперь|на\s+доске|now)" + E)
# «туда», «это ослабленное место», «это поле», «этот пункт»: the square named just before
_THERE = re.compile(W + r"(?:туда|туда\s+же|(?:эт[оуи]|этот|эту|этого)\s+(?:\w+\s+)?(?:мест[оа]|пол[еяю]|пункт[аеу]?|"
                    r"точк[уаи]|слабост[ьи]))" + E)
# a square that is a route, not a target: «через f2», «ходом d3», «по диагонали a1–h8»
_ROUTE = re.compile(W + r"(?:через|ходом|ход|диагонал\w*|линии|линию|вертикал\w*|горизонтал\w*|via|through)\s*$")
_MOVE = re.compile(r"(?<![A-Za-z0-9])(?:(?P<num>\d{1,3})\s?(?P<dots>\.\.\.|…|\.)\s?|(?P<bdots>\.\.\.|…))?"
                   r"(?P<san>[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|O-O-O|O-O|0-0-0|0-0|"
                   r"(?P<pfrom>[a-h][1-8])\s?[-–]\s?(?P<pto>[a-h][1-8])|[a-h][1-8](?:=[QRBN])?)(?P<check>[+#]?)"
                   r"(?![A-Za-z0-9])")
_RU_LET = {"К": "N", "С": "B", "Л": "R", "Ф": "Q", "Кр": "K"}
_RU_SAN = re.compile(r"(?<![А-Яа-яЁёA-Za-z])(Кр|[КСЛФ])(?=[a-h]?[1-8]?[x:×х]?[a-hабвсдефгх][1-8])")
_CYR_FILE = {"а": "a", "б": "b", "в": "c", "с": "c", "ц": "c", "д": "d", "е": "e", "э": "e", "ф": "f", "г": "g", "х": "h"}
# a word that may carry a claim; a sentence without one is only read for its antecedents
_CLAIMWORD = re.compile(r"бь|бит|атак|напа|удар|бо[ейю]|защи|прикры|поддерж|подкреп|охран|держ|контрол|простре|связ|"
                        r"вис[ия]|hang|prise|стере|оберег|страху|мет[ия]|прицел|укреп|зоне|"
                        r"запер|перекры|загор|смотр|цел|дав|гон|гроз|угро|взя|забр|бер|attack|hit|defend|protect|pin|"
                        r"aim|eye|press|chase|threat|hold|control|cover|guard", re.I)
_TAKE = re.compile(r"бь[её]т|бьют|берет|забирает|взял\w*|забрал\w*|съел\w*|takes|captures")
# verbs that can only mean a capture (unlike «бьёт», which also means «attacks»)
_TAKE_SURE = re.compile(r"берет|берут|забирает|забирают|взял\w*|забрал\w*|съел\w*|съедает|takes|captures")
_FORK = re.compile(W + r"(?:вилк\w*|двойн\w+\s+удар\w*|fork\w*|double\s+attack)" + E)


def normalize(text: str) -> str:
    """ё → е, emphasis out, Russian piece letters and Cyrillic files of written moves as SAN («Кf6», «Сg4», «Фxg2#»)."""
    t = (text or "").replace("ё", "е").replace("Ё", "Е").replace("*", " ").replace(" ", " ")
    t = re.sub(r"(?<![А-Яа-яA-Za-z])(Кр|[КСЛФKQRBN])([x:×х]?)([абвсцдеэфгх])(?=[1-8](?![0-9]))",
               lambda m: m.group(1) + ("x" if m.group(2) else "") + _CYR_FILE[m.group(3)], t)
    t = _RU_SAN.sub(lambda m: _RU_LET[m.group(1)], t)
    t = re.sub(r"(?<=[KQRBNa-h1-8])[:×](?=[a-h][1-8])", "x", t)
    return t


# ───────────────────────────── tokens ─────────────────────────────
@dataclass
class Tok:
    kind: str  # PIECE SQ BOUND MOVE PRON WHICH REL NEG OWNER SIDE SEP POSS
    start: int
    end: int
    text: str
    ptype: Optional[int] = None
    cases: str = ""
    sq: Optional[int] = None
    owner: object = None
    rel: str = ""
    san: str = ""  # MOVE: SAN, or 'g8f6' (from-to), or '@N:f6' (a knight to f6, told in words)
    num: Optional[str] = None  # MOVE: '135...', '4.'
    gender: str = ""
    move_cue: bool = False
    soft: bool = False  # MOVE: castling told as a noun
    span: tuple = ()  # MOVE told in words: the whole phrase (its motion verb is accounted for)
    threat: bool = False  # MOVE named as a threat/idea («грозит Rxe1»): not played
    told: bool = False  # MOVE narrated as already made
    from_sq: bool = False  # PIECE: «конь с g5» — the square it stands (stood) on, not where it went
    route: bool = False  # SQ: «через f2», «по диагонали a1–h8» — not a target
    attr: object = False  # PIECE in the genitive of another noun or after a genitive preposition («из-под удара пешки
    # d5», «гамбит слона», «у коня»): neither a subject nor an antecedent


# A noun or a preposition that takes the next piece word in the genitive («из-под удара пешки d5», «гамбит слона», «у
# коня», «для ладьи»): that piece is no subject and no antecedent of a pronoun.
_GEN_HEAD = re.compile(W + r"(?:удар[ау]?|атак[иу]|защит[ыу]|бо[яю]|давлени[яе]|гамбит|размен[ау]?|жертв[ыу]|развити[яе]|"
                       r"выход[ау]?|отступлени[яе]|ход[ау]?|позици[ияю]|диагонал[иь]|лини[ия]|вертикал[иь]|поле|пол[яю]|"
                       r"место|места|потер[иья]|выигрыш[ау]?|взяти[яе]|маневр[ау]?|перевод[ау]?|продвижени[яе]|"
                       r"(?P<prep>у|от|из|без|для|до|против|возле|около|кроме|вместо|из-под|из-за|после|вокруг|мимо|ради))\s+"
                       r"(?:(?:бел|черн|тво|сво|мо|ваш|ег|е|их|чуж|лишн|одн|последн|вражеск)\w*\s+){0,2}$")


def _free(taken, a, b):
    return all(b <= x or a >= y for x, y in taken)


def tokenize(t: str) -> list:
    low = t.lower()
    toks: list = []
    taken: list = []

    for m in _SEP.finditer(low):
        toks.append(Tok("SEP", m.start(), m.end(), m.group(0)))
    # moves told in words: «конь с g8 на f6 вышел», «пешка идёт на g3», «конь с b8 встал на c6», «рокировка»
    words = [(m.start(), m.group(1)) for m in _WORD.finditer(low)]
    piece_at = [a for a, w in words if w in _P]
    for m in filter(None, (_TOLD_FROM_TO.match(low, a) for a in piece_at)):
        pt = _P[m.group("p")][0]
        if pt and not _REL_RE.search(m.group("gap") + m.group(0)[m.end("gap") - m.start():m.start("b") - m.start()]) and \
                not re.search(r"[,;:—–]", m.group("gap")):
            phrase = m.group(0)
            toks.append(Tok("MOVE", m.start("a"), m.end("b"), phrase, san=m.group("a") + m.group("b"), ptype=pt,
                            span=(m.start(), m.end()), told=bool(re.search(r"(?:л|ла|ли|лся|лась)\s", phrase))))
            taken.append((m.start("a"), m.end("b")))
    for m in filter(None, (_MOTION_TO.match(low, a) for a, w in words if w in _P or w in ("он", "она"))):
        word = m.group("p")
        if word in ("он", "она"):
            pt = _pronoun_mover(toks, low, m.start(), "m" if word == "он" else "f")
            if not pt:
                continue
        else:
            pt = _P[word][0]
            if not (pt and "N" in _P[word][1]):
                continue
        if _free(taken, m.start("b"), m.end("b")):
            # «конь e6 идёт на c7»: the square between the piece and the motion verb is where it goes from
            frm = m.group("mid") if m.group("mid") and re.fullmatch(SQ, m.group("mid")) else None
            toks.append(Tok("MOVE", m.start("b"), m.end("b"), m.group(0),
                            san=(frm + m.group("b")) if frm else f"@{_LETTER[pt]}:{m.group('b')}", ptype=pt,
                            span=(m.start(), m.end()), told=bool(re.search(r"(?:л|ла|ли|лся|лась)$", m.group("v")))))
            taken.append((m.start("b"), m.end("b")))
    for m in _STRIKE_TO.finditer(low):  # «удар конём на f7», «жертва слоном на h7»: a move named by its blow
        pt, cases = _P[m.group("p")][0], _P[m.group("p")][1]
        if pt and "I" in cases and _free(taken, m.start("b"), m.end("b")):
            toks.append(Tok("MOVE", m.start("b"), m.end("b"), m.group(0), san=f"@{_LETTER[pt]}:{m.group('b')}", ptype=pt,
                            span=(m.start(), m.end())))
            taken.append((m.start("b"), m.end("b")))
    for m in filter(None, (_TOLD_PLAYED.match(low, a) for a in piece_at)):
        pt = _P[m.group("p")][0]
        if pt and _free(taken, m.start("b"), m.end("b")):
            toks.append(Tok("MOVE", m.start("b"), m.end("b"), m.group(0), san=f"@{_LETTER[pt]}:{m.group('b')}", ptype=pt,
                            span=(m.start(), m.end()), told=True))
            taken.append((m.start("b"), m.end("b")))
    for m in re.finditer(W + r"(?:(?P<long>длинн\w+)\s+|коротк\w+\s+)?рокировк(?:а|у|ой|и)" + E, low):
        toks.append(Tok("MOVE", m.start(), m.end(), m.group(0), san="O-O-O" if m.group("long") else "O-O", soft=True,
                        ptype=chess.KING))
        taken.append((m.start(), m.end()))
    # every relation word starts a word: try the (long) alternation only there — the same leftmost non-overlapping
    # matches finditer gives, at a fraction of the cost
    upto = -1
    for a, _w in words:
        if a < upto:
            continue
        m = _REL_RE.match(low, a)
        if m is None:
            continue
        upto = m.end()
        if not _free(taken, m.start(), m.end()):
            continue
        toks.append(Tok("REL", m.start(), m.end(), m.group(0), rel=m.lastgroup.split("__")[0]))
        taken.append((m.start(), m.end()))
    for m in _MOVE.finditer(t):
        if not _free(taken, m.start(), m.end()):
            continue
        san = m.group("san").replace("0", "O")
        num = None
        if m.group("num"):
            num = m.group("num") + ("..." if m.group("dots") in ("...", "…") else ".")
        elif m.group("bdots"):
            num = "..."  # a Black move with no number («...Сg4»): the side only
        tk = Tok("MOVE", m.start(), m.end(), m.group(0), san=san + m.group("check"), num=num)
        before = low[max(0, m.start() - 24):m.start()]
        if m.group("pfrom"):
            prev_mv = [o for o in toks if o.kind == "MOVE" and o.end <= m.start()] + \
                [o for o in toks if o.kind == "SQ" and o.move_cue and o.end <= m.start()]
            prev_mv = max(prev_mv, key=lambda o: o.end, default=None)
            line_of_prev = prev_mv is not None and m.start() - prev_mv.end <= 6 and \
                (prev_mv.san[-2:] if prev_mv.kind == "MOVE" else chess.square_name(prev_mv.sq)) == m.group("pfrom")
            if line_of_prev or re.search(W + r"(?:диагонал\w*|лини\w+|вертикал\w*|горизонтал\w*|центр\w*|цеп\w+|структур\w*)\s*(?:«|\")?\s*$", before):
                tk.kind, tk.route = "SQ", True  # «по диагонали a1–h8»: a line, not a move
                tk.sq = chess.parse_square(m.group("pfrom"))
            else:
                tk.san = m.group("pfrom") + m.group("pto")
        elif re.fullmatch(SQ, san) and not num and not m.group("check"):
            tk.kind = "SQ"
            tk.sq = chess.parse_square(san)
            tk.move_cue = bool(_MOVE_CUE.search(before)) or not low[:m.start()].strip(" «\"")
            tk.route = bool(_ROUTE.search(before))
            if re.search(r"(?:^|[.;:!?(—–,]\s*)(?:(?:своим|последним|этим|первым|следующим|вторым)\s+)?ходом\s*$",
                         low[:m.start()]):
                tk.move_cue, tk.route = True, False  # «Ходом d4 ты отгоняешь коня»: a move, not a route
        toks.append(tk)
        taken.append((m.start(), m.end()))
    for start, w in words:
        if not (w in _P or w in _PRON or w in _WHICH or w in _NOUNS):
            continue
        end = start + len(w)
        if not _free(taken, start, end):
            continue
        if w in _P:
            pt, cs = _P[w]
            tk = Tok("PIECE", start, end, w, ptype=pt, cases="".join(sorted(cs)), gender=_gender(w))
            gh = _GEN_HEAD.search(low[max(0, start - 30):start]) if "G" in cs and len(cs) > 1 else None
            if gh:
                # after a preposition («у чёрного короля»): not a subject, still an antecedent; after a noun
                # («гамбит слона», «из-под удара пешки d5»): neither
                tk.attr = "prep" if gh.group("prep") else "noun"
            toks.append(tk)
        elif w in _PRON:
            cs, g = _PRON[w]
            tk = Tok("PRON", start, end, w, cases=cs, gender=g)
            sm = re.match(r"\s+(?:уже\s+|теперь\s+|сейчас\s+)?(?:на|on)\s+([a-h][1-8])(?![0-9])", low[end:end + 20])
            if sm:  # «он на f6 ничем не прикрыт», «его на f6 никто не защищает»: the square the pronoun's piece stands on
                tk.sq = chess.parse_square(sm.group(1))
            toks.append(tk)
        elif w in _WHICH:
            cs, g = _WHICH[w]
            if g == "x" and not re.search(r",\s*$", low[:start]):
                continue  # English «which/who» relative only after a comma («Which piece …?» asks)
            toks.append(Tok("WHICH", start, end, w, cases=cs, gender=g))
        else:
            toks.append(Tok("NOUN", start, end, w, gender=_NOUNS[w]))
    for rx, val in _OWNER:
        for m in rx.finditer(low):
            if _free(taken, m.start(), m.end()):
                toks.append(Tok("OWNER", m.start(), m.end(), m.group(0), owner=val))
    for rx, val in _SIDE:
        for m in rx.finditer(low):
            if _free(taken, m.start(), m.end()):
                toks.append(Tok("SIDE", m.start(), m.end(), m.group(0), owner=val))
    for m in _NEG.finditer(low):
        # «Нет, конь f6 нападает на e4», «Нет-нет, …»: the answer word to the question, not a negation of the verb
        if m.group(0) == "нет" and re.match(r"\s*[,—–:!.?-]", low[m.end():m.end() + 3]):
            continue
        if _free(taken, m.start(), m.end()):
            toks.append(Tok("NEG", m.start(), m.end(), m.group(0)))
    seps = [0] + sorted(t.end for t in toks if t.kind == "SEP") + [len(low)]
    for t in toks:  # «Рокировка невозможна», «рокировки нет»: castling named, not made
        if t.kind == "MOVE" and t.soft:
            a = max(x for x in seps if x <= t.start)
            b = min((x for x in seps if x > t.end), default=len(low))
            if re.search(W + r"(?:невозможн\w*|нельзя|запрещ\w*|не\s+(?:може\w*|получ\w*|успе\w*|включа\w*|разреш\w*)|нет|"
                         r"impossible|cannot|can't)" + E, low[a:b]):
                t.kind = "NOTE"
    moves = [(t.start, t.end) for t in toks if t.kind == "MOVE"]
    toks = [t for t in toks if not (t.kind == "SEP" and any(a <= t.start < b for a, b in moves))]
    toks.sort(key=lambda x: (x.start, -x.end))
    _bare_moves_in_lines(toks, low)
    # a move narrated as made, and every move before a past «ответили/сыграл» in the sentence («h3 — чёрные ответили Nc6»)
    told_cue = [m.end() for m in _TOLD_CUE.finditer(low)]
    told_upto = max((m.start() for m in _TOLD_CUE.finditer(low) if re.search(r"л[аи]?$|шли$", m.group(0))), default=-1)
    for i, tk in enumerate(toks):
        if tk.kind == "PRON" and tk.text in ("его", "ее", "их") and \
                _POSS_NEXT.match(low[tk.end:tk.end + 24]):
            tk.kind = "POSS"
        if tk.kind == "MOVE" and _THREAT_GOV.search(low[max(0, tk.start - 30):tk.start]):
            tk.threat = True
        if tk.kind == "MOVE" and not tk.threat and (any(0 <= tk.start - e <= 40 for e in told_cue) or tk.end <= told_upto):
            tk.told = True
        if tk.kind == "SQ" and tk.move_cue and tk.end <= told_upto:
            tk.told = True
        # «b3 hits the bishop», «e5 бьёт…»: a square opening a clause right before a relation word is a move (not after
        # «а/но»: «а f7 защищает только король», «но h4 прикрыта пешкой g3» put the object first)
        if tk.kind == "SQ" and i + 1 < len(toks) and toks[i + 1].kind == "REL" and toks[i + 1].start - tk.end <= 2 and \
                re.search(r"(?:^|[.;:!?(—–]\s*)$", low[:tk.start].rstrip(" «\"")):
            tk.move_cue = True
    for tk in toks:
        if tk.kind == "PRON" and tk.sq is not None:
            for o in toks:
                if o.kind == "SQ" and o.sq == tk.sq and tk.end < o.start <= tk.end + 20:
                    o.kind = "BOUND"
    for j, tk in enumerate(toks):
        if tk.kind != "PIECE":
            continue
        # «конь на f6», «конь f3», «пешку d4», «ладья с d8»;  «на c1 (всё ещё) сидит слон»
        m = re.match(r"\s*(?:(?:белых|черных|соперника|противника)\s+(?=на\s))?(?:(?P<prep>на|с|со|из|on|at|from)\s+)?"
                     r"(?:пол[еяю]\s+)?([a-h][1-8])(?![0-9])", low[tk.end:tk.end + 28]) or \
            re.match(r"\s+(?:уже\s+|все\s+еще\s+|теперь\s+)?(?:забрал\w*|залез\w*|стоит|стоят|находится|оказал\w*|сидит|"
                     r"расположен\w*|stands|sits|is)\s+(?:on\s+|на\s+)([a-h][1-8])(?![0-9])", low[tk.end:tk.end + 40])
        if m and m.groupdict().get("prep") in ("на", "on") and "A" in tk.cases and \
                re.search(W + r"(?:нацел|направ|навел|наводит)\w*\s+(?:\w+\s+)?$", low[max(0, tk.start - 30):tk.start]):
            m = None  # «нацелил слона на f7»: the piece aimed and its target, not the piece on f7
        if m:
            tk.sq = chess.parse_square(m.group(m.lastindex))
            tk.from_sq = bool(m.groupdict().get("prep") in ("с", "со", "из", "from"))
            for o in toks:
                if o.kind == "SQ" and o.start == tk.end + m.start(m.lastindex):
                    o.kind = "BOUND"
                    if not tk.from_sq and tk.ptype and m.lastindex == 2 and _proposed(toks, low, tk, o):
                        # «c4 или конь f3, который берёт под контроль e5», «Лучше всего конь f3»: a move proposed in
                        # words — the piece there after it (none when it already stands there)
                        o.kind, o.san, o.ptype, o.span = "MOVE", f"@{_LETTER[tk.ptype]}:{chess.square_name(tk.sq)}", \
                            tk.ptype, (tk.start, o.end)
        else:
            m = re.search(r"(?:на|on)\s+([a-h][1-8])\s+(?:\w+\s+){0,2}(?:сидит|стоит|стоят|находится|sits|stands)\s+(?:\w+\s+)?$",
                          low[max(0, tk.start - 40):tk.start])
            if m:
                tk.sq = chess.parse_square(m.group(1))
            elif "N" in tk.cases:
                # «С h3 белый король берёт под контроль g5»: the square it acts from, before it
                m = re.search(r"(?:^|[,:—–]\s*|^\W*)(с|со|от|from|на|on)\s+(?:пол[яе]\s+)?([a-h][1-8])\s+(?:\w+\s+){0,2}$",
                              low[max(0, tk.start - 30):tk.start])
                if m and not any(o.kind in ("PIECE", "MOVE", "REL") and o.end <= tk.start and o.start >= tk.start - 30 for o in toks):
                    tk.sq, tk.from_sq = chess.parse_square(m.group(2)), m.group(1) not in ("на", "on")
                    for o in toks:
                        if o.kind == "SQ" and o.start == max(0, tk.start - 30) + m.start(2):
                            o.kind = "BOUND"
                            if not tk.from_sq and tk.ptype:
                                # «На b5 конь нападает на d6 и c7», "On f5 the knight attacks g7": the piece placed on
                                # the square — a move there when it is not on it yet (none when it already is)
                                o.kind, o.san, o.ptype, o.span = "MOVE", f"@{_LETTER[tk.ptype]}:{m.group(2)}", tk.ptype, \
                                    (o.start, tk.end)
        mv = next((o for o in toks if o.kind == "MOVE" and o.ptype and o.text.startswith(tk.text) and o.start > tk.start
                   and o.start - tk.end < 40), None)
        if mv is not None:  # the piece of a move told in words stands on its destination after it
            tk.sq = chess.parse_square(mv.san[-2:])
            tk.from_sq = False
            for o in toks:
                if o.kind == "SQ" and tk.end <= o.start < mv.end:
                    o.kind = "BOUND"
        prev = low[max(0, tk.start - 22):tk.start]
        for rx, val in _OWNER_BEFORE:
            om = rx.search(prev)
            # «слон b3 у белых атакован пешкой e6»: an owner word before a verb is not the next piece's owner
            if om and not any(o.kind == "REL" and max(0, tk.start - 22) + om.start() <= o.start < tk.start for o in toks):
                tk.owner = val
        if tk.owner is None and j > 0 and toks[j - 1].kind == "POSS" and tk.start - toks[j - 1].end <= 20:
            tk.owner = "opp"  # «их пешку d4», «его пешка e5»: the other side's
        if tk.sq is None and tk.ptype:
            mentions = [o for o in toks if o.kind == "PIECE" and o is not tk and o.ptype == tk.ptype and o.sq is not None
                        and o.start < tk.start and (o.owner is None or tk.owner is None or o.owner == tk.owner)]
            same = {o.sq for o in mentions}
            # a written move of that kind of piece since the mention (review fp2 01.11: «Тогда конь f6 забирает пешку e4, а
            # после Nxe4 d5 пешка нападает …»): the bare noun right after the line is the piece that move brought —
            # its destination; further away it may be either, no square
            since = max((o.end for o in mentions), default=-1)
            moved = [o for o in toks if o.start >= since and o.end <= tk.start and
                     ((o.kind == "MOVE" and not o.threat and _move_ref(o).piece == _LETTER.get(tk.ptype)) or
                      (o.kind == "SQ" and o.move_cue and tk.ptype == chess.PAWN))]
            if moved and same:
                last = moved[-1]
                if re.fullmatch(r"[\s,—–:]*", low[last.end:tk.start]):
                    mr = _move_ref(last if last.kind == "MOVE" else Tok("MOVE", last.start, last.end, last.text, san=last.text))
                    if mr.to:
                        tk.sq = chess.parse_square(mr.to)
            elif len(same) == 1:
                tk.sq = same.pop()
        m = re.match(r"\s*(?:[a-h][1-8]\s+)?(белых|черных|соперника|противника)" + E, low[tk.end:tk.end + 18])
        if m and tk.owner is None:
            tk.owner = {"белых": chess.WHITE, "черных": chess.BLACK}.get(m.group(1), "opp")
        if tk.from_sq and _LEFT.match(low, tk.end + 4 if tk.sq is not None else tk.end):
            # «пешка с d7 пошла вперёд»: the piece left that square — it is the one a move of the sentence brought
            # to its destination, or unknown
            mine = {_move_ref(o).to for o in toks if o.kind == "MOVE" and _move_ref(o).piece == _LETTER.get(tk.ptype)}
            tk.sq = chess.parse_square(mine.pop()) if len(mine) == 1 else None
            tk.from_sq = False
    return toks


_LINE_GAP = re.compile(r"[\s,]*(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?)?")


def _bare_moves_in_lines(toks, low) -> None:
    """«После e4 e5 Nf3 Nc6 конь f3 нападает на пешку e5», «e4 e6 d4 d5 Nc3», «1...a6 2.Ba4 b5: …», «После d4 d5 c4 пешка
    c4 …»: a line written without move numbers. In a run of moves and squares (only spaces, commas, move numbers
    between) that a move or a move cue opens, a bare square is a pawn move of the line when a written move follows it in
    the run — or, for the run's last ones, when the run is three long and ends the clause or comes right before a
    piece word (the piece the line just moved)."""
    seq = [t for t in toks if t.kind in ("MOVE", "SQ") and not t.route]
    runs, cur = [], []
    for t in seq:
        if cur and _LINE_GAP.fullmatch(low[cur[-1].end:t.start]):
            cur.append(t)
        else:
            if cur:
                runs.append(cur)
            cur = [t]
    if cur:
        runs.append(cur)
    for run in runs:
        if len(run) < 2 or not (run[0].kind == "MOVE" or run[0].move_cue):
            continue
        written = [i for i, t in enumerate(run) if i and t.kind == "MOVE" and not t.span]
        upto = written[-1] if written else 0
        ends = bool(re.match(r"\s*(?:[:;.!?)—–]|$|(?:" + _PIECE_ALT + r")" + E + ")", low[run[-1].end:run[-1].end + 12]))
        # «после Nxe4 d5 пешка нападает»: a line after «после» that ends before a piece word or the clause end — its bare
        # squares are its moves however short it is (review fp2 01.11)
        cued = run[0].kind == "MOVE" and bool(re.search(W + r"(?:после|after)\s*$", low[max(0, run[0].start - 12):run[0].start]))
        tail = (len(run) >= 3 or cued) and ends
        for i, t in enumerate(run):
            if t.kind == "SQ" and (i < upto or tail):
                t.move_cue = True


def _proposed(toks, low, piece, bound) -> bool:
    """«c4 или конь f3», «конь f3 или c4», «Лучше всего конь f3»: the piece on the square is a move the words propose
    (an alternative of «или» to a written move or square, or right after a move cue)."""
    if re.search(W + r"(?:или|либо|or)\s+$", low[max(0, piece.start - 8):piece.start]):
        k = low.rfind(" ", 0, max(0, low.rfind(" ", 0, piece.start - 1)))
        if any(o.kind in ("MOVE", "SQ") and o.end <= piece.start and o.end >= k - 2 for o in toks):
            return True
    if re.match(r"\s+(?:или|либо|or)\s+", low[bound.end:bound.end + 8]):
        nxt = re.match(r"\s+(?:или|либо|or)\s+", low[bound.end:bound.end + 8]).end() + bound.end
        if any(o.kind in ("MOVE", "SQ") and o.start == nxt for o in toks):
            return True
    return bool(_MOVE_CUE.search(low[max(0, piece.start - 30):piece.start])) and \
        not re.search(W + r"(?:после|через|after)\s*$", low[max(0, piece.start - 30):piece.start]) and \
        not re.search(W + r"(?:до|перед|после|с)\s+(?:\w+\s+)?ход\w*\s*$", low[max(0, piece.start - 30):piece.start])
    # («До первого хода ферзь d1 …», «с первого хода»: a time, not a move proposed — review fp2 01.11)


def _pronoun_mover(toks, low, at, gender):
    """«слон с h2: он идёт на e5» — the piece the pronoun of a motion stands for: the only piece of its gender named
    before it in the sentence (nominative), else unknown."""
    cands = {_P[w.group(1)][0] for w in re.finditer(rf"{W}({_PIECE_ALT}){E}", low[:at])
             if "N" in _P[w.group(1)][1] and _gender(w.group(1)) == gender and _P[w.group(1)][0]}
    return cands.pop() if len(cands) == 1 else None


# ───────────────────────────── raw claims ─────────────────────────────
@dataclass
class _R:
    what: str  # piece / square / move / side
    ptype: Optional[int] = None
    sq: Optional[int] = None
    owner: object = None
    move: Optional[Tok] = None
    text: str = ""
    from_sq: bool = False
    pronoun: bool = False


@dataclass
class _Raw:
    rel: str
    agent: Optional[_R]
    patients: list
    neg: bool
    tense: str  # present / past / future
    question: str  # '' / 'wh' / 'yn'
    pos: int
    clause: tuple
    blockers: list = field(default_factory=list)
    instrument: Optional[_R] = None
    verb: str = ""
    to: Optional[_R] = None
    modal: bool = False
    inverted: bool = False  # the agent comes after the verb («пешку e7 бьют и конь c6»)
    skip: str = ""  # a reason the words give no checkable claim («слон с пешкой держат» — joint agents)
    unresolved: bool = False  # a pronoun in a slot that has no single antecedent
    end: int = 0
    cover: bool = False  # «не прикрыт»: to shield as well as to defend
    count: Optional[int] = None  # «атакована дважды», «две белые фигуры атакуют»: how many attackers/defenders
    plan: bool = False  # «поставить коня на e5, откуда он будет бить по e7»: geometry of the square the plan names


_PASSIVE = ("PASS_ATT", "PASS_DEF", "UNDEF", "PASS_PIN", "CTRL_G", "CTRL_I", "HANG")


def _clauses(text, toks):
    cuts = [0] + sorted({t.end for t in toks if t.kind == "SEP"}) + [len(text)]
    return [(a, b) for a, b in zip(cuts, cuts[1:]) if b > a]


def _ref(tk):
    if tk.kind == "PIECE":
        return _R("piece", tk.ptype, tk.sq, tk.owner, text=tk.text, from_sq=tk.from_sq)
    if tk.kind in ("SQ", "BOUND"):
        return _R("square", sq=tk.sq, text=tk.text)
    if tk.kind == "MOVE":
        return _R("move", move=tk, text=tk.text)
    return None


def _focus_from(state) -> dict:
    out: dict = {}
    for g, letter, sq, owner, nom in state.get(FOCUS_KEY, ()) or ():
        own = {"w": chess.WHITE, "b": chess.BLACK}.get(owner, owner or None)
        out.setdefault(g, []).append((_R("piece", _PTYPE.get(letter, 0) if letter else 0,
                                         chess.parse_square(sq) if sq else None, own, text=""), nom))
    return out


def _antecedents(toks, focus, text_low=""):
    """What each pronoun stands for, and the pieces this sentence leaves as candidates for the next one.  Candidates
    are the pieces of its gender named before it in this sentence (not the agent right after «под ударом»/«прикрыта»,
    not a dative/prepositional mention), else those of the sentences before.  One distinct candidate → it; several →
    the only nominative one for a nominative pronoun; otherwise unknown (None).  A resolved pronoun stands for its
    referent from then on (a pronoun chain).  «который» stands for the noun right before it."""
    cur: dict = {}
    out = {}
    last_rel = None
    last_noun = None
    last_move = last_move_ref = None

    def key(r):  # two unsquared mentions are the same piece only when they are the same mention (a pronoun chain)
        return (r.ptype, r.sq) if r.sq is not None else (r.ptype, None, r.owner, id(r))

    last_piece_at: dict = {}
    noun_at: dict = {}
    for t in toks:
        if t.kind == "NOUN":
            noun_at[t.gender] = t.start
        if t.kind == "PRON":
            g = "m" if t.gender == "x" else t.gender
            cands = cur.get(g) or focus.get(g) or []
            if t.gender == "x":
                # English «it» has no gender: every piece named before is a candidate (a pawn is «she» to the
                # Russian gender table, not to «it») — but not the subject of the verb it is the object of («The
                # knight on f6 defends it»: «it» is not the knight; that would be «itself»).
                verb = max((o for o in toks if o.kind == "REL" and o.end <= t.start), key=lambda o: o.start, default=None)
                subj = max((o for o in toks if o.kind == "PIECE" and verb is not None and o.end <= verb.start),
                           key=lambda o: o.start, default=None)
                skip = (subj.ptype, subj.sq) if subj is not None and subj.sq is not None else None
                nxt = next((o for o in toks if o.start >= t.end and o.kind not in ("NEG", "BOUND")), None)
                as_subject = nxt is not None and nxt.kind == "REL" and bool(_CLAUSE_GAP.match(text_low[t.end:nxt.start]))
                if as_subject:
                    # "…, and it also eyes c2": the subject goes on — the previous verb's subject
                    cands = [(_R("piece", subj.ptype, subj.sq, subj.owner, text=subj.text), True)] \
                        if subj is not None and subj.sq is not None else []
                else:
                    here = [x for gg in ("m", "f") for x in cur.get(gg, []) if (x[0].ptype, x[0].sq) != skip]
                    cands = here or [x for gg in ("m", "f") for x in focus.get(gg, []) if (x[0].ptype, x[0].sq) != skip]
                    # "The knight on c3 defends e4, and the knight on f6 attacks it": a bare square named before is a
                    # candidate too
                    cands = cands + [(_R("square", sq=o.sq), False) for o in toks
                                     if o.kind == "SQ" and o.end <= t.start and not o.move_cue and not o.route]
            distinct = {key(r): r for r, _ in cands}
            r = None
            if last_move is not None and "N" in t.cases and 0 <= t.start - last_move.end <= 3:
                r = last_move_ref  # «Bb5+ он и слона уводит …»: the pronoun is the move's piece
            elif len(distinct) == 1 and t.gender == "x":
                r = next(iter(distinct.values()))
            elif len(distinct) == 1 and (noun_at.get(g, -1) < last_piece_at[g] if cur.get(g) else g not in noun_at):
                r = next(iter(distinct.values()))
            if r is not None and t.gender != "x" and "N" not in t.cases and r is not last_move_ref:
                # «Ферзь d1 не достаёт до f3 — его защищает пешка g2»: an object pronoun after a bare square named
                # since its antecedent may stand for what stands on that square («поле f3», the knight there) as well
                # — two readings, no verdict.  A square some piece of the sentence stands on is that piece's.
                since = last_piece_at.get(g, -1) if cur.get(g) else -1
                held = {o.sq for o in toks if o.kind == "PIECE" and o.sq is not None}
                if any(o.kind == "SQ" and since < o.start and o.end <= t.start and not o.move_cue and not o.route
                       and o.sq not in held and o.sq != r.sq for o in toks):
                    r = None
            out[id(t)] = r
            if r is not None:
                cur.setdefault(g, []).append((r, "N" in t.cases))
                last_piece_at[g] = t.start
        elif t.kind == "WHICH":
            r = None
            if last_noun is not None and t.start - last_noun[1] <= 4 and \
                    (last_noun[0].what == "square" or last_noun[2] == t.gender or t.gender in ("p", "x")):
                r = last_noun[0]
            out[id(t)] = r
        elif t.kind == "PIECE" and t.ptype and t.attr == "noun":
            last_noun = (_R("piece", t.ptype, t.sq, t.owner, text=t.text, from_sq=t.from_sq), t.end + (3 if t.sq is not None else 0), t.gender)
        elif t.kind == "PIECE" and t.ptype:
            agentive = last_rel is not None and set(t.cases) & set("GI") and t.start - last_rel.end < 30
            ref = _R("piece", t.ptype, t.sq, t.owner, text=t.text, from_sq=t.from_sq)
            if not agentive and set(t.cases) & set("NAI"):
                cur.setdefault(t.gender, []).append((ref, "N" in t.cases))
                last_piece_at[t.gender] = t.start
            last_noun = (ref, t.end + (3 if t.sq is not None else 0), t.gender)
        elif t.kind in ("SQ", "BOUND") and last_noun is not None and last_noun[0].sq == t.sq:
            last_noun = (last_noun[0], t.end, last_noun[2])
        elif t.kind == "SQ" and not t.move_cue:
            last_noun = (_R("square", sq=t.sq, text=t.text), t.end, "n")
        if t.kind == "MOVE":
            mr = _move_ref(t)
            if mr.piece and mr.to and not mr.castle:
                last_move = t
                last_move_ref = _R("piece", _PTYPE[mr.piece], chess.parse_square(mr.to), text=t.text)
                if not t.threat:
                    # «Чёрные сыграли Nf6. Он нападает на …»: the piece a written move moved is an antecedent, where it
                    # went
                    g = "f" if _PTYPE[mr.piece] in _FEMININE else "m"
                    cur.setdefault(g, []).append((last_move_ref, True))
                    last_piece_at[g] = t.start
        elif t.kind == "SQ" and re.search(r"(?:^|[:—–.!?(])\s*[«\"]?$", text_low[:t.start]):
            last_move, last_move_ref = t, _R("piece", None, t.sq, text=t.text)  # «d3: d3 он защищает e4»: the piece on d3
        if t.kind == "REL":
            last_rel = t if t.rel in _PASSIVE else None
        elif t.kind == "SEP":
            last_rel = None
    return out, cur


_FIRST_GAP = re.compile(
    r"^[\s:,]*(?:(?:же|эт\w+|тот|того|ту|та|this|that|две|два|три|обе|оба|two|three|both|на|по|в|во|сразу|прямо|еще|и|уже|"
    r"также|тоже|сам|сама|само|только|одновременно|заодно|теперь|сейчас|всё|все|ещё|целых|the|a|an|on|at|already|also|"
    r"only|directly|just|now|ваш\w*|тво\w*|сво\w*|мо[йюяе]\w*|их|его|ее|бел\w+|черн\w+|your|his|their|white'?s?|"
    r"black'?s?|enemy|opponent'?s|надежно|прочно|спокойно|просто|пол[еяю]|пункт\w*|клетк\w*|"
    # «грозит взять пешку d4», "threatens to take the pawn": the capture the threat names
    r"взять|забрать|съесть|побить|выиграть|to|take|capture|win)\s+)*$")
# Up to two attributive adjectives before a piece noun («атакует слабую пешку d4», «напал на центральную пешку»): words
# whose ending is an adjective's (the case agreement is the noun's); not a relation word, not a pronoun.
_ADJ = re.compile(W + r"[а-я]{2,}(?:ую|юю|ой|ей|ого|его|ый|ий|ая|яя|ое|ее|ые|ие|ых|их|ым|им|ыми|ими)" + E)


def _strip_adj(gap: str) -> str:
    """*gap* without up to two adjective-form words (for a gap that ends at a piece noun)."""
    words = list(_ADJ.finditer(gap))
    if not words or len(words) > 2 or any(_REL_RE.match(gap, w.start()) for w in words):
        return gap
    return _ADJ.sub(" ", gap)
_LIST_GAP = re.compile(r"^[\s,:]*(?:(?:и|а\s+также|and|or|или|на|по|the|a|еще|также|both|пол[еяю]|пункт\w*)\s*,?\s*)*$")


def bind(text: str, toks: list, focus: dict) -> list:
    low = text.lower()
    ante, _ = _antecedents(toks, focus, low)
    claims: list = []
    question = ""
    if text.rstrip().endswith("?"):
        question = "wh" if re.search(W + r"(?:кто|какая|какой|какие|какую|каким|что|чем|кем|which|what|who)" + E, low) else "yn"
        if re.search(W + r"ли" + E, low):
            question = "yn"
    clauses = _clauses(text, toks)
    agentive = set()
    for i, t in enumerate(toks):
        if t.kind == "REL" and t.rel in _PASSIVE:
            nxt = next((o for o in toks[i + 1:] if o.kind == "PIECE"), None)
            if nxt is not None and set(nxt.cases) & set("GI") and nxt.start - t.end < 30:
                agentive.add(id(nxt))
    if _GENERIC_EN.search(low):
        return []
    def agent_new_subject(before, r):
        """The clause's last subject before the verb is a person or a side («а ты тут же и напал», «но белые, конечно,
        нацелились»), not a piece."""
        subj = [t for t in before if t.kind in ("SIDE", "PIECE", "PRON", "MOVE", "SQ", "WHICH")]
        return bool(subj) and subj[-1].kind == "SIDE" and bool(re.fullmatch(
            r"ты|вы|я|мы|белые|ч[её]рные|соперник|противник|you|white|black", subj[-1].text.strip().lower()))

    spans = _relative_spans(toks, low, clauses)
    for r in [t for t in toks if t.kind == "REL"]:
        ca, cb = next(((a, b) for a, b in clauses if a <= r.start < b), (0, len(text)))
        # a list announced before a colon continues after it: «атакует две фигуры: пешку h6 и ладью»
        if low[cb - 1:cb] == ":" and re.search(W + r"(?:две|два|три|обе|оба|обоих|двух|two|three|both)\s+\w+\s*:$", low[ca:cb]):
            cb = next((b for a, b in clauses if a == cb), cb)
        inside = [t for t in toks if ca <= t.start < cb and t is not r and t.kind != "SEP"]
        before = [t for t in inside if t.end <= r.start]
        after = [t for t in inside if t.start >= r.end]
        # A relative clause («конь f6, который нападает на e4, сам защищён …», «пешка e4, которую атакует конь f6, …»)
        # is a clause of its own: the main verb's words skip it, and its own verb sees only its words.
        own = next(((a, b) for a, b in spans if a <= r.start < b), None)
        if own is None:
            before = [t for t in before if not any(a <= t.start < b for a, b in spans)]
        else:
            before = [t for t in before if own[0] <= t.start]
            after = [t for t in after if t.start < own[1]]
        # A negation stands next to its verb: never across a comma or a dash («Нет, конь f6 нападает на e4»).
        neg = any(t.kind == "NEG" and 0 <= r.start - t.end <= 12 and not any(o.kind == "REL" and t.end <= o.start < r.start for o in toks)
                  and not re.search(r"[,;:—–]", low[t.end:r.start])
                  for t in before) and r.rel not in ("UNDEF", "UNDEF_A")
        if r.rel not in ("UNDEF", "UNDEF_A"):
            subj = [t for t in before if t.kind in ("PIECE", "PRON", "WHICH", "MOVE", "SQ", "SIDE")]
            neg = neg or any(t.kind == "NEG" and (not subj or t.start > subj[-1].start)
                             and not re.search(r"[,;:—–]", low[t.end:r.start])
                             and not any(o.kind == "REL" and t.end <= o.start < r.start for o in toks) for t in before)
        if r.rel not in ("UNDEF", "UNDEF_A") and re.search(r"(?<![a-z])not(?![a-z])", r.text.lower()):
            neg = True  # "is not pinned", "is not attacked": the negation inside the words of the relation
        verb = r.text.split()[0]
        if r.rel == "UNDEF_A":
            verb = r.text.split()[-1]  # «никто не защищал»: the finite verb is the last word
        if r.rel in ("UNDEF", "HANG", "PASS_ATT", "PASS_DEF", "CTRL_G", "CTRL_I", "PASS_PIN") and \
                _APPEARS.search(low[max(ca, r.start - 40):r.start]):
            continue  # «пешка только выглядела беззащитной», «казалось, что конь под ударом»: an appearance, not a claim
        intent = bool(re.search(W + r"(?:хоч\w*|хотел\w*|хотят|чтобы)\s+(?:\w+\s+)?$", low[ca:r.start]))
        modal = not intent and (bool(re.search(
            W + r"(?:может|можешь|могут|можно|сможет|сможешь|смогут|способ\w+|приходится|придется|нужно|надо|должен|"
            r"должна|должны|обязан\w*|вынужден\w*|can|could|may|might|must|need\s+to|have\s+to)" + E, low[ca:r.start]))
            or (bool(re.search(r"(?:ть|ться|ти)$", verb)) and r.rel not in ("CAPW", "THREAT")
                and not re.search(W + r"(?:будет|будут|станет|станут|will)\s+(?:\w+\s+)?$", low[ca:r.start])
                # «продолжает давить», «начинает атаковать»: a phase verb — the relation holds now
                and not re.search(W + r"(?:продолжа(?:ет|ют|ешь)|начина(?:ет|ют|ешь)|keeps|continues)\s+$", low[ca:r.start])))
        perfective_future = bool(re.match(r"(?:под|за|при|на|от|вы|по|у|пере|сыгра|сдела|спас|съе|созда)\w+(?:ит|ет|ут|ют|ят|ат)$", verb)) and \
            not re.search(r"(?:ает|яет|ует|ивает|ывает|ают|яют|уют|ивают|ывают)$", verb) and verb not in ("нападает", "подкрепит")
        tense = "future" if _FUTURE.search(low[ca:cb]) or perfective_future else (
            "past" if re.search(r"(?:л|ла|ли|ло|в)$", verb) or re.search(W + r"(?:был[аио]?|were|was)" + E, low[ca:r.end])
            or _PAST_ADV.search(low[ca:cb]) or _LINK_PAST.search(low[ca:r.start])
            else "present")
        unresolved = []
        inverted_agent = False

        # «ферзь бьёт по королю через f2 и g4»: two squares to pass through are the moves it would make, not a line
        routes = bool(_ROUTES.search(low[r.end:cb]))
        # «король успевает встать на b7 или b6, откуда поле a8 уже под контролем»: what holds from a square the piece
        # would go to — a position the sentence only imagines
        whence = bool(re.search(W + r"(?:откуда|оттуда|from\s+where|from\s+there)" + E, low[max(ca, r.start - 60):r.start]))
        # «пешка h3 связана королём»: a king pins nothing — «связан + the king (instrumental)» is «tied to the king», held
        # by it, not a pin
        if r.rel in ("PIN", "PASS_PIN") and re.match(r"\s*(?:своим\s+|собственным\s+|его\s+|её\s+|ее\s+)?корол(?:ём|ем)" + E, low[r.end:r.end + 30]):
            whence = True

        # «поддержал слона c4 в атаке на f7»: joins the attack on f7, it does not defend the bishop
        joins = r.rel in ("DEF", "PASS_DEF") and bool(re.search(
            W + r"(?:в\s+(?:атаке|нападении|давлении|ударе)|in\s+the\s+attack)" + E, low[r.end:cb]))
        # «Мой слон вернулся на f8, а ты тут же и напал на e5», «… но белые нацелились на h7»: a person or a side named
        # as the subject of this clause is the verb's subject, not a piece of the clause before (a capture «грозят
        # взять ферзём» names its piece as the instrument and stays)
        # «(Своим) ходом Bc5 чёрные защитили пешку e5», «Ходом d4 ты отгоняешь коня c6»: the move named by «ходом» is
        # what does it
        by_move = next((t for t in before if (t.kind == "MOVE" or (t.kind == "SQ" and t.move_cue)) and not t.threat
                        and re.search(W + r"ходом\s*$", low[max(ca, t.start - 12):t.start])), None)
        # «Чем белые защищают пешку e4?», «Кто защищает слона c4?», «Какой фигурой чёрные защищают f7?»: the question
        # takes for granted that some piece (of that side) does it
        wh_any = question == "wh" and r.rel in ("ATT", "DEF", "HOLD", "SOFT") and bool(re.search(
            # (not «кто/что защищает …?»: a teacher's question whose answer may be «никто»)
            W + r"(?:чем|кем|как(?:ой|ими)\s+(?:\w+\s+)?фигур(?:ой|ами)|как(?:ая|ую|ие)\s+из|котор(?:ая|ую|ые)\s+из|"
            r"which\s+(?:\w+\s+)?piece)" + E, low[ca:r.start]))
        if r.rel != "CAPW" and not intent and agent_new_subject(before, r) and by_move is None and not wh_any and \
                not any(t.kind == "PIECE" and "I" in t.cases for t in after):
            continue

        def add(rel, agent, pats, **kw):
            if intent and (agent is None or agent.what != "move"):
                return  # «хочешь отогнать коня» is checkable only as the purpose of a named move
            if joins:
                return
            if whence and not routes and tense == "future" and rel in ("ATT", "SOFT", "HOLD") and agent is not None and \
                    agent.what == "piece" and agent.sq is not None and agent.ptype and agent.ptype != chess.PAWN:
                wm = re.search(r"([a-h][1-8])\s*,?\s*(?:откуда|оттуда)" + E, low[max(ca, r.start - 60):r.start])
                if wm and chess.parse_square(wm.group(1)) == agent.sq:
                    kw["plan"] = True  # the square the plan puts the piece on, named right before «откуда»
            if (routes or whence) and not kw.get("skip") and not kw.get("plan"):
                kw["skip"] = "route" if routes else "whence or tied"
            if "count" not in kw and rel in ("PASS_ATT", "PASS_DEF", "ATT", "DEF"):
                kw["count"] = _count(low, ca, cb, r, agent)
            claims.append(_Raw(rel, agent, [p for p in pats if p is not None], neg, tense, question, r.start, (ca, cb),
                               verb=verb, modal=modal and rel != "UNDEF", unresolved=bool(unresolved), end=r.end,
                               cover="прикры" in r.text.lower(),
                               inverted=inverted_agent, **kw))

        def pron(t):
            got = ante.get(id(t))
            if got is None:
                if t.sq is not None:  # «он на f6»: the square says which piece
                    return _R("piece", None, t.sq, None, text=t.text, pronoun=True)
                unresolved.append(t)
                return None
            if t.sq is not None and got.sq is not None and got.sq != t.sq:
                unresolved.append(t)
                return None
            return _R(got.what, got.ptype, t.sq if t.sq is not None else got.sq, got.owner, text=t.text,
                      from_sq=got.from_sq, pronoun=True)

        if r.rel in _PASSIVE or r.rel == "UNDEF_A":
            pat = None
            if r.rel in ("UNDEF", "UNDEF_A") and re.search(
                    W + r"(?:кроме|except|but|только|only|если\s+не\s+считать|не\s+считая|разве\s+что|за\s+исключением|"
                    r"помимо|со\s+стороны|с\s+фланга|с\s+тыла|сбоку|сзади|спереди|from\s+the\s+side)" + E, low[r.end:cb]):
                continue  # «ничем не прикрыт, если не считать короля», «… со стороны слона b4», «… с фланга»
            if r.rel == "UNDEF_A":
                # «nothing defends h4»: the object is what follows the verb — not a piece named earlier in the clause
                nxt = next((t for t in after if (t.kind == "PRON" and "A" in t.cases) or (t.kind == "PIECE" and "A" in t.cases)
                            or (t.kind == "SQ" and not t.move_cue and not t.route)), None)
                acc = [nxt] if nxt is not None else \
                    [t for t in inside if t.kind == "PRON" and "A" in t.cases] + \
                    [t for t in inside if t.kind == "PIECE" and "A" in t.cases]
                pat = pron(acc[0]) if acc and acc[0].kind == "PRON" else (_ref(acc[0]) if acc else None)
                add("UNDEF", None, [pat])
                continue
            # «Конь f3 прыгает на g5, и под ударом оказывается пешка f7», «…, а под боем уже f7»: the inverted passive
            # names its object after the cue — the list after it comes first, and the backward search never crosses a
            # move told in words (its piece is the subject of the other predicate).
            conj_first = r.rel == "PASS_ATT" and bool(re.search(
                r"(?:^|[,—–]\s*)(?:и|а|и\s+тогда|тогда|теперь|сразу)\s+(?:\w+\s+)?$", low[ca:r.start].strip(" ") + " "))
            for t in ([] if conj_first else before[::-1]):
                if t.kind == "MOVE" and t.span:
                    break
                if t.kind in ("PRON", "WHICH") and "N" in t.cases:
                    pat = pron(t)
                    break
                if t.kind == "PIECE" and "N" in t.cases and id(t) not in agentive:
                    pat = _ref(t)
                    break
                if t.kind == "SQ" and not t.move_cue and not t.route:
                    pat = _ref(t)
                    break
                if t.kind == "REL":
                    break
            pats = [pat]
            if pat is None and r.rel == "PASS_ATT":
                pats = []
                if conj_first and not _forward_list(after, low, r, pats):
                    for t in before[::-1]:  # nothing after the cue: the object before it after all
                        if t.kind == "MOVE" and t.span:
                            break
                        if t.kind == "PIECE" and "N" in t.cases and id(t) not in agentive:
                            pats.append(_ref(t))
                            break
                        if t.kind == "SQ" and not t.move_cue and not t.route:
                            pats.append(_ref(t))
                            break
                        if t.kind == "REL":
                            break
            if pat is None and r.rel == "PASS_ATT" and not pats:
                # «под ударом остаются и пешка h2, и ладья f1»: the list right after (not «…, и её защищает пешка g7»)
                pats = []
                _forward_list(after, low, r, pats)
            # the agent: genitive after «под ударом/боем/защитой/контролем» (под ударом коня), instrumental after a
            # participle (атакован пешкой, защищён конём, прострелено слоном)
            want = "G" if re.match(r"под\s", r.text.lower()) else "I"
            by = lambda t: "A" in t.cases and re.search(r"(?<![a-z])by\s+(?:\w+\s+){0,2}$", low[r.end:t.start])  # noqa: E731
            ag = [t for t in after if t.kind == "PIECE" and t.start - r.end < 30
                  and (want in t.cases or by(t))  # "is attacked by the queen": English has no case, «by» says it
                  and ("N" not in t.cases or t.sq is not None or by(t))
                  and not (r.rel == "PASS_PIN" and t.ptype == chess.KING)
                  and not _with_governs(low, after, r.end, t, r"с|со|to")]
            to = None
            if r.rel == "PASS_PIN":  # «связана твоим слоном d4 с королём g1»: the piece behind
                bk = [t for t in after if t.kind == "PIECE" and "I" in t.cases and t.sq is not None
                      and _with_governs(low, after, r.end, t, r"с|со")]
                to = _ref(bk[0]) if bk else None
            if r.rel == "PASS_ATT" and re.match(r"\s*не\s+(?:стоит|стоят|находится|оказыва\w+|оста[её]тся)" + E, low[r.end:r.end + 30]):
                neg = True  # «под боем не стоит»
            first_after = next((t for t in after if t.kind != "NEG"), None)
            if r.rel in ("PASS_ATT", "CTRL_G") and not ag and first_after is not None and \
                    first_after.kind in ("SQ", "MOVE") and re.fullmatch(r"\s*", low[r.end:first_after.start]):
                # «Слон c4 под ударом b3 уйдёт на a6» (review miss2 01.11): the attacker is named by a square or a move with
                # no piece — what comes there, not what stands there now; not read
                continue
            if not [p for p in pats if p is not None] and not unresolved:
                pats = _elided(claims, ca, low, r) or pats  # «… атакована пешкой c3, но защищена конём e4»
            if not [p for p in pats if p is not None] and not unresolved and r.rel in ("UNDEF", "HANG", "PASS_ATT", "PASS_DEF") \
                    and re.search(r"\s[—–]\s*$", low[max(0, ca - 3):ca]) and r.start - ca < 12:
                # «Конь на f6 — без прикрытия», «Пешка e5 — под ударом»: the piece the clause before names, with no
                # verb of its own
                pa = next((a for a, b in clauses if b == ca), None)
                ptoks = [t for t in toks if pa is not None and pa <= t.start < ca]
                noms = [t for t in ptoks if t.kind == "PIECE" and "N" in t.cases and t.sq is not None]
                if noms and not any(t.kind in ("REL", "MOVE") for t in ptoks):
                    pats = [_ref(noms[-1])]
            add(r.rel, _ref(ag[0]) if ag else None, pats, to=to)
            continue
        if r.rel == "CAPW":
            ins = [t for t in after if t.kind == "PIECE" and "I" in t.cases and t.start - r.end < 20]
            sqm = re.match(r"[^.;:]{0,30}?\bна\s+([a-h][1-8])", low[r.end:cb])
            if ins and sqm and not re.search(r"(?:на|в)\s*$", low[r.end:ins[0].start]):
                side = next((t.owner for t in before[::-1] if t.kind == "SIDE"), None)
                add("CAPW", _R("side", owner=side), [_R("square", sq=chess.parse_square(sqm.group(1)))],
                    instrument=_R("piece", ins[0].ptype, None, ins[0].owner))
                continue
            if re.match(r"\s+(?:на|с\s+шахом\s+на)\s+[a-h][1-8]", low[r.end:r.end + 20]):
                continue
            if _TAKE_SURE.match(verb):  # «он забирает пешку f7 и нападает на …»: a capture told — the board after it
                r = Tok("REL", r.start, r.end, r.text, rel="TAKE")
            elif re.match(r"бь", verb):
                r = Tok("REL", r.start, r.end, r.text, rel="ATT")
            else:
                continue
        if r.rel == "THREAT":
            m = re.match(r"\s*(?:взять|забрать|побить|съесть)\s+(\w+)\s+на\s+([a-h][1-8])", low[r.end:cb])
            if m and m.group(1) in _P and "I" in _P[m.group(1)][1]:
                side = next((t.owner for t in before[::-1] if t.kind == "SIDE"), None)
                add("CAPW", _R("side", owner=side), [_R("square", sq=chess.parse_square(m.group(2)))],
                    instrument=_R("piece", _P[m.group(1)][0]))
                continue
        if r.rel == "LOCK":
            # «слон на c1, запертый своими же пешками d3 и h3» / «пешка e6 перекрыла слону f8» / «d6 перекрыла дорогу слону c8»
            locked = [t for t in before if t.kind == "PIECE" and t.sq is not None and t.ptype != chess.PAWN]
            bl = [t for t in after if t.kind == "PIECE" and "I" in t.cases]
            blsq = [t.sq for t in bl if t.sq is not None]
            if bl:
                j = toks.index(bl[0])
                blsq += [t.sq for t in toks[j + 1:j + 4] if t.kind == "SQ" and t.start < cb]
            dat = [t for t in after if t.kind == "PIECE" and "D" in t.cases and t.sq is not None and t.ptype != chess.PAWN]
            subj = [t for t in before if (t.kind == "PIECE" and "N" in t.cases and t.sq is not None) or (t.kind == "SQ" and not t.move_cue)]
            if dat and subj and not neg:
                add("LOCK", _R("piece", dat[0].ptype, dat[0].sq, dat[0].owner, text=dat[0].text), [],
                    blockers=[subj[-1].sq])
            elif locked and blsq and not neg:
                add("LOCK", _ref(locked[-1]), [], blockers=blsq)
            continue
        if r.rel == "PIN_N":
            mv = [t for t in after if t.kind == "MOVE" and t.start - r.end < 6]
            if mv and re.search(r"(?:избежать|избегая|предотвратить|против|избавиться|не\s+допустить|avoid|prevent)\s+\w*\s*$",
                                low[max(0, r.start - 30):r.start]):
                add("PIN_AFTER", _R("move", move=mv[0], text=mv[0].text), [])
            continue

        # ── active relations ──  agent: nominative / move / pronoun / «с sq» before the verb, or after it when an
        # accusative stands before (object first: «её защищает конь e4»); patients: accusative, «на/по»+…, bare squares
        def is_agent(t):
            return (t.kind == "PIECE" and "N" in t.cases and not t.attr and not re.search(r"(?:\s|^)(?:с|со)\s*$", low[max(0, t.start - 4):t.start])) or \
                t.kind == "MOVE" or (t.kind == "SQ" and t.move_cue) or (t.kind in ("PRON", "WHICH") and "N" in t.cases) or \
                t.kind == "SIDE"

        def to_ref(t):
            if t.kind in ("PRON", "WHICH"):
                return pron(t)
            if t.kind == "SQ" and not t.move_cue:
                return _R("piece", None, t.sq, None, text=t.text)  # «её прикрывают d6 и …»: what stands on d6
            if t.kind == "SQ":
                return _R("move", move=Tok("MOVE", t.start, t.end, t.text, san=t.text), text=t.text)
            if t.kind == "SIDE":
                return _R("side", owner=t.owner)
            return _ref(t)

        to = None
        # a piece named right after an earlier verb of the clause is its object, not this verb's subject ("b3 hits the
        # bishop and threatens to win it"), unless a verb of its own follows it
        cand = [t for t in before if is_agent(t) and not (
            t.kind == "PIECE" and "A" in t.cases and any(o.kind == "REL" and o.end <= t.start for o in before)
            and not _heads_clause(toks, t, low, cb))]
        agent_t = cand[-1] if cand else None
        acc_before = [t for t in before if (t.kind in ("PIECE", "PRON", "WHICH") and "A" in t.cases and "N" not in t.cases)
                      and (agent_t is None or t.start > agent_t.start)]
        n_after = next((t for t in after if t.kind == "PIECE" and t.cases in ("N",) and t.start - r.end < 25
                        and _FIRST_GAP.match(re.sub(r"\b(?:и|both)\b", " ", low[r.end:t.start])) and "," not in low[r.end:t.start]), None)
        if n_after is not None and (agent_t is None or agent_t.kind == "SIDE" or acc_before):
            agent_t = n_after
        elif acc_before and (agent_t is None or agent_t.kind == "SIDE"):
            # «её прикрывают d6 и конь c6»: the object first, the agents after the verb — a bare square names one
            first = next((t for t in after if t.kind in ("PIECE", "SQ") and t.start - r.end < 25), None)
            if first is not None and _FIRST_GAP.match(re.sub(r"(?:бел|черн)\w*", " ", low[r.end:first.start])) and \
                    ((first.kind == "PIECE" and (first.cases == "N" or (not first.ptype and _COUNT_PIECES.search(low[r.end:first.end]))))
                     or (first.kind == "SQ" and not first.move_cue and not first.route)):
                agent_t = first
        if agent_t is not None and agent_t.start < r.start and agent_t.kind != "WHICH" and \
                re.search(r",\s*(?:где|куда|откуда|когда|если|пока|чтобы|раз|where|when|if)" + E, low[agent_t.end:r.start]):
            agent_t = None  # «конь ушёл с поля, где его атаковали»: the verb belongs to a subordinate clause
        agent = to_ref(agent_t) if agent_t is not None else None
        # «Лучше b5 — отгоняешь коня g5»: a 2nd-person verb with no agent of its own is the move the sentence told
        # …and «Начни с b3 — белые сразу нападают на слона»: a side is the agent of the move it just made
        if (agent is None or agent.what == "side") and (re.search(r"(?:ешь|ишь|ете|ите)$", verb) or (agent is not None and agent.what == "side")):
            mv = [t for t in toks if (t.kind == "MOVE" or (t.kind == "SQ" and t.move_cue)) and t.start < r.start
                  and t.end >= ca - 30 and not t.threat]
            if mv:
                agent = to_ref(mv[-1]) if mv[-1].kind == "MOVE" else _R("move", move=Tok("MOVE", mv[-1].start, mv[-1].end, mv[-1].text, san=mv[-1].text))
        wh = re.search(W + r"(?:кто|что|who|what)\s+(?:\w+\s+)?$", low[ca:r.start])
        wh_agent = bool(wh)
        if wh and agent_t is not None and agent_t.start < r.start and agent_t.end <= ca + wh.start():
            agent_t = agent = None  # «раз слон b5 связал коня, кто теперь защищает e5?»: «кто» is the agent
        if agent is None and not acc_before and not wh_agent:
            prev = [t for t in toks if t.end <= ca and ((t.kind == "PIECE" and "N" in t.cases and t.sq is not None) or t.kind == "MOVE")]
            if prev and question:
                agent_t = prev[-1]
                agent = to_ref(agent_t)
        if agent is None and _PLAN_CUE.search(low[ca:r.start]):
            # «фианкетто с g3 и слоном на g2 будет целиться туда»: the one piece the set-up names acts
            named = [t for t in before if t.kind == "PIECE" and t.sq is not None and t.ptype]
            if len(named) == 1:
                agent_t = named[0]
                agent = _ref(agent_t)
        if (agent is None or agent.what == "side") and by_move is not None:
            agent_t = by_move
            agent = to_ref(by_move)
        if (agent is None or agent.what == "side") and r.rel not in ("TAKE", "CAPW"):
            # «Белые защищают пешку e4 конём f3»: a side (or nobody) as the subject, the piece in the instrumental —
            # that piece does it
            ins = next((t for t in after if t.kind == "PIECE" and "I" in t.cases and t.sq is not None and t.ptype
                        and t.start - r.end < 40
                        and not re.search(r"(?:^|\s)(?:с|со|вместе\s+с|together\s+with|with)\s+(?:\w+\s+)?$",
                                          low[max(r.end, t.start - 25):t.start])), None)
            if ins is not None:
                side = agent.owner if agent is not None else None
                agent_t = ins
                agent = _R("piece", ins.ptype, ins.sq, ins.owner if ins.owner is not None else side, text=ins.text)
        if wh_any and (agent is None or agent.what == "side"):
            side = agent.owner if agent is not None else next((t.owner for t in before if t.kind == "SIDE"), None)
            if side is None:
                om = re.search(W + r"из\s+(бел|черн)\w*" + E, low[ca:r.start])
                side = {"бел": chess.WHITE, "черн": chess.BLACK}.get(om.group(1)) if om else None
            agent = _R("piece", 0, None, side if side in (chess.WHITE, chess.BLACK) else None, text="")
        if r.rel == "TAKE" and (agent is None or agent.what == "side"):
            add("TAKE", agent, [])  # «Чёрные забирают пешку e4»: a capture we cannot place — what follows is unknown
            continue
        if agent is None or agent.what == "side":
            continue
        pats, last = [], r.end
        inverted = agent_t is not None and agent_t.start > r.start
        for t in ([] if inverted else after):
            if t is not agent_t and t.kind in ("PIECE", "PRON", "SQ") and _heads_clause(toks, t, low, cb):
                break  # «… attacks e5, and the knight on c6 defends it»: the subject of the next clause, not an object
            if t is agent_t or t.kind in ("OWNER", "NEG", "BOUND", "NOUN"):
                if t.kind == "OWNER" and pats and not _LIST_GAP.match(low[last:t.start]):
                    break
                if t.kind == "BOUND" or (t.kind == "OWNER" and pats):
                    last = t.end
                continue
            if t.kind == "REL" or (t.kind == "PIECE" and t.cases == "N") or \
                    (t.kind == "PIECE" and re.match(r"\s+(?:can|can't|cannot|is|has|will|must|moves|goes|may)" + E, low[t.end:t.end + 10])):
                break
            gap = low[last:t.start]
            if t.kind == "PIECE" and t.ptype == 0 and t.sq is None and re.search(r"(?:две|два|три|обе|оба|обоих|двух|two|three|both)\s*$", gap):
                last = t.end  # «атакует две фигуры: пешку h6 и ладью» — the count announces the list
                continue
            if t.kind == "SQ" and t.route:
                last = t.end  # «бьёт через f2», «по диагонали a1–h8»: a route, not a target
                continue
            if t.kind == "PIECE":
                gap = _strip_adj(gap)
            if pats and not _LIST_GAP.match(gap):
                break
            if not pats and (t.start - r.end > 40 or not _FIRST_GAP.match(gap)):
                if t.kind == "PRON" and _THERE.search(gap):
                    pass
                else:
                    break
            if t.kind == "PIECE" and ("A" in t.cases or ("D" in t.cases and re.search(r"по\s*$", (r.text if not pats else "") + gap))
                                      or (r.rel == "SOFT" and "G" in t.cases)):
                pats.append(_ref(t))
            elif t.kind == "SQ" and not t.move_cue:
                if re.search(r"(?:^|\s)(?:с|со|из|from)\s+$", gap):  # «слон бьёт с g5»: where the agent stands
                    if agent is not None and agent.what == "piece" and agent.sq is None:
                        agent = _R("piece", agent.ptype, t.sq, agent.owner, text=agent.text, from_sq=True)
                    last = t.end
                    continue
                pats.append(_ref(t))
            elif t.kind == "PRON" and "A" in t.cases and not re.match(r"\s*(?:" + _PIECE_ALT + r")" + E, low[t.end:t.end + 12]):
                pats.append(pron(t))
            else:
                if pats:
                    break
                continue
            last = t.end
        if not pats and not inverted:
            th = _THERE.search(low, r.end, cb)
            if th and th.start() - r.end <= 30:
                sq = _there_square(toks, low, th.start(), agent, focus)
                if sq is not None:
                    pats.append(_R("square", sq=sq, text=th.group(0)))
                else:
                    unresolved.append(th)
        if inverted:  # «держат её только пешка c2»: the accusative between the verb and its agent
            for t in after:
                if t is agent_t:
                    break
                if t.kind == "PRON" and "A" in t.cases:
                    pats.append(pron(t))
                    break
                if t.kind == "PIECE" and "A" in t.cases and "N" not in t.cases:
                    pats.append(_ref(t))
                    break
        if not pats and inverted:
            sqs = [t for t in before if t.kind == "SQ" and not t.move_cue and not t.route]
            if len(sqs) == 1:
                pats.append(_ref(sqs[0]))
        if not pats and not (inverted and any(t.kind == "PRON" and "A" in t.cases and r.end <= t.start < agent_t.start for t in after)):
            for t in before[::-1]:
                if re.search(r"[,;]|" + W + r"(?:и|а|но)" + E, low[t.end:r.start]):
                    break  # «Пешку f7 слон бьёт»: the object right before, in the same stretch — not another verb's
                if t.kind == "PIECE" and t.cases in ("A", "AG") and t.sq is not None:
                    pats.append(_ref(t))
                    break
                if t.kind in ("PRON", "WHICH") and "A" in t.cases:
                    pats.append(pron(t))
                    break
        joint = agent_t is not None and agent_t.kind == "PIECE" and bool(re.match(
            r"\s*(?:[a-h][1-8]\s+)?(?:вместе\s+)?(?:с|со)\s+(?:\w+\s+)?(?:" + _PIECE_ALT + r")" + E, low[agent_t.end:agent_t.end + 40])) and \
            any(t.kind == "PIECE" and "I" in t.cases and agent_t.end < t.start <= agent_t.end + 40 for t in toks)
        if r.rel == "PIN" and to is None:  # «ладья e1 связывает коня e6 с ладьёй e8»: the piece behind
            bk = [t for t in after if t.kind == "PIECE" and "I" in t.cases and t.sq is not None
                  and re.search(r"(?:^|\s)(?:с|со)\s+(?:\w+\s+)?$", low[r.end:t.start])]
            to = _ref(bk[0]) if bk else None
        if re.match(r"(?:нацел|направ|навел|наводит)", verb) and len(pats) >= 2 and pats[0] is not None and \
                pats[0].what == "piece" and pats[1] is not None and pats[1].what == "square":
            # «ты нацелил слона на f7», «Ходом 3.Bc4 ты нацелил слона на f7»: the piece aimed is the subject (the move's
            # piece when the move moved one of that kind), the square its target
            if agent.what == "move" and _move_ref(agent.move).piece == _LETTER.get(pats[0].ptype):
                pass
            else:
                agent = pats[0]
            pats = pats[1:]
        own_sq = agent.sq if agent.what == "piece" else (
            chess.parse_square(_move_ref(agent.move).to) if agent.what == "move" and _move_ref(agent.move).to else None)
        if own_sq is not None:  # «слона на g7, откуда он будет давить», «после ...exd5 — давление на d5»: not its own target
            pats = [p for p in pats if p is None or p.sq != own_sq]
        if not [p for p in pats if p is not None] and not unresolved:
            pats = _elided(claims, ca, low, r, inverted)  # «Пешку d4 атакует пешка c3, а защищает конь e4»
            if not pats:
                continue
        inverted_agent = inverted
        add(r.rel, agent, pats, skip="joint" if joint else "", to=to)  # two pieces together: neither alone is claimed
        if not inverted and agent_t is not None and agent_t.kind == "PIECE" and not joint:
            k = toks.index(agent_t) - 1
            nxt = agent_t.start
            while k >= 0 and toks[k].kind in ("BOUND", "OWNER", "SIDE"):
                nxt = min(nxt, toks[k].start) if toks[k].kind != "BOUND" else nxt
                k -= 1
            # A coordinated subject names its last member with «и» («конь, слон и ладья бьют …»); a bare comma before
            # the agent is an enumeration of where things stand, the verb the last one's («чёрный король на a8, ладья
            # на f8, ферзь чёрных на f2 давит на b2»).
            joined = False
            while k >= 0 and toks[k].kind == "PIECE" and "N" in toks[k].cases and toks[k].start >= ca and \
                    re.fullmatch(r"\s*(?:(?:на\s+)?[a-h][1-8]\s*)?(?:,|и|а\s+также)\s*" if joined else
                                 r"\s*(?:(?:на\s+)?[a-h][1-8]\s*)?,?\s*(?:и|а\s+также)\s*", low[toks[k].end:nxt]):
                joined = True
                add(r.rel, _ref(toks[k]), pats, to=to)
                nxt = toks[k].start
                k -= 1
                while k >= 0 and toks[k].kind in ("BOUND", "OWNER", "SIDE"):
                    nxt = min(nxt, toks[k].start) if toks[k].kind != "BOUND" else nxt
                    k -= 1
        if inverted and agent_t is not None and agent_t.kind in ("PIECE", "SQ"):
            # «пешку e7 бьют и конь c6, и ферзь d8, и король e8»: every agent of the list
            last = agent_t.end
            for t in after:
                if t.start < last:
                    continue
                if t.kind in ("OWNER", "BOUND", "NOUN"):
                    last = t.end if t.kind == "BOUND" else last
                    continue
                ok = (t.kind == "PIECE" and "N" in t.cases) or (t.kind == "SQ" and acc_before and not t.move_cue and not t.route)
                if not ok or not re.fullmatch(r"[\s,]*(?:и|а\s+также|and)?[\s,]*(?:и\s+)?", low[last:t.start]):
                    break
                add(r.rel, _ref(t), pats)
                last = t.end
    return claims


_CLAUSE_GAP = re.compile(r"^\s*(?:(?:also|already|now|only|still|then|too|тоже|также|уже|сразу|теперь|сам|сама|"
                         r"же|в\s+свою\s+очередь),?\s*)*$")


_NUM = {"дв": 2, "тр": 3, "четыр": 4, "обе": 2, "оба": 2, "обоих": 2, "two": 2, "three": 3, "four": 4, "both": 2}
_COUNT_ADV = re.compile(W + r"(?:(?P<adv>дважды|трижды|четырежды|twice)|(?P<n>два|две|три|четыре|two|three|four)\s+(?:раза|times))" + E)
_COUNT_PIECES = re.compile(W + r"(?P<n>две|два|двумя|двух|три|тремя|трех|четыре|четырьмя|обе|оба|обоих|two|three|four|both)\s+"
                           r"(?:(?:бел|черн)\w*\s+|(?:white|black)\s+)?(?:фигур\w*|pieces)" + E)


def _numval(word: str) -> Optional[int]:
    word = word.replace("ё", "е")
    if word in ("дважды", "twice"):
        return 2
    if word == "трижды":
        return 3
    if word == "четырежды":
        return 4
    return next((v for k, v in _NUM.items() if word.startswith(k)), None)


def _count(low, ca, cb, r, agent) -> Optional[int]:
    """How many attackers or defenders a passive or a generic subject names: «атакована дважды», «защищён три раза»,
    «защищена двумя фигурами», «две белые фигуры атакуют пешку e5»; None when no count is said."""
    clause = low[ca:cb]
    m = _COUNT_ADV.search(clause)
    if m and r.rel in ("PASS_ATT", "PASS_DEF"):
        return _numval(m.group("adv") or m.group("n"))
    m = _COUNT_PIECES.search(clause)
    if m and (r.rel in ("PASS_ATT", "PASS_DEF") or (agent is not None and agent.what == "piece" and not agent.ptype)):
        return _numval(m.group("n"))
    return None


_GENDER_END = (("ы", "p"), ("а", "f"), ("о", "n"), ("н", "m"), ("т", "m"))


def _elided(claims, ca, low, r, inverted: bool = True) -> list:
    """«Пешка d4 атакована пешкой c3, но защищена конём e4», «Пешку d4 атакует пешка c3, а защищает конь e4»: a clause
    after «но/а/зато/и» whose verb has no object of its own goes on with the object of the clause right before it
    (its gender agreeing with a participle's ending)."""
    head = low[max(0, ca - 14):r.start]
    # nothing between the conjunction and the verb but adverbs: «но та теперь защищена», «но этот пункт прикрыт», «а
    # слон бьёт …» name their own subject
    if not re.search(r"(?:,|—|–)\s*(?:но|а|зато|и|but|and)\s+(?:(?:тоже|также|уже|теперь|сейчас|сразу|еще|при\s+этом|"
                     r"зато|still|also|already|now)\s+)*$", head):
        return []
    if r.rel not in _PASSIVE and not inverted:
        return []  # an active verb with its object elided names its agent after it («а защищает конь e4»)
    prev = [c for c in claims if c.clause[1] == ca and c.patients and all(p is not None for p in c.patients)]
    if not prev:
        return []
    last = prev[-1]
    pats = list(last.patients)
    if r.rel in _PASSIVE and last.rel not in _PASSIVE and not last.inverted:
        # «Конь e4 атакует пешку c3, но защищён пешкой d6»: the second predicate's subject is the first one's (after
        # an object-first clause — «пешка f2 — её бьёт пешка f3, а защищена только королём» — the object is the topic)
        if last.agent is None or last.agent.what != "piece":
            return []
        pats = [last.agent]
    word = r.text.lower().split()[-1]
    if r.rel in ("PASS_DEF", "PASS_ATT", "PASS_PIN", "UNDEF") and re.search(r"(?:н|т)[аоы]?$", word):
        g = next((g for end, g in _GENDER_END if word.endswith(end)), None)
        for p in pats:
            pg = None if p.what != "piece" or not p.ptype else ("f" if p.ptype in _FEMININE else "m")
            if g is not None and pg is not None and g != pg and g != "p":
                return []
    return pats


def _forward_list(after, low, r, pats) -> bool:
    """«под ударом остаются и пешка h2, и ладья f1», «под боем оказывается пешка f7»: the objects named right after
    an inverted passive cue, appended to *pats*; True when there is one."""
    last = r.end
    for t in after:
        if t.kind in ("BOUND", "OWNER", "NEG", "NOUN"):
            last = t.end if t.kind == "BOUND" else last
            continue
        gap = _strip_adj(low[last:t.start]) if t.kind == "PIECE" else low[last:t.start]
        if not (_LIST_GAP.match(gap) or (not pats and _FIRST_GAP.match(re.sub(
                W + r"(?:остают\w*|оста[её]тся|оказ\w+|сразу|одна|один|два|две|уже|теперь|сейчас)" + E, " ", gap)))):
            break
        if t.kind == "PIECE" and t.cases in ("N", "NA", "GNA") and t.sq is not None:
            pats.append(_ref(t))
        elif t.kind == "SQ" and not t.move_cue and not t.route and not pats:
            pats.append(_ref(t))
        else:
            break
        last = t.end
    return bool(pats)


def _relative_spans(toks, low, clauses) -> list:
    """The relative clauses of the sentence, (start, end): from the comma before «который/которую/на которую/which»
    to the comma that closes it (or the end of its clause)."""
    out = []
    for w in toks:
        if w.kind != "WHICH":
            continue
        m = re.search(r",\s*(?:(?:на|в|по|с|со|за|под|от|к|из|у|для|of|on|to|by|from)\s+)?$", low[max(0, w.start - 8):w.start])
        if not m:
            continue
        start = max(0, w.start - 8) + m.start()
        cb = next((b for a, b in clauses if a <= w.start < b), len(low))
        close = low.find(",", w.end, cb)
        out.append((start, close if close >= 0 else cb))
    return out


def _heads_clause(toks, t, low, cb) -> bool:
    """The mention *t* is the subject of a clause of its own: an active relation word follows it (its square and a
    negation may come between) — «The knight on f3 attacks e5 and the knight on c6 defends it»: «the knight on c6» is
    not a second object of «attacks». English has no case to tell the subject from the object, so the order does."""
    i = toks.index(t)
    end = t.end
    for o in toks[i + 1:]:
        if o.start >= cb:
            return False
        if o.kind == "BOUND" or (o.kind == "OWNER" and o.start - end <= 2):
            end = o.end
            continue
        if o.kind == "NEG":
            if not _CLAUSE_GAP.match(low[end:o.start]):
                return False
            end = o.end
            continue
        if o.kind != "REL" or not _CLAUSE_GAP.match(low[end:o.start]):
            return False
        return o.rel not in _PASSIVE or bool(re.match(r"(?:is|are)\s", o.text))
    return False


def _there_square(toks, low, at, agent, focus):
    """«туда», «это ослабленное место»: the one free square named before it in this sentence (not a move, not where a
    piece stands, not a «с/через» square), else the one the sentence before named; None when not exactly one."""
    agent_sq = agent.sq if agent is not None else None
    free = {t.sq for t in toks if t.kind == "SQ" and t.end <= at and not t.move_cue and not t.route and t.sq != agent_sq
            and not re.search(r"(?:^|\s)(?:с|со|из|from)\s+$", low[max(0, t.start - 5):t.start])}
    if len(free) == 1:
        return free.pop()
    if free:
        return None
    prev = focus.get("_squares") or ()
    return chess.parse_square(prev[0]) if len(prev) == 1 else None


# ───────────────────────────── position (textual) ─────────────────────────────
def _move_ref(tok: Tok) -> MoveRef:
    """A MOVE token as a MoveRef: SAN, a move told in words (from–to, or a piece to a square), castling."""
    san = tok.san
    side = None
    number = tok.num if tok.num and tok.num != "..." else None
    if tok.num:
        side = chess.BLACK if tok.num.endswith("...") else chess.WHITE
    if san.startswith("O-O"):
        return MoveRef(san=None if tok.soft else san, piece="K", castle="long" if san.startswith("O-O-O") else "short",
                       number=number, side=side, told=tok.told)
    if san.startswith("@"):
        letter, to = san[1:].split(":")
        return MoveRef(piece=letter, to=to, told=tok.told)
    if re.fullmatch(r"[a-h][1-8][a-h][1-8]", san):
        return MoveRef(piece=_LETTER[tok.ptype] if tok.ptype else "P", frm=san[:2], to=san[2:], told=tok.told)
    core = san.rstrip("+#")
    m = re.match(r"^(?P<p>[KQRBN])?(?P<ff>[a-h])?(?P<fr>[1-8])?(?P<x>x)?(?P<to>[a-h][1-8])", core)
    if not m:
        return MoveRef(san=san, number=number, side=side, told=tok.told)
    frm = m.group("ff") + m.group("fr") if m.group("ff") and m.group("fr") else None
    return MoveRef(san=san, piece=m.group("p") or "P", frm=frm, to=m.group("to"), capture=bool(m.group("x")),
                   number=number, side=side, told=tok.told)


def _same_move(a: MoveRef, b: MoveRef) -> bool:
    """«Nc6: конь с b8 встал на c6» — the same move written twice."""
    if a.castle or b.castle:
        return bool(a.castle and b.castle and a.castle == b.castle)
    return a.to is not None and a.to == b.to and (a.piece is None or b.piece is None or a.piece == b.piece)


def _merge(a: MoveRef, b: MoveRef) -> MoveRef:
    return MoveRef(san=a.san or b.san, piece=a.piece or b.piece, frm=a.frm or b.frm, to=a.to or b.to,
                   capture=a.capture or b.capture, castle=a.castle or b.castle, number=a.number or b.number,
                   side=a.side if a.side is not None else b.side, told=a.told or b.told)


_SKIP = "skip"


def _unread_number(low: str, toks: list) -> Optional[int]:
    """Where the sentence writes a move number whose move the tokenizer did not read («1.e4e5»), or None."""
    if not re.search(r"\d\s?\.", low):
        return None
    spans = [(t.start, t.end) for t in toks if t.kind in ("MOVE", "SQ", "BOUND")]
    for m in re.finditer(r"(?<![\w.])\d{1,3}\s?(?:\.\.\.|…|\.)\s?(?=[a-hkqrbnoа-я0])", low):
        if not any(a <= m.start() < b for a, b in spans):
            return m.start()
    return None


_LONG_ALG = re.compile(r"[a-h][1-8][a-h][1-8]")
_SAN_WRITTEN = re.compile(r"(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x?[a-h]?[1-8](?:=[QRBN])?|O-O(?:-O)?)[+#]?[!?]*")


def _drop_restated(seq: list) -> list:
    """The moves of a written sequence without a pawn move restated in long notation next to it («e4 (e2e4)», «e2e4,
    то есть e4»): the bare square goes, the long move stays. Only a long-algebraic neighbour restates — a capture
    that later lands on the pawn's square («1.e4 e5 2.d4 … 5…exd4») is a move of its own (fix1101 F1: the line after
    a recapture used to lose 2.d4 and never reach its board)."""
    out = []
    for i, t in enumerate(seq):
        near = seq[max(0, i - 1):i] + seq[i + 1:i + 2]
        if len(t.san) == 2 and any(_LONG_ALG.fullmatch(o.san) and o.san[2:] == t.san for o in near):
            continue
        out.append(t)
    return out


def _two_moves(a, b, low: str) -> bool:
    """Two written SAN moves in a row are two moves even when they read alike («3...Nxd4 4.Nxd4»: each side takes on
    d4): only a move told again in words or in another notation («Nc6: конь с b8 встал на c6») is one move twice."""
    if a is None or b is None:
        return False
    if not (_SAN_WRITTEN.fullmatch(a.san or "") and _SAN_WRITTEN.fullmatch(b.san or "")):
        return False
    return bool(_LINE_GAP.fullmatch(low[a.end:b.start]))


def _position(c: _Raw, text: str, toks: list, told_capture: Optional[tuple], unread_at: Optional[int] = None) -> Pos:
    """The position *c* is about, as the words say it."""
    low = text.lower()
    tense = c.tense
    if c.question == "yn":
        return Pos(at=_SKIP, tense=tense, skip_reason="yesno")
    if c.unresolved:
        return Pos(at=_SKIP, tense=tense, skip_reason="pronoun")
    if c.skip:
        return Pos(at=_SKIP, tense=tense, skip_reason=c.skip)
    hypo = _HYPO.search(low[:c.clause[1]])
    if hypo:
        return Pos(at=_SKIP, tense=tense, skip_reason="if" if re.search(W + r"бы" + E, hypo.group(0)) else "general")
    if c.modal:
        return Pos(at=_SKIP, tense=tense, skip_reason="modal")
    # «туда, откуда он бьёт и по королю, и по коню»: a place the words do not name
    if re.search(W + r"(?:туда|там|поле|место),?\s+(?:откуда|куда|где)\s+(?:[^\W\d]+\s+){0,2}$", low[max(0, c.pos - 40):c.pos]):
        return Pos(at=_SKIP, tense=tense, skip_reason="unnamed place")
    if re.match(r"[^.;:!?]{0,40}?" + W + r"(?:с|со|из|from)\s+(?:того\s+|такого\s+)?(?:пол[яе]|мест[ао]|square),?\s+"
                r"(?:где|откуда|куда|которое|where|from\s+which)" + E, low[c.end:c.clause[1]]):
        return Pos(at=_SKIP, tense=tense, skip_reason="unnamed place")
    clause = low[c.clause[0]:c.clause[1]]
    played = {t.sq for t in toks if t.kind == "SQ" and not t.move_cue and t.end <= c.pos and t.sq is not None
              and _PLAY_VERB_BEFORE.search(low[max(0, t.start - 30):t.start])}
    if played and any(r is not None and r.what == "piece" and r.sq in played for r in [c.agent] + list(c.patients)):
        # «d4 не мешает чёрным сыграть d5: пешку d5 защищает c6» (review miss2 01.11): the piece stands on the square of
        # a move the sentence names but does not play — the board after that move, which this reading does not build
        return Pos(at=_SKIP, tense=tense, skip_reason="square of a named move")
    if c.agent is not None and c.agent.what == "piece" and c.agent.sq is not None and \
            re.search(W + r"(?:ходом|ходами|by\s+playing|with)\s+[*_]*(?:\d{1,3}\s?\.{1,3}\s?)?(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|"
                      r"[a-h]x?[a-h]?[1-8]|O-O)", text[c.end:c.clause[1]]):
        # «Твой король на e3 сразу нападает на пешку ходом Kd4» (review fp2 01.11): the relation comes with a move the
        # clause names after it — the piece's square is the one it leaves; the board after it is not read here
        return Pos(at=_SKIP, tense=tense, skip_reason="by move")
    ph = _PLAN_HEAD.search(low[:c.pos])
    if tense != "future" and ph and not _NOW_AGAIN.search(low[:c.pos]) and \
            not any((t.kind == "MOVE" or (t.kind == "SQ" and t.move_cue)) and ph.start() <= t.start < c.pos for t in toks):
        # «План за белых: ладьи на c1 и d1, давление на пешку d5» (review fp2 01.11): what a plan or an idea puts where
        # is the set-up it aims at, not the board now
        return Pos(at=_SKIP, tense=tense, skip_reason="plan")
    if tense == "future" and (c.plan or _PLAN_CUE.search(low[:c.end])) and c.rel in ("ATT", "SOFT", "HOLD") and \
            c.agent is not None and c.agent.what == "piece" and c.agent.sq is not None and c.agent.ptype:
        return Pos(at="plan", tense=tense)  # «фианкетто: слон с g2 будет бить по e6» — the geometry of the set-up
    if tense == "future" and c.rel in ("ATT", "SOFT", "HOLD") and c.agent is not None and c.agent.what == "piece" and \
            c.agent.sq is not None and c.agent.ptype and c.agent.ptype != chess.PAWN and not c.neg and \
            not c.agent.from_sq and not re.search(W + r"(?:после|after|если|когда|if|when)" + E, clause):
        # «Слон на b2 будет давить на h7», «Конь на f5 будет атаковать e6»: what a piece on that square will reach is
        # its geometry — false in every position when the square is off its lines
        return Pos(at="plan", tense=tense)
    if tense == "future" and not re.search(W + r"(?:после|after)" + E, clause):
        return Pos(at=_SKIP, tense=tense, skip_reason="future")
    upto = c.pos
    agent_move = c.agent.move if c.agent is not None and c.agent.what == "move" else None
    if agent_move is not None:
        upto = max(upto, agent_move.end)
    moves_seq = [t for t in toks if (t.kind == "MOVE" or (t.kind == "SQ" and t.move_cue)) and (t.start < upto or t is agent_move)
                 and not t.threat]
    # a move named before the claim but not told as a move (a motion verb we could not read): the board moved unseen
    spans = [t.span for t in toks if t.kind == "MOVE" and t.span]
    movers = {_move_ref(t if t.kind == "MOVE" else Tok("MOVE", t.start, t.end, t.text, san=t.text)).piece for t in moves_seq}
    if "K" in movers:
        movers.add("R")  # castling moves the rook too
    for m in _UNPARSED_MOVE.finditer(low[:c.pos]):
        if told_capture is not None and told_capture[0] <= m.start() < told_capture[6]:
            continue  # the capture the sentence told, read
        # right after a move read («конь с g8 на f6 вышел», «… встал на f6, вышел в центр»): the same move told on, unless
        # another piece follows as its mover («встал на f6, вышел мой слон»)
        after_move = any(b <= m.start() and re.fullmatch(r"[\s,]*", low[b:m.start()]) for a, b in spans) and not (
            (w2 := re.match(rf"\s+(?:\w+\s+)?({_PIECE_ALT}){E}", low[m.end():m.end() + 25]))
            and _LETTER.get(_P[w2.group(1)][0]) not in movers) and not \
            re.match(r"\s+(?:(?:на|в)\s+[a-h][1-8]|назад|обратно|back)" + E, low[m.end():m.end() + 12])  # «, вернулся на f3»
        if any(a <= m.start() < b for a, b in spans) or after_move or \
                any(t.kind == "MOVE" and not t.threat and m.end() <= t.start <= m.end() + 30 for t in toks):
            continue  # inside a move read, right after it («конь с g8 на f6 вышел»), or before the move it tells
        # «рокировка …: король уходит» — the motion of a move the sentence already told; not a motion to another square
        # than that move's («после h6 Bh4 g5 слон уйдёт на g3»: a new move, review fp2 01.11)
        w = re.search(rf"({_PIECE_ALT})\s+(?:\w+\s+)?$", low[max(0, m.start() - 30):m.start()])
        dest = re.match(r"\s+(?:на|в|to)\s+([a-h][1-8])(?![0-9])", low[m.end():m.end() + 14])
        if w and _LETTER.get(_P[w.group(1)][0]) in movers and any(t.start < m.start() for t in moves_seq) and not (
                dest and not any(_move_ref(t if t.kind == "MOVE" else Tok("MOVE", t.start, t.end, t.text, san=t.text)).to
                                 == dest.group(1) for t in moves_seq)):
            continue
        return Pos(at=_SKIP, tense=tense, skip_reason="unparsed move")
    # «после 1.e4e5 2.Nf3 …»: a numbered move the words write but the parser cannot read — the line is not the one it
    # reads, the board after it is unknown
    if unread_at is not None and unread_at < c.pos:
        return Pos(at=_SKIP, tense=tense, skip_reason="unparsed move")
    seq = [t if t.kind == "MOVE" else Tok("MOVE", t.start, t.end, t.text, san=t.text, told=t.told) for t in moves_seq]
    seq = _drop_restated(seq)
    seq = [t for i, t in enumerate(seq) if not (i and not t.ptype and re.fullmatch(r"[a-h][1-8][a-h][1-8]", t.san)
                                                 and _move_ref(seq[i - 1]).to == t.san[:2])]
    # «Nc3 или Nd2»: alternatives, not a line
    steps: list = []
    for t in seq:
        mr = _move_ref(t)
        if steps and re.fullmatch(r"\s*(?:или|or|/|либо)\s*(?:\S+\s+)?", low[steps[-1][-1][0].end:t.start]):
            steps[-1].append((t, mr))
        elif steps and len(steps[-1]) == 1 and _same_move(steps[-1][0][1], mr) and \
                not _two_moves(steps[-1][0][0], t, low):
            steps[-1] = [(t, _merge(steps[-1][0][1], mr))]  # «Nc6: конь с b8 встал на c6»
        else:
            steps.append([(t, mr)])
    then = bool(_THEN.search(low)) or bool(_NEXT.search(low[:c.pos]))
    if steps:
        at = "then" if then else "after"
        first = tuple(s[0][1] for s in steps)
        alts = []
        for i, s in enumerate(steps):
            for _, mr in s[1:]:
                alts.append(Pos(at=at, moves=first[:i] + (mr,) + first[i + 1:], tense=tense))
        if told_capture is not None and told_capture[0] < c.pos and not any(_same_move(told_capture[1], m) for m in first):
            if told_capture[2] or told_capture[5] == c.clause:
                alts.append(Pos(at=at, moves=first, tense=tense))
                first = first + (told_capture[1],)
            else:
                alts.append(Pos(at=at, moves=first + (told_capture[1],), tense=tense))
        first, cut = _before_capture_of_named(c, first)
        if cut:
            alts.append(Pos(at=at, moves=cut, tense=tense))
            if not first:
                return Pos(at="then" if then else "now", tense=tense, alts=tuple(alts))
        return Pos(at=at, moves=first, tense=tense, alts=tuple(alts))
    if told_capture is not None and told_capture[0] < c.pos:
        mr, sure = told_capture[1], told_capture[2]
        if not _before_capture_of_named(c, (mr,))[0] and _before_capture_of_named(c, (mr,))[1]:
            # «Ладья берёт пешку c6, которая связана с королём»: the piece taken — the board before the capture
            return Pos(at="then" if then else "now", tense=tense, alts=(Pos(at="after", moves=(mr,), tense=tense),))
        if sure or then:
            return Pos(at="then" if then else "after", moves=(mr,), tense=tense)
        # «бьёт» is «attacks» too: the board after the capture comes first only when the same clause goes on
        # («ферзь бьёт коня e2 и одновременно нападает на …»), not after «но/а» («он бьёт пешку e5, но её держат …»)
        if told_capture[5] == c.clause:
            return Pos(at="after", moves=(mr,), tense=tense, alts=(Pos(at="now", tense=tense),))
        return Pos(at="now", tense=tense, alts=(Pos(at="after", moves=(mr,), tense=tense),))
    if then:  # «Тогда …» names a position the sentence before set up — or nothing we know
        return Pos(at="then", tense=tense)
    if tense == "future" or (_COND.search(low[:c.pos]) and not re.search(W + r"пока" + E, low[:c.pos])):
        return Pos(at=_SKIP, tense=tense, skip_reason="conditional" if tense != "future" else "future")
    alts = []
    for t in toks:  # «угроза Qxf3+ — … под боем и король f2»: maybe after the threat
        if t.kind == "MOVE" and t.threat and t.start < c.pos:
            alts.append(Pos(at="after", moves=(_move_ref(t),), tense=tense))
    later: list = []
    prev_t = None
    for t in toks:  # «Ферзь на d5 сейчас под боем: белые играют Nc3»; «два ответа: Kg8 или fxg6» are two boards
        if t.kind == "MOVE" and t.start > c.pos and not t.threat:
            if prev_t is not None and re.fullmatch(r"\s*(?:или|or|/|либо)\s*", low[prev_t.end:t.start]):
                later = later[:-1]
            later.append(_move_ref(t))
            alts.append(Pos(at="after", moves=tuple(later), tense=tense))
            prev_t = t
    return Pos(at="now", tense=tense, alts=tuple(alts))


def _before_capture_of_named(c: _Raw, moves: tuple):
    """«**Rb:b5** — … слон связан ладьёй b7»: a move of the sequence takes a piece the claim names on that square (the
    piece named is not the one that lands there) — the claim is about the board before it. (moves kept, moves cut)."""
    named = {}
    for r in [c.agent] + list(c.patients):
        if r is not None and r.what == "piece" and r.sq is not None and r.ptype:
            named[chess.square_name(r.sq)] = _LETTER[r.ptype]
    for i, m in enumerate(moves):
        if m.capture and m.to in named and m.piece and named[m.to] != m.piece:
            return moves[:i], moves
    return moves, ()


# ───────────────────────────── claims ─────────────────────────────
_REL_NAME = {"ATT": "attack", "SOFT": "aim", "CHASE": "chase", "THREAT": "threat", "DEF": "defend", "HOLD": "hold",
             "CTRL_G": "hold", "CTRL_I": "hold", "UNDEF": "undefended", "PIN": "pins", "PIN_AFTER": "pin_after",
             "LOCK": "locked_by", "CAPW": "capture_with"}


def _side_owner(owner):
    if owner in (chess.WHITE, chess.BLACK):
        return owner, None
    return None, {"you": "you", "own": "own", "me": "their", "opp": "their"}.get(owner)


def _out_ref(r: Optional[_R], *, mover: bool = True) -> Optional[Ref]:
    if r is None:
        return None
    if r.what == "square":
        return Ref(sq=chess.square_name(r.sq), text=r.text)
    if r.what == "move":
        mr = _move_ref(r.move)
        if mr.castle or (mr.piece is None and mr.to is None):
            return None
        return Ref(sq=mr.to if mover else None, piece=mr.piece, text=r.text)
    if r.what == "piece":
        side, owner = _side_owner(r.owner)
        return Ref(sq=chess.square_name(r.sq) if r.sq is not None else None, piece=_LETTER.get(r.ptype) if r.ptype else None,
                   side=side, owner=owner, from_sq=r.from_sq, pronoun=r.pronoun, text=r.text)
    if r.what == "side":
        side, owner = _side_owner(r.owner)
        return Ref(side=side, owner=owner, text=r.text)
    return None


def _convert(c: _Raw, pos: Pos, told_capture) -> Optional[Claim]:
    rel = c.rel
    subj, objs, to = c.agent, list(c.patients), c.to
    cap0 = told_capture[1] if told_capture is not None and told_capture[0] < c.pos else None
    if cap0 is not None and cap0 in pos.moves:  # «Конь с f6 забирает пешку e4 … а сам конь после этого под боем»
        objs = [_R("piece", o.ptype, chess.parse_square(cap0.to), o.owner, text=o.text, pronoun=o.pronoun)
                if o is not None and o.what == "piece" and _LETTER.get(o.ptype) == cap0.piece and o.sq is not None
                and chess.square_name(o.sq) == cap0.frm else o for o in objs]
    question = {"wh": "which", "yn": "yesno"}.get(c.question, "")
    span = (min([c.pos] + [x.move.start for x in [subj] if x is not None and x.what == "move"]), c.end)
    if rel in _PASSIVE:
        if rel == "UNDEF":
            return Claim("undefended", None, tuple(r for r in map(_out_ref, objs) if r is not None), pos=pos,
                         question=question, span=span, kind="cover" if c.cover else "")
        if rel == "HANG":  # «пешка e5 висит»: attacked (and not enough defended) — at least attacked
            return Claim("hanging", None, tuple(r for r in map(_out_ref, objs) if r is not None), neg=c.neg, pos=pos,
                         question=question, span=span)
        if subj is not None and c.count and subj.what == "piece" and not subj.ptype and subj.sq is None:
            subj = None  # «защищена двумя фигурами»: a count, not a piece
        if subj is None:
            if rel == "PASS_ATT":
                # «… бьёт пешку e4 с шахом и создаёт вилку: под ударом остаются h2 и f1» — the fork is the capturer's
                if told_capture is not None and told_capture[0] < c.pos and _FORK.search(told_capture[3]):
                    mr = told_capture[1]
                    subj = _R("piece", _PTYPE.get(mr.piece or "", 0), chess.parse_square(mr.to) if mr.to else None,
                              text=told_capture[4])
                    rel = "ATT"
                else:
                    return Claim("attacked", None, tuple(r for r in map(_out_ref, objs) if r is not None), neg=c.neg,
                                 pos=pos, question=question, span=span, count=None if c.neg else c.count)
            elif rel == "PASS_DEF":  # «пешка e5 защищена» = not undefended
                return Claim("undefended", None, tuple(r for r in map(_out_ref, objs) if r is not None), neg=not c.neg,
                             pos=pos, question=question, span=span, count=None if c.neg else c.count)
            elif rel == "PASS_PIN":
                return Claim("pinned", None, tuple(r for r in map(_out_ref, objs) if r is not None), neg=c.neg,
                             to=_out_ref(to), pos=pos, question=question, span=span)
            else:  # CTRL_G / CTRL_I: «поле d6 под контролем»
                return Claim("hold", None, tuple(r for r in map(_out_ref, objs) if r is not None), neg=c.neg, pos=pos,
                             question=question, span=span)
        else:
            rel = {"PASS_ATT": "ATT", "PASS_DEF": "DEF", "PASS_PIN": "PIN", "CTRL_G": "HOLD", "CTRL_I": "HOLD"}[rel]
    if rel == "CAPW":
        side, owner = _side_owner(subj.owner if subj is not None else None)
        ins = c.instrument
        return Claim("capture_with", Ref(piece=_LETTER.get(ins.ptype) if ins and ins.ptype else None, side=side, owner=owner),
                     tuple(r for r in map(_out_ref, objs) if r is not None), neg=c.neg, pos=pos, question=question, span=span)
    if rel in ("ATT", "DEF") and c.count and not c.neg and subj is not None and subj.what == "piece" and not subj.ptype \
            and subj.sq is None:
        # «Пешку e5 атакуют две белые фигуры»: how many pieces (of that side) attack / defend it
        side, owner = _side_owner(subj.owner)
        objs_out = tuple(r for r in map(_out_ref, objs) if r is not None and r.sq)
        if not objs_out:
            return None
        if rel == "ATT":
            return Claim("attacked", Ref(side=side, owner=owner, text=subj.text), objs_out, pos=pos, question=question,
                         span=span, count=c.count)
        return Claim("undefended", None, objs_out, neg=True, pos=pos, question=question, span=span, count=c.count)
    if rel == "LOCK":
        return Claim("locked_by", _out_ref(subj), tuple(Ref(sq=chess.square_name(b)) for b in c.blockers), neg=c.neg,
                     pos=pos, question=question, span=span)
    if rel == "PIN_AFTER":
        return Claim("pin_after", _out_ref(subj), (), pos=pos, question=question, span=span)
    if subj is not None and subj.what == "piece" and (subj.from_sq or subj.sq is None) and subj.ptype and pos.at in ("after", "then"):
        # «Первый ход — Сb7: белый слон с g2 бьёт по ладье a8»: the piece «с g2» made the move the sentence told
        mine = [m for m in pos.moves if m.piece == _LETTER[subj.ptype] and m.to and not m.castle
                and (m.frm is None or subj.sq is None or m.frm == chess.square_name(subj.sq))]
        other = {m.to for p in pos.alts for m in p.moves if m.piece == _LETTER[subj.ptype]} - {m.to for m in mine}
        targets = {chess.square_name(o.sq) for o in objs if o is not None and o.sq is not None}
        # (not when a reading without that move stands beside it — «Ферзь бьёт пешку d6 и давит на f7»: «бьёт» is
        # «attacks» too, and on the board without the capture the queen is where it stands)
        if len(mine) == 1 and not other and mine[0].to not in targets and all(mine[0] in p.moves for p in pos.alts):  # («Nc3 или Nd2 защищает»: the mover of each alternative — left to the scene)
            subj = _R("piece", subj.ptype, chess.parse_square(mine[0].to), subj.owner, text=subj.text)
    cap = told_capture[1] if told_capture is not None and told_capture[0] < c.pos else None
    # «бьёт» is «attacks» too: when a board without the capture is a reading as well («Ферзь бьёт пешку d6 и давит на
    # f7»), the subject keeps the words' square — on the board after the capture the judge reads the piece that just
    # moved (claim_judge._candidates, _rebound), on the board without it the piece where it stands
    unsure = any(cap not in p.moves for p in pos.alts) if cap is not None else False
    if cap is not None and cap in pos.moves and not unsure and subj is not None and subj.what == "piece" and \
            _LETTER.get(subj.ptype) == cap.piece and (subj.sq is None or chess.square_name(subj.sq) == cap.frm):
        subj = _R("piece", subj.ptype, chess.parse_square(cap.to), subj.owner, text=subj.text)  # it stands where it took
    s = _out_ref(subj, mover=not (subj is not None and subj.what == "move" and pos.alts and pos.at != "now"))
    if s is None:
        return None
    # «связывает чёрные фигуры», «держит и короля, и коня»: no square to judge
    objs = [o for o in objs if o is None or o.sq is not None or (o.what == "piece" and o.ptype and rel not in ("HOLD",))]
    if not objs:
        return None
    if rel == "DEF" and any(o is not None and o.what == "piece" and o.ptype == chess.KING for o in objs):
        pos = Pos(at=_SKIP, tense=pos.tense, skip_reason="shield")  # «прикрывает своего короля»: shields, not defends
    if pos.at == "plan":
        rel_name = "plan_reach"
    else:
        rel_name = _REL_NAME[rel]
    # «прикрывает» is to shield as well as to defend (kind 'cover'); «защищает», «поддерживает», «охраняет» only defend
    return Claim(rel_name, s, tuple(r for r in map(_out_ref, objs) if r is not None), to=_out_ref(to), neg=c.neg,
                 question=question, pos=pos, span=span, kind="cover" if c.cover and rel_name == "defend" else "")


def _narrates_capture(c: _Raw, toks: list, text: str) -> bool:
    """«**Rxh6+**: ладья бьёт пешку h6 с шахом», «Ферзь бьёт пешку e4 с шахом», «1...Rxf3! Ладья бьёт коня»: the words
    tell the capture move itself (a written capture of that piece on that square, or «с шахом») — a move, not a
    claim that the piece attacks; the later claims of the sentence are about the board after it."""
    if c.rel != "ATT" or not _TAKE.match(c.verb) or c.agent is None or c.inverted:
        return False
    low = text.lower()
    if re.match(r"\s*(?:прямо\s+|точно\s+)?(?:по|в)" + E, low[c.end:c.end + 12]):
        return False
    if re.match(r"[^.;:—]{0,30}?с\s+шахом", low[c.end:c.clause[1]]):
        return True
    # «твоя пешка бьёт её на c6», «пешка e5 бьёт пешку d5 и встаёт на d6»: the square it takes on / lands on
    if re.match(r"\s*(?:ее|его|их)\s+на\s+[a-h][1-8]|[^.;:—]{0,30}?" + W + r"(?:и\s+)?(?:вста[её]т|встал\w*|оказыва\w+|"
                r"оказал\w*|переходит|перешл\w*|перешел)\s+на\s+[a-h][1-8]", low[c.end:c.clause[1]]):
        return True
    if c.agent.what == "move":
        letter = _move_ref(c.agent.move).piece
    elif c.agent.what == "piece":
        letter = _LETTER.get(c.agent.ptype)
    else:
        return False
    target = c.patients[0].sq if c.patients and c.patients[0] is not None else None
    for t in toks:
        if t.kind == "MOVE" and "x" in t.san and t.start < c.pos:
            mr = _move_ref(t)
            if mr.piece == letter and (target is None or mr.to == chess.square_name(target)):
                return True
    return False


def _told_capture(c: _Raw, text: str):
    """«Ферзь бьёт пешку e4 с шахом …»: (position, MoveRef of the capture, sure, clause, agent words) — the later claims
    of the sentence may be about the board after it; sure when the words can only mean a capture."""
    if c.rel not in ("ATT", "TAKE") or not _TAKE.match(c.verb) or c.agent is None or not c.patients or c.inverted:
        return None
    low = text.lower()
    if re.match(r"\s*(?:прямо\s+|точно\s+)?(?:по|в)" + E, low[c.end:c.end + 12]):
        return None  # «бьёт по f7», «бьёт прямо в ферзя» attacks
    p = c.patients[0]
    if p is None or p.sq is None or p.what != "piece" or c.agent.what not in ("piece", "move"):
        return None  # «конь бьёт e6, f7 и h7»: squares are attacked, not taken
    if c.agent.what == "move":
        mr = _move_ref(c.agent.move)
        piece = mr.piece
    else:
        piece = _LETTER.get(c.agent.ptype) if c.agent.ptype else None
    if not piece:
        return None
    frm = chess.square_name(c.agent.sq) if c.agent.what == "piece" and c.agent.sq is not None else None
    sure = bool(_TAKE_SURE.match(c.verb)) or bool(re.match(r"[^.;:]{0,30}?с\s+шахом", low[c.end:c.clause[1]]))
    return (c.pos, MoveRef(piece=piece, frm=frm, to=chess.square_name(p.sq), capture=True, told=True), sure,
            low[c.clause[0]:], c.agent.text, c.clause, c.end)


def _remember(toks, text, state, focus, cur):
    """The pieces this sentence named (and its resolved pronouns), by gender, become the next sentence's pronoun
    candidates; its free squares the next sentence's «туда»."""
    merged = {g: v for g, v in focus.items() if not g.startswith("_")}
    merged.update(cur)
    out = []
    for g, refs in merged.items():
        for r, nom in refs:
            owner = r.owner
            owner = {chess.WHITE: "w", chess.BLACK: "b"}.get(owner, owner) if owner is not None else ""
            out.append((g, _LETTER.get(r.ptype, "") if r.ptype else "", chess.square_name(r.sq) if r.sq is not None else "",
                        owner if isinstance(owner, str) else "", bool(nom)))
    state[FOCUS_KEY] = tuple(out)
    low = text.lower()
    free = []
    for t in toks:
        if t.kind == "SQ" and not t.move_cue and not t.route and \
                not re.search(r"(?:^|\s)(?:с|со|из|from)\s+$", low[max(0, t.start - 5):t.start]):
            name = chess.square_name(t.sq)
            if name not in free:
                free.append(name)
    state[SQUARES_KEY] = tuple(free)


# ───────────────────────────── presupposed relations (plan 31.10, P3A) ─────────────────────────────
# A sentence can take a relation for granted instead of asserting it: «конь уходит из-под связки» presupposes that the
# knight was pinned before it moved, «держать связку» that some pin exists, «слон c8 заперт» that the bishop has no
# way out, «поле f6 держала пешка g7, и конь там потерялся» that g7's hold on f6 is why the knight was lost. The
# negation and the question keep a presupposition («конь не уйдёт из-под связки», «хочешь снять связку?»), so these
# claims are made whatever the mood of the verb — only a hypothetical, a rule, a conditional or a future the board
# cannot show (the ordinary ``_position`` skips) leaves them out.
#
# What each emits (``Claim.kind`` names the detector, ``config.detector_mode``; 'off' emits nothing, the judge and
# the relation check apply 'shadow'):
#   pin_escape  «X уходит/уйти/увести X/выходит из-под связки», «снять/убрать связку», «развязать X», «X развязался»
#     · told move of the escaping piece in the sentence («Nd2: конь уходит из-под связки») →
#         Claim('pinned', objs=(Ref(piece=its letter [, side/owner]),), move=that move, presup='before_move'),
#         pos = the board after the move as the words tell it: the judge reads the piece that made pos's last move on
#         the board before it (the ref has no square on purpose — on any other board it binds to nothing);
#     · no told move, the verb indicative («конь c3 уходит из-под связки») → a plain Claim('pinned') on the board the
#         words point at, which is the board before the escape (presup '');
#     · a proposal (infinitive, imperative, a modal or purpose frame: «надо снять связку», «увести короля из-под
#         связки», «чтобы развязать пешку c5») → Claim('pin_exists', presup='exists');
#     · the king as the escaping piece («уйти королём из-под связки») → Claim('pin_exists', objs=(the king's side,),
#         to=Ref(piece='K')): some piece of that side is pinned to the king (before the king's move, or on some board).
#   pin_noun    «держать/сохранить/усилить связку», «под связку» → Claim('pin_exists', subj=the holder when the sentence
#     names one, objs=(the pinned piece, a square «по f7», or the pinned side) | (), to=«с королём», presup='exists').
#   locked      «заперт(ый/ым/ы)», «не может выйти», «без ходов» about a knight, bishop, rook or queen with no blocker
#     named (with a blocker the existing ``locked_by`` claim says it) → Claim('locked', subj=the piece).
#   cover_cause a hold/attack claim of the sentence on a bare square Z and a loss word («потерялся», «погиб», «пропал»,
#     «висел», «подставил») about a piece on Z → Claim('cover_cause', subj=the holder, objs=(Ref(sq=Z),),
#     to=the lost piece as the words name it): the holder's control of Z is named as the cause of the loss.
# pin_exists matching: a pin on the board whose pinner fits ``subj`` (when given), whose pinned piece fits ``objs[0]``
# (a piece, a square, or a side-only ref = any piece of that side; any piece when ``objs`` is empty) and whose piece
# behind fits ``to`` (when given).
_PRESUP_CUE = re.compile(r"связк|связанн|развяз|заперт|запир|замуров|взаперти|в\s+клетке|заблокир|блокиру|обездвиж|застр[яе]|"
                         r"ходов|хода|некуда|"
                         r"не\s+(?:может|могут|сможет|смогут|в\s+состоянии)\s+(?:\w+\s+){0,2}?(?:выйти|выбраться|двинуться|"
                         r"сдвинуться|пошевел|шевельн|сделать|ходить|пойти|уйти|отступить)|не\s+(?:выйти|выбраться|двинуться|"
                         r"сдвинуться)|без\s+ходов|"
                         r"(?:больше|уже|теперь)\s+не\s+(?:связан|под\s+связк)")
# the escape cue (fix1101 F1): «из-под связки» with any verb; «из связки / от связки» with a verb of leaving or freeing
_PIN_FROM_UNDER = re.compile(W + r"из-под\s+(?:(?:эт\w+|сво\w+|всех|всякой|любой|этой\s+неприятной)\s+)?связ(?:ки|ок)" + E)
_PIN_OUT_OF = re.compile(W + r"(?:из|от)\s+(?:(?:эт\w+|сво\w+|всех|всякой|любой)\s+)?связ(?:ки|ок)" + E)
_ESC_VERB = re.compile(
    W + r"(?:(?:у|вы|от|с)(?:ход(?:ит|ят|ишь|им|и|ите|ить|я)|йти|йд[её]т|йдут|йд[её]шь|йди|йдите|ш[её]л|шла|шли|шло)|"
    r"(?:у|вы)(?:вод(?:ит|ят|ишь|и|ите|ить|я)|вести|вед[её]т|ведут|вед[её]шь|веди|ведите|в[её]л|вела|вели)|"
    r"убира\w*|убрать|убер\w*|убрал\w*|спаса\w*|спасти|спас(?:ет|ут|ешь|и|ите|л\w*)?|выскальзыва\w*|выскольз\w*|"
    r"ускольза\w*|ускольз\w*|вырыва\w*|вырва\w*|освобожда\w*|освобод\w*|высвобо\w*|избавля\w*|избав\w*|"
    r"выбира\w*|выбра\w*|выпута\w*|выручa\w*|выруча\w*|выруч\w*|убега\w*|убеж\w*|убежа\w*|сбега\w*|сбежа\w*|"
    r"отступа\w*|отступ(?:ит|ят|и|ил\w*)|выпрыгива\w*|выпрыгн\w*|прыга\w*|прыгн\w*)" + E)
# the verbs that move another piece out («увести/вывести/убрать/спасти/освободить ферзя из-под связки»): the accusative
# piece is the one that escapes
_ESC_TRANSITIVE = re.compile(r"^(?:увод|увест|увед|ув[её]л|увел|вывод|вывест|вывед|выв[её]л|вывел|убира|убра|убер|спас|"
                             r"освобожда|освобод|высвобо|избавля|избав|выруча|выруч|выпута)(?!.*(?:ся|сь)$)")
# any finite verb, infinitive or imperative right before the cue («конь прыгает из-под связки»): its tense and mood
_ANY_VERB = re.compile(W + r"[а-я]{2,}(?:ть|ти|ться|тись|ет|ит|ут|ют|ат|ят|ется|ится|утся|ются|атся|ятся|ешь|ишь|ете|"
                       r"ите|ал|ял|ил|ел|ул|ла|ли|ло|лся|лась|лись|ай|яй|ей|уй|йся|йте|ись|айся|ейся|ися)" + E)
_REMOVE_PIN = re.compile(
    W + r"(?P<v>сн(?:ять|ял\w*|има(?:ет|ют|ешь|ем|ть|ется)|ими|имите|им[её]т|имут|им[её]шь|имем)|убра(?:ть|л\w*)|"
    r"убер(?:и|ите|[её]т|ут|[её]шь|[её]м)|убира\w*|разорв\w*|разрыва\w*|разруша\w*|разруш(?:ить|ит|ил\w*|ат)|"
    r"ликвидиру\w*|ликвидирова\w*|нейтрализу\w*|нейтрализова\w*|прерыва\w*|прерв\w*|избавля\w*|избав\w*)\s+"
    r"(?:(?:эт\w+|сво\w+|все|всю|неприятн\w+|опасн\w+|неудобн\w+)\s+)?связк(?:у|и)" + E)
# «связка (коня b1) исчезает / пропала / снята»: the pin as the subject of its own end
_PIN_ENDS = re.compile(
    W + r"связк[аиу]\s+(?P<gap>(?:[^\s.;:!?,]+\s+){0,4}?)(?P<v>сним(?:ает|ают|ет|ут)|снял\w*|убира\w*|убрал\w*|разрыва\w*|"
    r"разорвал\w*|ликвидиру\w*|исчеза\w*|исчезн\w*|исчезл\w*|пропада\w*|пропад[её]т|"
    r"пропал\w*|снят[аы]?|снимается|сняли|кончает\w*|кончил\w*|законч\w*|разрушен\w*|разрушает\w*|разорван\w*|"
    r"ликвидирован\w*|уходит|ушла|уйд[её]т|пропадет|прекраща\w*|прекрат\w*|рассыпа\w*|распада\w*|распал\w*)" + E)
# «после Nd2 конь больше не связан», «теперь конь не под связкой»: the denial of a pin the told move ended
_PIN_GONE = re.compile(W + r"(?P<v>(?:больше|уже|теперь|наконец)\s+(?:[^\W\d]+\s+(?:[a-h][1-8]\s+)?){0,3}?(?:уже\s+)?не\s+"
                       r"(?P<st>связан[аоы]?|под\s+связк(?:ой|ами))|перестал?\w*\s+(?:быть\s+)?(?P<st2>связанн\w+))" + E)
# «связанный конь», «конь, связанный слоном f5», «конь b1 в связке»: the attribute or the state of a pin
_PIN_ATTR = re.compile(W + r"(?:связанн(?:ый|ая|ого|ой|ую|ому|ым)(?:\s+(?:слоном|ферз[её]м|ладь[её]й)(?:\s+[a-h][1-8])?)?"
                       r"|(?P<state>(?:находится\s+|стоит\s+)?(?:в|под)\s+связк(?:е|ой)))" + E)
_UNPIN = re.compile(W + r"(?P<v>развяж\w*|развязыва\w*|развяза(?:ть|ться|л\w*|в\w*|н\w*))" + E)
_HOLD_PIN = re.compile(
    W + r"(?P<v>держ(?:ать|ит|ат|ал\w*|и|ишь|ите|у|им)|удержива\w*|удерж(?:ать|ит|ат|ал\w*|и)|"
    r"сохран(?:я\w*|ить|ит|ят|ил\w*|и|им)|усил(?:ить|ива\w*|ит|ят|ил\w*|ь|им)|поддержива\w*)\s+"
    r"(?:(?:эт\w+|сво\w+|ту|всю|же)\s+)?связку" + E)
_UNDER_PIN = re.compile(W + r"под\s+(?:(?:эт\w+|сво\w+)\s+)?связку" + E)
# a frame that makes the verb a proposal, not a report: the presupposed pin is on some board of the line, not
# necessarily the one the verb's tense names
_PROPOSAL = re.compile(
    W + r"(?:нужно|надо|стоит|стоило|можно|можешь|может|можете|сможешь|сможет|должен|должна|должны|пора|придется|"
    r"приходится|хочешь|хочет|хотят|хочу|хотел\w*|попробуй\w*|попытайся|постарайся|старайся|чтобы|успева\w*|"
    r"успе(?:ет|ют|ешь|ть|л\w*)|давай(?:те)?|сначала|не\s+да(?:ет|ют|ст|дут|вая|вать)|позволя\w*|меша\w*|помешать|"
    r"способ\w*|идея|цель|задача|план|главное|важно|лучше|полезно|логично)" + E)
# «No legal move» as one predicate class (review-miss2 01.11), not a phrase: a negated ability to move («не может
# выйти / сдвинуться (с места) / сделать (ни одного) хода», «не сможет двинуться», «не выйти», «не выбраться»), a zero
# quantity of moves («ни одного хода», «ходов не имеет», «нет ходов», «без ходов», «лишён ходов»), or a state
# participle («заблокирован», «обездвижен», «замурован», «застрял», «взаперти»). «заперт» itself is the REL LOCK token.
_MOVE_INF = r"(?:выйти|выбраться|двинуться|сдвинуться|пошевелиться|шевельнуться|ходить|сходить|пойти|уйти|отступить|выбраться)"
_LOCKED_EXTRA = re.compile(W + r"(?:(?:не|никак\s+не)\s+(?:может|могут|сможет|смогут|в\s+состоянии)\s+(?:никуда\s+|вообще\s+|даже\s+)?"
                           r"(?:" + _MOVE_INF + r"|сделать\s+(?:ни\s+одного\s+|ни\s+единого\s+|ни\s+)?ход[а]?)(?:\s+с\s+места)?|"
                           r"не\s+(?:выйти|выбраться|двинуться|сдвинуться|пошевелиться)|"
                           r"ни\s+(?:одного|единого)\s+хода|(?:нет|не\s+имеет|не\s+имеют|лиш[её]н\w*)\s+(?:ни\s+одного\s+)?ходов|"
                           r"ходов\s+(?:нет|не\s+имеет|не\s+имеют|не\s+осталось)|без\s+(?:единого\s+)?ходов|"
                           r"(?:сидит|сидят|остается|остаются|оста[её]тся|осталс\w+|оказал\w*)?\s*взаперти|"
                           r"замурован\w*|заблокирован\w*|обездвижен\w*|застрял\w*|застревает|застряв\w*|"
                           r"(?:оказывается|оказался|оказалась|окажется|сидит|остается|оста[её]тся)\s+в\s+клетке)" + E)
# the transitive and noun forms: the piece locked is the object — «замуровывает слона c8», «оставляет слона c8
# взаперти», «с запиранием слона c8», «блокирует коня b8»
_LOCK_TRANS = re.compile(W + r"(?:замуровыва\w*|замуровал\w*|замурует|запира(?:ет|ют|л|ла|ли)|запер(?:ла|ли)?|запрет|запрут|"
                         r"заблокировал\w*|заблокирует|блокиру(?:ет|ют)|обездвижива\w*|обездвижил\w*|"
                         r"оставля(?:ет|ют)|оставил\w*|оставит|держ(?:ит|ат)|запирани\w+|замуровывани\w+)" + E)
# «слону f1 некуда ходить», «ферзю ходить некуда»: no square to go to — read as «no safe move» (rel trapped, the weaker)
_NOWHERE = re.compile(W + r"(?:некуда\s+(?:ходить|идти|пойти|двигаться|двинуться|ступить|деться|податься|отступить)|"
                      r"(?:ходить|идти|пойти|двигаться|деться|податься|отступить)\s+некуда)" + E)
# a blocker or a cause named with the lock («заперт пешками», «заперт цепью d6–e5», «упирается в свою пешку», «плохой
# слон»): a structural restriction, not the strict «no way out» — the locked_by claim of bind judges what it can
_LOCK_BLOCKER = re.compile(W + r"(?:за|своими|своей|своим|своею|собственн\w*|пешками|пешкой|фигурами|фигурой|цеп\w*|"
                           r"пешечн\w*|центр\w*|структур\w*|упира\w*|уперт\w*|плох\w*|ходом|пешк[аи]\s+[a-h][1-8])" + E)
# a hedge: «почти заперт», «наполовину», «фактически», «как бы» — not the strict «no way out»
_LOCK_HEDGE = re.compile(W + r"(?:почти|наполовину|полу\w*|фактически|практически|в\s+каком-то\s+смысле|как\s+бы|"
                         r"своего\s+рода|в\s+некотором\s+роде|отчасти|частично|довольно|слегка|немного|"
                         r"по\s+сути|можно\s+сказать|считай|как\s+будто|словно|будто|"
                         # a scope that narrows «no way out» to some moves: «некуда ходить, кроме e7», «не может выйти в
                         # игру», «по вертикали», «вперёд» — the piece may well have other moves
                         r"кроме|за\s+исключением|только|лишь|except|в\s+игру|полезн\w*|хорош\w*|активн\w*|"
                         r"по\s+(?:вертикал|горизонтал|диагонал|лини)\w*|вперед|назад|в\s+центр|на\s+фланг\w*)" + E)
# An exception to «no way out» told anywhere after the cue in the sentence (review fp2 01.11): «…: d2 и c3 заняты,
# свободно только a3», «заперта, если не считать b1 и c1», «разве что на a3». The strict claim is then not what the words
# say; left unjudged.
_LOCK_EXCEPT = re.compile(W + r"(?:если\s+не\s+считать|не\s+считая|разве\s+что|за\s+вычетом|за\s+исключением|кроме|помимо|"
                          r"(?:свобод|открыт|доступн)\w*\s+(?:только|лишь)|(?:только|лишь)\s+(?:одно\s+)?(?:поле|ход)|"
                          r"except|apart\s+from|other\s+than|save\s+for)" + E)
# the next clause after «:» / «—» / «, если» / «, кроме» / «, но» names what is still open: «…: свободно a3», «…, но a3 свободно»
_LOCK_EXCEPT_NEXT = re.compile(r"\s*[:—–,]\s*(?:(?:но|а|хотя|if|but)\s+)?[^.;!?]{0,80}?" + W
                               + r"(?:свобод\w*|открыт\w*|доступн\w*|можно\s+(?:пойти|уйти|встать)|может\s+(?:пойти|уйти|встать)|"
                               r"free|open)" + E)


_LOCK_RESTRICTED = re.compile(W + r"(?:связ\w+|не\s+(?:открыв|подстав|остав|отда|потеря)\w*|без\s+(?:потер|того|риска|опасност)\w*|"
                              r"иначе|чтобы\s+не|безопасно|безнаказанно|спокойно|с\s+пользой)" + E)
_LOCK_CAUSE_NEXT = re.compile(r"\s*(?:[:—–,]\s*)?(?:[а-я]+\s+){0,2}?(?:закрыва\w*|загоражива\w*|загородил\w*|блокиру\w*|меша\w*|"
                              r"запира\w*|перекрыва\w*|стоит|стоят)" + E)


def _sentence_after(low: str, at: int) -> str:
    ends = [i for i in (low.find(c, at) for c in ".;!?\n") if i >= 0]
    return low[at: min(ends) if ends else len(low)]


# «заперт» meaning trapped (it can move, every way out loses) or confined (a king's net): not a claim about moves
_TRAPPED = re.compile(W + r"(?:отступ\w*|ловушк\w*|пойма\w*|поймать|окруж\w*|сбежа\w*|убежа\w*|бежать)" + E)
_LOSS = re.compile(W + r"(?:потерял\w*|потерян\w*|потеря(?:ть|ешь|ет|ем|ют)|погиб\w*|пропал\w*|пропада\w*|висел\w*|"
                   # review-miss2 01.11: «стал добычей», «попал под удар», «потеря коня» (the noun), «его съели»
                   r"(?:стал\w*|оказал\w*)\s+добыч\w+|добыч\w+|попал\w*\s+под\s+(?:удар|бой|взятие)|потер(?:и|ю|я|ей)|"
                   r"подставил\w*|подставлен\w*|подставлял\w*|съели|съел[аи]?|съеден\w*|забрали|забрал[аи]?|"
                   r"взяли|отдал[аи]?|отдан\w*|погубил\w*|лишил\w*|стоил\w*\s+(?:тебе|вам|белым|черным)|"
                   r"поплатил\w*|достал\w*\s+(?:белым|черным|сопернику)|"
                   r"срубил\w*|срубили|побил[аи]?|выиграл[аи]?|lost|was\s+lost|hung|dropped)" + E)
_NO_PIN = re.compile(W + r"(?:нет|никакой|никаких|без)\s+(?:\w+\s+)?связ(?:ки|ок|ку)" + E)
_PIN_LETTERS = ("N", "B", "R", "Q")


# Past markers of a clause whose relation word is not a finite verb (review fp2 01.11): «Раньше пешку b4 никто не
# защищал», «пешка оставалась без защиты», «до этого конь был под ударом».
_PAST_ADV = re.compile(W + r"(?:раньше|прежде|до\s+этого|до\s+того|ранее|когда-то|в\s+тот\s+момент|на\s+тот\s+момент|"
                       r"earlier|previously|before\s+that|at\s+that\s+point|at\s+the\s+time)" + E)
_LINK_PAST = re.compile(W + r"(?:оказал(?:ся|ась|ось|ись)|оставал(?:ся|ась|ось|ись)|остал(?:ся|ась|ось|ись)|стоял[аио]?|"
                        r"стал[аио]?|находил(?:ся|ась|ось|ись)|висел[аио]?)\s+(?:\w+\s+){0,2}$")
# an appearance verb before the relation: the speaker reports a look, often to deny it
_APPEARS = re.compile(W + r"(?:выгляд\w*|казал\w*|кажется|кажутся|казаться|мнимо|seem\w*|look(?:s|ed)?|appear\w*)\s+"
                      r"(?:\w+\s+){0,2}$")


def _with_governs(low: str, toks: list, start: int, t, preps: str) -> bool:
    """The preposition («с», «со», "to") governs the piece token *t*: it stands right before it, with at most one word
    between that is not itself a piece noun (review fp2 01.11: in «связан с королём слоном b4» the «с» governs «королём»,
    and «слоном b4» is the agent — the pin's word order, either way)."""
    m = re.search(r"(?:^|\s)(?:" + preps + r")\s+(?:\w+\s+)?$", low[start:t.start])
    if not m:
        return False
    a = start + m.start()
    return not any(x is not t and x.kind in ("PIECE", "PRON") and a <= x.start < t.start for x in toks)


def _detector_live(name: str) -> bool:
    """The detector may emit (mode 'on' or 'shadow'); 'off' — via COACH_DETECTORS_OFF — emits nothing."""
    try:
        from src import config

        return config.detector_enabled(name)
    except Exception:  # noqa: BLE001 — a broken switch never breaks the parser
        return False


def _verb_tense(verb: str, clause_low: str) -> str:
    if _FUTURE.search(clause_low):
        return "future"
    if re.search(r"(?:л|ла|ли|ло|лся|лась|лись)$", verb):
        return "past"
    if re.match(r"(?:под|за|при|на|от|вы|по|у|пере|сыгра|сдела|спас|съе|созда|раз)\w+(?:ит|ет|ут|ют|ят|ат|ится|ется|утся)$", verb) \
            and not re.search(r"(?:ает|яет|ует|ивает|ывает|ают|яют|уют|ивают|ывают|ается|ивается|ывается)$", verb) \
            and not re.match(r"(?:уход|выход|отход|увод|вывод|убира|спаса)", verb):
        return "future"
    return "present"


def _is_proposal(verb: str, low: str, ca: int, at: int) -> bool:
    """An infinitive, an imperative or a modal/purpose frame before the verb in its clause."""
    if re.search(r"(?:ть|ти|ться|тись)$", verb):
        return True
    if verb.endswith(("и", "ите", "ись", "итесь")) and not verb.endswith(("ли", "лись")):
        return True  # «сними», «уведи», «развяжи», «уходи» (not the past «ушли», «вели»)
    return bool(_PROPOSAL.search(low[ca:at]))


def _clause_of(clauses: list, at: int, n: int) -> tuple:
    return next(((a, b) for a, b in clauses if a <= at < b), (0, n))


def _pres_pos(text: str, toks: list, at: int, end: int, clause: tuple, tense: str, agent=None):
    """The position of a presupposition claim at *at*: the ordinary reading of the words (``_position``) for a raw claim
    with no question and no modal (a presupposition survives both)."""
    raw = _Raw("PRESUP", agent, [], False, tense, "", at, clause, end=end)
    return _position(raw, text, toks, None, _unread_number(text.lower(), toks))


def _side_ref(owner) -> Optional[Ref]:
    side, own = _side_owner(owner)
    if side is None and own is None:
        return None
    return Ref(side=side, owner=own)


def _piece_ref(tk, ante: dict) -> Optional[_R]:
    """A PIECE (or a resolved pronoun) token as an _R."""
    if tk is None:
        return None
    if tk.kind == "PIECE":
        return _R("piece", tk.ptype, tk.sq, tk.owner, text=tk.text, from_sq=tk.from_sq)
    if tk.kind in ("PRON", "WHICH"):
        got = ante.get(id(tk))
        if got is None or got.what != "piece":
            return None
        return _R("piece", got.ptype, got.sq, got.owner, text=tk.text, pronoun=True)
    return None


def _sentence_side(toks: list, low: str, ca: int, at: int):
    """The side the clause names as its subject («белые», «чёрные», «ты», «у чёрных»), or None."""
    m = re.search(W + r"у\s+(бел|черн)\w*" + E, low[ca:at])
    if m:
        return chess.WHITE if m.group(1) == "бел" else chess.BLACK
    sides = [t for t in toks if t.kind == "SIDE" and ca <= t.start < at]
    return sides[-1].owner if sides else None


def _escape_move(toks: list, low: str, at: int, verb_end: int, cb: int):
    """The move the sentence tells for the pin's end at *at* (fix1101 F1), whoever makes it: the last told move before
    the verb («Bd2 развязывает коня c3», «После 4...Be7 конь f6 выходит из-под связки», «Ход Nd2 снимает связку»), else
    one the words attach right after it («развяжись ходом Nd2», «развяжи коня: Bd2», «чтобы развязать коня, сыграй
    Bd2»). Not a move named as a threat or an idea, not one in another sentence. None when the sentence tells none."""
    moves = [x if x.kind == "MOVE" else Tok("MOVE", x.start, x.end, x.text, san=x.text, told=x.told)
             for x in toks if (x.kind == "MOVE" or (x.kind == "SQ" and x.move_cue)) and not x.threat]
    before = [x for x in moves if x.end <= at]
    if before:
        return before[-1]
    after = [x for x in moves if x.start >= verb_end]
    if after:
        x = after[0]
        gap = low[verb_end:x.start]
        if len(gap) <= 70 and not re.search(r"[.;!?]", gap) and \
                re.search(W + r"(?:ход(?:ом)?|сыграй\w*|играй\w*|сыграть|move)\s*$|[:—–]\s*$", gap) and \
                not re.search(W + r"(?:после|если|когда|after|if|when)" + E, gap):
            return x
    return None


def _negated_at(low: str, ca: int, vstart: int) -> bool:
    """«не развязывает», «не уйдёт из-под связки», «не снимает связку»: a negation governs the verb."""
    return bool(re.search(W + r"(?:не|ни|никак|нельзя|никогда)\s+(?:(?:[^\W\d]+)\s+){0,2}$", low[ca:vstart]))


def _pin_claims(t: str, low: str, toks: list, ante: dict) -> list:
    """The pin presuppositions of the sentence (detectors pin_escape and pin_noun).

    pin_escape (fix1101 F1) reads the parts of the claim, not one phrase: the piece that leaves the pin (the subject of
    an intransitive verb, the object of a transitive one, a genitive after «связку (с)», the side the clause names), the
    verb's mood (report, proposal, question, negation) and the move the sentence tells for it — any piece's move, the
    escaping piece's own or another one's (an interposition, a capture of the pinner). With a move M the claim is
    Claim('pinned', objs=(the piece,), move=M, presup='before_move', escape=…): the pin held on the board right before
    M (presupposition), and — for an affirmative report or proposal where M is another piece's move — it no longer
    holds right after M (assertion). The judge finds the board M is played on: the board's last move when it is M,
    or the board itself when M is a legal move there — of the escaping piece's side, from the square the words name."""
    out: list = []
    clauses = _clauses(t, toks)
    escape_on, noun_on = _detector_live("pin_escape"), _detector_live("pin_noun")
    if _NO_PIN.search(low):
        return out
    question = t.rstrip().endswith("?")
    seen: set = set()

    def add(rel, objs, presup, at, end, clause, tense, kind, subj=None, to=None, move=None, agent=None, escape=False):
        pos = _pres_pos(t, toks, at, end, clause, tense, agent)
        if pos.at == _SKIP:
            return
        objs = tuple(o for o in objs if o is not None)
        key = (rel, objs, presup, move, to)
        if key in seen:
            return
        seen.add(key)
        out.append(Claim(rel, subj, objs, to=to, pos=pos, span=(at, end), presup=presup, move=move, kind=kind,
                         escape=escape))

    def emit(ref, owner_ref, verb, vstart, cue_end, ca, cb, rel_word, subj=None, verb_end=None):
        """One escape: *ref* the piece that leaves the pin (an _R, or None with *owner_ref* a side), *verb* its verb."""
        proposal = _is_proposal(verb, low, ca, vstart)
        tense = "present" if proposal else _verb_tense(verb, low[ca:cb])
        neg = _negated_at(low, ca, vstart)
        mv = _escape_move(toks, low, vstart, verb_end if verb_end is not None else cue_end, cb)
        if mv is not None and proposal and mv.end <= vstart and \
                re.search(W + r"(?:после|если|когда|на|в\s+ответ\s+на|after|if|when|once)\s*(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?)?$",
                          low[max(0, mv.start - 16):mv.start]):
            # «После 3...Bb4 надо развязать коня c3»: the move told is the moment, not the means — the pin is on the
            # board after it, some board of the sentence
            mv = None
        move = _move_ref(mv) if mv is not None else None
        # the assertion «the pin is gone right after M» is the words' only for a report of M ending it now («Bd2
        # развязывает коня», «После Bd2 конь выходит из-под связки», «Ход 4...Bd7 снял связку»): not for a proposal
        # or a purpose («играй a3, чтобы развязать коня» — the pin may end a move later), not for the future («после a3
        # конь выйдет из-под связки»), not with a word that puts the end later («потом», «в итоге»)
        affirm = not neg and not question and not proposal and tense in ("present", "past") and \
            not re.search(W + r"(?:потом|затем|позже|в\s+итоге|в\s+конце\s+концов|со\s+временем|рано\s+или\s+поздно|"
                          r"скоро|вскоре|later|eventually)" + E, low[ca:cb])
        if ref is None or not ref.ptype:
            side_ref = owner_ref
            if side_ref is None and ref is not None and ref.owner is not None:
                side_ref = _side_ref(ref.owner)
            if move is not None and not move.castle:
                # «Сначала Nd2, чтобы развязаться», «4...Be7 снимает эту связку»: some piece of the mover's side was
                # pinned before the move (the side the words name, else the mover's)
                add("pin_exists", [side_ref], "before_move", vstart, cue_end, (ca, cb), tense, "pin_escape", move=move)
            elif proposal and (rel_word == "remove" or (ref is not None and ref.owner is not None)):
                if re.search(W + r"(?:не\s+да\w*|не\s+позвол\w*|меша\w*|помешать)" + E, low[ca:vstart]):
                    # «не даёт им развязаться», «мешает снять связку»: an agent keeps the pin — the pin_noun's claim
                    # (holding a pin), not an escape
                    add("pin_exists", [side_ref], "exists", vstart, cue_end, (ca, cb), "present", "pin_noun")
                    return
                # «снять связку» (a side or none named), «не даёт им развязаться»: some pin of some board of the
                # sentence. A bare side leaving a pin with no move told («чёрные должны избавиться от связки») is a
                # lesson's theme as often as this board's fact: unjudged
                add("pin_exists", [side_ref], "exists", vstart, cue_end, (ca, cb), "present", "pin_escape")
            return
        letter = _LETTER[ref.ptype]
        side, owner = _side_owner(ref.owner)
        own_move = move is not None and move.piece == letter and (ref.sq is None or move.frm in (None, chess.square_name(ref.sq)))
        if letter == "P" and rel_word == "escape" and (move is None or own_move):
            return  # a pawn steps out of a pin only by capturing: the words then name the capture
        king_moves = letter == "K" or (subj is not None and subj.ptype == chess.KING and rel_word == "escape")
        if king_moves:
            # the king steps off the line (or takes the piece with it): some piece of its side — the one named, when the
            # king leads it — was pinned to the king
            k = subj if letter != "K" else ref
            kside, kowner = _side_owner(k.owner)
            king = Ref(sq=chess.square_name(k.sq) if k.sq is not None and move is None else None, piece="K", side=kside,
                       owner=kowner, text=k.text)
            if letter != "K":
                objs = [Ref(sq=chess.square_name(ref.sq) if ref.sq is not None else None, piece=letter,
                            side=side if side is not None else kside, owner=owner or (kowner if side is None else None),
                            text=ref.text)]
            else:
                objs = [Ref(side=kside, owner=kowner)] if kside is not None or kowner is not None else []
            if move is not None and move.piece != "K":
                move = None  # «уйти королём» names the king's move: another piece's move is not it
            presup = "before_move" if move is not None else ("exists" if proposal or tense == "past" else "")
            if presup:
                add("pin_exists", objs, presup, vstart, cue_end, (ca, cb), tense, "pin_escape", to=king, move=move)
            return
        obj = Ref(sq=chess.square_name(ref.sq) if ref.sq is not None else None, piece=letter, side=side, owner=owner,
                  pronoun=ref.pronoun, text=ref.text)
        if move is not None and not move.castle:
            # whether M is the piece's own move the judge reads off the board (the from-square): the assertion is
            # judged only for another piece's move
            add("pinned", [obj], "before_move", vstart, cue_end, (ca, cb), tense, "pin_escape", move=move, escape=affirm)
            return
        if rel_word == "gone":
            return  # «больше не связан» with no move told: the denial is the ordinary claim of bind
        if proposal or tense == "past":
            # «надо развязать коня», «сними связку»: the pin the proposal ends is on the board it is made on (or some
            # board of the sentence). «Конь вышел из-под связки» with no move told: the pin held before a move the
            # sentence does not name — claim_judge leaves the past unjudged (the board now is after it, where the pin
            # is gone by the words' own account; fix1101 F1)
            add("pin_exists", [obj], "exists", vstart, cue_end, (ca, cb), tense, "pin_escape")
        elif rel_word == "remove":
            # «это снимает связку с коня» with no move told: the move is in another sentence, and the board now may
            # be before it or after it — unjudged rather than judged on the wrong ply
            return
        else:
            # a report with no move of its own: the board now (present) is the board before the escape
            add("pinned", [obj], "", vstart, cue_end, (ca, cb), tense, "pin_escape",
                agent=_R("piece", ref.ptype, ref.sq, ref.owner, text=ref.text))

    def subject_before(ca, at):
        noms = [x for x in toks if x.kind in ("PIECE", "PRON") and ca <= x.start < at and "N" in x.cases
                and not (x.kind == "PIECE" and x.attr)]
        return noms[-1] if noms else None

    def escape(verb_m, cue_start, cue_end, rel_word):
        """«конь уходит из-под связки», «увести ферзя из-под связки», «уйти королём …», «развязать пешку c5»."""
        ca, cb = _clause_of(clauses, cue_start, len(t))
        verb = verb_m.group(0).split()[0]
        vstart = verb_m.start()
        reflexive = verb.endswith(("ся", "сь"))
        nom = subject_before(ca, vstart)
        subj = _piece_ref(nom, ante)
        upto = cue_start if cue_start > verb_m.end() else cb
        acc = [x for x in toks if x.kind in ("PIECE", "PRON") and verb_m.end() <= x.start < upto and "A" in x.cases
               and "N" not in x.cases and (x.kind == "PRON" or x.start - verb_m.end() <= 30)]
        transitive = not reflexive and (bool(_ESC_TRANSITIVE.match(verb)) or rel_word == "unpin" or bool(acc))
        mover = None
        if transitive:  # the accusative is the piece that leaves the pin («увести ферзя», «развязать пешку c5»)
            mover = acc[0] if acc else None
            if mover is None and rel_word == "unpin":
                # «развязать коня» with the object before the verb («коня c3 Bd2 развязывает»): the accusative first
                pre = [x for x in toks if x.kind == "PIECE" and ca <= x.start < vstart and "A" in x.cases and "N" not in x.cases]
                mover = pre[-1] if pre else None
        if mover is None and not transitive:
            ins = [x for x in toks if x.kind == "PIECE" and verb_m.end() <= x.start < cue_start and "I" in x.cases and x.ptype]
            mover = ins[0] if ins else nom  # «уйти королём», «конь уходит»
            if mover is None:
                dat = [x for x in toks if x.kind == "PRON" and ca <= x.start < vstart and "D" in x.cases]
                mover = dat[-1] if dat else None  # «не даёт им развязаться»
        ref = _piece_ref(mover, ante)
        owner_ref = None
        if ref is None:
            side = _sentence_side(toks, low, ca, vstart)
            if side is None and re.search(r"(?:и|ись|ите|итесь|ешь|ишься|ем|емся)$", verb):
                side = "you"
            owner_ref = _side_ref(side) if side is not None else None
        emit(ref, owner_ref, verb, vstart, cue_end, ca, cb, rel_word, subj=subj, verb_end=verb_m.end())

    def verb_before(ca, at, pat):
        verbs = [m for m in pat.finditer(low, max(ca, at - 45), at)]
        if verbs and not re.search(r"[,;:—–]", low[verbs[-1].end():at]):
            return verbs[-1]
        return None

    if escape_on:
        for cue in _PIN_FROM_UNDER.finditer(low):
            ca, _cb = _clause_of(clauses, cue.start(), len(t))
            v = verb_before(ca, cue.start(), _ESC_VERB) or verb_before(ca, cue.start(), _ANY_VERB)
            if v is None:
                continue
            escape(v, cue.start(), cue.end(), "escape")
        for cue in _PIN_OUT_OF.finditer(low):
            if low[max(0, cue.start() - 4):cue.start()].endswith("-"):
                continue
            ca, _cb = _clause_of(clauses, cue.start(), len(t))
            v = verb_before(ca, cue.start(), _ESC_VERB)
            if v is None:
                continue
            escape(v, cue.start(), cue.end(), "escape")
        for m in _UNPIN.finditer(low):
            if m.group("v").startswith("развязан"):
                continue  # «развязанный», «развязана»: a state, not the act
            escape(m, m.end(), m.end(), "unpin")
        for m in list(_REMOVE_PIN.finditer(low)) + list(_PIN_ENDS.finditer(low)):
            ca, cb = _clause_of(clauses, m.start(), len(t))
            verb = m.group("v")
            vstart = m.start("v") if m.re is _PIN_ENDS else m.start()
            owner = _sentence_side(toks, low, ca, m.start())
            if owner is None and re.search(r"(?:и|ите|ешь|ете|ем)$", verb):
                owner = "you"  # «сними связку», «снимаешь связку»: the one addressed is pinned
            if m.re is _PIN_ENDS:
                head = m.start() + len("связк") + 1
                pinned = [x for x in toks if x.kind == "PIECE" and head <= x.start < m.start("v") and "G" in x.cases and x.ptype]
            else:
                pinned = [x for x in toks if x.kind == "PIECE" and m.end() <= x.start < cb and "G" in x.cases and x.ptype
                          and x.start - m.end() < 20]
            ref = _piece_ref(pinned[0], ante) if pinned else None
            emit(ref, _side_ref(owner) if ref is None and owner is not None else None, verb, vstart, m.end(), ca, cb,
                 "remove", verb_end=m.end())
        # a piece called pinned by an attribute or a state (review-miss2 01.11): «Связанный конь b1 освобождается после
        # Nd2», «Конь, связанный слоном f5, уйдёт на d2», «Nd2 освобождает связанного коня», «Конь b1 в связке, так что
        # сначала Nd2» — the pin is said to hold before the move the sentence tells (or now, with none)
        for m in _PIN_ATTR.finditer(low):
            ca, cb = _clause_of(clauses, m.start(), len(t))
            if _negated_at(low, ca, m.start()) or question or _HYPO.search(low[:cb]):
                continue
            piece = None
            if m.group("state"):
                piece = next((x for x in reversed(toks) if x.kind == "PIECE" and x.ptype and x.end <= m.start()
                              and m.start() - x.end <= 6), None)
            else:
                piece = next((x for x in toks if x.kind == "PIECE" and x.ptype and m.end() <= x.start <= m.end() + 2), None) \
                    or next((x for x in reversed(toks) if x.kind == "PIECE" and x.ptype and x.end <= m.start()
                             and re.fullmatch(r"\s*(?:[a-h][1-8]\s*)?,\s*", low[x.end:m.start()])), None)
            if piece is None or piece.sq is None or piece.ptype == chess.KING:
                continue
            ref = _piece_ref(piece, ante)
            mv = _escape_move(toks, low, m.start(), m.end(), len(t))
            letter = _LETTER[ref.ptype]
            side, owner = _side_owner(ref.owner)
            obj = Ref(sq=chess.square_name(ref.sq), piece=letter, side=side, owner=owner, text=ref.text)
            if any(x.kind == "MOVE" and x.end <= min(m.start(), piece.start) for x in toks):
                continue  # a move told before the attribute: the pin is on that line's board
            if mv is not None:
                add("pinned", [obj], "before_move", m.start(), m.end(), (ca, cb), "present", "pin_escape", move=_move_ref(mv))
            else:
                add("pinned", [obj], "", m.start(), m.end(), (ca, cb), "present", "pin_escape",
                    agent=_R("piece", ref.ptype, ref.sq, ref.owner, text=ref.text))
        for m in _PIN_GONE.finditer(low):
            ca, cb = _clause_of(clauses, m.start(), len(t))
            if _escape_move(toks, low, m.start(), m.end(), cb) is None:
                continue
            nom = subject_before(ca, m.start("st") if m.group("st") else m.start())
            ref = _piece_ref(nom, ante)
            if ref is None or not ref.ptype:
                continue
            emit(ref, None, "связан", m.start(), m.end(), ca, cb, "gone", verb_end=m.end())
    if noun_on:
        for m in list(_HOLD_PIN.finditer(low)) + list(_UNDER_PIN.finditer(low)):
            ca, cb = _clause_of(clauses, m.start(), len(t))
            hold = m.re is _HOLD_PIN
            verb = m.group("v") if hold else ""
            if hold and verb.startswith("держ") and re.match(r"\s*(?:ся|сь)", low[m.end("v"):m.end("v") + 3]):
                continue
            subj = None
            pinned = None
            if hold:
                noms = [x for x in toks if x.kind in ("PIECE", "PRON") and ca <= x.start < m.start() and "N" in x.cases
                        and not (x.kind == "PIECE" and x.attr)]
                if noms:
                    subj = _piece_ref(noms[-1], ante)
                else:
                    before = [x for x in toks if x.kind == "PIECE" and x.end <= m.start() and x.ptype]
                    after_all = [x for x in toks if x.kind == "PIECE" and x.start >= m.end() and x.ptype and x.start < cb
                                 and not ("G" in x.cases and x.start - m.end() < 20)]
                    if len(before) == 1 and not after_all:
                        subj = _piece_ref(before[0], ante)  # «что ты хочешь получить от этого слона — держать связку»
                gen = [x for x in toks if x.kind == "PIECE" and m.end() <= x.start < cb and "G" in x.cases and x.ptype
                       and x.start - m.end() < 20 and not re.search(r"(?:^|\s)(?:с|со)\s+$", low[m.end():x.start])]
                if gen:
                    pinned = _out_ref(_piece_ref(gen[0], ante))
                else:
                    sq = re.match(r"\s*(?:по|на)\s+([a-h][1-8])(?![0-9])", low[m.end():m.end() + 12])
                    if sq:
                        pinned = Ref(sq=sq.group(1), text=sq.group(0).strip())
            else:
                acc = [x for x in toks if x.kind in ("PIECE", "PRON") and ca <= x.start < m.start() and "A" in x.cases
                       and "N" not in x.cases]
                nom = [x for x in toks if x.kind in ("PIECE", "PRON") and ca <= x.start < m.start() and "N" in x.cases
                       and not (x.kind == "PIECE" and x.attr)]
                pinned = _out_ref(_piece_ref((acc or nom or [None])[-1], ante))
                pinner = [x for x in toks if x.kind == "PIECE" and m.end() <= x.start < cb and "G" in x.cases and x.ptype
                          and re.match(r"\s*(?:от|со\s+стороны)\s+(?:\w+\s+)?$", low[m.end():x.start])]
                subj = _piece_ref(pinner[0], ante) if pinner else None
                verb = next((w for w in re.findall(rf"{L}+", low[ca:m.start()])[::-1]), "")
            behind = [x for x in toks if x.kind == "PIECE" and m.end() <= x.start < cb and "I" in x.cases and x.ptype
                      and re.search(r"(?:^|\s)(?:с|со)\s+(?:\w+\s+)?$", low[m.end():x.start])]
            to = _out_ref(_piece_ref(behind[0], ante)) if behind else None
            if pinned is None and subj is None and not hold:
                side = _sentence_side(toks, low, ca, m.start())
                pinned = _side_ref(side) if side is not None else None
            s = _out_ref(subj) if subj is not None else None
            if s is None and hold:
                s = _side_ref(_sentence_side(toks, low, ca, m.start()))  # «чёрные сохраняют связку»: a pinner of theirs
            if s is not None and s.piece == "K":
                continue  # «связан королём»: a king pins nothing
            add("pin_exists", [pinned], "exists", m.start(), m.end(), (ca, cb), _verb_tense(verb, low[ca:cb]) if verb else "present",
                "pin_noun", subj=s, to=to)
    return out


_FRENCH = "rnbqkbnr/ppp2ppp/4p3/3pP3/3P4/8/PPP2PPP/RNBQKBNR b KQkq - 0 3"


def _locked_judge_ready() -> bool:
    """The judge reads 'locked' as «no way out» — at most one legal move or one square of reach (P3B, plan 31.10): the
    French bishop c8 after 1.e4 e6 2.d4 d5 3.e5, whose one move is d7, is locked. The judge of WP-0 reads it as «no
    legal move at all» and would cut that true sentence, so until the judge says so the grammar emits no 'locked'
    claim (a probe of the contract on one board, ~0.1 ms, only for a sentence with a locked cue)."""
    try:
        from src import claim_judge

        v, _ = claim_judge.judge_on(Claim("locked", Ref(sq="c8", piece="B"), ()), chess.Board(_FRENCH), None)
        return v is True
    except Exception:  # noqa: BLE001
        return False


def _locked_claims(t: str, low: str, toks: list, ante: dict) -> list:
    """«слон c8 заперт», «конь на g1 и слон на f1 пока заперты», «у белых пока заперт слон f1», «чёрный ферзь без ходов»,
    «слону f1 некуда ходить»: a piece with no way out (detector locked). The parts are read, not a phrase (fix1101 F1):
    the subject on either side of the cue (a nominative piece, a dative one before «некуда»), its square from the words
    or «заперт на d1», the side from «у белых» / a colour word, the tense from the verb («окажется заперт» is the board
    after the line the sentence tells). Left unjudged — the strict verdict is not what the words mean — when the clause
    names a blocker or a cause («заперт пешками / цепью d6–e5 / центром», «упирается в свою пешку», «плохой слон»: the
    locked_by claim of bind says what it can), when a hedge softens it («почти», «фактически»), or when it is denied."""
    out: list = []
    if not _detector_live("locked") or _TRAPPED.search(low) or not _locked_judge_ready():
        return out
    clauses = _clauses(t, toks)
    cues = [(x.start, x.end, x.text, "locked") for x in toks if x.kind == "REL" and x.rel == "LOCK" and x.text.startswith("заперт")]
    cues += [(m.start(), m.end(), m.group(0), "locked") for m in _LOCKED_EXTRA.finditer(low)]
    cues += [(m.start(), m.end(), m.group(0), "trapped") for m in _NOWHERE.finditer(low)]
    for m in _LOCK_TRANS.finditer(low):
        w = m.group(0)
        if w.startswith(("оставля", "оставил", "оставит", "держ")) and not re.search(
                W + r"(?:взаперти|в\s+клетке|без\s+ходов)" + E, low[m.end():m.end() + 40]):
            continue  # «оставляет слона c8 взаперти», not «оставляет слона на c8»
        cues.append((m.start(), m.end(), w, "locked_obj"))
    seen = set()
    for a, b, word, rel in cues:
        ca, cb = _clause_of(clauses, a, len(t))
        clause = low[ca:cb]
        if _LOCK_EXCEPT.search(_sentence_after(low, a)) or _LOCK_EXCEPT_NEXT.match(low[cb:cb + 200]):
            continue  # an exception told after the cue («: …, свободно только a3», «, если не считать b1 и c1»)
        if re.match(r"не\s|никак", word) and "никуда" not in word and re.match(
                r"\s*(?:(?:на|в|во|к|до|через|за)\s+\S+|туда|вперед|назад|сюда|дальше)", low[b:b + 24]):
            continue  # «Слон c4 не может пойти на f7»: one move denied (a capture that costs), not every move
        if _LOCK_RESTRICTED.search(_sentence_after(low, ca)) or _LOCK_CAUSE_NEXT.match(low[cb:cb + 120]):
            # «связанный конь не может уйти, не открыв ферзя», «слон связан и не может уйти на e3»: a pin or a cost
            # restricts the moves, not their absence; «…: её закрывают конь g1 и пешка h2» names the blockers
            continue
        if _LOCK_BLOCKER.search(clause) or _LOCK_HEDGE.search(clause) or \
                any(x.kind == "PIECE" and "I" in x.cases and ca <= x.start < cb and x.start >= b for x in toks):
            continue  # a blocker, a cause or a hedge named: not the strict «no way out»
        if any(x.kind == "NEG" and ca <= x.start < a and not re.search(r"(?:выйти|ходов|некуда)", word) for x in toks) or \
                re.search(W + r"не\s+(?:\w+\s+)?$", low[ca:a]):
            continue
        subjects = []
        if rel == "locked_obj":
            obj = next((x for x in toks if x.kind == "PIECE" and b <= x.start < cb and set(x.cases) & {"A", "G"}
                        and not x.attr), None)
            if obj is None or re.search(W + r"(?:своими|своей|пешками|пешкой|цеп\w*)" + E, low[b:obj.start]):
                continue
            subjects.append(obj)
            rel = "locked"
        elif rel == "trapped" or re.match(r"не\s+(?:выйти|выбраться|двинуться|сдвинуться|пошевелиться)", word):
            # «ферзю некуда идти», «чёрному ферзю не выйти из d8»: an infinitive's subject is in the dative
            dat = [x for x in toks if x.kind in ("PIECE", "PRON") and ca <= x.start < a and "D" in x.cases
                   and not (x.kind == "PIECE" and x.attr)]
            if dat:
                subjects.append(dat[-1])
        noms = [x for x in toks if x.kind in ("PIECE", "PRON") and ca <= x.start < a and "N" in x.cases
                and not (x.kind == "PIECE" and x.attr)]
        if subjects:
            pass
        elif rel == "locked_obj":
            continue
        elif noms:
            subjects.append(noms[-1])
            k = toks.index(noms[-1]) - 1
            nxt = noms[-1].start
            while k >= 0 and word.endswith("ы"):  # «конь на g1 и слон на f1 заперты»: every member of the subject
                x = toks[k]
                if x.kind in ("BOUND", "OWNER"):
                    k -= 1
                    continue
                if x.kind == "PIECE" and "N" in x.cases and x.start >= ca and \
                        re.fullmatch(r"\s*(?:(?:на\s+)?[a-h][1-8]\s*)?(?:,|и)\s*", low[x.end:nxt]):
                    subjects.append(x)
                    nxt = x.start
                    k -= 1
                    continue
                break
        else:
            # the subject after the cue: «запертый слон c8», «у белых пока заперт слон f1»
            nxt = next((x for x in toks if x.kind == "PIECE" and b <= x.start < cb), None)
            if nxt is not None and nxt.start - b <= 3 and "N" in nxt.cases and \
                    (nxt.sq is not None or re.match(r"(?:ый|ого|ому|ым|ая|ую|ой|ые|ых|ыми)$", word[6:]) is None):
                subjects.append(nxt)
        sq_after = re.match(r"\s*(?:(?:с\s+места\s+)?(?:на|в|из|с)\s+)([a-h][1-8])(?![0-9])", low[b:b + 20])
        for s in subjects:
            ref = _piece_ref(s, ante)
            if ref is None or _LETTER.get(ref.ptype) not in _PIN_LETTERS:
                continue  # a king is confined, a pawn blocked: other relations
            if ref.sq is None and sq_after:
                ref = _R("piece", ref.ptype, chess.parse_square(sq_after.group(1)), ref.owner, text=ref.text)
            if ref.owner is None:
                cm = re.search(r"(?:^|\s)(?P<w>бел|черн)(?:ый|ая|ое|ого|ой|ому|ым|ую)\s+(?:\w+\s+)?$", low[max(0, s.start - 24):s.start])
                if cm:  # «Белому ферзю ходить некуда»: a colour adjective names the piece's side
                    ref = _R("piece", ref.ptype, ref.sq, chess.WHITE if cm.group("w") == "бел" else chess.BLACK,
                             text=ref.text, pronoun=ref.pronoun)
            if ref.owner is None:
                side = _sentence_side(toks, low, ca, a)
                if side in (chess.WHITE, chess.BLACK):
                    ref = _R("piece", ref.ptype, ref.sq, side, text=ref.text, pronoun=ref.pronoun)
            if re.search(W + r"(?:останется|останутся|окажется|окажутся|станет|станут|будет|будут)" + E, clause):
                # «На 2.d4 d5 3.e5 слон c8 окажется заперт», «Если чёрные сыграют 2...d5, ты ответишь 3.e5, и слон c8
                # останется запертым»: the future of a numbered line the sentence tells is the board after that line
                line = [x for x in toks if x.kind == "MOVE" and not x.threat and x.end <= a]
                tense = "present" if line and all(x.num for x in line) and \
                    re.search(W + r"(?:после|на|при|если|когда|как\s+только|в\s+варианте|вариант\w*|after|if|on|when)" + E,
                              low[:line[0].start]) else "future"
            else:
                prev = low[ca:a].split()
                tense = "present" if prev and re.match(r"(?:оказал|осталс|остал)", prev[-1]) else \
                    _verb_tense(prev[-1] if prev else "", clause)
            pos = _pres_pos(t, toks, a, b, (ca, cb), tense, ref)
            if pos.at == _SKIP:
                continue
            key = (ref.ptype, ref.sq, ref.owner, rel)
            if key in seen:
                continue
            seen.add(key)
            out.append(Claim(rel, _out_ref(ref), (), pos=pos, span=(a, b), kind="locked"))
    return out


# cover_cause (fix1101 F1): the parts of «Z held by H — so X was lost there», read in either order and voice
_HOLD_VERB = re.compile(W + r"(?:держ(?:ит|ат|ал\w*|ать)|удержива\w*|контролир\w*|бь[её]т|бьют|бил[аи]?|бил\w*|атаку\w*|"
                        r"атаковал\w*|простреливал\w*|простреливает|простреливают|смотр(?:ит|ят|ел\w*)\s+на|"
                        r"нацел\w*\s+на|бер(?:ет|ут)\s+под\s+(?:контроль|удар))" + E)
# the cause told after the loss: «конь пропал, потому что …», «конь погиб: f6 держит пешка g7», «… ведь …»
_CAUSE_AFTER = re.compile(W + r"(?:потому\s+что|потому,\s*что|ведь|так\s+как|поскольку|из-за\s+того,?\s+что|из-за|"
                          r"since|because)" + E + r"|[:—–]")
# a contrast between the hold and the loss: the hold is then no cause («g7 держала f6, но конь всё равно погиб»)
_CONTRAST = re.compile(W + r"(?:но|однако|хотя|несмотря|все\s+равно|тем\s+не\s+менее|зато|а|though|but|although|"
                       r"despite|still)" + E)
_LOSS_TAKER = re.compile(r"^(?:съели|съел|забрал|взяли|срубил|побил|выиграл)")


def _cover_cause_claims(t: str, low: str, toks: list, claims: list) -> list:
    """«поле f6 держала пешка g7, и конь там просто потерялся», «конь пропал на f6, потому что это поле держала пешка
    g7», «из-за того, что пешка g7 бьёт f6, твой конь потерялся», «на f6 конь погиб из-за пешки g7»: a hold on a square
    named as the cause of the loss of a piece on it (detector cover_cause). The parts are read separately: the loss (a
    loss verb, with the lost piece as its subject or — for a taker's verb, «коня там съели» — its object), the hold
    (the bind claim of the sentence, or a holder piece with its square, a hold verb and the square in a clause of its
    own, in either word order; «из-за пешки g7» names the holder alone), the square (named with the loss, «там» / «это
    поле», or the hold's), and the link (the hold before the loss with no contrast between, or after it with a causal
    word). The lost piece named on the square, or by «там / на Z», is bound by the words; named by its kind alone, the
    judge binds it to the game's capture on that square of a piece of that kind (``to.sq`` None)."""
    out: list = []
    if not _detector_live("cover_cause"):
        return out
    losses = [m for m in _LOSS.finditer(low) if not re.search(W + r"не\s*$", low[max(0, m.start() - 4):m.start()])]
    if not losses:
        return out
    clauses = _clauses(t, toks)
    pieces = [x for x in toks if x.kind == "PIECE" and x.ptype]

    def lost_of(m):
        """(lost piece token, its square bound by the words or None, the loss clause) for the loss word *m*."""
        ca, cb = _clause_of(clauses, m.start(), len(t))
        taker = bool(_LOSS_TAKER.match(m.group(0)))
        noun = bool(re.fullmatch(r"потер(?:и|ю|я|ей)", m.group(0)))
        cand = [x for x in pieces if ca <= x.start < cb and not x.attr and "I" not in x.cases
                and not re.search(W + r"(?:из-за|у|для|от|под)\s+(?:\w+\s+)?$", low[max(ca, x.start - 14):x.start])]
        if noun:
            # «причина потери коня»: the piece lost is the genitive right after the noun
            cand = [x for x in cand if "G" in x.cases and 0 <= x.start - m.end() <= 3]
        elif taker:
            cand = [x for x in cand if "A" in x.cases and "N" not in x.cases] or \
                   [x for x in cand if "A" in x.cases]
        else:
            cand = [x for x in cand if "N" in x.cases] or cand
        if not cand:
            return None
        x = min(cand, key=lambda y: abs(y.start - m.start()))
        if abs(x.start - m.start()) > 40:
            return None
        zone = low[max(ca, min(x.start, m.start()) - 4):min(cb, max(x.end, m.end()) + 14)]
        z = chess.square_name(x.sq) if x.sq is not None else None
        here = sorted(re.finditer(W + r"на\s+([a-h][1-8])(?![0-9])", low[ca:cb]),
                      key=lambda h: abs(ca + h.start() - m.start()))
        if z is None and here:
            z = here[0].group(1)
        there = bool(re.search(W + r"(?:там|туда|здесь|на\s+этом\s+поле)" + E, zone))
        return x, z, there, (ca, cb)

    def holds():
        """(holder token, Z or None (an anaphor), pos, (start, end)) of every hold the sentence tells."""
        got = []
        for c in claims:
            if c.rel not in ("hold", "attack", "aim", "defend") or c.neg or c.question or c.pos.at == _SKIP or \
                    c.subj is None or not c.subj.sq or not c.subj.piece:
                continue
            for o in c.objs:
                if o is not None and o.sq and not o.piece:
                    h = next((x for x in pieces if x.sq is not None and chess.square_name(x.sq) == c.subj.sq), None)
                    got.append((c.subj, o.sq, c.pos, c.span, h))
        for v in _HOLD_VERB.finditer(low):
            ca, cb = _clause_of(clauses, v.start(), len(t))
            if re.search(W + r"(?:не|ни)\s+$", low[max(ca, v.start() - 4):v.start()]):
                continue
            hs = [x for x in pieces if ca <= x.start < cb and x.sq is not None and "N" in x.cases and not x.attr]
            if len(hs) != 1:
                continue
            h = hs[0]
            sqs = [x for x in toks if x.kind == "SQ" and ca <= x.start < cb and x.sq != h.sq and
                   (not x.move_cue or re.fullmatch(r"\s*", low[x.end:v.start()]))]  # «f6 держит пешка g7»
            if len(sqs) == 1:
                z = chess.square_name(sqs[0].sq)
            elif not sqs and _THERE.search(low[ca:cb]):
                z = None  # «это поле держала пешка g7»: the square of the loss
            else:
                continue
            tense = _verb_tense(v.group(0).split()[0], low[ca:cb])
            # the board is read before the clause's own words: its square is no move («f6 держит пешка g7»)
            at = min([h.start, v.start()] + [x.start for x in sqs])
            pos = _pres_pos(t, toks, at, v.end(), (ca, cb), "present" if tense == "future" else tense)
            if pos.at == _SKIP:
                continue
            got.append((_out_ref(_piece_ref(h, {})), z, pos, (min(h.start, v.start()), max(h.end, v.end())), h))
        # the hold as a noun or a participle (review-miss2 01.11): «f6 под контролем пешки g7», «под ударом пешки g7»,
        # «поле было под пешкой g7», «пешка g7, контролирующая f6»
        for m in re.finditer(W + r"под\s+(?:(?:контролем|ударом|боем|прицелом|обстрелом|защитой)\s+)?(?:\w+\s+)?(" + _PIECE_ALT
                             + r")" + E, low):
            h = next((x for x in pieces if m.start(1) <= x.start < m.end(1) + 1 and x.sq is not None), None)
            if h is None:
                continue
            ca, cb = _clause_of(clauses, m.start(), len(t))
            sqs = [x for x in toks if x.kind == "SQ" and ca <= x.start < cb and x.sq != h.sq and not x.move_cue]
            z = chess.square_name(sqs[0].sq) if len(sqs) == 1 else None
            pos = _pres_pos(t, toks, ca, m.end(), (ca, cb), "present")
            if pos.at != _SKIP:
                got.append((_out_ref(_piece_ref(h, {})), z, pos, (m.start(), h.end), h))
        for m in re.finditer(W + r"(" + _PIECE_ALT + r")" + E + r"\s+[a-h][1-8]\s*,?\s*(?:контролирующ|держащ|бьющ|атакующ|"
                             r"простреливающ)\w*\s+(?:поле\s+)?([a-h][1-8])", low):
            h = next((x for x in pieces if m.start(1) <= x.start < m.end(1) + 1 and x.sq is not None), None)
            if h is None:
                continue
            ca, cb = _clause_of(clauses, m.start(), len(t))
            pos = _pres_pos(t, toks, ca, m.end(), (ca, cb), "present")
            if pos.at != _SKIP:
                got.append((_out_ref(_piece_ref(h, {})), m.group(2), pos, (m.start(), m.end()), h))
        for m in re.finditer(W + r"из-за\s+(?:\w+\s+)?(" + _PIECE_ALT + r")" + E, low):
            h = next((x for x in pieces if m.start(1) <= x.start < m.end(1) + 1 and x.sq is not None), None)
            if h is None or not re.match(r"\s*(?:на\s+)?[a-h][1-8]", low[m.end(1):m.end(1) + 8]):
                continue
            ca, cb = _clause_of(clauses, m.start(), len(t))
            pos = _pres_pos(t, toks, ca, m.end(), (ca, cb), "present")  # «на f6 конь погиб из-за …»: f6 is no move
            if pos.at != _SKIP:
                got.append((_out_ref(_piece_ref(h, {})), None, pos, (m.start(), h.end), h))
        return got

    hs = holds()
    if not hs:
        return out
    done = set()
    for m in losses:
        lost = lost_of(m)
        if lost is None:
            continue
        x, z_loss, there, _lc = lost
        for subj, z_hold, pos, span, htok in hs:
            if htok is not None and x is htok:
                continue
            if span[0] < m.start():
                between = low[span[1]:m.start()]
                if _CONTRAST.search(between) or re.search(r"[.!?]", between):
                    continue
            else:
                between = low[m.end():span[0]]
                if not _CAUSE_AFTER.search(between) or _CONTRAST.search(between) or len(between) > 60:
                    if not (low[span[0]:].startswith("из-за") and len(between) <= 40):
                        continue
            z = z_hold or z_loss
            if z is None or (z_hold and z_loss and z_hold != z_loss):
                continue
            bound = z_loss == z or there
            if subj is None or subj.sq == z:
                continue
            side, owner = _side_owner(x.owner)
            key = (subj.sq, z)
            if key in done:
                continue
            done.add(key)
            out.append(Claim("cover_cause", subj, (Ref(sq=z),),
                             to=Ref(sq=z if bound else None, piece=_LETTER[x.ptype], side=side, owner=owner, text=x.text),
                             pos=pos, span=(min(span[0], m.start()), max(span[1], m.end())), kind="cover_cause"))
    return out


def _presupposed(t: str, low: str, toks: list, focus: dict, claims: list, ante: Optional[dict] = None) -> list:
    """The claims the sentence takes for granted (plan 31.10, P3A): pins, locked pieces, the cause of a loss."""
    try:
        if ante is None:
            ante, _ = _antecedents(toks, focus, low)
        out = []
        if re.search(r"связ|развяз", low):
            out += _pin_claims(t, low, toks, ante)
        if "заперт" in low or _LOCKED_EXTRA.search(low) or _NOWHERE.search(low) or _LOCK_TRANS.search(low):
            out += _locked_claims(t, low, toks, ante)
        out += _cover_cause_claims(t, low, toks, claims)
        return out
    except Exception:  # noqa: BLE001 — a presupposition never breaks the claims the sentence asserts
        return []


_TOK_CACHE: dict = {}


def _tokens(t: str) -> list:
    """tokenize(t), kept for the few sentences checked last (extract and written_moves read the same sentence; the
    tokens are read, never changed, after tokenize)."""
    got = _TOK_CACHE.get(t)
    if got is None:
        got = tokenize(t)
        if len(_TOK_CACHE) >= 32:
            try:
                _TOK_CACHE.pop(next(iter(_TOK_CACHE)), None)
            except (RuntimeError, StopIteration):  # another thread changed it: start afresh
                _TOK_CACHE.clear()
        _TOK_CACHE[t] = got
    return got


@lru_cache(maxsize=256)
def written_moves(text: str) -> tuple:
    """The moves *text* writes, in order, as the parser reads them: SAN, «e4-e5», a move told in words, castling, a bare
    square only where the words make it a move («Сыграй d3», «Лучший ход — d3», «После e4 e5 Nf3»). Not a move named
    as a threat or an idea. A move written twice («Nc6: конь с b8 встал на c6») is one."""
    t = normalize(text)
    if not re.search(r"[a-h][1-8]|o-o|0-0|рокировк", t.lower()):
        return ()
    toks = _tokens(t)
    seq = [x if x.kind == "MOVE" else Tok("MOVE", x.start, x.end, x.text, san=x.text, told=x.told)
           for x in toks if (x.kind == "MOVE" or (x.kind == "SQ" and x.move_cue)) and not x.threat]
    seq = _drop_restated(seq)
    low = t.lower()
    out: list = []
    prev = None
    for x in seq:
        mr = _move_ref(x)
        if out and _same_move(out[-1], mr) and not out[-1].castle and not _two_moves(prev, x, low):
            out[-1] = _merge(out[-1], mr)
        else:
            out.append(mr)
        prev = x
    return tuple(out)


def extract(text: str, state: dict, language: Optional[str] = None) -> list[Claim]:
    """The claims *text* makes. *state* is ``ctx.relation_state`` (immutable values only: the previous
    sentence's antecedents for pronouns, «тогда»); *language* is the answer's language when known."""
    if state is None:
        state = {}
    if language and language.lower().startswith(("kk", "kz")):
        return []  # Kazakh is out of scope (plan §3.2)
    t = normalize(text)
    low = t.lower()
    has_claim_word = bool(_CLAIMWORD.search(low))
    presup = bool(_PRESUP_CUE.search(low))
    if not has_claim_word and not re.search(rf"{W}(?:{_PIECE_ALT}){E}|[a-h][1-8]", low):
        out = _presupposed(t, low, _tokens(t), _focus_from(state), []) if presup else []
        state[SQUARES_KEY] = ()
        return out
    toks = _tokens(t)
    focus = _focus_from(state)
    focus["_squares"] = state.get(SQUARES_KEY) or ()
    ante, cur = _antecedents(toks, focus, low)
    claims: list = []
    if has_claim_word:
        idioms = [(m.start(), m.end()) for m in _IDIOM.finditer(low)]
        raws = [c for c in bind(t, toks, focus) if not any(a <= c.pos < b for a, b in idioms)]
        told = None
        unread_at = _unread_number(low, toks)
        # «Конь бьёт с шахом и …»: a capture/check told with no square — the board after it is unknown
        blind_from = next((m.start() for m in re.finditer(W + r"(?:бь[её]т|бьют|берет|берут|забирает|забирают)\s+с\s+шахом" + E, low)), None)
        for c in raws:
            if blind_from is not None and c.pos > blind_from:
                break  # a capture we could not read comes before: the board after it is unknown
            if c.rel == "TAKE":
                cap = _told_capture(c, t)
                if cap is None:
                    blind_from = c.pos
                elif told is None:
                    told = cap
                continue
            pos = _position(c, t, toks, told, unread_at)
            claim = _convert(c, pos, told)
            if claim is not None and (claim.subj is not None or claim.objs) and not _narrates_capture(c, toks, t):
                claims.append(claim)
            if c.rel == "ATT" and _TAKE.match(c.verb):
                cap = _told_capture(c, t)
                if cap is not None and told is None:
                    told = cap
                elif cap is None and (_TAKE_SURE.match(c.verb) or
                                      re.match(r"[^.;:—]{0,20}?с\s+шахом" + E, low[c.end:c.clause[1]])):
                    blind_from = c.pos
    if presup or _LOSS.search(low):
        claims += _presupposed(t, low, toks, focus, list(claims), ante)
    _remember(toks, t, state, focus, cur)
    claims.sort(key=lambda x: x.pos.at == _SKIP)
    return claims
