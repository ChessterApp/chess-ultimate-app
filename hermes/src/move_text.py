"""A move in the student's words, read one way on every path (2026-10-15).

Thirteen readers turned text into moves — the game pre-step, the voice game, make_game_move, the
«а если…» check, the past move by number, the answer check — each with its own table of Russian
letters and its own idea of what a move looks like. A form one of them read, another did not: «слон си
четыре» was a move only in a game, «конь ф3» was read as the pawn move f3, «Кхе5» as «Nhe5», «g1-f3» as
Nf3 and f3 at once (inventory 2026-10-15). Here is the one reading: the text is normalised once
(squares said aloud, castling with zeros or a Cyrillic «О», figurines), then every legal move of the
position it names is found by src/move_matcher.named_moves, whose readings all end on the board.
"""

from __future__ import annotations

import re
from typing import Optional

import chess

# File letters as typed or transliterated: Latin, Cyrillic look-alikes and the Russian names of letters.
FILES = {
    "a": "a", "b": "b", "c": "c", "d": "d", "e": "e", "f": "f", "g": "g", "h": "h",
    "а": "a", "б": "b", "в": "b", "с": "c", "ц": "c", "д": "d", "е": "e", "э": "e", "ф": "f", "г": "g", "х": "h",
}

# Squares said aloud, as speech recognition writes them: «си четыре», «це 4», «эф три», «е два е четыре»
# (voice, 2026-10-14: «слон си четыре» was no move).
# …and the bare Russian letters the transcription writes for a file said quickly («с шесть», «д четыре»,
# «г пять»), plus «за» — what it heard for «це» on Alexander's phone («конь за шесть» = Nc6, 25.10).
_SPOKEN_FILE = {
    "a": ("а", "эй"), "b": ("бэ", "бе", "би", "б"), "c": ("цэ", "це", "си", "сэ", "с", "за"), "d": ("дэ", "де", "ди", "д"),
    "e": ("е", "э"), "f": ("эф", "эфф", "ф"), "g": ("гэ", "ге", "же", "джи", "г", "ж"), "h": ("аш", "аша", "ха", "эйч", "х"),
}
_SPOKEN_RANK = {"один": "1", "одна": "1", "раз": "1", "два": "2", "две": "2", "три": "3", "четыре": "4",
                "четыри": "4", "пять": "5", "шесть": "6", "семь": "7", "восемь": "8"}
_FILE_WORD = {w: f for f, words in _SPOKEN_FILE.items() for w in words}
# Letter names that are also ordinary words («а три хода назад», «же», «ха»): a square only next to a piece
# word or a move cue, or in a short utterance.
_AMBIGUOUS = {"а", "е", "э", "же", "ха", "с", "за", "д", "г", "ж", "х", "б", "ф"}
_SPOKEN_SQUARE = re.compile(
    r"(?<![\w-])(" + "|".join(sorted(list(_FILE_WORD) + list("abcdefgh"), key=len, reverse=True)) + r")[\s-]*("
    + "|".join(sorted(_SPOKEN_RANK, key=len, reverse=True)) + r"|[1-8])(?![\w-])",
    re.IGNORECASE)
_MOVE_CONTEXT = re.compile(
    r"(?:кон\w*|слон\w*|лад\w*|ферз\w*|корол\w*|пешк\w*|knight|bishop|rook|queen|king|pawn|на|ход\w*|сыгра\w*|"
    r"пойд\w*|иду|бью|бер\w*|возьм\w*|если|давай)\W*$", re.IGNORECASE)


def spoken_squares(text: str) -> str:
    """*text* with squares said in words written as squares («слон си четыре» → «слон c4»)."""
    t = text or ""
    short = len(t.split()) <= 6

    def sub(m: "re.Match") -> str:
        word = m.group(1).lower().replace("ё", "е")
        file = word if word in "abcdefgh" else _FILE_WORD.get(word)
        rank = _SPOKEN_RANK.get(m.group(2).lower(), m.group(2))
        if word in _AMBIGUOUS and m.group(2).lower() in _SPOKEN_RANK and not short \
                and not _MOVE_CONTEXT.search(t[max(0, m.start() - 20):m.start()]):
            return m.group(0)
        return f"{file}{rank}" if file and rank else m.group(0)

    t = _SPOKEN_SQUARE.sub(sub, t)
    # «e2 e4», «e2 - e4» — a move said from square to square
    return re.sub(r"(?<![\w-])([a-h][1-8])\s*[-–—]?\s+([a-h][1-8])(?![\w-])", r"\1\2", t)


_FIGURINES = str.maketrans({"♔": "K", "♚": "K", "♕": "Q", "♛": "Q", "♖": "R", "♜": "R",
                            "♗": "B", "♝": "B", "♘": "N", "♞": "N"})


def normalize(text: str) -> str:
    """The student's text with moves in one spelling: ё → е, figurines, castling with zeros or a Cyrillic
    «О» as O-O / O-O-O, squares said aloud as squares."""
    t = (text or "").replace("ё", "е").replace("Ё", "Е").translate(_FIGURINES)
    t = re.sub(r"(?<![0-9A-Za-zА-Яа-я-])[0OО]-[0OО]-[0OО](?![0-9A-Za-zА-Яа-я-])", "O-O-O", t)
    t = re.sub(r"(?<![0-9A-Za-zА-Яа-я-])[0OО]-[0OО](?![0-9A-Za-zА-Яа-я-])", "O-O", t)
    return spoken_squares(t)


def moves_in(text: str, board: chess.Board) -> list[dict]:
    """Every legal move of *board* that *text* names, in order: [{move, san, at, words}]."""
    from src.move_matcher import named_moves

    if not text or board is None:
        return []
    return named_moves(normalize(text), board)


def one_move(text: str, board: chess.Board) -> Optional[str]:
    """The one legal move *text* names, in SAN — written in any notation (SAN, long, UCI, Russian) or in
    words; None when it names none or several."""
    from src.notation import russian_to_san

    t = normalize(text).strip()
    if not t:
        return None
    def notation(candidate: str) -> Optional[str]:
        try:
            return board.san(board.parse_san(candidate))
        except ValueError:
            pass
        try:
            mv = chess.Move.from_uci(re.sub(r"[-–—:x]", "", candidate).lower())
            if mv in board.legal_moves:
                return board.san(mv)
        except ValueError:
            pass
        return None

    for candidate in (t, t.rstrip("+#!?")):
        san = notation(candidate)
        if san:
            return san
    # Words, Russian letters, a Latin C for С, lower case: «сс4» is the bishop, not the c-pawn.
    found = moves_in(t, board)
    if len(found) == 1:
        return found[0]["san"]
    return None if found else notation(russian_to_san(t.rstrip("+#!?")))
