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

# Named lines students ask about by name, in any of their spellings — slang
# included («жареная печень» is the Fried Liver Attack). Each pattern maps to
# one exact book name. On production (2026-09-30) the coach, asked «как играть
# против жареной печени», took the quiet Italian on the board for it, then
# explained the fork with a knight jumping f3-d5: the name reached neither the
# book nor the model's tools. Checked in order; the first match wins, so the
# specific lines come before the families they belong to.
_NAMED = [
    (r"жарен\w*\s+печен|печен\w*\s+жарен|фегателло|fegatello|fried[\s-]*liver|фрайд\s*ливер",
     "Italian Game: Two Knights Defense, Fried Liver Attack"),
    (r"траксл|уилкс|wilkes|traxler", "Italian Game: Two Knights Defense, Traxler Counterattack"),
    (r"полерио|polerio", "Italian Game: Two Knights Defense, Polerio Defense"),
    (r"вариант\w*\s+фриц|fritz\s+variation", "Italian Game: Two Knights Defense, Fritz Variation"),
    (r"ульвестад|ulvestad", "Italian Game: Two Knights Defense, Ulvestad Variation"),
    (r"детск\w*\s+мат|scholar'?s\s+mate", "Scholar's Mate"),
    (r"дурацк\w*\s+мат|fool'?s\s+mate", "Barnes Opening: Fool's Mate"),
    (r"(?:мат\w*|ловушк\w*)\s+легал|\bлегаля\b|l[ée]gal'?s?\s+(?:mate|trap)", "Légal Trap"),
    (r"шиллинг|блэкберн|блекберн|blackburne[\s-]+shilling|костич|kosti[cć]", "Blackburne Shilling Trap"),
    (r"пианиссимо|pianissimo", "Italian Game: Giuoco Pianissimo"),
    (r"джуоко|giuoco\s+piano|тих\w+\s+итальянск", "Italian Game: Giuoco Piano"),
    (r"венгерск\w*\s+защит|hungarian\s+defen", "Italian Game: Hungarian Defense"),
    (r"эванс|evans\s+gambit", "Italian Game: Evans Gambit"),
    (r"макс\w*\s+ланге|max\s+lange", "Italian Game: Scotch Gambit, Max Lange Attack"),
    (r"атак\w*\s+маршал|marshall\s+attack", "Ruy Lopez: Marshall Attack"),
    (r"берлинск\w*\s+(?:защит|стен)|berlin\s+(?:defen|wall)", "Ruy Lopez: Berlin Defense"),
    (r"стаффорд|stafford", "Petrov's Defense: Stafford Gambit"),
    (r"х[эе]ллоуин|halloween", "Four Knights Game: Halloween Gambit"),
    (r"югославск\w*\s+атак|yugoslav\s+attack", "Sicilian Defense: Dragon Variation, Yugoslav Attack"),
    (r"ускоренн\w*\s+дракон|accelerated\s+dragon", "Sicilian Defense: Accelerated Dragon"),
    (r"смит[\s-]*морр|гамбит\w*\s+морр|morra\s+gambit", "Sicilian Defense: Smith-Morra Gambit"),
    (r"алапин|alapin", "Sicilian Defense: Alapin Variation"),
    (r"найдорф|najdorf", "Sicilian Defense: Najdorf Variation"),
    (r"дракон|dragon", "Sicilian Defense: Dragon Variation"),
    (r"лондонск|london\s+system", "Queen's Pawn Game: London System"),
    (r"двух\s+коней|two\s+knights", "Italian Game: Two Knights Defense"),
]

# Families by name. Adjectives are matched in the feminine/neuter forms the
# opening names take («сицилианская», «английское начало»), and a surname only
# next to «защита»/«дебют» — «партии Алехина» are a player's games, not the
# Alekhine Defense.
_FAMILIES = [
    # «сицилианка», «испанка», «итальянка», «француженка» — how players say it;
    # «сицилиялық қорғаныс», «итальян/испан партиясы» — Kazakh.
    (r"сицилианск|сицилианк|сицилиял|sicilian", "Sicilian Defense"),
    (r"испанск(?:ая|ую|ой|ие|их)|испанк|испан\s+парти|ruy\s+lopez|spanish\s+(?:game|opening)", "Ruy Lopez"),
    (r"итальянск(?:ая|ую|ой|ие|их)|итальянк|итальян\s+парти|italian\s+(?:game|opening)", "Italian Game"),
    (r"французск(?:ая|ую|ой)\s*(?:защит|парти)?|француженк|француз\s+қорған|french\s+defen", "French Defense"),
    (r"каро[\s-]*канн|caro[\s-]*kann", "Caro-Kann Defense"),
    (r"скандинавск(?:ая|ую|ой)|scandinavian", "Scandinavian Defense"),
    (r"принят\w*\s+ферзев|queen'?s\s+gambit\s+accepted", "Queen's Gambit Accepted"),
    (r"отказанн\w*\s+ферзев|queen'?s\s+gambit\s+declined", "Queen's Gambit Declined"),
    (r"ферзев\w*\s+гамбит|queen'?s\s+gambit", "Queen's Gambit"),
    (r"полуславянск|semi[\s-]*slav", "Semi-Slav Defense"),
    (r"славянск(?:ая|ую|ой)|славянк|slav\s+defen", "Slav Defense"),
    (r"староиндийск|староиндийк|king'?s\s+indian", "King's Indian Defense"),
    (r"новоиндийск|новоиндийк|queen'?s\s+indian", "Queen's Indian Defense"),
    (r"(?:защит\w*|дебют\w*)\s+нимцович|нимцо[\s-]*индийск|nimzo[\s-]*indian", "Nimzo-Indian Defense"),
    (r"(?:защит\w*)\s+грюнфельд|gr[üu]nfeld", "Grünfeld Defense"),
    (r"английск(?:ое|ого|ому|им)\s+начал|английск\w*\s+дебют|english\s+opening", "English Opening"),
    (r"(?:дебют\w*|начал\w*)\s+рети|r[ée]ti\s+opening", "Réti Opening"),
    (r"пирц|уфимцев|pirc", "Pirc Defense"),
    (r"защит\w*\s+алехин|alekhine'?s?\s+defen", "Alekhine Defense"),
    (r"русск(?:ая|ую|ой)\s+парти|защит\w*\s+петров|petrov|petroff|russian\s+game", "Russian Game"),
    (r"шотландск(?:ая|ую|ой|ий)|scotch\s+(?:game|opening|gambit)", "Scotch Game"),
    (r"венск(?:ая|ую|ой|ий)|vienna\s+(?:game|gambit)", "Vienna Game"),
    (r"королевск\w*\s+гамбит|king'?s\s+gambit", "King's Gambit"),
    (r"волжск\w*\s+гамбит|benko", "Benko Gambit"),
    (r"бенони|benoni", "Benoni Defense"),
    (r"голландск(?:ая|ую|ой)|голландк|dutch\s+defen", "Dutch Defense"),
    (r"каталон|catalan", "Catalan Opening"),
    (r"(?:защит\w*)\s+тарраш|tarrasch", "Tarrasch"),
    (r"(?:защит\w*)\s+чигорин|chigorin", "Chigorin"),
    (r"четыр[её]х\s+коней|four\s+knights", "Four Knights Game"),
    (r"тр[её]х\s+коней|three\s+knights", "Three Knights Opening"),
    (r"дебют\w*\s+слона|bishop'?s\s+opening", "Bishop's Opening"),
    (r"защит\w*\s+филидор|philidor\s+defen", "Philidor Defense"),
    (r"(?:систем\w*)\s+колле|colle\s+system", "Colle System"),
    (r"тромповск|trompowsky", "Trompowsky Attack"),
    (r"будапештск|budapest", "Budapest Defense"),
    (r"понциани|ponziani", "Ponziani Opening"),
    (r"энглунд|englund", "Englund Gambit"),
    (r"латышск\w*\s+гамбит|latvian\s+gambit", "Latvian Gambit"),
    (r"датск\w*\s+гамбит|danish\s+gambit", "Danish Gambit"),
    (r"центральн\w*\s+дебют|center\s+game", "Center Game"),
]

_FAMILIES_RE = [(re.compile(r"(?<![а-яёa-z])(?:" + p + ")", re.IGNORECASE), name) for p, name in _FAMILIES]
_NAMED_RE = [(re.compile(r"(?<![а-яёa-z])(?:" + p + ")", re.IGNORECASE), name) for p, name in _NAMED]

# Traps that are not ECO lines, with the defences the coach should show. Moves
# checked with python-chess (each trap ends in mate).
TRAPS = [
    ("C23", "Scholar's Mate", "1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7#"),
    ("C23", "Scholar's Mate, defence 3...g6", "1. e4 e5 2. Bc4 Nc6 3. Qh5 g6 4. Qf3 Nf6"),
    ("C23", "Scholar's Mate, defence 3...Qe7", "1. e4 e5 2. Bc4 Nc6 3. Qh5 Qe7"),
    ("C41", "Légal Trap", "1. e4 e5 2. Nf3 d6 3. Bc4 Bg4 4. Nc3 g6 5. Nxe5 Bxd1 6. Bxf7+ Ke7 7. Nd5#"),
    ("C41", "Légal Trap, declined 5...dxe5 (no mate, a pawn down)", "1. e4 e5 2. Nf3 d6 3. Bc4 Bg4 4. Nc3 g6 5. Nxe5 dxe5 6. Qxg4"),
    ("C50", "Blackburne Shilling Trap", "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nd4 4. Nxe5 Qg5 5. Nxf7 Qxg2 6. Rf1 Qxe4+ 7. Be2 Nf3#"),
    ("C50", "Blackburne Shilling Trap, avoided 4. Nxd4", "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nd4 4. Nxd4 exd4 5. c3"),
]


def named_opening(text: str) -> Optional[str]:
    """The book name of the opening *text* talks about, or None.

    A named line («жареная печень» → the Fried Liver Attack) wins over its
    family; a family («сицилианская») maps to the family name.
    """
    lowered = (text or "").lower().replace("ё", "е").replace("’", "'")
    for rx, name in _NAMED_RE:
        if rx.search(lowered):
            return name
    for rx, name in _FAMILIES_RE:
        if rx.search(lowered):
            return name
    return None

# Russian names of opening families (the part of a book name before ":"), for
# the engine line: the coach named the Ruy Lopez "Puy Lopez" and called one
# position both Italian and Spanish when it named openings by eye (2026-09-29).
RU_FAMILY = {
    "Ruy Lopez": "испанская партия",
    "Italian Game": "итальянская партия",
    "Sicilian Defense": "сицилианская защита",
    "French Defense": "французская защита",
    "Caro-Kann Defense": "защита Каро-Канн",
    "Scandinavian Defense": "скандинавская защита",
    "Queen's Gambit": "ферзевый гамбит",
    "Queen's Gambit Accepted": "принятый ферзевый гамбит",
    "Queen's Gambit Declined": "отказанный ферзевый гамбит",
    "Slav Defense": "славянская защита",
    "Semi-Slav Defense": "полуславянская защита",
    "King's Indian Defense": "староиндийская защита",
    "Queen's Indian Defense": "новоиндийская защита",
    "Nimzo-Indian Defense": "защита Нимцовича",
    "Grünfeld Defense": "защита Грюнфельда",
    "English Opening": "английское начало",
    "Réti Opening": "дебют Рети",
    "Pirc Defense": "защита Пирца–Уфимцева",
    "Alekhine Defense": "защита Алехина",
    "Russian Game": "русская партия (защита Петрова)",
    "Petrov's Defense": "русская партия (защита Петрова)",
    "Scotch Game": "шотландская партия",
    "Vienna Game": "венская партия",
    "King's Gambit": "королевский гамбит",
    "King's Gambit Accepted": "принятый королевский гамбит",
    "King's Gambit Declined": "отказанный королевский гамбит",
    "Benko Gambit": "волжский гамбит",
    "Benoni Defense": "защита Бенони",
    "Dutch Defense": "голландская защита",
    "Catalan Opening": "каталонское начало",
    "London System": "лондонская система",
    "Bishop's Opening": "дебют слона",
    "Four Knights Game": "партия четырёх коней",
    "Three Knights Opening": "партия трёх коней",
    "Philidor Defense": "защита Филидора",
    "Modern Defense": "современная защита",
    "Colle System": "система Колле",
    "Trompowsky Attack": "атака Тромповского",
    "Budapest Defense": "будапештская защита",
    "Center Game": "центральный дебют",
    "Queen's Pawn Game": "дебют ферзевых пешек",
    "King's Pawn Game": "дебют королевской пешки",
    "Ponziani Opening": "дебют Понциани",
    "Englund Gambit": "гамбит Энглунда",
    "Bird Opening": "дебют Берда",
    "Nimzo-Larsen Attack": "дебют Нимцовича–Ларсена",
    "Owen Defense": "защита Оуэна",
    "Horwitz Defense": "защита Горвица",
    "Elephant Gambit": "гамбит слона",
    "Latvian Gambit": "латышский гамбит",
    "Danish Gambit": "датский гамбит",
    "Indian Defense": "индийская защита",
    "Old Indian Defense": "староиндийская защита (старая)",
    "Bogo-Indian Defense": "защита Боголюбова",
}


def _position_key(board) -> str:
    """Placement, side to move, castling and en passant — the clocks do not name an opening."""
    return " ".join(board.fen().split()[:4])


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
        self._by_position: Optional[dict[str, tuple[str, str, str]]] = None

    # ── lookups ──────────────────────────────────────────────────────
    def by_eco(self, eco: str) -> list[tuple[str, str, str]]:
        return sorted(self._by_eco.get((eco or "").upper().strip(), []), key=lambda e: len(_split_moves(e[2])))

    def by_name(self, name: str, limit: Optional[int] = None) -> list[tuple[str, str, str]]:
        """Lines whose name contains *name* (case-insensitive, RU aliases and slang honoured).

        The line named exactly comes first, then lines where the name starts a
        part of the book name, then the rest: «Fried Liver» is the Fried Liver
        Attack, not the shorter Anti-Fried Liver Defense (3...h6).
        """
        key = (name or "").strip().lower()
        if not key:
            return []
        named = named_opening(key)
        if named:
            key = named.lower()
        else:
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

        def rank(entry) -> tuple:
            full = entry[1].lower().replace("’", "'")
            parts = [p.strip() for p in re.split(r"[:,]", full)]
            if full == key_norm:
                closeness = 0
            elif any(p.startswith(key_norm) for p in parts) or full.startswith(key_norm):
                closeness = 1
            else:
                closeness = 2
            return (closeness, len(_split_moves(entry[2])), entry[1])

        hits.sort(key=rank)
        return hits[:limit] if limit else hits

    def exact(self, name: str) -> Optional[tuple[str, str, str]]:
        """The shortest line named exactly *name*, or None."""
        found = [e for e in self.entries if e[1] == name]
        return min(found, key=lambda e: len(_split_moves(e[2]))) if found else None

    def branches(self, name: str, pgn: str, points: int = 5, per_point: int = 4) -> list[dict]:
        """Named book lines of the same branch that leave *pgn* — where a side
        can play something else — and named continuations after its last move.

        Only lines of *name*'s parent count: for «Two Knights Defense, Fried
        Liver Attack» that is the Two Knights Defense (Traxler, Polerio, Fritz…),
        not every opening that starts 1.e4 e5. Each item is {"ply", "move",
        "name", "eco", "line"}: *ply* indexes the differing move (0 = White's
        first). The last *points* branch points, in move order, the shortest
        line per differing move.
        """
        base = name.rsplit(",", 1)[0] if "," in name else name.split(":", 1)[0]
        seq = _split_moves(pgn)
        found: dict[tuple[int, str], tuple[str, str, str]] = {}
        for entry in self.entries:
            if entry[1] == name or not entry[1].startswith(base):
                continue
            moves = _split_moves(entry[2])
            k = 0  # the first ply where the entry leaves the line (or runs past it)
            while k < len(seq) and k < len(moves) and moves[k] == seq[k]:
                k += 1
            if k >= len(moves):
                continue  # a prefix of the line
            key = (k, moves[k])
            old = found.get(key)
            if old is None or len(_split_moves(entry[2])) < len(_split_moves(old[2])):
                found[key] = entry
        latest = sorted({k for k, _ in found}, reverse=True)[:points]
        items = []
        for k in sorted(latest):
            at_k = sorted(((m, e) for (kk, m), e in found.items() if kk == k),
                          key=lambda me: (len(_split_moves(me[1][2])), me[1][1]))
            for move, entry in at_k[:per_point]:
                items.append({"ply": k, "move": move, "name": entry[1], "eco": entry[0], "line": entry[2]})
        return items

    def by_position(self, fen: str) -> Optional[dict]:
        """The book line that ends exactly in *fen*'s position (any move order), or None.

        The index — every line replayed once, ~0.2 s for the 3,800 lines — is
        built on first use. Where several lines reach one position the shortest
        (most general) name wins.
        """
        import chess

        if self._by_position is None:
            index: dict[str, tuple[str, str, str]] = {}
            for entry in self.entries:
                board = chess.Board()
                try:
                    for san in _split_moves(entry[2]):
                        board.push_san(san)
                except ValueError:
                    continue
                key = _position_key(board)
                old = index.get(key)
                if old is None or len(_split_moves(entry[2])) < len(_split_moves(old[2])):
                    index[key] = entry
            self._by_position = index
        try:
            key = _position_key(chess.Board(fen))
        except ValueError:
            return None
        entry = self._by_position.get(key)
        if entry is None:
            return None
        family = entry[1].split(":")[0].strip()
        found = {"eco": entry[0], "name": entry[1], "book_line": entry[2]}
        if family in RU_FAMILY:
            found["name_ru"] = RU_FAMILY[family]
        return found

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
                return OpeningBook(entries + list(TRAPS), directory)
    logger.warning("opening book: TSV directory not found, using the embedded fallback")
    return OpeningBook(list(_FALLBACK) + list(TRAPS), "embedded")
