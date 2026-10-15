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


def denied_in(clause: str) -> bool:
    """A denial anywhere in *clause* («до h4 ей не достать»)."""
    return bool(DENIAL.search(clause))
