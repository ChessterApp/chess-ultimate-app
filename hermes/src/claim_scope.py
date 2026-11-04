"""Is a sentence of the coach about the board as it is, and is a claim in it denied — decided once (2026-10-15).

The answer checker grew seven detectors for two questions — _HYPO, _GENERAL/_NOW, _FUTURE_VERB, _FUTURE_FILL
for «is this about now or about what could be», and _NEGATION, _negated_before, _NEGATED_WORD for «is this
claim denied» — each with its own word list, each patched after one incident, so a sentence passed one and
failed the next (inventory 2026-10-15). Here are the two lists and the two questions; the detectors in
src/answer_check.py and src/answer_check_rules.py are names for these.
"""

from __future__ import annotations

import re

_W = r"(?<![а-яёa-zәғқңөұүһі])"
_E = r"(?![а-яёa-zәғқңөұүһі])"

# Words that put what follows in a condition, a line of play, a future or a rule in general — not the board
# as it is: «после», «если», «тогда», «бы», «сыграй», "if", "would", "after"…
CONDITIONAL = re.compile(
    _W + r"(?:после|если|когда|пока|тогда|даже|будет|будут|бы|сыграй|сыграйте|сыграв|сыграть|играй|играйте|"
    r"поставь|поставьте|переведи|переведите|представь|допустим|скажем|вместо|в\s+общем|по\s+правилам|обычно|"
    r"всегда|никогда|получится|получается|выйдет|окажется|"
    r"after|if|when|once|then|would|will|could|should|were|play|plays|played|playing|put|place|instead|"
    r"imagine|suppose|say|let'?s|unless|even|in\s+general|always|never|usually|would\s+be|that\s+gives|"
    r"егер|кезде|сонда|болады)" + _E, re.IGNORECASE)
# Words that pin a claim to the board as it is: «сейчас», «здесь», «на доске», "now", "here"…
NOW = re.compile(
    _W + r"(?:сейчас|здесь|тут|в\s+этой\s+позиции|на\s+доске|уже|now|here|right\s+now|at\s+the\s+moment|"
    r"in\s+this\s+position|on\s+the\s+board|қазір|осы\s+жерде|бұл\s+позицияда)" + _E, re.IGNORECASE)
# An answer that opens with yes/no answers the question about this board.
YES_NO = re.compile(r"^\W*(?:да|нет|конечно|увы|yes|no|nope|sure|unfortunately|иә|жоқ)" + _E, re.IGNORECASE)
# A verb form that says what a piece will do, not what it does.
FUTURE_VERB = re.compile(r"буд(?:ет|ут|ешь)|бы\b|останеш|останет|останут|окажеш|окажет|окажут|получиш|получит|"
                         r"would|will|'ll|can|could|end\s+up|going\s+to|get\s+left|с\s+(?:нападением|темпом|атакой|ударом)",
                         re.IGNORECASE)
# A denial: «не», «нет», «нельзя», "not", "never", "can't"…
DENIAL = re.compile(r"(?<![а-яёa-z])(?:не|ни|нет|никак|нельзя|not|never|nor|cannot|n't)(?![а-яёa-z])|[a-z]+n'?t(?![a-z])",
                    re.IGNORECASE)


def conditional_before(text: str, upto: int) -> bool:
    """A conditional word stands before position *upto* of *text*: the claim there is about what could be."""
    return bool(CONDITIONAL.search(text[:upto]))


def about_now(text: str, strict: bool = False) -> bool:
    """*text* speaks of the board as it is. With *strict*, only a now-word or a yes/no opening says so; otherwise
    a sentence with no conditional word counts too."""
    if CONDITIONAL.search(text) and not NOW.search(text):
        return False
    if strict:
        return bool(NOW.search(text) or YES_NO.search(text))
    return True


def denied_before(text: str, start: int, window: int = 24) -> bool:
    """A denial stands right before position *start* of *text* («не бьёт», «нельзя рокироваться», "doesn't
    attack"): the claim is denied, not made. The denial may be one word away («не просто бьёт»)."""
    before = text[max(0, start - window):start]
    return bool(re.search(r"(?:^|[\s*_«\"(])(?:не|ни|нет|никак|нельзя|never|not|n't|cannot|can't)[*_]*\s*(?:\w+\s+)?$",
                          before, re.IGNORECASE) or re.search(r"[a-z]+n'?t\s*$", before, re.IGNORECASE))


# A state denied by the copula after it: «король под шахом не стоит», «под боем не находится», «под ударом уже не
# оказывается», "in check it is not". Only a copula — «король под шахом не может рокироваться» asserts the check.
_DENIED_COPULA = re.compile(
    r"^[\s*_»\"]*(?:(?:сам|сама|при\s+этом|сейчас|уже|здесь|тут)\s+)?(?:не|ни|никак\s+не)\s+(?:стоит|стоят|находится|"
    r"находятся|оказывается|оказываются|оказался|оказалась|оказалось|остается|остался|осталась|был|была|было|"
    r"является)(?![а-яёa-z])", re.IGNORECASE)


def denied_after(text: str, end: int) -> bool:
    """The state named right before position *end* of *text* is denied by the copula after it («король под шахом не
    стоит»; stalemate-now, live 02.11: "the white king is not in check" on a true «и сам король под шахом не стоит»)."""
    return bool(_DENIED_COPULA.match(text[end:end + 40]))


def denied_in(clause: str) -> bool:
    """A denial anywhere in *clause* («до h4 ей не достать»)."""
    return bool(DENIAL.search(clause))


# ── Rule talk: a sentence that states a law or defines notation is not a claim about this board (fix1102 K4) ────
# Live 02.11 (verify1102 §6.2): nine true sentences were judged on the board in front of the student — «Рокировка
# разрешена, только если ни король, ни эта ладья ещё не двигались» (castling_status: "White cannot castle here"),
# «Она теряется только в четырёх случаях: …, король под шахом прямо сейчас, …» and "you can't castle while your
# king is in check" (_king_issues: "the white king is not in check"), «Запись хода всегда состоит из …: К:d5 — конь
# берёт на d5» (_san_issues: "Nxd5 is impossible"), «Двойной знак означает …: +− — белые выигрывают» (_eval_issues).
# rule_spans finds those parts once; the answer check hides them from every detector that judges the position and
# leaves them to the detectors that judge a law (src/answer_check._check_sentence). What is not a rule frame is not
# touched: a sentence pinned to this position (a now-word in the frame's head, a square or a move in a law frame) is
# still judged as before.

_LAW_PREDICATE = (
    r"(?:разреш[её]н\w*|разреша\w*|запрещ[её]н\w*|запреща\w*|возможн\w*|невозможн\w*|допуска\w*|допустим\w*|"
    r"легальн\w*|нелегальн\w*|законн\w*|можно|нельзя|теря\w*|потерян\w*|отменя\w*|сохраня\w*|"
    r"can|may|(?:is|are)\s+(?:only\s+|still\s+)?(?:allowed|legal|illegal|possible|impossible|forbidden|lost|kept)|"
    r"loses?|keeps?)"
)
# The restriction that turns the predicate into a law: «только если», «лишь когда», «в четырёх случаях:», "only if",
# "unless", "as long as". A bare «если» is not one — «если ты сыграешь Bxf7…» is a line on this board.
_LAW_RESTRICTION = (
    r"(?:(?:только|лишь|исключительно)\s+(?:тогда\s*,?\s*)?(?:если|когда|пока|при\s+условии|в\s+(?:\w+\s+){0,2}?случа\w+)|"
    r"в\s+(?:двух|тр[её]х|четыр[её]х|пяти|шести|нескольких|следующих|таких|\d+)\s+случа\w+|при\s+условии,?\s+что|"
    r"only\s+(?:if|when|while)|unless|as\s+long\s+as|"
    r"in\s+(?:two|three|four|five|six|these|the\s+following|\d+)\s+cases)"
)
# "while" is a restriction only after a prohibition ("you can't castle while your king is in check"); after "can" it
# is mostly «в то время как» ("the knight can take while the bishop covers d6").
_LAW_FRAME = re.compile(
    _W + _LAW_PREDICATE + _E + r"[^.;!?]{0,60}?" + _W + r"(?P<r>" + _LAW_RESTRICTION + r")" + _E
    + r"|" + r"(?<![a-z])(?:can'?t|cannot|can\s+not|may\s+not|must\s+not|mustn'?t|(?:is|are)\s+not\s+allowed\s+to|"
    r"(?:is|are)\s+(?:illegal|forbidden|impossible))(?![a-z])[^.;!?]{0,60}?(?<![a-z])(?P<r2>while|unless|only\s+if|"
    r"only\s+when|as\s+long\s+as)(?![a-z])"
    # …and «пока» after a Russian prohibition: «рокироваться нельзя, пока король под шахом»
    + r"|" + _W + r"(?:нельзя|запрещ[её]н\w*|запреща\w*|невозможн\w*)" + _E + r"[^.;!?]{0,60}?" + _W + r"(?P<r3>пока)" + _E,
    re.IGNORECASE)
# A definition of notation or of a sign: «Двойной знак означает…», «Запись хода всегда состоит из…», "The x means a
# capture". The game's own record («запись партии») is not notation talk.
_DEFINITION_FRAME = re.compile(
    _W + r"(?:знак\w*|значк\w*|значок|символ\w*|запис[ьи](?!\s+(?:партии|игры|этой|твоей|вашей))|нотаци\w*|обозначени\w*|"
    r"букв[аы]|sign|signs|symbol|symbols|notation|letter)" + _E + r"[^.;!?]{0,50}?"
    + _W + r"(?:означа\w*|обознача\w*|читается|состоит|пишется|пишут|записыва\w*|показыва\w*|"
    r"means?|stands?\s+for|denotes?|indicates?|is\s+written|consists?\s+of)" + _E,
    re.IGNORECASE)
# A term defined: «Пат — это когда…», "Stalemate is when…".
_TERM_FRAME = re.compile(
    r"^\W*(?:пат|мат|шах|рокировка|взятие\s+на\s+проходе|цугцванг|stalemate|checkmate|check|castling|en\s+passant|"
    r"zugzwang)\s*(?:[—–-]\s*(?:это\s+)?|is\s+)(?:когда|ситуация|положение|позиция,\s+(?:в\s+которой|когда)|when|a\s+position)"
    + _E, re.IGNORECASE)
# What pins a law frame to the board in front of the student: a square or a written move anywhere in it.
_BOARD_TOKEN = re.compile(r"(?<![a-zа-я0-9])(?:[KQRBNКЛСФ][a-h]?[1-8]?[x:×]?[a-h][1-8]|[a-h][x:×][a-h][1-8]|[a-h][1-8])"
                          r"(?![a-z0-9])", re.IGNORECASE)


def _clause_start(text: str, at: int) -> int:
    cut = max(text.rfind(c, 0, at) for c in ".;!?")
    return cut + 1 if cut >= 0 else 0


def _clause_end(text: str, at: int) -> int:
    ends = [i for i in (text.find(";", at),) if i >= 0]
    return min(ends) if ends else len(text)


def rule_spans(text: str, *, anchored_answer: bool = False) -> list:
    """The (start, end) parts of *text* that state a rule in general or define notation, signs or a term — not claims
    about the board in front of the student. *anchored_answer*: a yes/no opening answers a question about this board,
    so it pins the head of a law frame (the condition after «только если», "while" stays a rule).

    * law frame — a law predicate with its restriction, «Рокировка разрешена, только если …», "you can't castle while
      …", «Она теряется только в четырёх случаях: …»: the restriction to the end of its clause is the rule; the head
      before it is too unless a now-word (or an answering yes/no) pins it. A square or a move in the frame pins all of
      it — «Слон c4 можно взять, только если конь f3 уйдёт» is about this board — and nothing is hidden;
    * definition — «Двойной знак означает …», «Запись хода всегда состоит из …: Лf1 — ладья идёт на f1» (the examples
      go with it), «Пат — это когда …»: to the end of the sentence, unless a now-word pins the head («Знак + здесь
      означает…»)."""
    spans = []
    for m in _LAW_FRAME.finditer(text):
        r = next(m.start(g) for g in ("r", "r2", "r3") if m.group(g))
        start = _clause_start(text, m.start())
        end = _clause_end(text, r)
        if _BOARD_TOKEN.search(text[start:end]):
            continue
        head = text[start:r]
        pinned = bool(NOW.search(head)) or (anchored_answer and bool(YES_NO.search(text[start:])) and start == 0)
        spans.append((r if pinned else start, end))
    for rx in (_DEFINITION_FRAME, _TERM_FRAME):
        for m in rx.finditer(text):
            start = _clause_start(text, m.start())
            if NOW.search(text[start:m.end()]):
                continue
            spans.append((start, len(text)))
    if not spans:
        return []
    spans.sort()
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [tuple(x) for x in merged]


def without_spans(text: str, spans: list) -> str:
    """*text* with *spans* left out (one space each), for the detectors that judge the board."""
    out, at = [], 0
    for s, e in spans:
        out.append(text[at:s])
        out.append(" ")
        at = e
    out.append(text[at:])
    return "".join(out)
