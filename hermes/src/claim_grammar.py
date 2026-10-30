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
          "которого": ("AG", "m"), "которую": ("A", "f"), "которым": ("I", "m"), "которой": ("GDIP", "f")}

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
     + r"|без\s+защиты|undefended|unprotected"),
    ("UNDEF_A", r"(?:никто|ничто|ничего|ничем|nothing|nobody)\s+(?:(?:ее|его|их|it)\s+)?(?:не\s+)?"
     r"(?:защища\w*|прикрыва\w*|defends|protects)"),
    ("HOLD", r"держ(?:ит|ат|ал\w*)\s+под\s+(?:ударом|боем|прицелом|контролем)|бер(?:ет|ут)\s+под\s+контроль|"
     r"брал\w*\s+под\s+контроль|взял\w*\s+под\s+контроль"),
    ("PASS_ATT", r"под\s+(?:ударом|боем|атакой)|атакован[аоы]?" + E + r"|(?:is|are)\s+attacked|under\s+attack"),
    ("CTRL_G", r"под\s+контролем"),
    ("CTRL_I", r"прострелен[аоы]?" + E + r"|простреливаем\w*"),
    ("PASS_DEF", r"защищ[её]н[аоы]?" + E + r"|прикрыт[аоы]?" + E + r"|под\s+защитой|поддержан[аоы]?" + E
     + r"|(?:is|are)\s+(?:defended|protected)"),
    ("PASS_PIN", r"связан[аоы]?" + E + r"|(?:is|are)\s+pinned"),
    ("PIN", r"связыва\w*|связал\w*|pins|pinning"),
    ("PIN_N", r"связк\w*|pin" + E),
    ("LOCK", r"заперт\w*|запер(?:ла|ли|л)?" + E + r"|запира\w*|перекры\w*|загород\w*|загоражива\w*"),
    ("SOFT", r"смотр(?:ит|ят|ел\w*)\s+(?:на|в)|целит\w*|целя\w*|нацел\w*|дав(?:ит|ят|ил\w*|ить)\s+(?:на|по)|"
             r"давлени\w*\s+на|eyes|aims?\s+at|press(?:es|ing)?\s+on"),
    ("CHASE", r"отгоня\w*|отгон(?:ит|ишь|ят|я|ять)|отогна\w*|прогоня\w*|прогна\w*|выгоня\w*|kicks?|chases?|chasing"),
    ("THREAT", r"гроз(?:ит|ят|ил\w*)|угрожа\w*|threatens?"),
    ("CAPW", r"возьм\w*|заберут|забирают|бьют|бьет|бьешь|берут|берет|берешь|забирает|забираешь"),
    ("ATT", r"бь[её]т|бьют|бил[аи]?|бить|атакует|атакуют|атакуя|атаковал\w*|атаковать|напада\w*|напал\w*|напав|"
            r"нападет|нападут|с\s+ударом\s+по|с\s+(?:нападением|атакой)\s+на|attacks?|attacking|hits"),
    ("DEF", r"защища\w*|защитит\w*|защитил\w*|защитить|прикрыва\w*|прикрыл\w*|поддержива\w*|поддерж(?:ит|ал\w*|ать)|"
            r"подкреп\w*|охраня\w*|defends?|defending|protects?|guards?|(?:вста[её]т|встал\w*)\s+на\s+защиту|"
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
    r"упорн\w*\s+защит\w*|нет\s+защиты|"
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
_MOVE_CUE = re.compile(W + r"(?:лучше|ход\w*|сыграй\w*|играй\w*|играем|ответили|ответил[аи]?|ответ|ответь|после|через|"
                       r"продолжени\w*|начни\s+с|начинай\s+с|идея|отвечай|пошли|пошел|сделали|сделал|play|after|move)"
                       r"\s*[:—–-]?\s*$")
_SEP = re.compile(r"[.;:!?()\n]|\s[—–]\s|,\s*(?:но|а|зато|поэтому|потому\s+что|так\s+что|чтобы|хотя|что|если|когда|"
                  r"but|so|because|while|if|when)" + E + r"|" + W + r"потому,?\s+что" + E + r"|" + W + r"так\s+как" + E)
_UNPARSED_MOVE = re.compile(
    W + r"(?:ид[её]т|идти|пойд[её]т|вста[её]т|встанет|уходит|уйти|уйд[её]т|уш[её]л|ушла|отходит|отойти|отойд[её]т|"
    r"отступа\w*|отступит|прыгает|прыгнет|переходит|перейд[её]т|выходит|выйдет|входит|войд[её]т|заходит|зайд[её]т|"
    r"берет|берут|взять|возьм[её]т|забирает|забрать|заберет|съест|бь[её]т\s+(?:с\s+шахом\s+)?на|бить\s+на|ходит|"
    r"сделает\s+ход|пойдет|врыва\w+|ворвал\w*|ворв[её]тся|вторга\w+|вторгнет\w*|переводит\w*|перевед[её]т\w*|"
    r"приходит|прид[её]т|подходит|подойд[её]т|бросается|бросит\w*|goes|moves|takes|captures|retreats|jumps)" + E)
_THREAT_GOV = re.compile(W + r"(?:гроз\w*|угро\w*|threat\w*|иде[яюи]|хоч\w*|хотят|готов\w*|планиру\w*|собира\w*|"
                         r"мечта\w*)\s*[:—–-]?\s*$")
_GENERIC_EN = re.compile(r"\b(?:a|an|any|every|each)\s+(?:\w+\s+)?(?:knight|bishop|rook|queen|king|pawn|piece)s?\b", re.I)
_MOTION = (r"(?:ид[её]т|пойд[её]т|вста[её]т|встал[аи]?|уходит|уш[её]л|ушла|отходит|отош[её]л|отошла|отступает|"
           r"отступил[аи]?|прыгает|прыгнул[аи]?|переходит|перешел|перешла|выходит|вышел|вышла|заходит|заш[её]л|зашла|"
           r"прыгнет|встанет|поднимается|поднял(?:ся|ась)|спускается|спустил(?:ся|ась)|возвращается|вернул(?:ся|ась)|"
           r"врывается|ворвал(?:ся|ась)|вторгается|вторгся|вторглась|приходит|пришел|пришла|подходит|подошел|подошла|"
           r"lands|goes|jumps|moves)")
_MOTION_TO = re.compile(rf"(?P<p>{_PIECE_ALT}|он|она){E}\s+(?:\S+\s+)?(?P<v>{_MOTION})\s+(?:на|в|to|on)\s+"
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
            toks.append(Tok("MOVE", m.start("b"), m.end("b"), m.group(0), san=f"@{_LETTER[pt]}:{m.group('b')}", ptype=pt,
                            span=(m.start(), m.end()), told=bool(re.search(r"(?:л|ла|ли|лся|лась)$", m.group("v")))))
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
    for m in _REL_RE.finditer(low):
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
            toks.append(Tok("PIECE", start, end, w, ptype=pt, cases="".join(sorted(cs)), gender=_gender(w)))
        elif w in _PRON:
            cs, g = _PRON[w]
            tk = Tok("PRON", start, end, w, cases=cs, gender=g)
            sm = re.match(r"\s+(?:уже\s+|теперь\s+|сейчас\s+)?(?:на|on)\s+([a-h][1-8])(?![0-9])", low[end:end + 20])
            if sm and "N" in cs:  # «он на f6 ничем не прикрыт»: the square the pronoun's piece stands on
                tk.sq = chess.parse_square(sm.group(1))
            toks.append(tk)
        elif w in _WHICH:
            cs, g = _WHICH[w]
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
        if m:
            tk.sq = chess.parse_square(m.group(m.lastindex))
            tk.from_sq = bool(m.groupdict().get("prep") in ("с", "со", "из", "from"))
            for o in toks:
                if o.kind == "SQ" and o.start == tk.end + m.start(m.lastindex):
                    o.kind = "BOUND"
        else:
            m = re.search(r"(?:на|on)\s+([a-h][1-8])\s+(?:\w+\s+){0,2}(?:сидит|стоит|стоят|находится|sits|stands)\s+(?:\w+\s+)?$",
                          low[max(0, tk.start - 40):tk.start])
            if m:
                tk.sq = chess.parse_square(m.group(1))
            elif "N" in tk.cases:
                # «С h3 белый король берёт под контроль g5»: the square it acts from, before it
                m = re.search(r"(?:^|[,:—–]\s*|^\W*)(с|со|от|from|на)\s+(?:пол[яе]\s+)?([a-h][1-8])\s+(?:\w+\s+){0,2}$",
                              low[max(0, tk.start - 30):tk.start])
                if m and not any(o.kind in ("PIECE", "MOVE", "REL") and o.end <= tk.start and o.start >= tk.start - 30 for o in toks):
                    tk.sq, tk.from_sq = chess.parse_square(m.group(2)), m.group(1) != "на"
                    for o in toks:
                        if o.kind == "SQ" and o.start == max(0, tk.start - 30) + m.start(2):
                            o.kind = "BOUND"
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
            if rx.search(prev):
                tk.owner = val
        if tk.owner is None and j > 0 and toks[j - 1].kind == "POSS" and tk.start - toks[j - 1].end <= 20:
            tk.owner = "opp"  # «их пешку d4», «его пешка e5»: the other side's
        if tk.sq is None and tk.ptype:
            same = {o.sq for o in toks if o.kind == "PIECE" and o is not tk and o.ptype == tk.ptype and o.sq is not None
                    and o.start < tk.start and (o.owner is None or tk.owner is None or o.owner == tk.owner)}
            if len(same) == 1:
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


_PASSIVE = ("PASS_ATT", "PASS_DEF", "UNDEF", "PASS_PIN", "CTRL_G", "CTRL_I")


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
            distinct = {key(r): r for r, _ in cands}
            r = None
            if last_move is not None and "N" in t.cases and 0 <= t.start - last_move.end <= 3:
                r = last_move_ref  # «Bb5+ он и слона уводит …»: the pronoun is the move's piece
            elif len(distinct) == 1 and (noun_at.get(g, -1) < last_piece_at[g] if cur.get(g) else g not in noun_at):
                r = next(iter(distinct.values()))
            out[id(t)] = r
            if r is not None:
                cur.setdefault(g, []).append((r, "N" in t.cases))
                last_piece_at[g] = t.start
        elif t.kind == "WHICH":
            r = None
            if last_noun is not None and t.start - last_noun[1] <= 4 and \
                    (last_noun[0].what == "square" or last_noun[2] == t.gender or t.gender == "p"):
                r = last_noun[0]
            out[id(t)] = r
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
    r"black'?s?|enemy|opponent'?s|надежно|прочно|спокойно|просто|пол[еяю]|пункт\w*|клетк\w*)\s+)*$")
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
    for r in [t for t in toks if t.kind == "REL"]:
        ca, cb = next(((a, b) for a, b in clauses if a <= r.start < b), (0, len(text)))
        # a list announced before a colon continues after it: «атакует две фигуры: пешку h6 и ладью»
        if low[cb - 1:cb] == ":" and re.search(W + r"(?:две|два|три|обе|оба|обоих|двух|two|three|both)\s+\w+\s*:$", low[ca:cb]):
            cb = next((b for a, b in clauses if a == cb), cb)
        inside = [t for t in toks if ca <= t.start < cb and t is not r and t.kind != "SEP"]
        before = [t for t in inside if t.end <= r.start]
        after = [t for t in inside if t.start >= r.end]
        neg = any(t.kind == "NEG" and 0 <= r.start - t.end <= 12 and not any(o.kind == "REL" and t.end <= o.start < r.start for o in toks)
                  for t in before) and r.rel not in ("UNDEF", "UNDEF_A")
        if r.rel not in ("UNDEF", "UNDEF_A"):
            subj = [t for t in before if t.kind in ("PIECE", "PRON", "WHICH", "MOVE", "SQ", "SIDE")]
            neg = neg or any(t.kind == "NEG" and (not subj or t.start > subj[-1].start)
                             and not any(o.kind == "REL" and t.end <= o.start < r.start for o in toks) for t in before)
        verb = r.text.split()[0]
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
            else "present")
        unresolved = []
        inverted_agent = False

        def add(rel, agent, pats, **kw):
            if intent and (agent is None or agent.what != "move"):
                return  # «хочешь отогнать коня» is checkable only as the purpose of a named move
            claims.append(_Raw(rel, agent, [p for p in pats if p is not None], neg, tense, question, r.start, (ca, cb),
                               verb=verb, modal=modal and rel != "UNDEF", unresolved=bool(unresolved), end=r.end,
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
            if r.rel in ("UNDEF", "UNDEF_A") and re.search(W + r"(?:кроме|except|but|только|only)" + E, low[r.end:cb]):
                continue
            if r.rel == "UNDEF_A":
                acc = [t for t in inside if t.kind == "PRON" and "A" in t.cases] + \
                      [t for t in inside if t.kind == "PIECE" and "A" in t.cases]
                pat = pron(acc[0]) if acc and acc[0].kind == "PRON" else (_ref(acc[0]) if acc else None)
                add("UNDEF", None, [pat])
                continue
            for t in before[::-1]:
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
                # «под ударом остаются и пешка h2, и ладья f1»: the list right after (not «…, и её защищает пешка g7»)
                pats = []
                last = r.end
                for t in after:
                    if t.kind in ("BOUND", "OWNER", "NEG", "NOUN"):
                        last = t.end if t.kind == "BOUND" else last
                        continue
                    gap = low[last:t.start]
                    if not (_LIST_GAP.match(gap) or (not pats and _FIRST_GAP.match(re.sub(W + r"(?:остают\w*|оста[её]тся|оказ\w+|сразу|одна|один|два|две)" + E, " ", gap)))):
                        break
                    if t.kind == "PIECE" and t.cases in ("N", "NA") and t.sq is not None:
                        pats.append(_ref(t))
                    elif t.kind == "SQ" and not t.move_cue and not t.route and not pats:
                        pats.append(_ref(t))
                    else:
                        break
                    last = t.end
            want = {"PASS_ATT": "G", "CTRL_G": "G", "CTRL_I": "I"}.get(r.rel, "I")
            ag = [t for t in after if t.kind == "PIECE" and want in t.cases and t.start - r.end < 30
                  and ("N" not in t.cases or t.sq is not None)
                  and not (r.rel == "PASS_PIN" and t.ptype == chess.KING)
                  and not re.search(r"(?:^|\s)(?:с|со|to)\s+(?:\w+\s+)?$", low[r.end:t.start])]
            to = None
            if r.rel == "PASS_PIN":  # «связана твоим слоном d4 с королём g1»: the piece behind
                bk = [t for t in after if t.kind == "PIECE" and "I" in t.cases and t.sq is not None
                      and re.search(r"(?:^|\s)(?:с|со)\s+(?:\w+\s+)?$", low[r.end:t.start])]
                to = _ref(bk[0]) if bk else None
            if r.rel == "PASS_ATT" and re.match(r"\s*не\s+(?:стоит|стоят|находится|оказыва\w+|оста[её]тся)" + E, low[r.end:r.end + 30]):
                neg = True  # «под боем не стоит»
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
            return (t.kind == "PIECE" and "N" in t.cases and not re.search(r"(?:\s|^)(?:с|со)\s*$", low[max(0, t.start - 4):t.start])) or \
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
        cand = [t for t in before if is_agent(t)]
        agent_t = cand[-1] if cand else None
        acc_before = [t for t in before if (t.kind in ("PIECE", "PRON") and "A" in t.cases and "N" not in t.cases)
                      and (agent_t is None or t.start > agent_t.start)]
        n_after = next((t for t in after if t.kind == "PIECE" and t.cases in ("N",) and t.start - r.end < 25
                        and _FIRST_GAP.match(re.sub(r"\b(?:и|both)\b", " ", low[r.end:t.start])) and "," not in low[r.end:t.start]), None)
        if n_after is not None and (agent_t is None or agent_t.kind == "SIDE" or acc_before):
            agent_t = n_after
        elif acc_before and (agent_t is None or agent_t.kind == "SIDE"):
            # «её прикрывают d6 и конь c6»: the object first, the agents after the verb — a bare square names one
            first = next((t for t in after if t.kind in ("PIECE", "SQ") and t.start - r.end < 25), None)
            if first is not None and _FIRST_GAP.match(low[r.end:first.start]) and \
                    ((first.kind == "PIECE" and first.cases == "N") or (first.kind == "SQ" and not first.move_cue and not first.route)):
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
        if r.rel == "TAKE" and (agent is None or agent.what == "side"):
            add("TAKE", agent, [])  # «Чёрные забирают пешку e4»: a capture we cannot place — what follows is unknown
            continue
        if agent is None or agent.what == "side":
            continue
        pats, last = [], r.end
        inverted = agent_t is not None and agent_t.start > r.start
        for t in ([] if inverted else after):
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
                if t.kind == "PRON" and "A" in t.cases:
                    pats.append(pron(t))
                    break
        joint = agent_t is not None and agent_t.kind == "PIECE" and bool(re.match(
            r"\s*(?:[a-h][1-8]\s+)?(?:вместе\s+)?(?:с|со)\s+(?:\w+\s+)?(?:" + _PIECE_ALT + r")" + E, low[agent_t.end:agent_t.end + 40])) and \
            any(t.kind == "PIECE" and "I" in t.cases and agent_t.end < t.start <= agent_t.end + 40 for t in toks)
        if r.rel == "PIN" and to is None:  # «ладья e1 связывает коня e6 с ладьёй e8»: the piece behind
            bk = [t for t in after if t.kind == "PIECE" and "I" in t.cases and t.sq is not None
                  and re.search(r"(?:^|\s)(?:с|со)\s+(?:\w+\s+)?$", low[r.end:t.start])]
            to = _ref(bk[0]) if bk else None
        own_sq = agent.sq if agent.what == "piece" else (
            chess.parse_square(_move_ref(agent.move).to) if agent.what == "move" and _move_ref(agent.move).to else None)
        if own_sq is not None:  # «слона на g7, откуда он будет давить», «после ...exd5 — давление на d5»: not its own target
            pats = [p for p in pats if p is None or p.sq != own_sq]
        if not [p for p in pats if p is not None] and not unresolved:
            continue
        inverted_agent = inverted
        add(r.rel, agent, pats, skip="joint" if joint else "", to=to)  # two pieces together: neither alone is claimed
        if not inverted and agent_t is not None and agent_t.kind == "PIECE" and not joint:
            k = toks.index(agent_t) - 1
            nxt = agent_t.start
            while k >= 0 and toks[k].kind in ("BOUND", "OWNER", "SIDE"):
                nxt = min(nxt, toks[k].start) if toks[k].kind != "BOUND" else nxt
                k -= 1
            while k >= 0 and toks[k].kind == "PIECE" and "N" in toks[k].cases and toks[k].start >= ca and \
                    re.fullmatch(r"\s*(?:(?:на\s+)?[a-h][1-8]\s*)?(?:,|и|а\s+также)\s*", low[toks[k].end:nxt]):
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


def _position(c: _Raw, text: str, toks: list, told_capture: Optional[tuple]) -> Pos:
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
    if tense == "future" and _PLAN_CUE.search(low[:c.end]) and c.rel in ("ATT", "SOFT", "HOLD") and \
            c.agent is not None and c.agent.what == "piece" and c.agent.sq is not None and c.agent.ptype:
        return Pos(at="plan", tense=tense)  # «фианкетто: слон с g2 будет бить по e6» — the geometry of the set-up
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
        if any(a <= m.start() < b for a, b in spans) or \
                any(t.kind == "MOVE" and not t.threat and m.end() <= t.start <= m.end() + 30 for t in toks):
            continue
        # «рокировка …: король уходит» — the motion of a move the sentence already told
        w = re.search(rf"({_PIECE_ALT})\s+(?:\w+\s+)?$", low[max(0, m.start() - 30):m.start()])
        if w and _LETTER.get(_P[w.group(1)][0]) in movers and any(t.start < m.start() for t in moves_seq):
            continue
        return Pos(at=_SKIP, tense=tense, skip_reason="unparsed move")
    seq = [t if t.kind == "MOVE" else Tok("MOVE", t.start, t.end, t.text, san=t.text, told=t.told) for t in moves_seq]
    seq = [t for t in seq if not (len(t.san) == 2 and any(o is not t and len(o.san) == 4 and o.san[2:] == t.san for o in seq))]
    seq = [t for i, t in enumerate(seq) if not (i and not t.ptype and re.fullmatch(r"[a-h][1-8][a-h][1-8]", t.san)
                                                 and _move_ref(seq[i - 1]).to == t.san[:2])]
    # «Nc3 или Nd2»: alternatives, not a line
    steps: list = []
    for t in seq:
        mr = _move_ref(t)
        if steps and re.fullmatch(r"\s*(?:или|or|/|либо)\s*(?:\S+\s+)?", low[steps[-1][-1][0].end:t.start]):
            steps[-1].append((t, mr))
        elif steps and len(steps[-1]) == 1 and _same_move(steps[-1][0][1], mr):
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
                         question=question, span=span)
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
                                 pos=pos, question=question, span=span)
            elif rel == "PASS_DEF":  # «пешка e5 защищена» = not undefended
                return Claim("undefended", None, tuple(r for r in map(_out_ref, objs) if r is not None), neg=not c.neg,
                             pos=pos, question=question, span=span)
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
        if len(mine) == 1 and not other and mine[0].to not in targets:  # («Nc3 или Nd2 защищает»: the mover of each alternative — left to the scene)
            subj = _R("piece", subj.ptype, chess.parse_square(mine[0].to), subj.owner, text=subj.text)
    cap = told_capture[1] if told_capture is not None and told_capture[0] < c.pos else None
    if cap is not None and cap in pos.moves and subj is not None and subj.what == "piece" and \
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
    return Claim(rel_name, s, tuple(r for r in map(_out_ref, objs) if r is not None), to=_out_ref(to), neg=c.neg,
                 question=question, pos=pos, span=span)


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
    if not has_claim_word and not re.search(rf"{W}(?:{_PIECE_ALT}){E}|[a-h][1-8]", low):
        state[SQUARES_KEY] = ()
        return []
    toks = tokenize(t)
    focus = _focus_from(state)
    focus["_squares"] = state.get(SQUARES_KEY) or ()
    _, cur = _antecedents(toks, focus, low)
    claims: list = []
    if has_claim_word:
        idioms = [(m.start(), m.end()) for m in _IDIOM.finditer(low)]
        raws = [c for c in bind(t, toks, focus) if not any(a <= c.pos < b for a, b in idioms)]
        told = None
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
            pos = _position(c, t, toks, told)
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
    _remember(toks, t, state, focus, cur)
    claims.sort(key=lambda x: x.pos.at == _SKIP)
    return claims
