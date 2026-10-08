"""Moves of the position named in a message, in any of the usual written forms (2026-10-08).

The client asked «Что если я пойду Се3?» — Cyrillic С and Cyrillic е — and the
coach saw no move: the engine never looked at it and the model answered from
its head (production, 2026-10-07). Of 48 everyday ways to write four moves of
that position the old patterns read 22: «слон на е3» with the е of a Russian
keyboard, «с1-е3», «c1e3», «Ce3» with a Latin C, «се3», «Кб5», «ф6», «ферзь бьёт
h5», «съем пешку h5» named nothing.

Turned around here: the text is read for square tokens in any spelling (Latin,
Cyrillic look-alikes and transliteration: а б в с д е ф г х), with what stands
before them — a piece letter (K Q R B N, К Кр С Л Ф, a Latin C for С), a
from-square, a piece word (слон, слоном, bishop, піл…) or a capture verb — and
each reading counts only when exactly one LEGAL move of the side to move fits it.
A piece standing on the square named with it («конь f6 висит») is a
description, not a move. No model call, no network: microseconds.
"""

from __future__ import annotations

import re
from typing import Optional

import chess

# A file letter as typed: Latin, Cyrillic look-alikes (а с е в), transliteration (б д ф г х), э/ц.
_FILE = {
    "a": "a", "b": "b", "c": "c", "d": "d", "e": "e", "f": "f", "g": "g", "h": "h",
    "а": "a", "б": "b", "в": "b", "с": "c", "ц": "c", "д": "d", "е": "e", "э": "e", "ф": "f", "г": "g", "х": "h",
}
_FILE_CHARS = "a-hA-HабвсцдеэфгхАБВСЦДЕЭФГХ"
# A piece letter right before a square: SAN, Russian notation, a Latin C for С, lower case on a phone.
_PIECE_LETTER = {
    "K": chess.KING, "Q": chess.QUEEN, "R": chess.ROOK, "B": chess.BISHOP, "N": chess.KNIGHT,
    "Кр": chess.KING, "кр": chess.KING, "К": chess.KNIGHT, "к": chess.KNIGHT, "С": chess.BISHOP, "с": chess.BISHOP,
    "C": chess.BISHOP, "Л": chess.ROOK, "л": chess.ROOK, "Ф": chess.QUEEN, "ф": chess.QUEEN,
}
# An upper-case piece letter may stand apart from its square («С е3»); a lower-case one only right
# against it («се3», «кс3») — «конь с f3 на d5», «к e5» are prepositions.
_SQUARE = (r"(?<![A-Za-zА-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі])"
           r"(?:(?P<pu>Кр|[KQRBNКСЛФC])(?P<su>[ \-–:xх×]?)(?=[" + _FILE_CHARS + r"][1-8](?![0-9]))"
           r"|(?P<pl>кр|[кслф])(?P<sl>[\-–:xх×]?)(?=[" + _FILE_CHARS + r"][1-8](?![0-9])))?"
           r"(?P<file>[" + _FILE_CHARS + r"])(?P<rank>[1-8])(?![0-9])")
_SQUARE_RE = re.compile(_SQUARE)

# Piece words (Russian, English, Kazakh), every case form.
_PIECE_WORDS = [
    (chess.KING, r"корол[ьяюеё]м?|корол[её]м|king|патша\w*"),
    (chess.QUEEN, r"ферз[ьяюеё]м?|ферз[её]м|queen|уәзір\w*"),
    (chess.ROOK, r"ладь[яюиеё]й?|ладь[её]й|ладья|rook|тура\w*"),
    (chess.BISHOP, r"слон\w{0,3}|bishop|піл\w*"),
    (chess.KNIGHT, r"кон[ьяюеё]м?|кон[её]м|knight|ат(?:пен|ты|қа)?"),
    (chess.PAWN, r"пешк\w{0,3}|пешечк\w*|pawn|сарбаз\w*"),
]
_PIECE_WORD_RE = re.compile(
    r"(?<![а-яёa-zәғқңөұүһі])(?:" + "|".join(f"(?P<w{t}>{p})" for t, p in _PIECE_WORDS) + r")(?![а-яёa-zәғқңөұүһі])",
    re.IGNORECASE)
_CAPTURE_VERB = re.compile(
    r"(?<![а-яёa-z])(?:бь[её]т|бьют|бить|побить|бью|бей|берёт|берет|бер[уё]|брать|взять|возьм\w*|возьми|съ[еє]\w*|съем|"
    r"забира\w*|забер\w*|забрать|руб\w*|срубить|takes?|captures?|grab)(?![а-яёa-z])", re.IGNORECASE)
_CUE = re.compile(
    r"(?<![а-яёa-z])(?:если|пойд\w*|пойти|сыгра\w*|сходи\w*|ход\w*|хочу|можно|давай|поставл\w*|постав\w*|двин\w*|"
    r"переве\w*|отве\w*|увед\w*|прыгн\w*|пойдёт|играть|what\s+if|play|move|put|go|егер|жүр\w*)(?![а-яёa-z])",
    re.IGNORECASE)


def _tokens(text: str) -> list[dict]:
    """Square tokens: {at, end, square, piece (a type or None), capture, raw}."""
    out = []
    for m in _SQUARE_RE.finditer(text):
        letter = m["pu"] or m["pl"]
        piece = _PIECE_LETTER.get(letter) if letter else None
        square = chess.parse_square(_FILE[m["file"].lower()] + m["rank"])
        sep = m["su"] or m["sl"] or ""
        out.append({"at": m.start(), "end": m.end(), "square": square, "piece": piece,
                    "capture": sep in (":", "x", "х", "×"), "raw": m.group(0)})
    return out


def _word_piece(m) -> Optional[int]:
    for t, _ in _PIECE_WORDS:
        if m.group(f"w{t}"):
            return t
    return None


def _fits(board: chess.Board, ptype: Optional[int], to: int, frm: Optional[int]) -> list[chess.Move]:
    moves = [mv for mv in board.legal_moves
             if mv.to_square == to and (frm is None or mv.from_square == frm)
             and (ptype is None or board.piece_type_at(mv.from_square) == ptype)
             and mv.promotion in (None, chess.QUEEN)]
    # «побить пешку d5» right after d7-d5: en passant lands on d6.
    if not moves and ptype in (None, chess.PAWN) and board.ep_square is not None:
        victim = board.ep_square + (-8 if board.turn == chess.WHITE else 8)
        if to == victim:
            moves = [mv for mv in board.legal_moves if board.is_en_passant(mv) and (frm is None or mv.from_square == frm)]
    return moves


def _describes(board: chess.Board, ptype: Optional[int], square: int) -> bool:
    """«конь f6 висит»: the named piece stands on the square — a piece, not a move."""
    here = board.piece_at(square)
    return here is not None and ptype is not None and here.piece_type == ptype


def named_moves(text: str, board: chess.Board) -> list[dict]:
    """Legal moves of *board* that *text* names: [{move, san, at, words}], in order of appearance."""
    if not text or board is None:
        return []
    text = text.replace("ё", "е").replace("Ё", "Е")
    low = text.lower()
    toks = _tokens(text)
    found: list[dict] = []
    used: set[int] = set()  # token indexes already read as part of a move

    def take(ptype, to, frm, at, words, *, capture=False, describe_ok=False):
        if not describe_ok and not capture and frm is None and _describes(board, ptype, to):
            return False
        fits = _fits(board, ptype, to, frm)
        if len(fits) != 1:
            return False
        mv = fits[0]
        if any(f["move"] == mv for f in found):
            return True
        found.append({"move": mv, "san": board.san(mv), "at": at, "words": words.strip()})
        return True

    # 1. from-to: «c1-e3», «c1e3», «Сс1-е3», «e2—e4», «c1:e3»
    for i, (a, b) in enumerate(zip(toks, toks[1:])):
        gap = text[a["end"]:b["at"]]
        # an explicit separator or none at all: «1.e4 e5» is a line, not a move from e4 to e5
        if b["piece"] is None and re.fullmatch(r"\s?[\-–—:xх×]\s?|", gap):
            if take(a["piece"], b["square"], a["square"], a["at"], text[a["at"]:b["end"]], describe_ok=True):
                used.update({i, i + 1})
    # 2. a piece letter with its square: «Се3», «Кхе5», «Ce3», «Фh5», «Кр:d5»
    for i, t in enumerate(toks):
        if i in used or t["piece"] is None:
            continue
        if take(t["piece"], t["square"], None, t["at"], t["raw"], capture=t["capture"]):
            used.add(i)
    # 3. a piece word with a square after it: «слон на е3», «слоном е3», «ферзь бьёт h5», «конь с f3 на d5»
    for wm in _PIECE_WORD_RE.finditer(low):
        ptype = _word_piece(wm)
        nxt = [(i, t) for i, t in enumerate(toks) if t["at"] >= wm.end() and i not in used and t["piece"] is None]
        if not nxt:
            continue
        i, t = nxt[0]
        between = low[wm.end():t["at"]]
        if len(between) > 40 or re.search(r"[.!?;]", between):
            continue
        frm = None
        m_from = re.fullmatch(r"\s*(?:с|from|)\s*", between)
        if m_from and len(nxt) > 1:
            j, t2 = nxt[1]
            if re.fullmatch(r"\s*(?:на|в|to)\s*", low[t["end"]:t2["at"]]):
                if take(ptype, t2["square"], t["square"], wm.start(), low[wm.start():t2["end"]], describe_ok=True):
                    used.update({i, j})
                continue
        capture = bool(_CAPTURE_VERB.search(between))
        # A piece word right before a square names the piece standing there unless the student is asking about a
        # move («если», «пойду», «хочу», «?»): «конь f6 висит» stays a piece.
        cue = bool(_CUE.search(low[max(0, wm.start() - 40):wm.start()]) or _CUE.search(between)
                   or capture or re.search(r"(?:на|в|to|on|onto)\s*$", between) or "?" in low[t["end"]:t["end"] + 3])
        if not cue:
            continue
        if take(ptype, t["square"], frm, wm.start(), low[wm.start():t["end"]], capture=capture):
            used.add(i)
    # 4. a capture verb with a square: «съем пешку h5», «взять на h5», «бью на f7 конём»
    for vm in _CAPTURE_VERB.finditer(low):
        nxt = [(i, t) for i, t in enumerate(toks) if t["at"] >= vm.end() and i not in used]
        if not nxt:
            continue
        i, t = nxt[0]
        between = low[vm.end():t["at"]]
        if len(between) > 30 or re.search(r"[.!?;]", between):
            continue
        instrument = None
        for wm in _PIECE_WORD_RE.finditer(low[t["end"]:t["end"] + 25]):
            instrument = _word_piece(wm)  # «… h5 ферзём»
            break
        if instrument is None:
            for wm in _PIECE_WORD_RE.finditer(low[max(0, vm.start() - 25):vm.start()]):
                instrument = _word_piece(wm)  # «ферзём взять h5»
        target = board.piece_at(t["square"])
        if target is None or target.color == board.turn:
            if not (instrument in (None, chess.PAWN) and board.ep_square is not None):
                continue
        if take(instrument, t["square"], None, vm.start(), low[vm.start():t["end"]], capture=True):
            used.add(i)
    # 5. a bare square asked about is a pawn move: «а если f6?», «ф6?», «пойду b4»
    for i, t in enumerate(toks):
        if i in used or t["piece"] is not None:
            continue
        before = low[max(0, t["at"] - 40):t["at"]]
        if re.search(r"(?:на|в|поле|клетк\w*|to|on|square)\s*$", before):
            continue  # «отступить на b3» — a square, not a pawn move
        if _PIECE_WORD_RE.search(before[-20:]) and not re.search(r"пешк|pawn|сарбаз", before[-20:]):
            continue  # «конь пойдёт b3»: a piece's square
        asked = bool(_CUE.search(before)) or "?" in low[t["end"]:t["end"] + 3] or len(re.findall(r"\w+", low)) <= 4
        if asked and take(chess.PAWN, t["square"], None, t["at"], t["raw"]):
            used.add(i)
    found.sort(key=lambda f: f["at"])
    return found
