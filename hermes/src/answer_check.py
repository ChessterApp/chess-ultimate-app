"""Checks a coach answer, sentence by sentence, against the board.

The text coach runs without reasoning (fast), and without it the model writes
chess it has not checked. On production (2026-09-30) it said a knight «с f3
прыгает на d5» (a knight cannot), that a knight on c7 would attack the queen
d8 (it does not), recaptured «...Nxe5» with no black knight in reach, and gave
the moves of the quiet Italian as the Fried Liver. Each of these is decidable
from the board, so the server checks every finished sentence before it is
shown (see coach_chat), and a wrong one is not shown: the rest of the answer
is rewritten from there.

What is checked — only what can be decided without guessing, so that a right
sentence is never stopped:

  * a piece moving from a square to a square (Russian and English wording,
    «конь с f3 на d5», «Nf3-d5»): can that piece move that way at all;
  * a piece attacking squares («конь на c7 бьёт a8 и d8»): does it, by its
    move pattern (lines are not checked for blockers — hypotheticals are fine);
  * written moves (Nf6, 5...Na5, 3.Nxe5): legal in a position of this turn —
    the board, the opening line, a line written earlier in the answer — or at
    least reachable by such a piece of that side; plain squares are not moves;
  * an opening named next to moves from 1.: are they that opening's book line.

Negated claims («ладью он не достаёт») are skipped: they deny, they do not claim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

import chess

SQ = r"[a-h][1-8]"
_SQ_RE = re.compile(rf"(?<![a-z0-9]){SQ}(?![0-9])")

# Russian piece nouns, every case, matched as whole words on lowercased text
# with ё → е. Stems alone would catch «конец», «королевский», «контроль».
_RU_PIECES = [
    (chess.KNIGHT, r"кон(?:ь|я|ю|е|и|ем|ей|ям|ями|ях)"),
    (chess.BISHOP, r"слон(?:а|у|ом|е|ы|ов|ам|ами|ах)?"),
    (chess.ROOK, r"лад(?:ья|ьи|ье|ью|ьей|ей|ьям|ьями|ьях)"),
    (chess.QUEEN, r"ферз(?:ь|я|ю|ем|е|и|ей)"),
    (chess.KING, r"корол(?:ь|я|ю|ем|е)"),
    (chess.PAWN, r"пеш(?:ка|ки|ке|ку|кой|ек|кам|ками|ках)"),
]
_EN_PIECES = [
    (chess.KNIGHT, r"knights?"), (chess.BISHOP, r"bishops?"), (chess.ROOK, r"rooks?"),
    (chess.QUEEN, r"queens?"), (chess.KING, r"kings?"), (chess.PAWN, r"pawns?"),
]
_W = r"(?<![а-яa-z])"
_E = r"(?![а-яa-z])"
_PIECE_WORD = re.compile(_W + "(?:" + "|".join(p for _, p in _RU_PIECES + _EN_PIECES) + ")" + _E)

_STOP = r"[^.!?;:\n—–()]"  # a claim stays inside one clause
# Between a piece and its verb a dash is Russian grammar («конём на c7 — вот он
# бил бы…»), not a new clause.
_STOP_MID = r"[^.!?;:,\n()]"
# Inside a move claim a comma starts another clause («конь с b1 пока плох, но
# после перевода на g3…» is not a jump b1-g3).
_STOP_MOVE = r"[^.!?;:,\n—–()]"

# «конь с f3 прыгает на d5», «слон уходит с c5 на a7», «knight from f3 to d5»
_MOVE_CLAIMS = []
for _ptype, _pat in _RU_PIECES:
    _MOVE_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"(?P<mid1>(?:\s+{_STOP_MOVE}+?){{0,2}}?)\s+(?:с|со|из)\s+(?P<a>{SQ})"
        rf"(?P<mid2>(?:\s+{_STOP_MOVE}+?){{0,3}}?)\s+на\s+(?P<b>{SQ})(?![0-9])")))
    _MOVE_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"\s+(?:с\s+)?(?P<a>{SQ})\s*[-–]\s*(?P<b>{SQ})(?![0-9])")))
for _ptype, _pat in _EN_PIECES:
    _MOVE_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"(?P<mid1>(?:\s+{_STOP_MOVE}+?){{0,2}}?)\s+(?:from|on)\s+(?P<a>{SQ})"
        rf"(?P<mid2>(?:\s+{_STOP_MOVE}+?){{0,3}}?)\s+(?:to|onto)\s+(?P<b>{SQ})(?![0-9])")))

# «конь на c7 бьёт a8 и d8», «слон c4 держит f7», «the knight on f7 attacks d8 and h8».
# The attacker is the subject: nominative («конь») or instrumental («конём на
# c7 — вот он бил бы…»); «связывает пешку f7 и смотрит на h7» is the queen's claim.
_RU_SUBJECTS = [
    (chess.KNIGHT, r"конь|кони|кон[её]м"),
    (chess.BISHOP, r"слон|слоны|слоном"),
    (chess.ROOK, r"ладья|ладьи|ладь[её]й"),
    (chess.QUEEN, r"ферзь|ферз[её]м"),
    (chess.KING, r"король|корол[её]м"),
    (chess.PAWN, r"пешка|пешки|пешкой"),
]
_RU_VERBS = (r"(?:бь[её]т|бьют|бил[аи]?\s+бы|атакует|атакуют|атаковал\w*|нападает|нападают|напал[аи]?|"
             r"угрожает|угрожают|держит|держат|смотрит|смотрят|давит|давят|целится|целятся|"
             r"защищает|защищают|контролирует|контролируют|вилк\w*)(?![а-я])")
_EN_VERBS = (r"(?:attacks|attack|hits|forks|targets|eyes|would\s+attack|is\s+attacking|defends|protects|"
             r"controls)(?![a-z])")
# «её держит только конь c6»: the subject comes after the verb — not this piece's claim.
_INVERTED = re.compile(r"^\s*(?:[^\s,]+\s+){0,2}?(?:конь|слон|ладья|ферзь|король|пешка|the\s+(?:knight|bishop|rook|queen|king|pawn))(?![а-яa-z])")
_ATTACK_CLAIMS = []
for _ptype, _pat in _RU_SUBJECTS:
    _ATTACK_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"\s+(?:на\s+)?(?P<a>{SQ})(?![0-9])(?P<mid>{_STOP_MID}{{0,40}}?)"
        rf"(?P<verb>{_RU_VERBS})(?P<targets>{_STOP}{{0,90}})")))
for _ptype, _pat in _EN_PIECES:
    _ATTACK_CLAIMS.append((_ptype, re.compile(
        _W + "(?:" + _pat + ")" + _E + rf"\s+(?:on\s+)?(?P<a>{SQ})(?![0-9])(?P<mid>{_STOP_MID}{{0,40}}?)"
        rf"(?P<verb>{_EN_VERBS})(?P<targets>{_STOP}{{0,90}})")))
# Where the targets of a claim end: another clause starts, or another piece
# becomes the subject («конь на f6 смотрит на e4, конь на c6 — на d4»).
_TARGETS_END = re.compile(
    r",?\s+(?:но|а|поэтому|чтобы|потому|если|когда|пока|затем|потом|после|хотя|but|so|because|if|when|while|"
    r"after|then|which|that|who|whose)\s|\s+котор\w*\s|,\s+and\s"
    r"|,\s*(?:(?:а|и|and)\s+)?(?:конь|слон|ладья|ферзь|король|пешка|the\s+(?:knight|bishop|rook|queen|king|pawn))"
    r"(?![а-яa-z])", re.IGNORECASE)
_NEGATION = re.compile(r"(?:^|\s)(?:не|ни|нет|never|not|n't|cannot|can't)\s*$|(?:не|not)\s+\w+\s*$", re.IGNORECASE)
# «Лe4 сыграть нельзя», «ладья так не ходит»: the sentence denies a move — its
# moves are the student's idea being refuted, not the coach's claims.
_DENIES = re.compile(
    r"нельзя|невозможн|не\s+може|не\s+могу|не\s+ход[иья]|не\s+получит|нелегальн|не\s+по\s+правилам|"
    r"illegal|not\s+legal|can'?t|cannot|impossible|isn'?t\s+possible", re.IGNORECASE)
# «Ke3–e5», «Nb1–d2–f1–g3», «...d7-d5»: a move written from-to (a chain of hops).
_LONG = re.compile(
    r"(?<![A-Za-z0-9])(?:(?P<num>\d{1,3})\s?(?P<dots>\.\.\.|…|\.)\s?|(?P<bdots>\.\.\.|…))?"
    r"(?P<piece>[KQRBN])?(?P<chain>[a-h][1-8](?:[-–][a-h][1-8])+)(?![0-9])")

# Written moves. Russian piece letters (Кf6, Сc4, Крg1) are read as SAN too.
_RU_SAN = re.compile(r"(?<![А-Яа-яA-Za-z])(Кр|К|С|Л|Ф)(?=x?[a-h][1-8])")
_RU_TO_SAN = {"Кр": "K", "К": "N", "С": "B", "Л": "R", "Ф": "Q"}
_FIGURINES = str.maketrans({"♔": "K", "♚": "K", "♕": "Q", "♛": "Q", "♖": "R", "♜": "R",
                            "♗": "B", "♝": "B", "♘": "N", "♞": "N"})


def _to_san(text: str) -> tuple[str, set]:
    """*text* with figurines and Russian piece letters as SAN letters, and the
    positions (in the result) where a Cyrillic «К» became N — models write «Кh1»
    for the king too, so there a king move is accepted as well."""
    text = (text or "").translate(_FIGURINES)
    out, cyr_k, last = [], set(), 0
    for m in _RU_SAN.finditer(text):
        out.append(text[last:m.start()])
        if m.group(1) == "К":
            cyr_k.add(sum(len(x) for x in out))
        out.append(_RU_TO_SAN[m.group(1)])
        last = m.end()
    out.append(text[last:])
    return "".join(out), cyr_k
_MOVE = re.compile(
    r"(?<![A-Za-z0-9.])(?:(?P<num>\d{1,3})\s?(?P<dots>\.\.\.|…|\.)\s?|(?P<bdots>\.\.\.|…))?"
    r"(?P<san>[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?"
    r"|O-O-O|O-O)(?P<check>[+#]?)(?![A-Za-z0-9])")
_NAMES = {chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook",
          chess.QUEEN: "queen", chess.KING: "king", chess.PAWN: "pawn"}


def _geometry_move(ptype: int, a: int, b: int) -> bool:
    """Can a piece of *ptype* move a → b on an empty board (either colour)?"""
    if a == b:
        return False
    dx = abs(chess.square_file(a) - chess.square_file(b))
    dy = abs(chess.square_rank(a) - chess.square_rank(b))
    if ptype == chess.KNIGHT:
        return {dx, dy} == {1, 2}
    if ptype == chess.BISHOP:
        return dx == dy
    if ptype == chess.ROOK:
        return dx == 0 or dy == 0
    if ptype == chess.QUEEN:
        return dx == dy or dx == 0 or dy == 0
    if ptype == chess.KING:
        castling = chess.square_name(a) in ("e1", "e8") and dy == 0 and dx == 2
        return max(dx, dy) == 1 or castling
    if ptype == chess.PAWN:
        return (dx == 0 and 1 <= dy <= 2) or (dx == 1 and dy == 1)
    return False


def _geometry_attack(ptype: int, a: int, b: int) -> bool:
    """Does a piece of *ptype* on a attack b by its pattern (blockers ignored)?"""
    if ptype == chess.PAWN:
        dx = abs(chess.square_file(a) - chess.square_file(b))
        dy = abs(chess.square_rank(a) - chess.square_rank(b))
        return dx == 1 and dy == 1
    if ptype == chess.KING:
        return a != b and max(abs(chess.square_file(a) - chess.square_file(b)),
                              abs(chess.square_rank(a) - chess.square_rank(b))) == 1
    return _geometry_move(ptype, a, b)


def _clause_targets(text: str) -> list[str]:
    cut = _TARGETS_END.search(text)
    if cut:
        text = text[: cut.start()]
    return _SQ_RE.findall(text)


_FEN_IN_TEXT = re.compile(r"[rnbqkpRNBQKP1-8]{1,8}(?:/[rnbqkpRNBQKP1-8]{1,8}){7} [wb] [KQkq-]{1,4} [a-h1-8-]{1,2}(?: \d+ \d+)?")


@dataclass
class CheckContext:
    """The positions of this turn a written move may belong to, and the moves
    the student wrote (the coach may repeat those to refute them)."""

    boards: list = field(default_factory=list)
    quoted: set = field(default_factory=set)
    MAX_BOARDS = 400

    @classmethod
    def from_fens(cls, fens: Iterable[Optional[str]] = (), lines: Iterable[str] = (),
                  question: str = "") -> "CheckContext":
        ctx = cls()
        ctx.add(chess.STARTING_FEN)
        for fen in fens:
            ctx.add(fen)
        for pgn in lines:
            ctx.add_line(pgn)
        converted, _ = _to_san(question or "")
        ctx.quoted = {m["san"] for m in _MOVE.finditer(converted)}
        return ctx

    def add_text(self, text: str) -> None:
        """Positions a tool result carries (a topic example, a puzzle, a game)."""
        for fen in _FEN_IN_TEXT.findall(text or ""):
            self.add(fen)
        for pgn in re.findall(r'"pgn"\s*:\s*"([^"]{8,})"', text or ""):
            self.add_line(pgn.replace("\\n", " "))

    def add(self, fen: Optional[str]) -> None:
        if not fen or len(self.boards) >= self.MAX_BOARDS:
            return
        try:
            board = chess.Board(fen)
        except ValueError:
            return
        key = board.board_fen() + (" w" if board.turn else " b")
        if all(b.board_fen() + (" w" if b.turn else " b") != key for b in self.boards):
            self.boards.append(board)

    def add_line(self, pgn: str) -> None:
        from src.openings_book import _split_moves

        board = chess.Board()
        header = re.search(r'\[FEN "([^"]+)"\]', pgn or "")
        if header:
            try:
                board = chess.Board(header.group(1))
            except ValueError:
                return
        pgn = re.sub(r"\[[^\]]*\]", " ", pgn or "")
        pgn = re.sub(r"\{[^}]*\}", " ", pgn)
        self.add(board.fen())
        for san in _split_moves(pgn):
            try:
                board.push_san(san)
            except ValueError:
                return
            self.add(board.fen())


_GROUP = re.compile(r"(?:пешки|пешек|пешкам|пешками|пешках|кони|коней|конями|слоны|слонов|слонами|"
                    r"ладьи|ладей|ладьями|ферзи|ферзей|pawns|knights|bishops|rooks)(?![а-яa-z])")


def _move_issues(text: str) -> list[str]:
    if _DENIES.search(text):
        return []
    issues = []
    for ptype, rx in _MOVE_CLAIMS:
        for m in rx.finditer(text):
            if _GROUP.match(m.group(0)):
                continue  # «пешки f7–g7–h7» names a group of pawns
            if ptype == chess.PAWN and m["a"][1] == m["b"][1]:
                continue  # pawns never move sideways: «пешкой e5–b5» is a chain
            between = (m.groupdict().get("mid1") or "") + (m.groupdict().get("mid2") or "")
            if _PIECE_WORD.search(between) or _SQ_RE.search(between):
                continue  # another piece or square in between: not one claim
            a, b = chess.parse_square(m["a"]), chess.parse_square(m["b"])
            if not _geometry_move(ptype, a, b):
                issues.append(f"a {_NAMES[ptype]} cannot move from {m['a']} to {m['b']}")
    return issues


def _attack_issues(text: str) -> list[str]:
    issues = []
    for ptype, rx in _ATTACK_CLAIMS:
        for m in rx.finditer(text):
            mid = m["mid"] or ""
            if _PIECE_WORD.search(mid) or _SQ_RE.search(mid):
                continue  # «конь на d5 и слон на c4 бьют f7»: whose attack?
            if _NEGATION.search(text[: m.start("verb")]):
                continue  # «ладью он не достаёт», «does not attack»
            if m["targets"].lstrip().startswith(","):
                continue  # «ладья d1 атакует, твои пешки g7/f7/h7 ещё стоят»
            if _INVERTED.match(m["targets"]):
                continue  # «пешка e5 висит, её держит только конь c6»
            a = chess.parse_square(m["a"])
            wrong = [t for t in _clause_targets(m["targets"])
                     if t != m["a"] and not _geometry_attack(ptype, a, chess.parse_square(t))]
            if wrong:
                issues.append(f"a {_NAMES[ptype]} on {m['a']} does not attack {', '.join(wrong)}")
    return issues


def _pawn_reaches(color: chess.Color, sq: int, dest: int, capture: bool) -> bool:
    forward = 1 if color == chess.WHITE else -1
    df = chess.square_file(dest) - chess.square_file(sq)
    dr = (chess.square_rank(dest) - chess.square_rank(sq)) * forward
    return abs(df) == 1 and dr == 1 if capture else df == 0 and dr in (1, 2)


def _reachable(boards: list, ptype: int, colors: list, dest: int, steps: int, capture: bool) -> bool:
    """Some piece of *ptype* and one of *colors* in some position stands on
    *dest* (the move was just played) or gets there in *steps* moves by its
    pattern — a capture or a check is a claim about now (one step), a quiet
    move may be a plan («...a6 и ...Ba7»: two)."""
    for board in boards:
        for color in colors:
            for sq in board.pieces(ptype, color):
                if sq == dest:
                    return True
                if ptype == chess.PAWN:
                    if _pawn_reaches(color, sq, dest, capture) or (not capture and _pawn_reaches(color, sq, dest, True)):
                        return True
                    continue
                if _geometry_move(ptype, sq, dest):
                    return True
                if steps > 1 and any(_geometry_move(ptype, sq, mid) and _geometry_move(ptype, mid, dest)
                                     for mid in chess.SQUARES):
                    return True
    return False


def _long_issues(text: str, ctx: CheckContext) -> tuple[list[str], str]:
    """From-to moves («Ke3–e5», «Nb1–d2–f1–g3», «...d7-d5»): each hop must be a
    move of that piece. Returns the issues and *text* with these moves blanked
    (the SAN scan must not read «Ke3» of «Ke3–e5» as a king going to e3)."""
    issues = []
    for m in _LONG.finditer(text):
        squares = re.findall(SQ, m["chain"])
        piece = m["piece"]
        explicit = bool(m["num"] or m["bdots"])
        if not piece and not explicit:
            continue  # «c2–c3», «диагональ a2–g8»: plain squares, not a written move
        ptype = chess.PIECE_SYMBOLS.index(piece.lower()) if piece else chess.PAWN
        for a, b in zip(squares, squares[1:]):
            if ptype == chess.KING and _geometry_move(chess.KNIGHT, chess.parse_square(a), chess.parse_square(b)):
                continue  # a Latin K for the Russian К (конь)
            if not _geometry_move(ptype, chess.parse_square(a), chess.parse_square(b)):
                issues.append(f"{m.group(0).strip()}: a {_NAMES[ptype]} cannot move from {a} to {b}")
                break
        # The first hop, where it is a legal move, continues a written line.
        for board in list(ctx.boards):
            try:
                move = chess.Move.from_uci(squares[0] + squares[1])
            except ValueError:
                break
            for color in (chess.WHITE, chess.BLACK):
                trial = board.copy(stack=False)
                trial.turn = color
                if move in trial.legal_moves:
                    trial.push(move)
                    ctx.add(trial.fen())
                    break
    blanked = _LONG.sub(lambda m: " " * len(m.group(0)) if (m["piece"] or m["num"] or m["bdots"]) else m.group(0), text)
    return issues, blanked


def _san_issues(text: str, ctx: CheckContext) -> list[str]:
    """Written moves that fit no position of the turn and no piece that could make them."""
    if _DENIES.search(text):
        return []  # «Лe4 сыграть нельзя»: the move is being refuted
    converted, cyr_k = _to_san(text)
    issues, converted = _long_issues(converted, ctx)
    in_line_until = -1  # a bare pawn move right after a played move is part of the line
    for m in _MOVE.finditer(converted):
        san, num, dots = m["san"], m["num"], m["dots"] or m["bdots"]
        numbered = bool(num or m["bdots"])
        is_piece = san[0] in "KQRBN"
        continues_line = in_line_until >= 0 and not converted[in_line_until:m.start()].strip()
        if not numbered and not is_piece and not continues_line:
            continue  # «e4» without a number is a square, not a move
        if num and not is_piece and re.fullmatch(r"[\s*_#>`-]*", converted[:m.start()]) \
                and re.match(r"\d{1,3}\.\s", converted[m.start():]):
            continue  # «1. f7 пешкасы…»: a numbered list item, not 1.f7
        if san.startswith("O-O") or san in ctx.quoted:
            continue
        list_item = bool(num) and dots == "." and re.fullmatch(r"[\s*_#>`-]*", converted[:m.start()]) \
            and re.match(r"\d{1,3}\.\s", converted[m.start():])
        if dots in ("...", "…"):
            colors = [chess.BLACK]
        elif num and dots == "." and not list_item:
            colors = [chess.WHITE]
        else:
            colors = [chess.WHITE, chess.BLACK]
        full = san + (m["check"] or "")
        legal_somewhere = False
        for board in list(ctx.boards):
            for color in colors:
                trial = board.copy(stack=False)
                trial.turn = color
                try:
                    move = trial.parse_san(full)
                except ValueError:
                    continue
                legal_somewhere = True
                trial.push(move)
                ctx.add(trial.fen())  # a line written in the answer goes on from here
                break
            if legal_somewhere:
                break
        in_line_until = m.end() if legal_somewhere else -1
        if legal_somewhere:
            continue
        ptype = chess.PIECE_SYMBOLS.index(san[0].lower()) if is_piece else chess.PAWN
        dest = chess.parse_square(re.findall(SQ, san)[-1])
        capture = "x" in san or bool(m["check"])
        if _reachable(ctx.boards, ptype, colors, dest, 1 if capture else 2, capture):
            continue
        if ptype == chess.KING and _reachable(ctx.boards, chess.KNIGHT, colors, dest, 1, capture):
            continue  # «Kc6» with a Latin K for the Russian К (конь)
        san_at = m.start("san")
        if san_at in cyr_k and _reachable(ctx.boards, chess.KING, colors, dest, 2, capture):
            continue  # «Кh1» written for the king
        side = {1: "white", 0: "black"}.get(colors[0]) if len(colors) == 1 else "any"
        label = (f"{num}{dots}" if num else (dots or "")) + full
        issues.append(f"{label} is impossible: no {side} {_NAMES[ptype]} can "
                      f"{'capture on' if capture else 'reach'} {chess.square_name(dest)} in the positions of this turn")
    return issues


def _opening_issues(text: str) -> list[str]:
    """Moves from 1. next to an opening name must be that opening's line."""
    from src.openings_book import get_book, named_openings, _split_moves

    names = named_openings(text)
    if not names:
        return []
    converted, _ = _to_san(text)
    start = re.search(r"(?<![0-9])1\s?\.\s?(?=[KQRBNa-hO])", converted)
    if not start:
        return []
    board, played = chess.Board(), []
    for m in _MOVE.finditer(converted, start.start()):
        try:
            board.push_san(m["san"] + (m["check"] or ""))
        except ValueError:
            break
        played.append(m["san"] + (m["check"] or ""))
    if len(played) < 4:
        return []
    book = get_book()
    # A named line decides when one is mentioned: «жареная печень — это
    # итальянская партия: 1.e4 … 5.d3 d6» is about the Fried Liver, and the
    # Italian around it does not excuse the moves.
    specific = [n for n, is_named in names if is_named]
    judged = specific or [n for n, _ in names]
    wrong = None
    for name in judged:
        verdict = _fits(book, name, played)
        if verdict is None or verdict:
            return []
        wrong = wrong or name
    real = book.identify(played)
    real_name = real["name"] if real else "another line"
    return [f"the moves {' '.join(played[:10])} are not the {wrong} — they are the {real_name}"]


def _keys_along(moves) -> list[str]:
    board, keys = chess.Board(), []
    for san in moves:
        try:
            board.push_san(san)
        except ValueError:
            break
        keys.append(board.board_fen() + (" w" if board.turn else " b"))
    return keys


def _fits(book, name: str, played: list[str]) -> Optional[bool]:
    """Do *played* moves belong to the opening *name*? None when the book cannot tell.

    Positions are compared, not move orders: 1.e4 e5 2.Qh5 Nc6 3.Bc4 is the
    Scholar's Mate position too.
    """
    from src.openings_book import _split_moves

    entry = book.exact(name) or next(iter(book.by_name(name)), None)
    if entry is None:
        return None
    line = [s.rstrip("+#") for s in _split_moves(entry[2])]
    seq = [s.rstrip("+#") for s in played]
    k = min(len(line), len(seq))
    if line[:k] == seq[:k]:
        return True
    seq_keys = _keys_along(seq)
    line_keys = _keys_along(line)
    if line_keys and line_keys[-1] in seq_keys:
        return True  # the named position is reached, by another order
    # Every position of the opening's lines (the line and the lines named after
    # it: its variations, a trap's defences).
    own = re.split(r"[:,]", name)[-1].strip()
    related = set()
    for other in book.entries:
        if other[1].startswith(name) or (own and own in other[1] and own != other[1].split(":")[0].strip()
                                         or other[1] == name):
            related.update(_keys_along(_split_moves(other[2])))
    if seq_keys and seq_keys[-1] in related:
        return True  # ends inside the opening, whatever the order
    deepest = max((i for i, key in enumerate(seq_keys) if key in related), default=-1)
    if len(seq_keys) - 1 - deepest >= 3 and deepest < len(line_keys) - 1:
        return False  # leaves the opening early and goes on elsewhere
    return None


def check_sentence(sentence: str, ctx: Optional[CheckContext] = None) -> list[str]:
    """The reasons *sentence* is wrong on the board; [] when nothing checkable is wrong."""
    ctx = ctx or CheckContext.from_fens()
    text = sentence.replace("ё", "е")
    lowered = text.lower()
    issues = _move_issues(lowered) + _attack_issues(lowered) + _san_issues(text, ctx) + _opening_issues(text)
    return list(dict.fromkeys(issues))


class SentenceGate:
    """Holds streamed text until a sentence is complete, then hands it out with its issues.

    Disabled, it passes text straight through (the stream as before).
    """

    MAX_HOLD = 600  # characters without a sentence end: check and release anyway

    def __init__(self, ctx: Optional[CheckContext] = None, enabled: bool = True):
        self.ctx = ctx or CheckContext.from_fens()
        self.enabled = enabled
        self._buf = ""

    def feed(self, text: str) -> list[tuple[str, list[str]]]:
        if not self.enabled:
            return [(text, [])] if text else []
        self._buf += text
        sentences, self._buf = _split_sentences(self._buf)
        if len(self._buf) > self.MAX_HOLD:
            sentences.append(self._buf)
            self._buf = ""
        return [(s, check_sentence(s, self.ctx)) for s in sentences]

    def flush(self) -> list[tuple[str, list[str]]]:
        rest, self._buf = self._buf, ""
        if not rest:
            return []
        return [(rest, check_sentence(rest, self.ctx) if self.enabled else [])]


def _split_sentences(buf: str) -> tuple[list[str], str]:
    """Complete sentences of *buf* (with their trailing spaces) and the unfinished rest.

    A sentence ends at a newline, or at . ! ? … followed by a space — except
    after a move number («1. e4», «5... Na5»). Punctuation at the very end
    waits for the next text: it may be «1.» of a move.
    """
    out: list[str] = []
    start = i = 0
    n = len(buf)
    while i < n:
        ch = buf[i]
        if ch == "\n":
            j = i + 1
            while j < n and buf[j] == "\n":
                j += 1
            out.append(buf[start:j])
            start = i = j
            continue
        if ch in ".!?…":
            j = i
            while j < n and buf[j] in ".!?…":
                j += 1
            if j >= n:
                break  # decide when more text comes
            if buf[j] in " \t\n":
                k = i
                while k > start and buf[k - 1].isalnum():
                    k -= 1
                if not buf[k:i].isdigit():
                    while j < n and buf[j] in " \t":
                        j += 1
                    out.append(buf[start:j])
                    start = i = j
                    continue
            i = j
            continue
        i += 1
    return out, buf[start:]


def fix_messages(turn_message: str, shown: str, wrong: str, issues: list[str], language_note: str) -> list[dict]:
    """The one tool-free call that writes the rest of an answer after a wrong sentence.

    It gets what the coach's turn got (the question, the board, the engine and
    opening blocks), what the student has already seen, the rejected sentence
    and why it is wrong — and continues from there.
    """
    system = (
        "You are a chess coach finishing your reply to a student. The beginning of the reply is "
        "already on the student's screen. The next sentence of your draft was checked on the "
        "board and is WRONG; it was not shown. Write the rest of the reply: continue right after "
        "the shown text, make the point the wrong sentence tried to make — correctly — and finish "
        "the thought in 2–4 short sentences, the way a coach talks. Do not mention a mistake, a "
        "draft or a check. Do not repeat what is already shown. Name only moves, squares and "
        "attacks you can read in the verified context (the engine block, the opening block, the "
        "facts, tool results); when unsure, explain the idea in words without moves. No engine "
        "names, no numbers, no [[marks]]."
    )
    user = (
        f"{turn_message}\n\n"
        f"## Already shown to the student\n{shown.strip() or '(nothing yet — write the whole answer)'}\n\n"
        f"## The next sentence of the draft — WRONG, not shown\n{wrong.strip()}\n"
        f"Why it is wrong (checked on the board): {'; '.join(issues)}.\n\n"
        f"{language_note}\nContinue the reply now."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
