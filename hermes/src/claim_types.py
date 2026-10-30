"""The claim schema of the relation checker: what a parser says a sentence claims, the boards it is about, and
the verdict (attack/defence claims, plan 30.10).

  text ─► claim_grammar.extract / claim_rules.extract ─► Claim[]          (words → claims, a textual Pos)
       ─► claim_scene.boards_for                       ─► BoardSet        (Pos → the boards it can mean)
       ─► claim_judge.decide                           ─► Verdict         (python-chess)
       ─► answer_check_relations.relation_issues       ─► issue strings   (off | shadow | on)

Every type is a frozen dataclass with ``to_dict``/``from_dict``. ``from_dict`` also reads the JSON the model
extractor of the llm design wrote (``obj`` + ``objs``, sides ``'w'``/``'b'``, moves as SAN strings, ``n``,
``plies``, ``question: true``, its relation names), so a later model extractor plugs into the same judge.

This file is frozen: a change needs every package owner to agree (plan §4). ``ctx.relation_state`` may hold only
immutable values (str, tuple, FEN, these frozen types), so a shallow copy of it is a full snapshot.
"""
from __future__ import annotations

import re
from dataclasses import MISSING, dataclass, fields
from typing import Optional

import chess

# Relations the attack-map judge (claim_judge, WP-B) decides.
RELATIONS = {"attack", "aim", "chase", "threat", "defend", "hold", "undefended", "attacked", "pinned", "pins",
             "pin_after", "locked_by", "capture_with", "plan_reach"}
# Relations the board-rule judge (claim_rules, WP-D) decides.
RULE_RELATIONS = {"only_move", "no_flight", "confined", "can_capture", "can_exchange", "occupied", "checks_along"}
# Relations of the llm schema the recorded extractions carry that neither judge decides in this round (the
# reference judge in tests/support/ref_judge.py does); kept under their own names so nothing is lost on reading.
OTHER_RELATIONS = {"gives_check", "blocks", "locked", "trapped", "can_move", "hanging"}
ALL_RELATIONS = RELATIONS | RULE_RELATIONS | OTHER_RELATIONS

# The llm schema's relation names → ours (the rest are the same word in both).
LLM_RELATIONS = {"attacks": "attack", "aims": "aim", "defends": "defend", "controls": "hold", "occupies": "occupied"}
TO_LLM_RELATIONS = {v: k for k, v in LLM_RELATIONS.items()}

PIECES = ("P", "N", "B", "R", "Q", "K")
PIECE_TYPE = {"P": chess.PAWN, "N": chess.KNIGHT, "B": chess.BISHOP, "R": chess.ROOK, "Q": chess.QUEEN, "K": chess.KING}
POS_AT = ("now", "after", "shown", "shown_after", "back", "then", "plan", "skip")
TENSES = ("present", "past", "future")
QUESTIONS = ("", "which", "yesno")
OWNERS = ("you", "own", "their")
SOURCES = ("grammar", "rules", "fixture", "llm")


def _side_in(value) -> tuple[Optional[bool], Optional[str]]:
    """A side as written in JSON: True/False, 'w'/'b', 'white'/'black'; 'me' is the student (owner 'you')."""
    if value is None or isinstance(value, bool):
        return value, None
    v = str(value).strip().lower()
    if v in ("w", "white"):
        return chess.WHITE, None
    if v in ("b", "black"):
        return chess.BLACK, None
    if v in ("me", "you"):
        return None, "you"
    raise ValueError(f"unknown side {value!r}")


def _drop_defaults(obj) -> dict:
    out = {}
    for f in fields(obj):
        v = getattr(obj, f.name)
        default = f.default_factory() if f.default is MISSING else f.default
        if v != default:
            out[f.name] = v
    return out


@dataclass(frozen=True)
class Ref:
    """A piece or a square the sentence mentions: «конь f6», «пешку e4», «поле d6», «твой слон», «он»."""

    sq: Optional[str] = None
    piece: Optional[str] = None  # 'N','B','R','Q','K','P'
    side: Optional[bool] = None  # chess.WHITE / chess.BLACK
    owner: Optional[str] = None  # 'you' | 'own' | 'their'
    from_sq: bool = False  # «конь с g5»: the piece that stands (or stood) on sq
    pronoun: bool = False  # «он», «её» resolved to this ref
    text: str = ""  # the words of the span, for the issue

    def to_dict(self) -> dict:
        return _drop_defaults(self)

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> Optional["Ref"]:
        if d is None:
            return None
        side, owner = _side_in(d.get("side"))
        return cls(sq=d.get("sq"), piece=d.get("piece"), side=side, owner=d.get("owner") or owner,
                   from_sq=bool(d.get("from_sq", False)), pronoun=bool(d.get("pronoun", False)), text=d.get("text") or "")


@dataclass(frozen=True)
class MoveRef:
    """A move written (SAN, Russian letters) or told in words («конь с g8 встал на f6»)."""

    san: Optional[str] = None
    piece: Optional[str] = None
    frm: Optional[str] = None
    to: Optional[str] = None
    capture: bool = False
    castle: Optional[str] = None  # 'short' | 'long'
    number: Optional[str] = None  # '135...', '4.'
    side: Optional[bool] = None
    told: bool = False  # narrated as already played

    def to_dict(self) -> dict:
        return _drop_defaults(self)

    @classmethod
    def from_dict(cls, d) -> "MoveRef":
        if isinstance(d, str):  # the llm schema writes a move as its SAN
            return parse_san_token(d)
        side, _ = _side_in(d.get("side"))
        return cls(san=d.get("san"), piece=d.get("piece"), frm=d.get("frm"), to=d.get("to"),
                   capture=bool(d.get("capture", False)), castle=d.get("castle"), number=d.get("number"), side=side,
                   told=bool(d.get("told", False)))


@dataclass(frozen=True)
class Pos:
    """Which position a claim is about, as the text says it; claim_scene turns it into boards."""

    at: str = "now"  # now|after|shown|shown_after|back|then|plan|skip
    moves: tuple = ()  # tuple[MoveRef, ...]
    plies_back: int = 0
    tense: str = "present"  # present|past|future
    alts: tuple = ()  # tuple[Pos, ...]: «X или Y»
    skip_reason: str = ""

    def to_dict(self) -> dict:
        out = _drop_defaults(self)
        if "moves" in out:
            out["moves"] = [m.to_dict() for m in self.moves]
        if "alts" in out:
            out["alts"] = [p.to_dict() for p in self.alts]
        return out

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Pos":
        if not d:
            return cls()
        at = d.get("at", "now")
        plies = int(d.get("plies_back", d.get("plies") or 0) or 0)
        tense = d.get("tense", "present")
        skip_reason = d.get("skip_reason", "")
        m = re.fullmatch(r"shb(\d)", at)
        if m:  # llm: the shown board N plies back
            at, plies = "shown", int(m.group(1))
        elif at in ("gen", "general", "if"):  # llm: a rule in general / a hypothetical
            at, skip_reason = "skip", skip_reason or ("general" if at != "if" else "if")
        if at == "back" and "tense" not in d:
            tense = "past"
        if at not in POS_AT:
            raise ValueError(f"unknown position kind {at!r}")
        return cls(at=at, moves=tuple(MoveRef.from_dict(x) for x in d.get("moves") or ()), plies_back=plies,
                   tense=tense, alts=tuple(cls.from_dict(x) for x in d.get("alts") or ()), skip_reason=skip_reason)


@dataclass(frozen=True)
class Claim:
    """One relation the sentence asserts (or asks about): «конь f6 нападает на d4» = attack(N f6 → d4)."""

    rel: str
    subj: Optional[Ref]
    objs: tuple  # tuple[Ref, ...]
    to: Optional[Ref] = None  # the piece behind a pin, the square a piece goes to
    neg: bool = False
    question: str = ""  # ''|'which'|'yesno'
    count: Optional[int] = None  # «атакован дважды»
    pos: Pos = Pos()
    span: tuple = (0, 0)
    source: str = "grammar"  # grammar|rules|fixture|llm
    # The move a board-rule claim is about («единственный ход — 34.Qc1») and its kind ('any' | 'block'): the llm
    # schema's ``move``/``kind``, which only_move needs (WP-D).
    move: Optional[MoveRef] = None
    kind: str = ""

    def to_dict(self) -> dict:
        out = {"rel": self.rel, "subj": self.subj.to_dict() if self.subj else None,
               "objs": [o.to_dict() for o in self.objs]}
        if self.to is not None:
            out["to"] = self.to.to_dict()
        if self.neg:
            out["neg"] = True
        if self.question:
            out["question"] = self.question
        if self.count is not None:
            out["count"] = self.count
        if self.pos != Pos():
            out["pos"] = self.pos.to_dict()
        if tuple(self.span) != (0, 0):
            out["span"] = list(self.span)
        if self.source != "grammar":
            out["source"] = self.source
        if self.move is not None:
            out["move"] = self.move.to_dict()
        if self.kind:
            out["kind"] = self.kind
        return out

    @classmethod
    def from_dict(cls, d: dict, source: Optional[str] = None) -> "Claim":
        rel = LLM_RELATIONS.get(d["rel"], d["rel"])
        objs = ([d["obj"]] if d.get("obj") else []) + list(d.get("objs") or [])
        q = d.get("question") or ""
        question = "which" if q is True else ("" if q is False else q)
        if question not in QUESTIONS:
            raise ValueError(f"unknown question kind {question!r}")
        span = d.get("span")
        span = tuple(span) if isinstance(span, (list, tuple)) and len(span) == 2 else (0, 0)
        count = d.get("count", d.get("n"))
        mv = d.get("move")
        return cls(rel=rel, subj=Ref.from_dict(d.get("subj")), objs=tuple(Ref.from_dict(o) for o in objs),
                   to=Ref.from_dict(d.get("to")), neg=bool(d.get("neg", False)), question=question,
                   count=int(count) if count is not None else None, pos=Pos.from_dict(d.get("pos")), span=span,
                   source=source or d.get("source") or "grammar", move=MoveRef.from_dict(mv) if mv else None,
                   kind=d.get("kind") or "")


@dataclass(frozen=True)
class BoardSet:
    """The boards a claim can mean: it is reported only when false on the primary board, true on no alternative
    and judgeable on the board the coach showed (plan §3.1)."""

    primary: Optional[chess.Board]
    where: str  # «after 4.e5», «on the board now» — the issue says which board it judged
    alternatives: tuple = ()
    shown: Optional[chess.Board] = None


@dataclass(frozen=True)
class Verdict:
    status: str  # true|false|undecided
    where: str = ""
    truth: str = ""  # one short board truth for the rewrite: what the subject really attacks / defends

    def to_dict(self) -> dict:
        return {"status": self.status, "where": self.where, "truth": self.truth}

    @classmethod
    def from_dict(cls, d: dict) -> "Verdict":
        return cls(status=d["status"], where=d.get("where", ""), truth=d.get("truth", ""))


UNDECIDED = Verdict("undecided")

# ── moves and squares in text ─────────────────────────────────────────────────────────────────────────────────
# Files written in Cyrillic lookalikes, as the answer check reads them («пешка е4», «слон на с4»).
_CYR_SQ = re.compile(r"(?<![а-яА-ЯёЁa-zA-Z])([асебдфгхАСЕБДФГХ])(?=[1-8](?![0-9]))")
_CYR_SQ_MAP = {"а": "a", "с": "c", "е": "e", "б": "b", "д": "d", "ф": "f", "г": "g", "х": "h"}
_SQUARE = re.compile(r"(?<![a-z0-9])([a-h][1-8])(?![0-9])")
_SAN_PARTS = re.compile(r"^(?P<piece>[KQRBN])?(?P<ff>[a-h])?(?P<fr>[1-8])?(?P<x>x)?(?P<to>[a-h][1-8])(?:=[QRBN])?[+#]?$")


def _latin_files(text: str) -> str:
    """Cyrillic file lookalikes as Latin letters; one character for one, so positions are kept."""
    return _CYR_SQ.sub(lambda m: _CYR_SQ_MAP[m.group(1).lower()], text or "")


def find_squares(text: str) -> list:
    """Every square in *text*, in order, with its offset: [('e4', 12), …]. «е4» in Cyrillic counts."""
    return [(m.group(1), m.start(1)) for m in _SQUARE.finditer(_latin_files(text).lower())]


def parse_san_token(tok: str, number: Optional[str] = None, side: Optional[bool] = None) -> MoveRef:
    """One SAN token (with an optional move number before it) as a MoveRef; the piece is 'P' for a pawn move."""
    t = (tok or "").strip()
    m = re.match(r"^(?P<num>\d{1,3})\s?(?P<dots>\.\.\.|…|\.)\s?|^(?P<bdots>\.\.\.|…)", t)
    if m:
        t = t[m.end():]
        if m.group("num"):
            number = number or m.group("num") + ("..." if m.group("dots") in ("...", "…") else ".")
            side = chess.BLACK if m.group("dots") in ("...", "…") else chess.WHITE
        else:
            side = chess.BLACK
    t = t.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    core = t.rstrip("+#!?")
    if core in ("O-O", "O-O-O"):
        return MoveRef(san=t, piece="K", castle="short" if core == "O-O" else "long", number=number, side=side)
    p = _SAN_PARTS.match(core)
    if not p:
        return MoveRef(san=t, number=number, side=side)
    frm = p.group("ff") + p.group("fr") if p.group("ff") and p.group("fr") else None
    return MoveRef(san=t, piece=p.group("piece") or "P", frm=frm, to=p.group("to"), capture=bool(p.group("x")),
                   number=number, side=side)


def find_moves(text: str) -> list:
    """The moves written in *text*, in order: SAN with figurines and Russian letters («Кf6», «Сc4», «Крg1»,
    Cyrillic files «Се3»), castling («O-O», «0-0»), numbers («135...Qg1», «4.e5»). A bare square is a pawn move
    to the reader (the parser decides from the words whether «e4» is a move or a square). Cyrillic «К» is read as
    a knight, as the answer check reads it."""
    from src.answer_check import _MOVE, _to_san

    t = _latin_files(text or "").replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    converted, _ = _to_san(t)
    out = []
    for m in _MOVE.finditer(converted):
        number, side = None, None
        if m.group("num"):
            dots = m.group("dots")
            number = m.group("num") + ("..." if dots in ("...", "…") else ".")
            side = chess.BLACK if dots in ("...", "…") else chess.WHITE
        elif m.group("bdots"):
            side = chess.BLACK
        out.append(parse_san_token(m.group("san") + (m.group("check") or ""), number=number, side=side))
    return out
