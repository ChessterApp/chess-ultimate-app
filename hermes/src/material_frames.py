"""The material balance a clause claims, read from its parts (review-miss2 01.11).

The patterns in src/answer_check (_MATERIAL, _MAT_FRAMES) read «у белых на пешку больше», «впереди на ладью»,
«лишняя пешка», «материал равный» in their own word orders. The same claims said otherwise — «Белые опережают тебя на
ладью», «У тебя минус ладья», «По материалу белые на ладью богаче», «Разница в материале — ферзь», «Сейчас пешек
поровну», «Материально позиция равная», «По материалу у сторон паритет», «Чёрные впереди по материалу» — were not.
Here a clause is read as

  EQUAL   a material anchor (материал, материально, по материалу, по очкам; or a unit in the plural genitive:
          «пешек», «фигур») + an equality word (равн-, поровну, одинаков-, паритет, сравнял-, баланс, равенств-), in any
          order; a hedge («почти», «примерно») widens it to 2 points; a unit anchor («пешек поровну») compares that unit;
  LEAD    a side (a subject, «у X», a genitive after a lead noun, a possessive person) + a comparative of more
          (впереди, больше, опережа-, сильнее, богаче, плюс, перевес, преимуществ-, лишн-) or of less (позади, меньше,
          отста-, уступа-, минус, беднее, слабее) + the amount (на <unit>, в <unit>, «— <unit>», плюс N); without an
          amount only with a material anchor, judged by its sign;
  DIFF    «разница в материале — ферзь» (no side): the size of the balance.

Unjudged: a question, a condition, the future, a denial, a flank or centre majority, an evaluation in pawns.

Rebuilt 02.11 (verify1102 B1: six kinds of true sentence were cut). The amount is a NOUN LIST read to its end («лишние
слон, конь и пешка», «впереди на ферзя, слона и двух коней»), summed in points; a list the reader cannot finish leaves
the claim unjudged. An amount after «больше/меньше/впереди…» needs its «на» («больше на пешку»): «больше четырёх пешек»
is "more than four", not a lead. Idioms carry no material word (mask_idioms: «всё равно», «плюс ко всему», «лишний
раз»), «плюс/минус» with no side before it is a conjunction or a noun («Плюс слон уходит…»), a subordinate clause
(«где», «который», «что», «чтобы») is a clause of its own, «N пешек перевеса» is an evaluation, and «после …», «если …»,
«при …» in the claim's clause make it a condition (a move written after «после» is left to the caller, which knows
the game's record).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_W = r"(?<![а-яёa-z])"
_E = r"(?![а-яёa-z])"
_POINTS = {"пешк": 1, "пешек": 1, "кон": 3, "слон": 3, "ладь": 5, "ладей": 5, "ферз": 9, "фигур": 3, "качеств": 2}
_UNIT = r"(?:пешк\w*|пешек|кон(?:ь|я|ем|ю|е|и|ей|ям|ями)|слон\w*|ладь\w*|ладей|ферз\w*|фигур\w*|качеств\w*)"
_NUMW = {"одну": 1, "одна": 1, "один": 1, "одного": 1, "одной": 1, "одним": 1, "две": 2, "два": 2, "двух": 2, "двумя": 2,
         "пару": 2, "пара": 2, "пары": 2, "три": 3, "трех": 3, "тремя": 3, "четыре": 4, "четырех": 4, "пять": 5, "пяти": 5,
         "шесть": 6, "шести": 6, "семь": 7, "семи": 7, "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9, "десять": 10}
_NUM = r"(?:\d{1,2}|" + "|".join(sorted(_NUMW, key=len, reverse=True)) + r")"
# One item of an amount: «две пешки», «целую ладью», «двух коней»; a number of points: «3 очка», «семь единиц», or a
# bare number that ends the phrase («на 3.»). A bare number before another noun («на два хода») is no amount.
_ITEM = re.compile(r"(?:(?P<n>" + _NUM + r")\s+)?(?:(?:лишн\w+|цел\w+)\s+)?(?P<u>" + _UNIT + r")" + _E)
_PTS = re.compile(r"(?P<pts>" + _NUM + r")\s*(?:(?:очк\w*|балл\w*|единиц\w*)" + _E + r"|(?=\s*(?:[,.;:!)—–-]|$)))")
_PREP = re.compile(r"(?:на|в|во)\s+")
_MOD = re.compile(r"(?:целую|целого|целых|всего|лишь|только|ровно)\s+")
# Between two items of a list: «, », « и », «, и », « плюс », « + »
_JOIN = re.compile(r"\s*,\s*(?:(?:и|плюс)\s+)?|\s+(?:и|плюс)\s+|\s*\+\s*")
# A unit in the nominative singular: after an oblique list («на пешку и конь …») a new subject, not an item
_NOM_SG = re.compile(r"(?:пешка|конь|слон|ладья|ферзь|фигура)$")
# The comparatives whose amount is said with «на»: «больше на пешку», «впереди на ладью» (not «больше четырёх пешек»)
_NEEDS_NA = re.compile(r"(?:впереди|больше|опережа\w*|обгоня\w*|сильнее|богаче|позади|меньше|отста\w*|уступа\w*|беднее|"
                       r"слабее)$")
_ANCHOR = re.compile(_W + r"(?:материал\w*|по\s+очкам|в\s+очках)" + _E)
_UNIT_PLURAL = re.compile(_W + r"(?P<u>пешек|фигур|коней|слонов|ладей|ферзей)" + _E)
_EQUAL = re.compile(_W + r"(?:равн\w*|равен|равна|равно|поровну|одинаков\w*|паритет\w*|сравнял\w*|сравня\w*|баланс\w*|"
                    r"равенств\w*|равновеси\w*|вровень)" + _E)
_HEDGE = re.compile(_W + r"(?:почти|примерно|практически|приблизительно|фактически|более-менее|плюс-минус|около|"
                    r"в\s+целом|формально|условно|по\s+сути)" + _E)
_MORE = re.compile(_W + r"(?:впереди|больше|опережа\w*|обгоня\w*|сильнее|богаче|плюс|в\s+плюсе|перевес\w*|преимуществ\w*|"
                   r"лишн\w+|выигрыва\w*\s+по\s+материалу)" + _E)
_LESS = re.compile(_W + r"(?:позади|меньше|отста\w*|уступа\w*|минус|в\s+минусе|беднее|слабее|проигрыва\w*\s+по\s+материалу)" + _E)
_DIFF = re.compile(_W + r"(?:разниц\w+|перевес\w*|преимуществ\w*)\s+(?:в\s+материале|по\s+материалу|материальн\w*)?" + _E)
_SIDE = re.compile(_W + r"(?:(?P<pre>у|от|чем|за|против|для|с|к|по)\s+)?(?P<s>белы[ехм]|белыми|черны[ехм]|черными|ты|тебя|тебе|"
                   r"вы|вас|вам|я|меня|мне|соперник\w*|противник\w*)" + _E)
_NOT = re.compile(_W + r"(?:не|ни|нет|без|если|бы|когда|станет|станут|будет|будут|окажется|окажутся|получит\w*|чтобы|"
                  r"может|могут|можно|должн\w*|нужно|надо|подума\w*|посмотр\w*|как(?:ой|ая|ое|ие|ую)|котор\w+|фланг\w*|крыл\w*|центре|большинств\w*|оценк\w*|движ\w*|"
                  r"компьютер\w*|позиционн\w*|в\s+пешках|за\s+(?:пешк|кон|слон|ладь|ферз|фигур)\w*|против|"
                  # an engine score: «больше четырёх пешек перевеса», «две пешки преимущества» (verify1102 B1)
                  r"(?:пешк\w*|пешек|очк\w*|единиц\w*)\s+(?:перевеса|преимущества)|при\s+(?:правильн|точн|лучш|люб|ход|размен|взяти)\w*|"
                  # the bishop pair, not a lead in material
                  r"двух\s+слонов|двумя\s+слонами|пар\w+\s+слонов|слонов\w*\s+пар\w+)" + _E)
_CLAUSE = re.compile(r"[.!?;:]|,\s*(?:но|а|зато|хотя|однако|и|причем|поэтому|так\s+что|тогда|пока|если|когда|чтобы|"
                     # a subordinate clause is a clause of its own: «…с поля, где чёрные могли его разменять»
                     r"где|куда|откуда|котор\w+|что|потому|так\s+как|ведь|раз|пусть)" + _E +
                     r"|\s(?:но|а|зато)\s")
# Idioms that carry a material word and say no material (verify1102 B1): «всё равно» (anyway), «равно как», «плюс ко
# всему» (besides), «лишний раз» (once more), «тем более», «более того». Masked with spaces: the offsets stay.
_IDIOM = re.compile(_W + r"(?:вс[её][\s-]+равно|равно\s+как|плюс\s+(?:ко\s+всему|к\s+тому|к\s+этому|ещ[её])|"
                    r"лишн(?:ий|его|ему|им)\s+раз\w*|тем\s+более|более\s+того|в\s+равной\s+(?:мере|степени))" + _E,
                    re.IGNORECASE)
# A condition in the claim's clause: «после других ходов», «если …», «в случае …». «после» with a move written right
# after it is left to the caller (the game's record may be the board now).
_COND = re.compile(_W + r"(?:после|в\s+случае|при\s+условии)" + _E)
_MOVE_NEXT = re.compile(r"\s*(?:\d{1,3}\s?\.|[kqrbnкфлс]?[a-h]?[1-8]?x?[a-h][1-8]|o-o)", re.IGNORECASE)


@dataclass
class MatClaim:
    kind: str  # equal | lead | diff
    who: str = ""  # lead: 'W' 'B' 'S' 'E'
    more: bool = True
    points: Optional[int] = None  # the amount in points (None: only the direction)
    unit: str = ""  # equal of one unit («пешек поровну»): the unit's stem
    hedged: bool = False
    at: int = 0
    end: int = 0
    span: str = ""
    pos: int = 0  # where the claim itself begins in the text (its side or predicate): conditions before it count
    atleast: bool = False  # «лишние X и Y»: at least that much (more extras may be left unnamed)


def _num(word: Optional[str]) -> Optional[int]:
    if not word:
        return 1
    return _NUMW.get(word, int(word) if word.isdigit() else None)


def _item_points(m) -> Optional[int]:
    n = _num(m["n"])
    p = next((v for k, v in _POINTS.items() if m["u"].startswith(k)), None)
    return None if p is None or n is None else n * p


@dataclass
class _Amount:
    points: Optional[int]
    start: int
    end: int
    prep: bool  # said with «на» / «в»
    partial: bool  # a list the reader could not finish: the claim is left unjudged


def mask_idioms(text: str) -> str:
    """*text* with every idiom of _IDIOM blanked out (same length)."""
    return _IDIOM.sub(lambda m: " " * len(m.group(0)), text or "")


def _amount(low: str, pos: int, limit: int) -> Optional[_Amount]:
    """The amount that starts at *pos* of *low* (within the clause ending at *limit*): one item or a list of them
    («ферзя, слона и двух коней»), in points. A list that goes on past what was read — another item after a comma, or
    after the clause boundary («на ферзя, слона, и двух коней») — is partial."""
    i = re.compile(r"[\s—–:=-]*").match(low, pos).end()
    start, prep = i, False
    p = _PREP.match(low, i)
    if p:
        prep, i = True, p.end()
    md = _MOD.match(low, i)
    if md:
        i = md.end()
    first = _ITEM.match(low, i, limit)
    if first is None:
        pt = _PTS.match(low, i, limit)
        if pt is None:
            return None
        return _Amount(_num(pt["pts"]), start, pt.end(), prep, False)
    items, j = [first], first.end()
    oblique = prep or not _NOM_SG.search(first["u"])
    while True:
        jm = _JOIN.match(low, j, limit)
        if jm is None:
            break
        nx = _ITEM.match(low, jm.end(), limit)
        if nx is None:
            break
        if oblique and _NOM_SG.search(nx["u"]):
            break  # «на пешку и конь у них активнее»: a new subject, not an item
        items.append(nx)
        j = nx.end()
    pts = [_item_points(x) for x in items]
    total = None if any(x is None for x in pts) else sum(pts)
    # what follows the last item read, past the clause too: one more item of the list means it was not read whole
    rest = re.match(r"\s*(?:,\s*)?(?:(?:и|плюс|\+)\s+)?(?:" + _NUM + r"\s+)?(?P<u>" + _UNIT + r")" + _E, low[j:])
    partial = rest is not None and not (oblique and _NOM_SG.search(rest["u"]))
    return _Amount(total, start, j, prep, partial)


def _who(word: str) -> str:
    w = word.lower()
    if w.startswith("бел"):
        return "W"
    if w.startswith("черн"):
        return "B"
    if w in ("ты", "тебя", "тебе", "вы", "вас", "вам"):
        return "S"
    return "E"


def _clauses(text: str) -> list:
    out, a = [], 0
    for m in _CLAUSE.finditer(text):
        out.append((a, m.start()))
        a = m.end()
    out.append((a, len(text)))
    return [(x, y) for x, y in out if y > x]


def read(text: str) -> list:
    """The material claims of *text* (lowercased, «ё» as «е»)."""
    low = mask_idioms((text or "").lower().replace("ё", "е"))
    out = []
    if "?" in low:
        return out
    for a, b in _clauses(low):
        cl = low[a:b]
        if _NOT.search(cl):
            continue
        anchor = _ANCHOR.search(cl)
        eq = _EQUAL.search(cl)
        if eq:
            up = _UNIT_PLURAL.search(cl)
            if (anchor or up) and not _conditional(cl, min(x.start() for x in (anchor or up, eq))):
                out.append(MatClaim("equal", unit=(up["u"] if up and not anchor else ""), hedged=bool(_HEDGE.search(cl)),
                                    at=a, end=b, span=cl.strip(), pos=a + min(x.start() for x in (anchor or up, eq))))
            continue
        more, less = _MORE.search(cl), _LESS.search(cl)
        pred = more or less
        if pred is None:
            dm = _DIFF.search(cl)
            if dm and anchor:
                am = _amount(low, a + dm.end(), b)
                if am is not None and am.points and not am.partial and not _SIDE.search(cl) and \
                        not _conditional(cl, dm.start()):
                    out.append(MatClaim("diff", points=am.points, at=a, end=b, span=cl.strip(), pos=a + dm.start()))
            continue
        if more and less:
            continue
        sides = [s for s in _SIDE.finditer(cl) if s["pre"] in (None, "у")
                 and not (s["pre"] is None and s["s"] in ("тебе", "вам", "мне", "белым", "черным"))]  # a dative is no owner
        sides = [s for s in sides if not (s["s"] in ("тебя", "вас", "меня") and s["pre"] is None)]  # «опережают тебя»: the object
        if not sides:
            continue
        word = pred.group(0)
        if word in ("плюс", "минус") and not any(s.start() < pred.start() for s in sides):
            continue  # «Плюс слон уходит…», «Минус этого хода — …»: a conjunction or a noun, not a side's lead
        side = min(sides, key=lambda s: abs(s.start() - pred.start()))
        pos = min(side.start(), pred.start())
        if _conditional(cl, pos):
            continue
        amount = _amount_after(low, a, b, pred)
        if amount is not None and _NEEDS_NA.search(word) and not amount.prep:
            amount = None  # «больше четырёх пешек»: more than four, not a lead of four
        if amount is None:
            amount = _amount_before(low, a, pred)
        if amount is not None and amount.partial:
            continue  # a list read only in part: unjudged
        pts = amount.points if amount is not None else None
        if pts is None and not anchor:
            continue  # «белые впереди», «чёрные сильнее»: no amount, no material word — maybe the evaluation
        if word.startswith("лишн") and pts is None:
            continue
        out.append(MatClaim("lead", who=_who(side["s"]), more=pred is more, points=pts, at=a, end=b, span=cl.strip(),
                            pos=a + pos, atleast=word.startswith("лишн")))
    return out


_GAP_AFTER = re.compile(r"(?:\s*(?:уже|сейчас|теперь|ровно|целых|всего|по\s+материалу|материально|у\s+\w+|тебя|вас|белых|"
                        r"черных|соперника|противника|[—–:-]))*")


def _amount_after(low: str, a: int, b: int, pred) -> Optional[_Amount]:
    """The amount right after the predicate (*pred* matched in the clause low[a:b]), past filler words («опережают
    тебя на ладью», «впереди — ладья»)."""
    gap = _GAP_AFTER.match(low, a + pred.end(), b)
    return _amount(low, gap.end(), b)


def _amount_before(low: str, a: int, pred) -> Optional[_Amount]:
    """The amount that ends right before the predicate: «на пешку больше», «на слона и пешку впереди», «пешкой меньше»
    (a bare «пешек больше» is a count, not a lead)."""
    head = low[a:a + pred.start()]
    for m in reversed(list(re.finditer(_W + r"на\s+", head))):
        am = _amount(head, m.start(), len(head))
        if am is not None and not head[am.end:].strip(" —–:-,"):
            return am
    ins = re.search(r"(?:(?P<n>" + _NUM + r")\s+)?(?P<u>(?:пешк|фигур|ладь|ферз|кон|слон|качеств)\w*(?:ой|ей|ем|ом))\s*$", head)
    if ins:
        return _Amount(_item_points(ins), ins.start(), ins.end(), True, False)
    return None


def _conditional(cl: str, pos: int = 0) -> bool:
    """A condition in the clause, before the claim («после других ходов у чёрных …») or after it («… после размена»).
    «после» with a move written right after it is the caller's: the game's record may lead to the board now."""
    return any(not _MOVE_NEXT.match(cl, m.end()) for m in _COND.finditer(cl))


def conditional(clause: str) -> bool:
    """*clause* (lowercased) names a condition — «после других ходов», «если …», «в случае …» — with no move written
    after «после»: a material claim in it is about another board (answer_check reads the rest of a claim's clause)."""
    return _conditional(clause.lower().replace("ё", "е"))
