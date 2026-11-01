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
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_W = r"(?<![а-яёa-z])"
_E = r"(?![а-яёa-z])"
_POINTS = {"пешк": 1, "пешек": 1, "кон": 3, "слон": 3, "ладь": 5, "ладей": 5, "ферз": 9, "фигур": 3, "качеств": 2}
_UNIT = r"(?:пешк\w*|пешек|кон(?:ь|я|ем|ю|е|и|ей|ям|ями)|слон\w*|ладь\w*|ладей|ферз\w*|фигур\w*|качеств\w*)"
_NUMW = {"одну": 1, "одна": 1, "один": 1, "одного": 1, "одной": 1, "две": 2, "два": 2, "двух": 2, "три": 3, "трех": 3,
         "четыре": 4, "четырех": 4, "пять": 5, "пяти": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10}
_NUM = r"(?:\d{1,2}|" + "|".join(_NUMW) + r")"
_AMOUNT = re.compile(r"(?:(?:на|в|во)\s+)?(?:(?:целую|целого|целых|всего|лишь|только|ровно)\s+)?(?:(?P<n>" + _NUM + r")\s+)?"
                     r"(?:(?:лишн\w+|целую|целого)\s+)?(?P<u>" + _UNIT + r")" + _E + r"|(?P<pts>" + _NUM + r")\s*(?:очк\w*|балл\w*|пешк\w*)?" + _E)
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
                  # the bishop pair, not a lead in material
                  r"двух\s+слонов|двумя\s+слонами|пар\w+\s+слонов|слонов\w*\s+пар\w+)" + _E)
_CLAUSE = re.compile(r"[.!?;:]|,\s*(?:но|а|зато|хотя|однако|и|причем|поэтому|так\s+что|тогда|пока|если|когда|чтобы)" + _E +
                     r"|\s(?:но|а|зато)\s")


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


def _points(m) -> Optional[int]:
    if m is None:
        return None
    if m["pts"]:
        return _NUMW.get(m["pts"], int(m["pts"]) if m["pts"].isdigit() else None)
    n = _NUMW.get(m["n"] or "", int(m["n"]) if (m["n"] or "").isdigit() else 1)
    u = m["u"]
    p = next((v for k, v in _POINTS.items() if u.startswith(k)), None)
    return None if p is None else n * p


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
    low = (text or "").lower().replace("ё", "е")
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
            if anchor or up:
                out.append(MatClaim("equal", unit=(up["u"] if up and not anchor else ""), hedged=bool(_HEDGE.search(cl)),
                                    at=a, end=b, span=cl.strip()))
            continue
        more, less = _MORE.search(cl), _LESS.search(cl)
        pred = more or less
        if pred is None:
            dm = _DIFF.search(cl)
            if dm and anchor:
                am = _AMOUNT.search(cl, dm.end())
                pts = _points(am)
                if pts and not _SIDE.search(cl):
                    out.append(MatClaim("diff", points=pts, at=a, end=b, span=cl.strip()))
            continue
        if more and less:
            continue
        sides = [s for s in _SIDE.finditer(cl) if s["pre"] in (None, "у")
                 and not (s["pre"] is None and s["s"] in ("тебе", "вам", "мне", "белым", "черным"))]  # a dative is no owner
        sides = [s for s in sides if not (s["s"] in ("тебя", "вас", "меня") and s["pre"] is None)]  # «опережают тебя»: the object
        if not sides:
            continue
        side = min(sides, key=lambda s: abs(s.start() - pred.start()))
        amount = _AMOUNT.search(cl, pred.end())
        if amount is not None and cl[pred.end():amount.start()].strip(" —–:-") and \
                not re.fullmatch(r"(?:\s*(?:уже|сейчас|теперь|ровно|целых|всего|на|по\s+материалу|материально|у\s+\w+|тебя|"
                                 r"вас|белых|черных|соперника|противника|лишн\w+|[—–:-]))*\s*", cl[pred.end():amount.start()]):
            amount = None
        if amount is None:
            before = re.search(r"(?:на\s+)?(?:" + _NUM + r"\s+)?" + _UNIT + r"\s*$", cl[:pred.start()])
            amount = _AMOUNT.match(cl, before.start()) if before else None
        pts = _points(amount)
        if pts is None and not anchor:
            continue  # «белые впереди», «чёрные сильнее»: no amount, no material word — maybe the evaluation
        if pred.group(0).startswith("лишн") and pts is None:
            continue
        out.append(MatClaim("lead", who=_who(side["s"]), more=pred is more, points=pts, at=a, end=b, span=cl.strip()))
    return out
