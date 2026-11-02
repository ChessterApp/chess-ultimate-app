"""Who took or gave up what, read from the parts of a clause (review-miss2 01.11).

The game-record detectors (student_capture, gave_up, trades) read their claims through closed patterns: a side, a past
verb, an accusative unit — in that order and in those forms. «Слона e7 съела твоя пешка», «Слон e7 был взят чёрной
пешкой», «Чёрные расстались с d-пешкой», «Отдав центральную пешку, чёрные …», «Ферзя белые пожертвовали за ладью» said
the same things and were not read. This module reads a clause by its parts instead:

  the predicate   a verb of TAKING (взять, забрать, побить, съесть, срубить, снять, уничтожить, выиграть + a unit …),
                  of LOSING (отдать, пожертвовать, потерять, зевнуть, подарить, уступить, сдать, лишиться, расстаться
                  с, остаться без, пропасть, погибнуть …) or of TRADING (разменять, обменять, променять), in the past,
                  active, passive (взят, отдана, потеряна), as a gerund (отдав, взяв), or as a noun frame (ценой,
                  жертва, взамен); a verb of PLAYING with a written move («Ход fxe7 сделал ты»);
  the arguments   by case, in any order — the subject (nominative: a side, a person, or a piece with its owner), the
                  object (accusative; genitive after «лишиться/без/ценой/жертва»; instrumental after «расстаться с»),
                  the instrument (instrumental: the capturing piece), the passive agent (instrumental), «у X» (the
                  owner of the unit taken), what came back («за», «в обмен на», «ради», «взамен», «получить»);
  the owner       of a piece: a possessive («твоя пешка» — the student's), a colour adjective, a genitive side after it
                  («пешка чёрных»), «свой» (the subject's), or «у X»;
  the number      «одну», «две», «всего одну», «больше ничего» (an exact count) or none (at least one).

Each clause becomes events — (kind 'take' | 'lose' | 'trade' | 'played', the side, the unit, …) — judged by the game's
record in src/answer_check (student_capture and gave_up) and src/trade_claims (trades). Not read (unjudged, never a
guess): a question, a condition or a wish, the future, a denial of the verb, a present tense (a threat, a line), a
clause whose side is not told.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import chess

_L = "а-яёa-z"
_WORD = re.compile(r"(?P<san>(?<![\w.])(?:\d{1,3}\s?\.{1,3}\s?)?(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8]"
                   r"(?:=[QRBN])?|O-O(?:-O)?|[a-h][1-8]-?[a-h][1-8])[+#]?(?![\w]))"
                   r"|(?P<sq>(?<![\w])[a-h][1-8](?![\w]))"
                   r"|(?P<w>[а-яёa-z]+(?:-[а-яёa-z]+)?)"
                   r"|(?P<p>[,;:—–()!?.])", re.IGNORECASE)

# ── the lexicon ──────────────────────────────────────────────────────────────────────────────────────────────────
_END3 = r"(?:а|и|о)?"
# taking: the taker is the subject (active), the instrument names the piece it took with
_TAKE_ACT = re.compile(r"(?:взял|забрал|побил|съел|сбил|срубил|снял|уничтожил|выиграл|отыграл|прихватил|скушал|слопал|"
                       r"урвал|захватил|отобрал|подобрал|выхватил)" + _END3 + "$")
_TAKE_GER = re.compile(r"(?:взяв|забрав|побив|съев|сбив|срубив|сняв|уничтожив|выиграв|отыграв|прихватив|отобрав)$")
_TAKE_PASS = re.compile(r"(?:взят|забран|побит|съеден|сбит|срублен|снят|уничтожен|выигран|отыгран|отобран)(?:а|о|ы)?$")
# losing: the loser is the subject (active), the unit lost the object
_LOSE_ACT = re.compile(r"(?:отдал|пожертвовал|потерял|зевнул|прозевал|подарил|уступил|сдал|проиграл|профукал)" + _END3 + "$")
_LOSE_GER = re.compile(r"(?:отдав|пожертвовав|потеряв|зевнув|прозевав|подарив|уступив|сдав|проиграв)$")
_LOSE_PASS = re.compile(r"(?:отдан|пожертвован|потерян|подарен|уступлен|утрачен|сдан|проигран|зевнут|прозеван)(?:а|о|ы)?$")
_LOSE_GEN = re.compile(r"(?:лишил(?:ся|ась|ось|ись)|лишившись)$")  # + genitive
_LOSE_WITH = re.compile(r"(?:расстал(?:ся|ась|ось|ись)|расставшись)$")  # с + instrumental
_LOSE_WITHOUT = re.compile(r"(?:остал(?:ся|ась|ось|ись)|оставшись)$")  # без + genitive
# the unit lost is the subject: «конь пропал», «ферзь погиб в обмен на ладью», «ферзь ушёл за ладью»
_LOSE_INTR = re.compile(r"(?:пропал|погиб|пал)(?:а|о|и|ла|ло|ли)?$")
_GONE = re.compile(r"(?:уш[её]л|ушла|ушло|ушли)$")
_TRADE_ACT = re.compile(r"(?:разменял|обменял|променял|сменял)(?:а|и|о)?$")
_TRADE_REFL = re.compile(r"(?:разменял|обменял)(?:ся|ась|ись)$")
_PLAY = re.compile(r"(?:сыграл|ответил|сделал|пош[её]л|пошла|пошли|играл|выбрал)(?:а|и|о)?$")
_RECEIVE = re.compile(r"(?:получил|получила|получили|получив)$")
_FUTURE = re.compile(r"(?:возьм|забер|побь|съест|съед(?:ят|ят)|срубит|сним|уничтож(?:ит|ат)|выиграет|выиграют|отдаст|отдадут|"
                     r"пожертву|потеря(?:ет|ют|ешь)|подарит|уступит|будет|будут|станет|станут|сможет|смогут)")
_NOT_TOLD = re.compile(r"(?<![а-яё])(?:если|бы|чтобы|можно|можешь|может|могут|мог|могла|могли|нужно|надо|стоит|стоило|следует|"
                       r"следовало|хотел\w*|хочешь|хотят|пытал\w*|пытается|собира\w*|представ\w*|допуст\w*|предполож\w*|"
                       r"обычно|часто|иногда|никогда|всегда|как\s+правило|якобы|будто|словно|кажется|казалось|"
                       r"когда|пока|после\s+того|прежде\s+чем|грозит|грозят|угрож\w*|готов\w*|"
                       r"if|would|could|should|might|when|unless)(?![а-яё])", re.IGNORECASE)
_NEG = re.compile(r"^(?:не|ни|нет|никто|ничего|никого|ничто|not|never)$")
# a restrictor makes a count exact: «всего одну», «только пешку», «больше ничего»
_EXACT = re.compile(r"^(?:всего|только|лишь|ровно|единственн\w*|одну|один|одного|одна)$")
_NUM = {"один": 1, "одного": 1, "одну": 1, "одна": 1, "одной": 1, "два": 2, "две": 2, "двух": 2, "пару": 2, "оба": 2, "обе": 2,
        "обоих": 2, "три": 3, "трех": 3, "четыре": 4, "четырех": 4, "пять": 5, "пяти": 5}
_SIDE = {}
for _w, _who, _cs in (("белые", "W", "N"), ("белых", "W", "GA"), ("белым", "W", "D"), ("белыми", "W", "I"),
                      ("черные", "B", "N"), ("черных", "B", "GA"), ("черным", "B", "D"), ("черными", "B", "I"),
                      ("ты", "S", "N"), ("тебя", "S", "GA"), ("тебе", "S", "DP"), ("тобой", "S", "I"), ("тобою", "S", "I"),
                      ("вы", "S", "N"), ("вас", "S", "GA"), ("вам", "S", "D"), ("вами", "S", "I"),
                      ("мы", "S", "N"), ("нас", "S", "GA"), ("нам", "S", "D"), ("нами", "S", "I"),
                      ("я", "E", "N"), ("меня", "E", "GA"), ("мне", "E", "DP"), ("мной", "E", "I"), ("мною", "E", "I")):
    _SIDE[_w] = (_who, set(_cs))
for _stem in ("соперник", "противник", "компьютер", "движок", "оппонент"):
    for _suf, _cs in (("", "N"), ("а", "GA"), ("у", "D"), ("ом", "I"), ("е", "P")):
        _SIDE[_stem + _suf] = ("E", set(_cs))
_SIDE["движка"] = ("E", {"G", "A"})
_POSS = re.compile(r"^(?:(?P<s>тво|ваш|наш)(?:й|я|е|и|его|ей|ю|ему|им|их|ими|а|у)?|(?P<e>мо)(?:й|я|е|и|его|ей|ю|ему|им|их|ими)|"
                   r"(?P<own>сво)(?:й|я|е|и|его|ей|ю|ему|им|их|ими|ею))$")
_COLOUR = re.compile(r"^(?:(?P<w>бел)|(?P<b>черн))(?:ый|ая|ое|ые|ого|ой|ую|ому|ым|ыми|ых)$")
_PREP = {"с", "со", "за", "на", "без", "у", "от", "ради", "взамен", "в", "во", "по", "из", "к", "под", "над", "при", "о", "об",
         "для", "до", "через", "между", "про"}
_CLAUSE_CUT = re.compile(r"^(?:а|но|однако|зато|хотя|поэтому|потому|так|ведь|тогда|когда|если|чтобы|где|который|которая|"
                         r"которое|которые|которого|которую|которым|которой)$")


@dataclass
class Tok:
    kind: str  # piece | side | poss | colour | num | exact | sq | san | neg | prep | verb | word | punct
    text: str
    start: int
    end: int
    ptype: Optional[int] = None  # piece: 0 «фигура» (any piece), else a chess piece type
    cases: set = field(default_factory=set)
    who: str = ""  # side / poss / colour: 'W' 'B' 'S' (the student) 'E' (the engine, the opponent) 'own' (свой)
    n: int = 0
    sq: Optional[str] = None
    owner: str = ""  # piece: its owner, as a who
    count: int = 1
    exact: bool = False
    vclass: str = ""  # verb: take | lose | trade | trade_refl | play | receive | gone
    voice: str = ""  # verb: act | ger | pass | gen | with | without | intr
    used: bool = False


@dataclass
class Event:
    kind: str  # take | lose | trade | played
    who: str  # the side that took / lost / played: 'W' 'B' 'S' 'E', or '' (unknown)
    ptypes: frozenset = frozenset()  # the unit taken / lost
    sq: Optional[str] = None  # its square, when named
    count: int = 1
    exact: bool = False
    instr: Optional[int] = None  # take: the piece that took
    instr_sq: Optional[str] = None
    instr_from: bool = False  # the instrument's square is the one it took from («с f6»)
    san: Optional[str] = None  # played: the written move; take: a written capture of the clause
    given: list = field(default_factory=list)  # trade: the units given (unit words)
    got: list = field(default_factory=list)  # trade: the units received
    subject_words: str = ""  # trade: the subject's own words (a player's name)
    gain: bool = False  # take: told as WON («выиграл пешку», «пешка выиграна»): a net gain, not just a capture (K7 02.11)
    at: int = 0
    end: int = 0
    text: str = ""


def _norm(text: str) -> str:
    return (text or "").replace("ё", "е").replace("Ё", "Е")


def _piece_table() -> dict:
    from src.claim_grammar import _P

    return _P


def tokens(text: str) -> list:
    """The tokens of *text* (already in Latin SAN, src/answer_check._to_san), with their roles."""
    table = _piece_table()
    out: list = []
    for m in _WORD.finditer(_norm(text)):
        if m["san"]:
            out.append(Tok("san", m["san"], m.start(), m.end()))
            continue
        if m["sq"]:
            out.append(Tok("sq", m["sq"].lower(), m.start(), m.end(), sq=m["sq"].lower()))
            continue
        if m["p"]:
            out.append(Tok("punct", m["p"], m.start(), m.end()))
            continue
        w = m["w"].lower()
        base = w.split("-")[-1] if re.match(r"^[a-h]-", w) else w  # «d-пешку»
        if base in table and table[base][0] is not None:
            pt, cs = table[base]
            cs = set(cs)
            if base in ("ладьи", "слоны", "кони", "ферзи"):
                cs.add("A")
            t = Tok("piece", w, m.start(), m.end(), ptype=pt, cases=cs)
            if base != w:
                t.sq = None  # a file named («d-пешка»): the pawn of that file, no square
            out.append(t)
        elif w in _SIDE:
            who, cs = _SIDE[w]
            out.append(Tok("side", w, m.start(), m.end(), who=who, cases=set(cs)))
        elif _POSS.match(w):
            pm = _POSS.match(w)
            out.append(Tok("poss", w, m.start(), m.end(), who="S" if pm["s"] else ("E" if pm["e"] else "own")))
        elif _COLOUR.match(w):
            cm = _COLOUR.match(w)
            out.append(Tok("colour", w, m.start(), m.end(), who="W" if cm["w"] else "B"))
        elif w in _NUM:
            out.append(Tok("num", w, m.start(), m.end(), n=_NUM[w], exact=bool(_EXACT.match(w))))
        elif _EXACT.match(w):
            out.append(Tok("exact", w, m.start(), m.end()))
        elif _NEG.match(w):
            out.append(Tok("neg", w, m.start(), m.end()))
        elif w in _PREP:
            out.append(Tok("prep", w, m.start(), m.end()))
        else:
            v = _verb(w)
            out.append(Tok("verb", w, m.start(), m.end(), vclass=v[0], voice=v[1]) if v else Tok("word", w, m.start(), m.end()))
    _attach(out)
    return out


def _verb(w: str) -> Optional[tuple]:
    for rx, cls, voice in ((_TAKE_ACT, "take", "act"), (_TAKE_GER, "take", "ger"), (_TAKE_PASS, "take", "pass"),
                           (_LOSE_ACT, "lose", "act"), (_LOSE_GER, "lose", "ger"), (_LOSE_PASS, "lose", "pass"),
                           (_LOSE_GEN, "lose", "gen"), (_LOSE_WITH, "lose", "with"), (_LOSE_WITHOUT, "lose", "without"),
                           (_LOSE_INTR, "lose", "intr"), (_GONE, "gone", "intr"), (_TRADE_ACT, "trade", "act"),
                           (_TRADE_REFL, "trade_refl", "act"), (_PLAY, "play", "act"), (_RECEIVE, "receive", "act")):
        if rx.match(w):
            return cls, voice
    return None


def _attach(toks: list) -> None:
    """Each piece's square, owner and count from the words around it."""
    for i, t in enumerate(toks):
        if t.kind != "piece":
            continue
        # after it: «пешка f6», «пешка на e7», «пешка чёрных», «пешка c» (a file letter)
        j = i + 1
        if j < len(toks) and toks[j].kind == "sq":
            t.sq = toks[j].sq
            toks[j].used = True
            j += 1
        elif j + 1 < len(toks) and toks[j].kind == "prep" and toks[j].text == "на" and toks[j + 1].kind == "sq" and \
                not any(x.kind == "verb" for x in toks[max(0, i - 3):i]):
            t.sq = toks[j + 1].sq
            toks[j + 1].used = True
            j += 2
        if j < len(toks) and toks[j].kind == "side" and toks[j].cases & {"G"} and toks[j].text not in ("тебя", "вас", "нас", "меня"):
            t.owner = toks[j].who
            toks[j].used = True
        # before it: a possessive, a colour, a number, a restrictor, adjectives between
        k = i - 1
        while k >= 0 and toks[k].kind in ("word", "poss", "colour", "num", "exact") and i - k <= 4:
            x = toks[k]
            if x.kind == "word" and not re.search(r"(?:ый|ий|ой|ая|яя|ое|ее|ые|ие|ого|его|ую|юю|ым|им|ых|их|ыми|ими|ую)$", x.text) \
                    and x.text not in ("еще", "уже", "сразу", "целую", "целого", "целых"):
                break
            if x.kind == "poss" and not t.owner:
                t.owner = x.who
            elif x.kind == "colour" and not t.owner:
                t.owner = x.who
            elif x.kind == "num":
                t.count = x.n
                t.exact = t.exact or x.exact
            elif x.kind == "exact":
                t.exact = True
            k -= 1
        if k >= 0 and toks[k].kind == "exact":
            t.exact = True


def clauses(toks: list) -> list:
    """Runs of tokens between sentence marks and the conjunctions that start another thought («, а», «, но», «; »)."""
    out, cur = [], []
    for i, t in enumerate(toks):
        if t.kind == "punct" and t.text in ".;!?():—–":
            if cur:
                out.append(cur)
            cur = []
            continue
        if t.kind == "punct" and t.text == "," and i + 1 < len(toks) and (
                (toks[i + 1].kind == "word" and _CLAUSE_CUT.match(toks[i + 1].text))):
            if cur:
                out.append(cur)
            cur = []
            continue
        cur.append(t)
    if cur:
        out.append(cur)
    return out


def _who_of_subject(cl: list, verb: Tok, exclude=()) -> tuple:
    """(who, the token) of the clause's nominative subject: a side or a person, else a piece with an owner."""
    sides = [t for t in cl if t.kind == "side" and "N" in t.cases and not t.used and t not in exclude
             and not _after_prep(cl, t)]
    if sides:
        best = min(sides, key=lambda t: abs(t.start - verb.start))
        return best.who, best
    return "", None


def _after_prep(cl: list, t: Tok) -> Optional[str]:
    i = cl.index(t)
    k = i - 1
    while k >= 0 and cl[k].kind in ("poss", "colour", "num", "exact", "word") and i - k <= 3:
        if cl[k].kind == "word" and not re.search(r"(?:ый|ий|ой|ая|яя|ое|ее|ые|ие|ого|его|ую|юю|ым|им|ых|их|ыми|ими)$", cl[k].text):
            break
        k -= 1
    if k >= 0 and cl[k].kind == "prep":
        return cl[k].text
    if k >= 1 and cl[k].kind == "word" and cl[k].text == "обмен" and cl[k - 1].kind == "prep":
        return "в обмен " + cl[k].text
    return None


def _units_after(cl: list, i: int) -> list:
    """The unit tokens of a list starting at cl[i] («ладью и пешку», «одну ладью», «ладью, коня»)."""
    got, j = [], i
    while j < len(cl):
        t = cl[j]
        if t.kind == "piece":
            got.append(t)
            j += 1
            continue
        if t.kind in ("num", "exact", "poss", "colour", "sq") or (t.kind == "word" and t.text in ("и", "плюс", "еще")) or \
                (t.kind == "punct" and t.text == ","):
            j += 1
            continue
        if t.kind == "word" and re.search(r"(?:ую|ой|ого|ую|ые|ых|ий|ый|ая)$", t.text) and j + 1 < len(cl) and cl[j + 1].kind == "piece":
            j += 1
            continue
        break
    return got


def _unit_words(units: list) -> str:
    return " и ".join(((f"{u.count} " if u.count > 1 else "") + u.text) for u in units)


# Noun frames of a loss: «ценой пешки», «(пошёл на) жертву пешки», «взамен пешки» — the genitive unit is what the clause's
# subject gave up (a «жертва» only told as done: with a past verb in its clause).
_NOUN_LOSS = re.compile(r"^(?:ценой|жертв(?:а|у|ой|ы|е)|взамен)$")
_PAST_WORD = re.compile(r"(?:л|ла|ли|ло|лся|лась|лись|в|вши|вшись)$")


def _noun_frames(cl: list) -> list:
    out = []
    for i, t in enumerate(cl):
        if not _NOUN_LOSS.match(t.text) or i + 1 >= len(cl):
            continue
        if t.text.startswith("жертв") and not any(x.kind in ("verb", "word") and x is not t and _PAST_WORD.search(x.text)
                                                   and x.text not in ("ли",) for x in cl):
            continue
        units = [u for u in _units_after(cl, i + 1) if "G" in u.cases]
        if units:
            out.append((t, units[0]))
    return out


def events(text: str) -> list:
    """The capture, loss, trade and attribution events *text* tells as done."""
    toks = tokens(text)
    out: list = []
    whole = [t for t in toks]
    for cl in clauses(toks):
        low = " ".join(t.text for t in cl)
        if _NOT_TOLD.search(low) or any(t.kind == "word" and _FUTURE.match(t.text) for t in cl):
            continue
        for head, unit in _noun_frames(cl):
            who, subj = _who_of_subject(cl, head)
            if not who:
                who, subj = _gerund_subject(whole, head)
            if who and not any(x.kind == "neg" for x in cl):
                ev = Event("lose", who, _ptypes(unit), unit.sq, unit.count, unit.exact)
                ev.at, ev.end = cl[0].start, cl[-1].end
                ev.text = text[ev.at:ev.end]
                out.append(ev)
        for verb in [t for t in cl if t.kind == "verb"]:
            if any(t.kind == "neg" and 0 <= verb.start - t.end <= 12 for t in cl):
                continue  # «не взял», «никто не отдавал»: a denial
            ev = _read(cl, verb, whole)
            if ev is not None:
                ev.gain = ev.kind == "take" and verb.text.startswith("выигр")
                ev.at, ev.end = cl[0].start, cl[-1].end
                ev.text = text[ev.at:ev.end]
                out.append(ev)
    return out


def _pieces(cl: list, cases: str, exclude=(), after: Optional[int] = None, before: Optional[int] = None,
            prep: Optional[str] = "none") -> list:
    out = []
    for t in cl:
        if t.kind != "piece" or t in exclude or not (t.cases & set(cases)):
            continue
        if after is not None and t.start < after:
            continue
        if before is not None and t.start >= before:
            continue
        p = _after_prep(cl, t)
        if prep == "none" and p is not None:
            continue
        if prep not in ("none", "any") and p != prep:
            continue
        out.append(t)
    return out


def _ptypes(t: Tok) -> frozenset:
    if t.ptype == 0:
        return frozenset({chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN})
    return frozenset({t.ptype})


def _received(cl: list, verb: Tok) -> list:
    """What came back: the units after «за», «в обмен на», «ради», «взамен», «получив/получили»."""
    for i, t in enumerate(cl):
        if t.start < verb.start - 60:
            continue
        if t.kind == "prep" and t.text in ("за", "ради", "взамен"):
            units = _units_after(cl, i + 1)
            if units:
                return units
        if t.kind == "word" and t.text == "обмен" and i + 1 < len(cl) and cl[i + 1].kind == "prep" and cl[i + 1].text == "на":
            units = _units_after(cl, i + 2)
            if units:
                return units
        if t.kind == "verb" and t.vclass == "receive" and t is not verb:
            j = i + 1
            while j < len(cl) and cl[j].kind in ("word", "prep") and cl[j].text in ("взамен", "лишь", "только", "всего", "за", "него", "нее", "это"):
                j += 1
            units = _units_after(cl, j)
            if units:
                return units
    return []


def _read(cl: list, verb: Tok, whole: list) -> Optional[Event]:
    cls, voice = verb.vclass, verb.voice
    if cls == "play":
        # the move bound to the verb: right after it («ты сыграл 5.fxe7», «ответил fxe7»; a bare square is a pawn move
        # there), or right before it as its object («Ход fxe7 сделал ты»)
        i = whole.index(verb)
        nxt = next((t for t in whole[i + 1:] if not (t.kind == "word" and t.text in ("ход", "ходом", "сразу", "тут", "же",
                                                                                        "только", "что", "уже", "потом"))), None)
        i = cl.index(verb)
        prev = cl[i - 1] if i > 0 else None
        san = None
        if nxt is not None and nxt.kind in ("san", "sq"):
            san = nxt.text
        elif prev is not None and prev.kind == "san":
            san = prev.text
        who, subj = _who_of_subject(cl, verb)
        if san and who:
            return Event("played", who, san=san)
        return None
    if cls in ("receive",):
        # «Непомнящий получил ферзя в обмен на ладью», «За ферзя белые взяли лишь одну ладью» (below, take + за)
        got = _units_after(cl, cl.index(verb) + 1)
        gave = []
        for i, t in enumerate(cl):
            if t.kind == "word" and t.text == "обмен" and i + 1 < len(cl) and cl[i + 1].text == "на":
                gave = _units_after(cl, i + 2)
            elif t.kind == "prep" and t.text == "за" and not gave:
                gave = _units_after(cl, i + 1)
        if got and gave and not {id(x) for x in got} & {id(x) for x in gave}:
            who, subj = _who_of_subject(cl, verb)
            return Event("trade", who, given=[_unit_words(gave)], got=[_unit_words(got)],
                         subject_words=_subject_words(cl, verb, subj))
        return None
    if cls in ("take",):
        return _read_take(cl, verb, whole)
    if cls in ("lose", "gone", "trade", "trade_refl"):
        return _read_lose(cl, verb, whole)
    return None


def _subject_words(cl: list, verb: Tok, subj: Optional[Tok]) -> str:
    """The words naming the subject (a side, or a capitalised name before the verb) for src/trade_claims._subject."""
    if subj is not None:
        return subj.text
    names = [t for t in cl if t.kind == "word" and t.start < verb.start and t.text[:1].isalpha()]
    return names[-1].text if names else ""


def _gerund_subject(whole: list, verb: Tok) -> tuple:
    """A gerund's subject is the main clause's: the nominative side nearest it in the sentence (either side of it)."""
    sides = [t for t in whole if t.kind == "side" and "N" in t.cases]
    if not sides:
        return "", None
    best = min(sides, key=lambda t: abs(t.start - verb.start))
    return best.who, best


def _read_take(cl: list, verb: Tok, whole: list) -> Optional[Event]:
    voice = verb.voice
    instr = None
    if voice in ("act", "ger"):
        who, subj = (_gerund_subject(whole, verb) if voice == "ger" else _who_of_subject(cl, verb))
        # a piece subject («Слона e7 съела твоя пешка», «Пешка f6, твоя, побила слона»): its owner is the taker
        noms = [t for t in _pieces(cl, "N") if not (t.cases & {"A"} and t.start > verb.start)]
        objs = _pieces(cl, "A", exclude=noms)
        if not who and noms:
            subj_piece = min(noms, key=lambda t: abs(t.start - verb.start))
            if not subj_piece.owner:
                own = _owner_near(cl, subj_piece)
                subj_piece.owner = own
            who = subj_piece.owner
            instr = subj_piece
            objs = [t for t in _pieces(cl, "A") if t is not subj_piece]
        given = []
        for i, t in enumerate(cl):
            if t.kind == "prep" and t.text == "за":
                given = _units_after(cl, i + 1)
                break
        objs = [t for t in objs if all(t is not g for g in given)]
        if not objs:
            return None
        patient = min(objs, key=lambda t: (t.start < verb.start, abs(t.start - verb.start)))
        if verb.text.startswith(("выигр", "отыгр")) and patient.ptype is None:
            return None
        if given and voice == "act":
            # «За ферзя белые взяли лишь одну ладью»: what was given for what was taken — a trade
            got = [patient] + [u for u in _units_after(cl, cl.index(patient) + 1) if u is not patient]
            return Event("trade", who, given=[_unit_words(given)], got=[_unit_words(got)],
                         subject_words=_subject_words(cl, verb, subj))
        if instr is None:
            ins = _pieces(cl, "I")
            instr = ins[0] if ins else None
        if instr is not None and instr.owner == "own":
            instr.owner = who
        if not who:
            # «Твоего коня взяли без размена» (no subject, the 3rd person plural): the other side took it
            owner = patient.owner or _possessor(cl)
            if owner in ("W", "B", "S", "E") and re.search(r"(?:ли)$", verb.text) and voice == "act":
                who = _other(owner)
        if not who and instr is not None and instr.owner in ("W", "B", "S", "E"):
            who = instr.owner
        if not who:
            return None
        if patient.owner == who:
            return None  # «ты взял свою пешку»: not a capture claim
        return _take_event(who, patient, instr, cl)
    if voice == "pass":
        # «Слон e7 был взят чёрной пешкой», «Слон на e7 взят твоей пешкой»
        noms = _pieces(cl, "N")
        if not noms:
            return None
        patient = min(noms, key=lambda t: abs(t.start - verb.start))
        agents = [t for t in _pieces(cl, "I") if t is not patient]
        side_agents = [t for t in cl if t.kind == "side" and "I" in t.cases]
        who, instr = "", None
        if agents:
            instr = agents[0]
            who = instr.owner if instr.owner in ("W", "B", "S", "E") else ""
        if not who and side_agents:
            who = side_agents[0].who
        if not who:
            owner = patient.owner or _possessor(cl)
            if owner in ("W", "B", "S", "E"):
                who = _other(owner)
        if not who:
            return None
        return _take_event(who, patient, instr, cl)
    return None


def _owner_near(cl: list, piece: Tok) -> str:
    """«Пешка f6, твоя, побила слона»: a possessive set off by commas right after the piece."""
    i = cl.index(piece)
    for t in cl[i + 1:i + 4]:
        if t.kind == "poss":
            return t.who
        if t.kind not in ("punct", "sq"):
            break
    return ""


def _possessor(cl: list) -> str:
    """«у тебя», «у белых»: the owner of the unit in the clause."""
    for i, t in enumerate(cl[:-1]):
        if t.kind == "prep" and t.text == "у" and cl[i + 1].kind == "side":
            return cl[i + 1].who
    return ""


def _other(who: str) -> str:
    return {"W": "B", "B": "W", "S": "E", "E": "S"}.get(who, "")


def _take_event(who: str, patient: Tok, instr: Optional[Tok], cl: list) -> Event:
    count, exact = patient.count, patient.exact
    sans = [t.text for t in cl if t.kind == "san" and "x" in t.text]
    ev = Event("take", who, _ptypes(patient), patient.sq, count, exact, san=sans[0] if len(sans) == 1 else None)
    if instr is not None and instr.ptype:
        ev.instr = instr.ptype
        ev.instr_sq = instr.sq
        i = cl.index(instr)
        if i + 2 < len(cl) and cl[i + 1].kind == "prep" and cl[i + 1].text in ("с", "со", "из") and cl[i + 2].kind == "sq":
            ev.instr_sq, ev.instr_from = cl[i + 2].sq, True
    return ev


def _read_lose(cl: list, verb: Tok, whole: list) -> Optional[Event]:
    cls, voice = verb.vclass, verb.voice
    if cls == "trade_refl":
        # «Ты сам разменялся: fxe7» — the move right after it is the speaker's attribution
        i = whole.index(verb)
        nxt = next((t for t in whole[i + 1:] if not (t.kind == "punct" and t.text in ":—–")), None)
        who, _ = _who_of_subject(cl, verb)
        if nxt is not None and nxt.kind == "san" and who:
            return Event("played", who, san=nxt.text)
        return None
    patient = None
    who = ""
    subj = None
    back = _received(cl, verb)
    if voice in ("act", "ger"):
        who, subj = (_gerund_subject(whole, verb) if voice == "ger" else _who_of_subject(cl, verb))
        objs = _pieces(cl, "A")
        objs = [t for t in objs if _after_prep(cl, t) is None and all(t is not b for b in back)]
        if objs:
            patient = min(objs, key=lambda t: (t.start < verb.start, abs(t.start - verb.start)))
    elif voice in ("gen", "without"):
        who, subj = (_gerund_subject(whole, verb) if verb.text.endswith("шись") else _who_of_subject(cl, verb))
        objs = [t for t in cl if t.kind == "piece" and "G" in t.cases and t.start > verb.start
                and (voice == "gen" or _after_prep(cl, t) == "без")]
        patient = objs[0] if objs else None
    elif voice == "with":
        who, subj = (_gerund_subject(whole, verb) if verb.text.endswith("шись") else _who_of_subject(cl, verb))
        objs = [t for t in cl if t.kind == "piece" and "I" in t.cases and _after_prep(cl, t) in ("с", "со")]
        patient = objs[0] if objs else None
    elif voice in ("pass", "intr"):
        noms = _pieces(cl, "N")
        if noms:
            patient = min(noms, key=lambda t: abs(t.start - verb.start))
            who = patient.owner if patient.owner in ("W", "B", "S", "E") else ""
            if not who:
                who = _possessor(cl)
        if cls == "gone" and not _received(cl, verb) and not re.search(r"(?:задаром|даром|бесплатно)", " ".join(t.text for t in cl)):
            return None  # «конь ушёл на d2»: a move, not a loss
    if patient is None:
        return None
    got = [u for u in back if u is not patient]
    if cls in ("trade", "gone") or got:
        given = [patient] + [u for u in _units_after(cl, cl.index(patient) + 1)
                             if u is not patient and all(u is not g for g in got)]
        if got:
            sw = _subject_words(cl, verb, subj) if voice in ("act", "ger", "gen", "with", "without") else ""
            if not who and not sw and voice in ("act", "ger", "gen", "with", "without"):
                return None
            return Event("trade", who, given=[_unit_words(given)], got=[_unit_words(got)], subject_words=sw,
                         count=patient.count)
        if cls in ("trade", "gone"):
            return None
    if not who and patient.sq:
        who = "@" + patient.sq  # «Пешка c5 отдана»: the owner of what stood there, read from the game
    if not who:
        return None
    return Event("lose", who, _ptypes(patient), patient.sq, patient.count, patient.exact)


def resolve(who: str, ctx) -> Optional[bool]:
    """The colour of a who ('W' 'B' 'S' 'E'), or None when the student's colour is not known."""
    if who == "W":
        return chess.WHITE
    if who == "B":
        return chess.BLACK
    student = getattr(ctx, "student_color", None)
    if student is None:
        return None
    if who == "S":
        return student
    if who == "E":
        return not student
    return None
