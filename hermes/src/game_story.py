"""The facts of a loaded game, computed from its moves — what the coach tells of the game is told from these (06.11).

The live run of 04.11 on production (04.11-2): the coach loaded the database games it was asked for and told them
from its own reading of the score — «партия перешла в ладейно-пешечное окончание» about rook and knight against rook
and bishop (Nakamura – Sindarov, 3708548), «белые выиграли ферзя и ладью за ферзя и слона» where it was for a queen and
a knight (Nakamura – Carlsen, 3686097), «лишняя пешка» that lasted one move. The move list of get_game_pgn says who
took what, one move at a time; adding it up into the material, the trades and the ending was left to the model.

Here the server adds it up, exactly, for every ply of the game's main line:

  * the material balance (pawn 1, knight 3, bishop 3, rook 5, queen 9) and how long each balance held — a lead that
    lasted one move is said as such;
  * the captures, grouped into exchanges (captures at most ``GROUP_GAP`` plies apart) and told as pairs: what each
    side took, the same pieces as a trade, the rest as «won X for Y»;
  * the pieces each side had besides the king — the ending, by its name (a rook ending is rooks and pawns only);
  * the key moments: promotions, the biggest lead, how the game ended.

``GameStory.facts()`` is that as text, for the model (src/tools/twic_search.get_game_pgn, the turn's board note) and
for the rewrite of a wrong sentence; ``story_issues`` reads the same claims in a sentence that tells the game — the
ending named, a trade, a lead held — and says where the sentence and the game differ (src/answer_check_db, under
COACH_LOADED_GAME_CHECK). A claim is judged only when the game decides it: an ending the game never reached, a trade
no exchange of the game made, a lead the game never held (or held for less than ``STABLE_PLIES`` when the sentence
says it was kept, or not at the end when it says «в итоге»). Generic sentences («в ладейных эндшпилях…»), denials,
conditions and other games are not read. Never raises.
"""

from __future__ import annotations

import io
import logging
import re
from collections import Counter
from typing import Optional

import chess
import chess.pgn

logger = logging.getLogger(__name__)

VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
NAME = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook", chess.QUEEN: "queen",
        chess.KING: "king"}
PIECES = (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
# Captures this many plies apart (or closer) are one exchange: 20...Bxd5 21.Nxd8 Bxf3 22.Ne6 Bd5 23.Nxf8 Kxf8.
GROUP_GAP = 3
# A lead «kept» («остались с лишней пешкой», «долго играли с лишней пешкой») held for at least this many positions
# (two moves); 18.Qxd5 … 19...Nxf2 held three.
STABLE_PLIES = 4
# The ending's phases are told from the first position with at most this many pieces (besides kings and pawns) on the
# board, and always the last ones.
ENDING_PIECES = 6
MAX_PHASES = 6
MAX_EXCHANGES = 40


def _plural(word: str, n: int) -> str:
    if n == 1:
        return word
    return {"ply": "plies"}.get(word, word + "s")


def _side_list(pieces: tuple) -> str:
    """(QUEEN, ROOK, ROOK, KNIGHT) → «queen, 2 rooks and knight»."""
    if not pieces:
        return "no pieces"
    counts = Counter(pieces)
    parts = [NAME[t] if counts[t] == 1 else f"{counts[t]} {_plural(NAME[t], counts[t])}" for t in PIECES if counts.get(t)]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _list(types: list) -> str:
    """[ROOK, KNIGHT, PAWN, PAWN] → «a rook, a knight and 2 pawns»."""
    if not types:
        return "nothing"
    counts = Counter(types)
    parts = []
    for t in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
        n = counts.get(t, 0)
        if n:
            parts.append(f"a {NAME[t]}" if n == 1 else f"{n} {_plural(NAME[t], n)}")
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _pieces(board: chess.Board, color: bool) -> tuple:
    """The side's pieces besides the king and the pawns, strongest first: (QUEEN, ROOK, ROOK, KNIGHT)."""
    return tuple(t for t in PIECES for _ in board.pieces(t, color))


def _points(board: chess.Board, color: bool) -> int:
    return sum(VALUE[t] * len(board.pieces(t, color)) for t in VALUE)


def ending_name(board: chess.Board) -> str:
    """The ending's name by the pieces on the board: «a rook ending», «rook and knight v rook and bishop»."""
    white, black = _pieces(board, chess.WHITE), _pieces(board, chess.BLACK)
    kinds = set(white) | set(black)
    if not kinds:
        return "a pawn ending (kings and pawns only)"
    single = {chess.ROOK: "a rook ending (rooks and pawns only)", chess.QUEEN: "a queen ending (queens and pawns only)",
              chess.KNIGHT: "a knight ending (knights and pawns only)"}
    if len(kinds) == 1 and next(iter(kinds)) in single:
        return single[next(iter(kinds))]
    if kinds == {chess.BISHOP}:
        return "a bishop ending" + (" with opposite-coloured bishops" if opposite_bishops(board) else "")
    extra = " (opposite-coloured bishops)" if opposite_bishops(board) else ""
    return f"{_side_list(white)} v {_side_list(black)}{extra}"


def opposite_bishops(board: chess.Board) -> bool:
    wb, bb = board.pieces(chess.BISHOP, chess.WHITE), board.pieces(chess.BISHOP, chess.BLACK)
    if len(wb) != 1 or len(bb) != 1:
        return False
    w, b = next(iter(wb)), next(iter(bb))
    return (chess.square_file(w) + chess.square_rank(w)) % 2 != (chess.square_file(b) + chess.square_rank(b)) % 2


class GameStory:
    """The game's main line, ply by ply: ``boards[i]`` is the position after *i* plies (0: the start), ``moves[i]``
    the move made from ``boards[i]``."""

    def __init__(self, line: list, headers: Optional[dict] = None):
        self.headers = dict(headers or {})
        self.moves: list = []
        self.boards: list = []
        self.labels: list = []
        self.taken: list = []  # per ply: the piece type it took, or None
        for board, move in line:
            if not self.boards:
                self.boards.append(board.copy(stack=False))
            before = self.boards[-1]
            if move not in before.legal_moves:
                break
            victim = None
            if before.is_capture(move):
                victim = chess.PAWN if before.is_en_passant(move) else before.piece_at(move.to_square).piece_type
            self.labels.append(f"{before.fullmove_number}{'.' if before.turn == chess.WHITE else '...'}{before.san(move)}")
            self.taken.append(victim)
            self.moves.append(move)
            after = before.copy(stack=False)
            after.push(move)
            self.boards.append(after)
        self.balance = [_points(b, chess.WHITE) - _points(b, chess.BLACK) for b in self.boards]

    # ── construction ────────────────────────────────────────────────────────────────────────────────────────────

    @classmethod
    def from_pgn(cls, pgn: str) -> Optional["GameStory"]:
        try:
            game = chess.pgn.read_game(io.StringIO(pgn or ""))
        except Exception:  # noqa: BLE001
            return None
        if game is None:
            return None
        board = game.board()
        line = []
        for move in game.mainline_moves():
            if move not in board.legal_moves:
                break
            line.append((board.copy(stack=False), move))
            board.push(move)
        if not line:
            return None
        return cls(line, dict(game.headers))

    @classmethod
    def of(cls, ctx) -> Optional["GameStory"]:
        """The story of the database game on the check context (src/answer_check_db.note_board_game), cached."""
        line = getattr(ctx, "loaded_game", None) if ctx is not None else None
        if not line:
            return None
        cached = getattr(ctx, "_loaded_story", None)
        if cached is not None and cached[0] is line:
            return cached[1]
        story = cls(line, getattr(ctx, "master_game", None) or {})
        try:
            ctx._loaded_story = (line, story)
        except Exception:  # noqa: BLE001
            pass
        return story

    # ── what the game did ───────────────────────────────────────────────────────────────────────────────────────

    @property
    def plies(self) -> int:
        return len(self.moves)

    def after(self, i: int) -> str:
        """The position after *i* plies, named by the ply that led to it."""
        return "the start" if i == 0 else self.labels[i - 1]

    def lead(self, color: bool, i: int) -> int:
        return self.balance[i] if color == chess.WHITE else -self.balance[i]

    def spans(self) -> list:
        """[(first, last, balance)]: the positions first..last (inclusive) with the same material balance."""
        out = []
        for i, bal in enumerate(self.balance):
            if out and out[-1][2] == bal:
                out[-1] = (out[-1][0], i, bal)
            else:
                out.append((i, i, bal))
        return out

    def steady(self, spans: list) -> list:
        """*spans* without the passing ones — a single position in the middle of an exchange («16.Nxc6 Qxc6»: White up 3
        for one ply) — and the neighbours they split joined again."""
        last = len(self.boards) - 1
        kept = [s for s in spans if s[1] > s[0] or s[1] == last or s[0] == 0]
        out: list = []
        for s in kept:
            if out and out[-1][2:] == s[2:]:
                out[-1] = (out[-1][0], s[1], *s[2:])
            else:
                out.append(s)
        return out

    def captures(self) -> list:
        return [k for k, t in enumerate(self.taken) if t is not None]

    def groups(self) -> list:
        """The exchanges: lists of capturing plies, each at most GROUP_GAP plies after the one before."""
        out: list = []
        for k in self.captures():
            if out and k - out[-1][-1] <= GROUP_GAP:
                out[-1].append(k)
            else:
                out.append([k])
        return out

    def took(self, plies: list) -> tuple:
        """(what White took, what Black took) in *plies*: lists of piece types."""
        white, black = [], []
        for k in plies:
            (white if self.boards[k].turn == chess.WHITE else black).append(self.taken[k])
        return white, black

    def phases(self) -> list:
        """[(first, last, white pieces, black pieces)]: the positions with the same pieces besides kings and pawns."""
        out = []
        for i, board in enumerate(self.boards):
            key = (_pieces(board, chess.WHITE), _pieces(board, chess.BLACK))
            if out and (out[-1][2], out[-1][3]) == key:
                out[-1] = (out[-1][0], i, *key)
            else:
                out.append((i, i, *key))
        return out

    def ending(self) -> str:
        """How the game ended, from the final position and the result."""
        final = self.boards[-1]
        result = self.headers.get("Result") or ""
        if final.is_checkmate():
            return f"{self.labels[-1]} is checkmate"
        if final.is_stalemate():
            return f"stalemate after {self.labels[-1]}"
        repeats = sum(1 for b in self.boards if b.board_fen() == final.board_fen() and b.turn == final.turn)
        if result == "1/2-1/2" and repeats >= 3:
            return f"a draw by repetition (the position after {self.labels[-1]} came {repeats} times)"
        if result == "1/2-1/2":
            return f"a draw agreed after {self.labels[-1]}"
        if result in ("1-0", "0-1"):
            loser = "Black" if result == "1-0" else "White"
            return f"{loser} resigned after {self.labels[-1]}"
        return f"the score stops after {self.labels[-1]} ({result or 'no result'})"

    # ── the text the model is given ─────────────────────────────────────────────────────────────────────────────

    def _held(self, first: int, last: int) -> str:
        """How long the positions first..last held: «for 3 plies, until 19...Nxf2» (the move that ended it)."""
        if last == len(self.boards) - 1:
            return "to the end of the game"
        n = last - first + 1
        moves = f" ({n // 2} moves)" if n >= 4 else ""
        return f"for {n} {_plural('ply', n)}{moves}, until {self.labels[last]}"

    def material_lines(self) -> list:
        out = []
        for first, last, bal in self.steady(self.spans()):
            since = "from the start" if first == 0 else f"after {self.labels[first - 1]}"
            if bal == 0:
                what = "level"
            else:
                who = "White" if bal > 0 else "Black"
                what = f"{who} up {abs(bal)}"
            out.append(f"{what} {since}, {self._held(first, last)}")
        if len(out) > 24:  # a long, swinging game: the first, the longest held, the last
            spans = self.steady(self.spans())
            keep = sorted(sorted(range(len(spans)), key=lambda j: spans[j][1] - spans[j][0], reverse=True)[:20]
                          + [0, len(spans) - 1])
            out = [out[j] for j in dict.fromkeys(keep)]
        return out

    def exchange_lines(self) -> list:
        out = []
        for plies in self.groups()[:MAX_EXCHANGES]:
            first, last = plies[0], plies[-1]
            moves = " ".join(self.labels[first:last + 1])
            white, black = self.took(plies)
            out.append(f"{moves}: {self.pairs(white, black)}; material after it: {self._balance_word(last + 1)}")
        return out

    @staticmethod
    def pairs(white: list, black: list) -> str:
        """What one exchange did, as pairs: the pieces both sides took are a trade, the rest «won X for Y»."""
        w, b = Counter(white), Counter(black)
        both = w & b
        w, b = w - both, b - both
        parts = []
        for t in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
            n = both.get(t, 0)
            if n:
                parts.append(f"{_plural(NAME[t], 2) if n == 1 else f'{n} pairs of {_plural(NAME[t], 2)}'} traded")
        wl, bl = list(w.elements()), list(b.elements())
        if wl and bl and sum(VALUE[t] for t in wl) >= sum(VALUE[t] for t in bl):
            parts.append(f"White won {_list(wl)} for {_list(bl)}")
        elif wl and bl:
            parts.append(f"Black won {_list(bl)} for {_list(wl)}")
        elif wl:
            parts.append(f"White won {_list(wl)}")
        elif bl:
            parts.append(f"Black won {_list(bl)}")
        return "; ".join(parts)

    def _balance_word(self, i: int) -> str:
        bal = self.balance[i]
        return "level" if bal == 0 else f"{'White' if bal > 0 else 'Black'} up {abs(bal)}"

    def phase_lines(self) -> list:
        phases = self.steady(self.phases())
        start = next((j for j, p in enumerate(phases) if len(p[2]) + len(p[3]) <= ENDING_PIECES), len(phases) - 1)
        start = min(start, max(0, len(phases) - MAX_PHASES))
        out = []
        for first, last, _, _ in phases[start:]:
            board = self.boards[first]
            pawns = f"pawns {len(board.pieces(chess.PAWN, chess.WHITE))}–{len(board.pieces(chess.PAWN, chess.BLACK))}"
            since = "from the start" if first == 0 else f"from {self.labels[first - 1]}"
            out.append(f"{since}, {self._held(first, last)}: {ending_name(board)}; {pawns}")
        return out

    def moment_lines(self) -> list:
        out = []
        for k, move in enumerate(self.moves):
            if move.promotion:
                out.append(f"{self.labels[k]}: {'White' if self.boards[k].turn else 'Black'} promotes to a "
                           f"{NAME[move.promotion]}")
        for color, word in ((chess.WHITE, "White"), (chess.BLACK, "Black")):
            steady = self.steady(self.spans())
            best = max(steady, key=lambda s: (s[2] if color == chess.WHITE else -s[2], -s[0]))
            lead = best[2] if color == chess.WHITE else -best[2]
            if lead > 0:
                out.append(f"{word}'s biggest lead (not counting a capture taken straight back): {lead} after "
                           f"{self.after(best[0])}, {self._held(best[0], best[1])}")
        out.append(f"The game ended: {self.ending()}; final material {self._balance_word(len(self.boards) - 1)}")
        return out

    def facts(self) -> str:
        """The facts as text for the model."""
        parts = [
            "Facts of this game, computed by the server from its moves — exact. Material in points (pawn 1, knight 3, "
            "bishop 3, rook 5, queen 9). Say the material, the trades, the extra pawns and the ending only as written "
            "here: a lead that held one move was not «an extra pawn» the side kept; an ending is a rook ending only when "
            "rooks and pawns are all that is left.",
            "Material balance:\n" + "\n".join(f"- {x}" for x in self.material_lines()),
        ]
        ex = self.exchange_lines()
        if ex:
            parts.append("Captures, grouped into exchanges (what each side took):\n" + "\n".join(f"- {x}" for x in ex))
        parts.append("Pieces besides kings and pawns (the ending):\n" + "\n".join(f"- {x}" for x in self.phase_lines()))
        parts.append("Key moments:\n" + "\n".join(f"- {x}" for x in self.moment_lines()))
        return "\n".join(parts)

    def shown_note(self, ply: Optional[int]) -> str:
        """Which position of the game the board shows — arrows go on that position."""
        if ply is None or not (0 <= ply < len(self.boards)):
            return ""
        where = "the final position" if ply == len(self.boards) - 1 else "an earlier position"
        return (f"The board shows {where} of this game, after {self.after(ply)} (ply {ply} of {self.plies}). Arrows "
                "are drawn on that position: an arrow for an earlier move of the game is not drawn there.")


def game_facts(pgn: str, ply: Optional[int] = None) -> str:
    """The facts of the game in *pgn* as text ('' when it does not parse). Never raises."""
    try:
        story = GameStory.from_pgn(pgn)
        if story is None:
            return ""
        note = story.shown_note(ply)
        return story.facts() + (f"\n{note}" if note else "")
    except Exception:  # noqa: BLE001
        logger.debug("game facts failed", exc_info=True)
        return ""


# ── the claims a sentence makes about the game, against the facts ───────────────────────────────────────────────

_B = r"(?<![\w-])"
_E = r"(?![\w-])"
_NOUN = r"(?:эндшпил(?:ь|я|ю|ем|е)|окончани(?:е|я|ю|ем|и)|концовк(?:а|и|у|ой|е))"
_ENDINGS = [
    ("rook", re.compile(_B + r"(?:ладейно-пешечн\w+|ладейн(?:ый|ого|ому|ым|ом|ое|ая|ую|ой))\s+" + _NOUN + _E
                        + r"|" + _B + r"rook(?:-and-pawn|\s+and\s+pawn)?\s+(?:ending|endgame)" + _E, re.IGNORECASE)),
    ("queen", re.compile(_B + r"(?:ферзево-пешечн\w+|ферзев(?:ый|ого|ому|ым|ом|ое|ая|ую|ой))\s+" + _NOUN + _E
                         + r"|" + _B + r"queen(?:-and-pawn|\s+and\s+pawn)?\s+(?:ending|endgame)" + _E, re.IGNORECASE)),
    ("pawn", re.compile(r"(?<![\w-])пешечн(?:ый|ого|ому|ым|ом|ое|ая|ую|ой)\s+" + _NOUN + _E
                        + r"|" + _B + r"(?<!rook\s)(?<!queen\s)(?<!rook-and-)(?<!queen-and-)(?:king\s+and\s+)?pawn\s+"
                        r"(?:ending|endgame)" + _E, re.IGNORECASE)),
    ("bishop", re.compile(_B + r"слонов(?:ый|ого|ому|ым|ом|ое|ая|ую|ой)\s+" + _NOUN + _E
                          + r"|" + _B + r"bishop\s+(?:ending|endgame)" + _E, re.IGNORECASE)),
    ("knight", re.compile(_B + r"конев(?:ой|ый|ого|ому|ым|ом|ое|ая|ую)\s+" + _NOUN + _E
                          + r"|" + _B + r"knight\s+(?:ending|endgame)" + _E, re.IGNORECASE)),
    ("opposite", re.compile(_B + r"(?:разноцветн\w+\s+слон\w*|слон\w*\s+разного\s+цвета|opposite[- ]colou?red\s+"
                            r"bishops|bishops\s+of\s+opposite\s+colou?rs?)" + _E, re.IGNORECASE)),
]
_ENDING_TEXT = {"rook": "a rook ending (rooks and pawns only)", "queen": "a queen ending (queens and pawns only)",
                "pawn": "a pawn ending (no pieces)", "bishop": "a bishop ending (bishops and pawns only)",
                "knight": "a knight ending (knights and pawns only)", "opposite": "opposite-coloured bishops"}
# A general truth, not this game: «в ладейных эндшпилях обычно…», «как правило», "usually".
_GENERIC = re.compile(_B + r"(?:обычно|как\s+правило|всегда|часто|нередко|типичн\w*|в\s+целом|вообще|любо\w+|таки\w+|"
                      r"подобн\w+|usually|typically|often|always|generally|in\s+general|such|any)" + _E, re.IGNORECASE)
_NEG = re.compile(_B + r"(?:не|нет|ни|без|not|no|never|without)" + _E, re.IGNORECASE)
# Told as what happened in the game (past), not about the board now nor a rule.
_HAPPENED = re.compile(
    _B + r"(?:перешл\w*|переш[её]л|свел\w*|св[её]л\w*|свелась|получил\w*|получилось|возник\w*|дошл\w*|дош[её]л|"
    r"оказал\w*|был\w*|стал\w*|сложил\w*|наступил\w*|случил\w*|закончил\w*|завершил\w*|разыгр\w*|остал\w*|"
    r"игрался|играли|играл\w*|вышл\w*|выш[её]л|пришл\w*|приш[её]л|"
    r"reached|became|turned|ended|arose|went|got|was|were|resulted|finished|played|left)" + _E, re.IGNORECASE)
# The end of the game: «в итоге», «в конце», «закончилась», "in the end".
_FINAL = re.compile(_B + r"(?:в\s+итоге|в\s+конце|к\s+концу|в\s+финал\w*|в\s+финальн\w+|в\s+заключительн\w+|"
                    r"закончил\w*|завершил\w*|итогов\w+|окончательн\w+|in\s+the\s+end|at\s+the\s+end|ended|finally|"
                    r"final)" + _E, re.IGNORECASE)
# A lead kept, not a moment: «остались с лишней пешкой», «долго играли», «так и не реализовали».
_KEPT = re.compile(_B + r"(?:остал\w*|сохранил\w*|сохраня\w*|удерж\w*|долго|долгое|весь|всю|вс[её]\s+время|до\s+конца|"
                   r"играл\w*\s+с|игра\w*\s+с|реализ\w*|kept|keep|remained|stayed|held|for\s+a\s+long|the\s+rest|"
                   r"played\s+(?:on\s+)?with|convert\w*)" + _E, re.IGNORECASE)


# A lead said as one: «лишняя пешка», «впереди на ладью», «на пешку больше», «перевес в качество», "a pawn up" — not
# «плюс ладья и конь» (a list of what a side has; recorded answers 06.11: Carlsen – Nepomniachtchi read as «up 8»).
_LEAD_WORD = re.compile(_B + r"(?:лишн\w+|впереди|позади|больше|меньше|опережа\w*|отста\w*|перевес\w*|"
                        r"преимуществ\w*|extra|up|ahead|down|behind)" + _E, re.IGNORECASE)


def _clause(low: str, start: int, end: int) -> str:
    left = max(low.rfind(c, 0, start) for c in ".;!?") + 1
    nxt = [i for i in (low.find(c, end) for c in ".;!?") if i >= 0]
    return low[left:min(nxt) if nxt else len(low)]


def _ending_matches(story: GameStory, kind: str, positions: list) -> bool:
    for i in positions:
        board = story.boards[i]
        kinds = set(_pieces(board, chess.WHITE)) | set(_pieces(board, chess.BLACK))
        if kind == "opposite":
            if opposite_bishops(board):
                return True
        elif kind == "pawn":
            if not kinds:
                return True
        elif kinds == {{"rook": chess.ROOK, "queen": chess.QUEEN, "bishop": chess.BISHOP,
                        "knight": chess.KNIGHT}[kind]}:
            return True
    return False


def ending_issues(low: str, story: GameStory, about: Optional[bool]) -> list:
    """«Партия перешла в ладейно-пешечное окончание» where the game never had rooks and pawns only."""
    out = []
    for kind, pattern in _ENDINGS:
        for m in pattern.finditer(low):
            clause = _clause(low, m.start(), m.end())
            left = max(low.rfind(c, 0, m.start()) for c in ".;:!?,—") + 1
            nxt = [i for i in (low.find(c, m.end()) for c in ".;:!?,—") if i >= 0]
            part = low[left:min(nxt) if nxt else len(low)]  # its own clause: «…, где Накамура не смог…» is another
            if _NEG.search(part) or _GENERIC.search(clause):
                continue  # «это не ладейный эндшпиль», «в ладейном эндшпиле обычно…»
            if about is not True and not _HAPPENED.search(clause):
                continue  # «ладейный эндшпиль — это…», a rule; the board now is the board check's
            final = bool(_FINAL.search(clause))
            positions = [len(story.boards) - 1] if final else list(range(len(story.boards)))
            if _ending_matches(story, kind, positions):
                continue
            last = story.boards[-1]
            where = (f"the game ended with {ending_name(last)}" if final else
                     f"the game never reached {_ENDING_TEXT[kind]}; it ended with {ending_name(last)}")
            out.append(f"«{m.group(0)}» does not match the game on the board: {where} "
                       "(tell the ending only from the game's facts)")
            return out
    return out


# What a side took and gave, in words: «выиграли ферзя и ладью за ферзя и слона», «отдал ладью за коня», «разменял
# коня на слона», "won a queen and a rook for a queen and a bishop".
_ACC = {"ферзя": chess.QUEEN, "ферзей": chess.QUEEN, "ладью": chess.ROOK, "ладьи": chess.ROOK, "ладей": chess.ROOK,
        "коня": chess.KNIGHT, "коней": chess.KNIGHT, "слона": chess.BISHOP, "слонов": chess.BISHOP,
        "пешку": chess.PAWN, "пешки": chess.PAWN, "пешек": chess.PAWN, "фигуру": "minor", "фигуры": "minor",
        "фигур": "minor", "queen": chess.QUEEN, "queens": chess.QUEEN, "rook": chess.ROOK, "rooks": chess.ROOK,
        "knight": chess.KNIGHT, "knights": chess.KNIGHT, "bishop": chess.BISHOP, "bishops": chess.BISHOP,
        "pawn": chess.PAWN, "pawns": chess.PAWN, "piece": "minor", "pieces": "minor"}
_COUNT = {"две": 2, "два": 2, "двух": 2, "три": 3, "трех": 3, "четыре": 4, "четырех": 4, "two": 2, "three": 3,
          "four": 4, "a": 1, "an": 1, "one": 1, "одну": 1, "одного": 1}
_ITEM = r"(?:(?:две|два|двух|три|трех|четыре|четырех|одну|одного|two|three|four|an?|one)\s+)?(?:лишн\w+\s+|extra\s+)?" \
        r"(?:ферзя|ферзей|ладью|ладьи|ладей|коня|коней|слона|слонов|пешку|пешки|пешек|фигуру|фигуры|фигур|queens?|rooks?|" \
        r"knights?|bishops?|pawns?|pieces?)"
_LIST = _ITEM + r"(?:\s*(?:,|\s+и|\s+and|,\s+and)\s+" + _ITEM + r")*"
_TRADE = [
    # (pattern, which group the side took, which it gave)
    (re.compile(_B + r"(?:выиграл\w*|получил\w*|забрал\w*|взял\w*|won|got|took|gained)\s+(?P<a>" + _LIST + r")\s+"
                r"(?:за|for)\s+(?P<b>" + _LIST + r")" + _E, re.IGNORECASE), "a", "b"),
    (re.compile(_B + r"(?:отдал\w*|пожертвовал\w*|gave\s+up|gave|sacrificed|returned)\s+(?P<b>" + _LIST + r")\s+"
                r"(?:за|for)\s+(?P<a>" + _LIST + r")" + _E, re.IGNORECASE), "a", "b"),
    (re.compile(_B + r"(?:разменял\w*|обменял\w*|traded|exchanged)\s+(?P<b>" + _LIST + r")\s+(?:на|for)\s+(?P<a>"
                + _LIST + r")" + _E, re.IGNORECASE), "a", "b"),
]
_SIDE_WORD = re.compile(_B + r"(?:(?P<w>белые|белым|белых|white)|(?P<b>ч[её]рные|ч[её]рным|ч[её]рных|black))" + _E,
                        re.IGNORECASE)


def _items(text: str) -> list:
    out = []
    for m in re.finditer(_ITEM, text, re.IGNORECASE):
        words = m.group(0).lower().split()
        n = _COUNT.get(words[0], 1) if len(words) > 1 else 1
        piece = _ACC.get(words[-1])
        if piece is None:
            return []
        if words[-1] in ("пешки", "ладьи", "фигуры") and len(words) == 1:
            n = 1  # the accusative singular is «пешку»; «пешки» alone is the genitive of one
        out += [piece] * n
    return out


def _fits(want: list, got: list) -> bool:
    """The pieces *want* (pawns aside; «фигура» a knight or a bishop) are exactly the pieces *got*."""
    w = Counter(t for t in want if t != chess.PAWN)
    g = Counter(t for t in got if t != chess.PAWN)
    minors = w.pop("minor", 0)
    for t in list(w):
        if g.get(t, 0) < w[t]:
            return False
        g[t] -= w[t]
    rest = +g
    return sum(rest.values()) == minors and all(t in (chess.KNIGHT, chess.BISHOP) for t in rest)


def _windows(story: GameStory):
    """The runs of captures a sentence may mean by one trade: any run inside an exchange that does not split a capture
    from its recapture (16.Nxc6 Qxc6 17.Bxb6 Qxb6 has no «knight for bishop» in 16...Qxc6 17.Bxb6)."""
    def recaptures(k, prev):
        return k == prev + 1 and story.moves[k].to_square == story.moves[prev].to_square

    for plies in story.groups():
        for i in range(len(plies)):
            if i and recaptures(plies[i], plies[i - 1]):
                continue
            for j in range(i, len(plies)):
                if j + 1 < len(plies) and recaptures(plies[j + 1], plies[j]):
                    continue
                yield plies[i:j + 1]


def trade_issues(original: str, low: str, story: GameStory, sides: callable) -> list:
    """«Белые выиграли ферзя и ладью за ферзя и слона» where no exchange of the game was that."""
    for pattern, took_key, gave_key in _TRADE:
        for m in pattern.finditer(low):
            took, gave = _items(m[took_key]), _items(m[gave_key])
            if not [t for t in took if t != chess.PAWN] and not [t for t in gave if t != chess.PAWN]:
                continue  # pawns only: not judged
            if not took or not gave:
                continue
            clause = _clause(low, m.start(), m.end())
            if _NEG.search(clause[:clause.find(m.group(0)) if m.group(0) in clause else len(clause)]):
                continue
            head = original[:m.start()] if len(original) == len(low) else ""
            named = sides(head[max(0, head.rfind(".") + 1):]) if head else set()
            sw = list(_SIDE_WORD.finditer(low[max(0, low.rfind(".", 0, m.start()) + 1):m.start()]))
            if sw:
                named = {chess.WHITE if sw[-1]["w"] else chess.BLACK}
            colors = list(named) if len(named) == 1 else [chess.WHITE, chess.BLACK]
            ok = False
            for window in _windows(story):
                white, black = story.took(window)
                for color in colors:
                    mine, theirs = (white, black) if color == chess.WHITE else (black, white)
                    if _fits(took, mine) and _fits(gave, theirs):
                        ok = True
                        break
                if ok:
                    break
            if ok:
                continue
            groups = [g for g in story.groups() if any(story.taken[k] != chess.PAWN for k in g)]
            # the exchange that took the most of what the sentence names — the one it most likely meant
            want = Counter(t for t in took + gave if t != chess.PAWN)

            def overlap(g):
                w, b = story.took(g)
                return sum((Counter(t for t in w + b if t != chess.PAWN) & want).values())

            best = max(groups, key=overlap, default=None)
            said = ""
            if best is not None and overlap(best):
                w, b = story.took(best)
                said = (f": the exchange {' '.join(story.labels[best[0]:best[-1] + 1])} was — "
                        f"{GameStory.pairs(w, b)}")
            return [f"«{m.group(0)}» does not match the game on the board — no exchange of it was that{said} "
                    "(tell the trades only from the game's facts)"]
    return []


def lead_issues(original: str, low: str, story: GameStory, sides: callable, about: Optional[bool]) -> list:
    """«Белые остались с лишней пешкой» where the lead held one move; «в итоге у чёрных лишняя фигура» where the game
    ended level; «у белых была лишняя ладья» where White never led by a rook."""
    from src import material_frames

    # the players' names read as the colours: «Накамура остался с лишней пешкой» → «белые …»
    text = low
    if len(original) == len(low):
        from src.player_names import _NAME_TOKEN

        chars = list(low)
        for tm in _NAME_TOKEN.finditer(original):
            tok = tm.group(0)
            if len(tok) < 4 or not tok[0].isupper():
                continue
            named = sides(tok)
            word = ("белые" if next(iter(named)) == chess.WHITE else "черные") if len(named) == 1 else ""
            if word and len(word) <= len(tok):  # the same length: the claim's offsets stay
                chars[tm.start():tm.end()] = list(word.ljust(len(tok)))
        text = "".join(chars)
    try:
        claims = material_frames.read(text)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for claim in claims:
        if claim.kind != "lead" or claim.who not in ("W", "B") or claim.points is None:
            continue
        clause = text[claim.at:claim.end]
        sentence = _clause(text, claim.at, claim.end)
        final = bool(_FINAL.search(clause))
        kept = bool(_KEPT.search(clause))
        if not (final or kept or _HAPPENED.search(clause)):
            continue  # the board now (present tense, even of a sentence naming the players): src/answer_check judges it
        if not _LEAD_WORD.search(claim.span or clause):
            continue  # «у белых две проходные плюс ладья и конь»: what a side has, listed — not a lead
        if _GENERIC.search(sentence) or re.search(_B + r"(?:после|after|когда|when|если|if)" + _E, clause):
            continue  # a moment named by a move («после 18.Qxd5 у белых лишняя пешка») is the move check's
        color = chess.WHITE if claim.who == "W" else chess.BLACK
        sign = 1 if claim.more else -1

        def holds(i):
            lead = sign * story.lead(color, i)
            if claim.hedged:
                return lead > 0
            return lead >= claim.points if claim.atleast else lead == claim.points

        side = "White" if color == chess.WHITE else "Black"
        span_text = (low[claim.at:claim.end] if len(low) == len(text) else claim.span or clause).strip()
        if final:
            last = len(story.boards) - 1
            if not holds(last):
                out.append(f"«{span_text}» does not match the game on the board: it ended "
                           f"{story._balance_word(last)} in material (tell the material only from the game's facts)")
                break
            continue
        runs = []
        for first, last, _ in story.spans():
            if all(holds(i) for i in range(first, last + 1)):
                if runs and runs[-1][1] == first - 1:
                    runs[-1] = (runs[-1][0], last)
                else:
                    runs.append((first, last))
        if kept:
            if any(last - first + 1 >= STABLE_PLIES for first, last in runs):
                continue
            if runs:
                first, last = max(runs, key=lambda r: r[1] - r[0])
                out.append(f"«{span_text}» does not match the game on the board: {side}'s lead of "
                           f"{claim.points} after {story.after(first)} held only {last - first + 1} "
                           f"{'ply' if last == first else 'plies'} — it was not kept (tell the material only from the "
                           "game's facts)")
            else:
                out.append(f"«{span_text}» does not match the game on the board: {side} never led by {claim.points} in "
                           "it (tell the material only from the game's facts)")
            break
        if not runs:
            out.append(f"«{span_text}» does not match the game on the board: {side} never led by {claim.points} in it "
                       "(tell the material only from the game's facts)")
            break
    return out


def story_issues(original: str, low: str, ctx, about: Optional[bool], sides: callable) -> list:
    """The ending, the trades and the leads *original* tells of the database game on the board, against its facts.
    *low* is the lowered sentence (moves as SAN), *about* whether it tells that game (src/answer_check_db), *sides* the
    sides a text names by their players. Never raises."""
    try:
        story = GameStory.of(ctx)
        if story is None or about is False:
            return []
        return (ending_issues(low, story, about) or trade_issues(original, low, story, sides)
                or lead_issues(original, low, story, sides, about))
    except Exception:  # noqa: BLE001 — the check never breaks a turn
        logger.debug("story check failed", exc_info=True)
        return []
