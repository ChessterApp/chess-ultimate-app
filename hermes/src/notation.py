"""Moves written the Russian way, turned into SAN (2026-10-08).

«1.е4 е5 2.Кф3 Кс6 3.Сс4 Сс5 4.с3 Кф6 5.д4 е:д4» — Cyrillic piece letters (Кр Ф Л С К), Cyrillic
look-alike and transliterated files (а б в с ц д е э ф г х), «:» or «х» for a capture, zeros for castling.
A game pasted like this was not read anywhere: the site's paste (chess.js) and the server's review
step (python-chess) know SAN only, so the coach got the moves as plain text. The site has the same
conversion in frontend/src/lib/russianNotation.ts.
"""

from __future__ import annotations

import re

_PIECES = {"Кр": "K", "Ф": "Q", "Л": "R", "С": "B", "К": "N"}
_FILES = {"а": "a", "б": "b", "в": "b", "с": "c", "ц": "c", "д": "d", "е": "e", "э": "e", "ф": "f", "г": "g", "х": "h"}
_F = "a-hабвсцдеэфгх"
_TOKEN = re.compile(
    rf"^(?P<p>Кр|[КФЛСKQRBN])?(?P<ff>[{_F}])?(?P<fr>[1-8])?(?P<x>[x:х×])?(?P<tf>[{_F}])(?P<tr>[1-8])"
    rf"(?:=?(?P<promo>[ФЛСКQRBN]))?(?P<tail>[+#!?]*)$")


def _file(ch: str) -> str:
    return _FILES.get(ch, ch)


def _token(tok: str) -> str:
    m = _TOKEN.match(tok)
    if not m:
        return tok
    piece = _PIECES.get(m["p"], m["p"] or "")
    promo = _PIECES.get(m["promo"], m["promo"]) if m["promo"] else ""
    return (piece + (_file(m["ff"]) if m["ff"] else "") + (m["fr"] or "") + ("x" if m["x"] else "")
            + _file(m["tf"]) + m["tr"] + (f"={promo}" if promo else "") + m["tail"])


def russian_to_san(text: str) -> str:
    """*text* with every move token in SAN; words and anything else left as they are."""
    if not text:
        return text
    text = re.sub(r"(?<![0-9-])0-0-0(?![0-9-])", "O-O-O", text)
    text = re.sub(r"(?<![0-9-])0-0(?![0-9-])", "O-O", text)
    out = []
    for part in re.split(r"(\s+|(?<=\d\.)|(?<=\.\.\.))", text):
        if not part or part.isspace():
            out.append(part or "")
            continue
        num = re.match(r"^(\d+\.(?:\.\.)?)(.*)$", part)
        if num:
            out.append(num[1] + _token(num[2]) if num[2] else part)
        else:
            out.append(_token(part))
    return "".join(out)
