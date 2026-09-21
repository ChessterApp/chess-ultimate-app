"""Opening reference: the 3,800-line ECO book from ``backend/data/openings/*.tsv``.

Replaces the 33 hand-typed ECO codes the coach used to know. The TSVs
(``eco\\tname\\tpgn``, one named line each, Lichess/ECO naming) are the same
files the game reviewer uses for book-move detection, so the coach and the
review agree on names.

Lookups: by ECO code, by name (English, with Russian aliases for the openings
students actually ask about), and by move sequence (longest matching book
prefix — "what opening is this?"). Loaded once, lazily; if the directory is
missing the embedded fallback keeps the tool alive.
"""

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Backend data dir on the production host; the repo-relative path covers a
# monorepo checkout (tests, local runs). Override with OPENINGS_TSV_DIR.
_CANDIDATE_DIRS = [
    os.environ.get("OPENINGS_TSV_DIR", ""),
    "/root/chess-app/backend/data/openings",
    str(Path(__file__).resolve().parents[2] / "backend" / "data" / "openings"),
]

# Russian (and a few Kazakh) names → English book names. Values are matched as
# substrings of the TSV name, so "Сицилианская" finds every Sicilian line and
# the family's shortest line is reported as the main line.
RU_ALIASES = {
    "сицилианск": "Sicilian Defense",
    "испанск": "Ruy Lopez",
    "итальянск": "Italian Game",
    "французск": "French Defense",
    "каро-канн": "Caro-Kann Defense",
    "каро канн": "Caro-Kann Defense",
    "скандинавск": "Scandinavian Defense",
    "ферзевый гамбит": "Queen's Gambit",
    "ферзевого гамбита": "Queen's Gambit",
    "принятый ферзевый": "Queen's Gambit Accepted",
    "отказанный ферзевый": "Queen's Gambit Declined",
    "славянск": "Slav Defense",
    "полуслав": "Semi-Slav Defense",
    "староиндийск": "King's Indian Defense",
    "новоиндийск": "Queen's Indian Defense",
    "нимцович": "Nimzo-Indian Defense",
    "грюнфельд": "Grünfeld Defense",
    "английск": "English Opening",
    "рети": "Réti Opening",
    "пирц": "Pirc Defense",
    "уфимцев": "Pirc Defense",
    "алехин": "Alekhine Defense",
    "русская парти": "Russian Game",
    "петров": "Russian Game",
    "шотландск": "Scotch Game",
    "венск": "Vienna Game",
    "королевский гамбит": "King's Gambit",
    "волжск": "Benko Gambit",
    "бенони": "Benoni Defense",
    "голландск": "Dutch Defense",
    "каталон": "Catalan Opening",
    "лондонск": "London System",
    "дракон": "Sicilian Defense: Dragon",
    "найдорф": "Sicilian Defense: Najdorf",
    "берлинск": "Ruy Lopez: Berlin Defense",
    "челябинск": "Sicilian Defense: Lasker-Pelikan Variation, Sveshnikov",
    "свешников": "Sicilian Defense: Lasker-Pelikan Variation, Sveshnikov",
    "шевенинген": "Sicilian Defense: Scheveningen",
    "тарраш": "Tarrasch",
    "чигорин": "Chigorin",
    "двух коней": "Italian Game: Two Knights Defense",
    "гамбит эванса": "Italian Game: Evans Gambit",
    "дебют слона": "Bishop's Opening",
    "четырёх коней": "Four Knights Game",
    "четырех коней": "Four Knights Game",
    "филидор": "Philidor Defense",
    "модерн": "Modern Defense",
    "современная защита": "Modern Defense",
    "колле": "Colle System",
    "тромповск": "Trompowsky Attack",
    "будапештск": "Budapest Defense",
    "защита двух коней": "Italian Game: Two Knights Defense",
    "центральный дебют": "Center Game",
    "дебют ферзевых пешек": "Queen's Pawn Game",
    "дебют королевской пешки": "King's Pawn Game",
    "гамбит": "Gambit",
}

# Embedded fallback when the TSV directory is unavailable.
_FALLBACK = [
    ("B20", "Sicilian Defense", "1. e4 c5"),
    ("B90", "Sicilian Defense: Najdorf Variation", "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6"),
    ("C00", "French Defense", "1. e4 e6"),
    ("B10", "Caro-Kann Defense", "1. e4 c6"),
    ("C50", "Italian Game", "1. e4 e5 2. Nf3 Nc6 3. Bc4"),
    ("C60", "Ruy Lopez", "1. e4 e5 2. Nf3 Nc6 3. Bb5"),
    ("C65", "Ruy Lopez: Berlin Defense", "1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6"),
    ("D30", "Queen's Gambit Declined", "1. d4 d5 2. c4 e6"),
    ("D10", "Slav Defense", "1. d4 d5 2. c4 c6"),
    ("E60", "King's Indian Defense", "1. d4 Nf6 2. c4 g6"),
    ("E20", "Nimzo-Indian Defense", "1. d4 Nf6 2. c4 e6 3. Nc3 Bb4"),
    ("D80", "Grünfeld Defense", "1. d4 Nf6 2. c4 g6 3. Nc3 d5"),
    ("A10", "English Opening", "1. c4"),
    ("A04", "Réti Opening", "1. Nf3"),
]

_MOVE_NUM_RE = re.compile(r"\d+\.(\.\.)?")


def _split_moves(pgn: str) -> tuple[str, ...]:
    """'1. e4 c5 2. Nf3' → ('e4', 'c5', 'Nf3')."""
    return tuple(tok for tok in _MOVE_NUM_RE.sub(" ", pgn or "").split() if tok not in ("*", "1-0", "0-1", "1/2-1/2"))


class OpeningBook:
    def __init__(self, entries: list[tuple[str, str, str]], source: str):
        self.entries = entries
        self.source = source
        self._by_eco: dict[str, list[tuple[str, str, str]]] = {}
        self._by_moves: dict[tuple[str, ...], tuple[str, str, str]] = {}
        for entry in entries:
            self._by_eco.setdefault(entry[0], []).append(entry)
            self._by_moves.setdefault(_split_moves(entry[2]), entry)
        self._max_depth = max((len(k) for k in self._by_moves), default=0)

    # ── lookups ──────────────────────────────────────────────────────
    def by_eco(self, eco: str) -> list[tuple[str, str, str]]:
        return sorted(self._by_eco.get((eco or "").upper().strip(), []), key=lambda e: len(_split_moves(e[2])))

    def by_name(self, name: str, limit: Optional[int] = None) -> list[tuple[str, str, str]]:
        """Lines whose name contains *name* (case-insensitive, RU aliases honoured)."""
        key = (name or "").strip().lower()
        if not key:
            return []
        for alias, english in RU_ALIASES.items():
            if alias in key:
                key = english.lower()
                break
        key_norm = key.replace("’", "'")
        hits = [e for e in self.entries if key_norm in e[1].lower().replace("’", "'")]
        if not hits:
            # Word-wise fallback: every word of the query appears in the name.
            words = [w for w in re.split(r"[\s:,]+", key_norm) if len(w) > 2]
            if words:
                hits = [e for e in self.entries if all(w in e[1].lower() for w in words)]
        hits.sort(key=lambda e: (len(_split_moves(e[2])), e[1]))
        return hits[:limit] if limit else hits

    def identify(self, moves) -> Optional[dict]:
        """Longest book line that is a prefix of *moves* (SAN list or PGN string)."""
        seq = _split_moves(moves) if isinstance(moves, str) else tuple(moves or ())
        for depth in range(min(len(seq), self._max_depth), 0, -1):
            entry = self._by_moves.get(seq[:depth])
            if entry:
                return {
                    "eco": entry[0],
                    "name": entry[1],
                    "book_line": entry[2],
                    "book_plies": depth,
                    "out_of_book_after": depth,
                    "total_plies": len(seq),
                }
        return None


def _load_dir(directory: str) -> list[tuple[str, str, str]]:
    entries = []
    for path in sorted(Path(directory).glob("*.tsv")):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) != 3 or parts[0] == "eco":
                    continue
                entries.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    return entries


@lru_cache(maxsize=1)
def get_book() -> OpeningBook:
    for directory in _CANDIDATE_DIRS:
        if directory and Path(directory).is_dir():
            entries = _load_dir(directory)
            if entries:
                logger.info("opening book: %d lines from %s", len(entries), directory)
                return OpeningBook(entries, directory)
    logger.warning("opening book: TSV directory not found, using the embedded fallback")
    return OpeningBook(list(_FALLBACK), "embedded")
