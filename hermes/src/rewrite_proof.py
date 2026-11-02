"""The rewrite after a wrong sentence says only what the check proved (fix1102 K6, VERDICT §6.4).

The rewrite (src/server.py ``_run_fix``, src/answer_check.fix_messages) is a model call that writes the rest of an
answer after a sentence the check cut. On the live run of 02.11 it wrote new false facts the check could not judge —
trap-blackburne «Конь вынужден уйти на f7 с шахом» in place of a true mating line, st1#9 «прикрыта только пешкой d7»,
d2-solution «свои же пешки и слон его запирают» — and it was handed broken issue texts («defended (by )», «exf4 is
impossible after exf4»). A sentence the check finds nothing wrong with is not therefore true: most board words are
judged by no detector at all. So the rewrite is held to a stricter rule than the draft:

  issues    ``fix_issues``: only well-formed issue texts reach the rewrite. An issue that lists nothing where it names a
            list («defended (by )»), or names the same move or square on both sides of a relation that needs two
            («exf4 is impossible after exf4», «e6xe6: a pawn on e6 cannot capture on e6») is the trace of a detector
            that lost its way; it is no proof, and a sentence with no other issue is left unjudged
            (``well_formed``). «no any queen» is worded «no queen of either side».
  proof     ``prove``: every board word of a rewritten sentence — a square, a move, a piece, check or mate, material,
            an evaluation, a motif, a relation verb, a quantifier («только», «все», «вынужден») — must lie inside what
            the check proved true: a relation claim the judge found TRUE on its boards (src/claim_judge), or the
            engine's own line from the board on the screen (the moves, in order, from its first; the squares they
            go from and to, the pieces they move and take, «шах»/«мат» when they give it). A sentence with no board
            word proves nothing and claims nothing: 'neutral'. Anything else is 'unproven' and is not shown.

What a rewrite needs to be shown (src/server.py): its first sentence that carries a board word must be proven — then the
rewrite stands in for the rest of the draft as before, its neutral sentences go out with it, an unproven or wrong one
later is left out; a rewrite whose first such sentence is wrong or unproven (or that brings none) is abandoned, and the
draft goes on after the cut sentence, every sentence of it checked as usual — the cut sentence is simply left out.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import chess

# ── issue texts ────────────────────────────────────────────────────────────────────────────────────────────────
# A list slot with nothing in it: «(by )», «()», «by ,».
_EMPTY_SLOT = re.compile(r"\(\s*(?:by|of|from|with|on|at)?\s*\)|\b(?:by|of|from)\s*[,;)]", re.IGNORECASE)
# The same move on both sides: «exf4 is impossible after exf4».
_SAME_MOVE = re.compile(r"(?<![\w.])(?P<a>[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)[+#]?\s+is\s+"
                        r"(?:impossible|illegal|not\s+possible)\s+after\s+(?:\d+\.(?:\.\.)?\s*)?(?P=a)[+#]?(?![\w])")
# A capture from a square onto itself: «e6xe6», «a pawn on e6 cannot capture on e6».
_SAME_SQUARE = re.compile(r"(?<![a-z0-9])(?P<s>[a-h][1-8])x(?P=s)(?![0-9])|\bon\s+(?P<t>[a-h][1-8])\s+(?:cannot|can't|does\s+not|"
                          r"doesn't)\s+(?:capture|move|go)\s+(?:on|to)\s+(?P=t)\b", re.IGNORECASE)
_NO_ANY = re.compile(r"\bno\s+any\s+(king|queen|rook|bishop|knight|pawn|piece)\b", re.IGNORECASE)


def malformed(issue: str) -> Optional[str]:
    """Why *issue* is not a statement a reader could check, or None: an empty list where it names one, the same move
    or square on both sides of a relation that needs two, an empty text."""
    text = " ".join(str(issue or "").split())
    if not text:
        return "empty"
    if _EMPTY_SLOT.search(text):
        return "empty list"
    if _SAME_MOVE.search(text):
        return "a move impossible after itself"
    if _SAME_SQUARE.search(text):
        return "a square onto itself"
    return None


def clean_issue(issue: str) -> str:
    """*issue* worded for the reader: «no any queen» → «no queen of either side»."""
    return _NO_ANY.sub(lambda m: f"no {m.group(1)} of either side", str(issue or ""))


def well_formed(issues: Iterable[str]) -> list:
    """The issues of one sentence a reader can check, worded for the reader; the malformed ones are left out (a
    sentence with no other issue is unjudged). Markers such as PROMISE_ISSUE pass as they are."""
    out = []
    for issue in issues or ():
        if not isinstance(issue, str):
            continue
        if malformed(issue):
            continue
        cleaned = clean_issue(issue)
        if cleaned not in out:
            out.append(cleaned)
    return out


fix_issues = well_formed  # what the rewrite is given


def ends_the_draft(issues: Iterable[str]) -> bool:
    """The cut sentence's issues condemn the rest of the draft, not the sentence alone: an answer in the wrong language
    («…; the whole answer must be in Russian») goes on in it — its short fragments («Play e4.») are too short for the
    language check to judge one by one. An abandoned rewrite then ends the answer instead of resuming the draft."""
    return any(isinstance(i, str) and "the whole answer must be in" in i for i in issues or ())

# ── board words of a sentence ───────────────────────────────────────────────────────────────────────────────────
_CYR_FILES = {"а": "a", "с": "c", "е": "e", "б": "b", "д": "d", "ф": "f", "г": "g", "х": "h"}


def normalized(sentence: str) -> str:
    """The sentence as the check reads it (src/answer_check._check_sentence, the same steps): no emphasis, «ё» as «е»,
    one gap between words, Cyrillic files as Latin — the text the relation checker's claim spans are in."""
    from src.answer_check import _EMPHASIS, _WS_RUN

    text = _EMPHASIS.sub("", sentence or "").replace("ё", "е")
    text = _WS_RUN.sub(lambda m: "\n" if "\n" in m.group(0) else " ", text)
    return re.sub(r"(?<![а-яА-Яa-zA-Z])([асебдфгхАСЕБДФГХ])(?=[1-8](?![0-9]))",
                  lambda m: _CYR_FILES[m.group(1).lower()], text)


_F = "[a-hасебдфгх]"  # a file, Latin or its Cyrillic lookalike («Кс7+»)
_MOVE_TOKEN = re.compile(
    r"(?<![\w.])(?:\d{1,3}\s?(?:\.\.\.|…|\.)\s?|\.\.\.|…)?"
    rf"(?:(?:Кр|[KQRBNКФЛС♔♕♖♗♘♙♚♛♜♝♞♟]){_F}?[1-8]?[x:×]?{_F}[1-8](?:=[QRBNФЛСК])?"
    rf"|{_F}[x:×]{_F}[1-8](?:=[QRBNФЛСК])?"
    r"|(?<=[.…]|\s)[a-h][1-8](?:=[QRBNФЛСК])?(?=[+#]|\s|[,.;:!?)»—–-]|$)"
    r"|O-O-O|O-O|0-0-0|0-0)[+#]?(?![\w])")
_NUMBERED = re.compile(r"^(?:\d{1,3}\s?(?:\.\.\.|…|\.)|\.\.\.|…)")
_SQUARE = re.compile(r"(?<![A-Za-z0-9])([a-h][1-8])(?![0-9])")

_WORDS = {
    # the pieces, by name (Russian, English, Kazakh)
    # (a bare «фигура» is not one: «развивай фигуры» is advice; «потеряешь фигуру» says it with «потеряешь»)
    "piece": r"кон[ьяюеи]\w*|кон[её]м|коней|слон\w*|ладь\w*|ладей|ферз\w*|корол\w*|пешк\w*|пешек"
             r"|knights?|bishops?|rooks?|queens?|kings?|pawns?"
             r"|уәзір\w*|патша\w*|сарбаз\w*|піл\w*|тура\w*",
    # check, mate, stalemate
    "check": r"шах\w*|мат|мата|мату|матом|мате|пат\w*|checks?|checkmate\w*|mates?|stalemate\w*",
    # the move called the best: the engine's own first move says it
    "best": r"лучш\w*\s+(?:всего|ход\w*|ответ\w*|продолжени\w*)|лучше\s+всего|сильнейш\w*|сильнее\s+всего"
            r"|правильн\w*|точн\w*\s+(?:всего|ход\w*)|best(?:\s+(?:move|reply))?|strongest|correct\s+move",
    # material and evaluation
    "eval": r"материал\w*|лишн\w*|перевес\w*|преимуществ\w*|выигр\w*|проигр\w*|теря\w*|потер\w*|ничь\w*|равн\w*"
            r"|лучше|хуже|выгодн\w*|невыгодн\w*|безнад\w*|решающ\w*|отыгр\w*|отда\w*|жертв\w*|размен\w*"
            r"|material|extra|advantage|winning|wins?|losing|lose|loses|lost|draw\w*|equal\w*|better|worse|sacrifice\w*"
            r"|trade\w*|exchange\w*",
    # a capture told in words: the move that makes it says it
    "capture": r"забира\w*|забер\w*|забрать|взять|взяти\w*|возьм\w*|бер[её]\w*|брать|съе\w*|бьешь|captur\w*"
               r"|recaptur\w*|takes?|taking|took",
    # motifs and plans
    "motif": r"вилк\w*|связк\w*|связа\w*|связыва\w*|сквозн\w*|ловушк\w*|угроз\w*|гроз\w*|ловит\w*|запира\w*|заперт\w*"
             r"|двойн\w+\s+удар\w*|открыт\w+\s+(?:нападени|шах)\w*|превращ\w*|прорыв\w*|проходн\w*|рокиров\w*"
             r"|forks?|pins?|pinned|skewer\w*|traps?|trapped|threat\w*|promot\w*|castl\w*",
    # relation verbs
    "relation": r"напада\w*|нападет|напал\w*|атаку\w*|атакова\w*|бь[её]т|бьют|бить|бил\w*|защищ\w*|защит\w*|прикры\w*"
                r"|держ\w*|контрол\w*|нацел\w*|давит|давят|целит\w*|смотрит|под\s+бо\w+|под\s+удар\w*|висит|висят"
                r"|attack\w*|defend\w*|protect\w*|guard\w*|hits?|controls?|covers?|hanging|undefended",
    # quantifiers and modality the claims do not carry
    "quant": r"только|лишь|единственн\w*|вс[её]|всех|всем|все|оба|обе|обоих|вынужд\w*|обязан\w*|нельзя|невозможн\w*"
             r"|никак\w*|никуда|некуда|ни\s+одн\w*|не\s+мо(?:жет|гут|чь)|only|both|all|must|forced|cannot|can't|never",
    # what the claims carry as a negation («ничем не защищена»)
    "neg": r"ничем|нечем|никем|некому|никто|ничто|ничего|nothing|nobody|none",
}
_WORD_RE = {kind: re.compile(r"(?<![\w-])(?:" + rx + r")(?![\w-])", re.IGNORECASE) for kind, rx in _WORDS.items()}
_PIECE_OF = [(re.compile(r"(?<![\w-])(?:кон[ьяюеи]\w*|кон[её]м|коней|knights?)(?![\w-])", re.I), chess.KNIGHT),
             (re.compile(r"(?<![\w-])(?:слон\w*|bishops?|піл\w*)(?![\w-])", re.I), chess.BISHOP),
             (re.compile(r"(?<![\w-])(?:ладь\w*|ладей|rooks?|тура\w*)(?![\w-])", re.I), chess.ROOK),
             (re.compile(r"(?<![\w-])(?:ферз\w*|queens?|уәзір\w*)(?![\w-])", re.I), chess.QUEEN),
             (re.compile(r"(?<![\w-])(?:корол\w*|kings?|патша\w*)(?![\w-])", re.I), chess.KING),
             (re.compile(r"(?<![\w-])(?:пешк\w*|пешек|pawns?|сарбаз\w*)(?![\w-])", re.I), chess.PAWN)]


@dataclass
class Anchor:
    kind: str  # square | move | piece | check | eval | motif | relation | quant | neg
    start: int
    end: int
    text: str
    san: str = ""  # a move: its SAN without the number
    piece: Optional[int] = None  # a piece word: its kind


def anchors(text: str) -> list:
    """The board words of *text* (as ``normalized`` gives it), in order."""
    out: list = []
    taken: list = []

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e in taken)

    from src.answer_check import _MOVE, _to_san

    for m in _MOVE_TOKEN.finditer(text):
        token = m.group(0)
        converted, _ = _to_san(token.replace("0-0-0", "O-O-O").replace("0-0", "O-O").replace(":", "x").replace("×", "x"))
        mv = _MOVE.search(converted)
        if not mv:
            continue
        bare = re.fullmatch(r"[a-h][1-8]", mv["san"]) and not _NUMBERED.match(token)
        if bare:
            continue  # a bare square is read as a square below
        out.append(Anchor("move", m.start(), m.end(), token, san=mv["san"] + (mv["check"] or "")))
        taken.append((m.start(), m.end()))
    for m in _SQUARE.finditer(text):
        if free(m.start(), m.end()):
            out.append(Anchor("square", m.start(), m.end(), m.group(1)))
    for kind, rx in _WORD_RE.items():
        for m in rx.finditer(text):
            if not free(m.start(), m.end()):
                continue
            piece = None
            if kind == "piece":
                piece = next((pt for prx, pt in _PIECE_OF if prx.fullmatch(m.group(0))), None)
            out.append(Anchor(kind, m.start(), m.end(), m.group(0), piece=piece))
            taken.append((m.start(), m.end()))
    out.sort(key=lambda a: a.start)
    return out


# ── the engine's own line ───────────────────────────────────────────────────────────────────────────────────────
def _bare(san: str) -> str:
    return (san or "").rstrip("+#!?")


def engine_moves(sentence_moves: list, ctx: Any) -> Optional[list]:
    """The moves of *sentence_moves* (SAN, in order) as played from the board on the screen when they are the first
    moves of one of the engine's lines of the turn (``ctx.engine_lines``: SAN lists from ``ctx.current``):
    [(board before, move, san as played)], or None."""
    current = getattr(ctx, "current", None)
    lines = list(getattr(ctx, "engine_lines", None) or [])
    if current is None or not sentence_moves or not lines:
        return None
    want = [_bare(s) for s in sentence_moves]
    for line in lines:
        if not line or len(line) < len(want):
            continue
        if [_bare(s) for s in line[:len(want)]] != want:
            continue
        board = current.copy(stack=False)
        played = []
        try:
            for san in line[:len(want)]:
                move = board.parse_san(san)
                played.append((board.copy(stack=False), move, board.san(move)))
                board.push(move)
        except ValueError:
            continue
        # «Nf3#» said of a move that is not mate, «+» of one that gives no check: not the engine's move as said
        if any(s.endswith("#") and not p[2].endswith("#") or s.endswith("+") and not p[2].endswith(("+", "#"))
               for s, p in zip(sentence_moves, played)):
            continue
        return played
    return None


# A move told as already made: «ты сыграл Кc6», «я ответил 3.Кc3», «мой последний ход — 1...Кf6».
_TOLD = re.compile(r"(?<![\w-])(?:сыграл\w*|ответил\w*|пош[её]л|пошла|пошли|сходил\w*|вышел|вышла|встал\w*|взял\w*|забрал\w*"
                   r"|побил\w*|сделал\w*|последни\w+\s+ход\w*|played|answered|replied|moved|took|captured|last\s+move)"
                   r"(?![\w-])", re.IGNORECASE)


def record_moves(sentence_moves: list, ctx: Any) -> Optional[list]:
    """The moves of *sentence_moves* (move anchors, in order) as plies of the game on the board (``ctx.game_moves``, from
    the start position): [(board before, move, san as played)], or None when one is not in the record — with its
    number, at that very ply; with «+»/«#», giving it."""
    record = list(getattr(ctx, "game_moves", None) or [])
    if not record or not sentence_moves:
        return None
    board = chess.Board()
    plies = []
    for raw in record:
        try:
            move = board.parse_san(str(raw))
        except ValueError:
            try:
                move = chess.Move.from_uci(str(raw))
            except ValueError:
                break
            if move not in board.legal_moves:
                break
        plies.append((len(plies), board.copy(stack=False), move, board.san(move)))
        board.push(move)
    out = []
    for a in sentence_moves:
        found = [p for p in plies if _bare(p[3]) == _bare(a.san)]
        num = re.match(r"\s*(\d{1,3})\s?(\.\.\.|…|\.)", a.text)
        if num:
            ply = 2 * (int(num.group(1)) - 1) + (1 if num.group(2) in ("...", "…") else 0)
            found = [p for p in found if p[0] == ply]
        if a.san.endswith("#"):
            found = [p for p in found if p[3].endswith("#")]
        elif a.san.endswith("+"):
            found = [p for p in found if p[3].endswith(("+", "#"))]
        if not found:
            return None
        out.append(found[-1][1:])
    return out


# ── the proof ───────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Proof:
    status: str  # neutral | proven | unproven
    why: str = ""
    words: list = field(default_factory=list)  # the board words that were not proven


def _record(sentence: str, ctx: Any) -> tuple:
    """(the text the relation checker read, [(claim, status)]) for *sentence*, as it recorded them while checking it —
    by that very text: a record of another text (or none) leaves the sentence's words with no claim to lie in."""
    text = normalized(sentence)
    rec = (getattr(ctx, "relation_verdicts", None) or {}).get(text)
    if rec and rec[0] == text:
        return rec
    return text, ()


def prove(sentence: str, ctx: Any) -> Proof:
    """Whether every board word of *sentence* — already checked with no issue on *ctx* — is proven: inside a relation
    claim the judge found true, or part of the engine's own line from the board on the screen. Never raises."""
    try:
        return _prove(sentence, ctx)
    except Exception as exc:  # noqa: BLE001 — what cannot be proven is not shown
        return Proof("unproven", f"proof failed: {type(exc).__name__}")


def _prove(sentence: str, ctx: Any) -> Proof:
    text, verdicts = _record(sentence, ctx)
    words = anchors(text)
    if not words:
        return Proof("neutral")
    spans = []  # the relation words of the claims found true
    claim_squares: set = set()  # …and the squares and pieces they are about
    claim_pieces: set = set()
    current = getattr(ctx, "current", None)
    for claim, status in verdicts or ():
        if status != "true" or getattr(claim, "question", ""):
            continue
        if tuple(getattr(claim, "span", (0, 0))) != (0, 0):
            spans.append((claim.span[0], claim.span[1], claim))
        for ref in [claim.subj, claim.to, *claim.objs]:
            if ref is None:
                continue
            if ref.sq:
                claim_squares.add(ref.sq)
                if ref.piece is None and current is not None:
                    try:
                        found = current.piece_at(chess.parse_square(ref.sq))
                    except ValueError:
                        found = None
                    if found is not None:
                        claim_pieces.add(found.piece_type)
            if ref.piece:
                claim_pieces.add(chess.Piece.from_symbol(ref.piece).piece_type)
    moves = [a for a in words if a.kind == "move"]
    played = engine_moves([a.san for a in moves], ctx) if moves else None
    if not moves:
        # «Играй e4»: a pawn move written as its square — the engine's first move when its line starts with it
        first = next((a for a in words if a.kind == "square"), None)
        played = engine_moves([first.text], ctx) if first is not None else None
    elif played is None and _TOLD.search(text):
        # moves told as made: the game's own record proves them (and what they moved, took, gave)
        played = record_moves(moves, ctx)
    line_squares: set = set()
    line_pieces: set = set()
    gives = {"check": False, "mate": False}
    if played:
        for board, move, san in played:
            line_squares.update({chess.square_name(move.from_square), chess.square_name(move.to_square)})
            mover = board.piece_at(move.from_square)
            if mover:
                line_pieces.add(mover.piece_type)
            taken = board.piece_at(move.to_square) if not board.is_en_passant(move) else chess.Piece(chess.PAWN, not board.turn)
            if taken:
                line_pieces.add(taken.piece_type)
            gives["check"] |= san.endswith(("+", "#"))
            gives["capture"] = gives.get("capture", False) or board.is_capture(move)
            gives["mate"] |= san.endswith("#")
            if board.is_castling(move):
                line_pieces.update({chess.KING, chess.ROOK})
            if not san[0].isupper():
                line_squares.add(san[-2:] if san[-1].isdigit() else _bare(san)[-2:])

    def inside(a: Anchor) -> Optional[Any]:
        return next((c for s, e, c in spans if s <= a.start and a.end <= e), None)

    unproven = []
    for a in words:
        claim = inside(a)
        if a.kind == "move":
            ok = played is not None
        elif a.kind == "quant":
            ok = False  # «только», «все», «вынужден»: no claim carries them
        elif a.kind == "neg":
            ok = claim is not None and (getattr(claim, "neg", False) or getattr(claim, "rel", "") == "undefended")
        elif claim is not None:
            ok = True
        elif a.kind == "square":
            ok = a.text in line_squares or a.text in claim_squares
        elif a.kind == "piece":
            ok = a.piece is not None and (a.piece in line_pieces or a.piece in claim_pieces)
        elif a.kind == "best":
            ok = played is not None  # the moves it names are the engine's line, from its first
        elif a.kind == "capture":
            ok = bool(gives.get("capture"))
        elif a.kind == "check":
            low = a.text.lower()
            ok = gives["mate"] if low.startswith(("мат", "checkmate", "mate")) else (
                gives["check"] if low.startswith(("шах", "check")) else False)
        else:
            ok = False
        if not ok:
            unproven.append(a.text)
    if unproven:
        return Proof("unproven", "not proven: " + ", ".join(dict.fromkeys(unproven)), list(dict.fromkeys(unproven)))
    return Proof("proven")


# ── the context the rewrite read ────────────────────────────────────────────────────────────────────────────────
# Counters and records of the whole turn: kept as they grew, the rewrite's calls included.
_KEEP = {"relation_stats", "relation_shadow", "relation_verdicts"}


def snapshot(ctx: Any) -> Optional[dict]:
    """What the check knows after the draft's sentences so far (the scene, the lines written, the antecedents, the
    boards the answer's moves added): a rewrite that is abandoned leaves the draft to be read from here, not from
    sentences the student never saw. One level of each field is copied. Never raises."""
    try:
        import copy
        import dataclasses

        names = [f.name for f in dataclasses.fields(ctx)] + [k for k in vars(ctx) if k not in
                                                             {f.name for f in dataclasses.fields(ctx)}]
        return {n: copy.copy(getattr(ctx, n)) for n in names if n not in _KEEP and hasattr(ctx, n)}
    except Exception:  # noqa: BLE001
        return None


def restore(ctx: Any, snap: Optional[dict]) -> None:
    """Put *snap* back (fields added since are left). Never raises."""
    if not snap:
        return
    for name, value in snap.items():
        try:
            setattr(ctx, name, value)
        except Exception:  # noqa: BLE001
            pass
