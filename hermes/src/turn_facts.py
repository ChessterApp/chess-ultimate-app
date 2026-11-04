"""The facts a turn gives the model, as data (plan 31.10, WP-0; frozen dataclass — the providers are P8's).

A fact is one English sentence the model reads, with its machine form and where it comes from. The answer check gets
the same list in ``CheckContext.facts``, so a detector can quote what the model was given in its issue
(«… (you were given: Nf6 is attacked by e5; safe squares: d5, g8, e4, g4)»).

Contract (plan §1.6): an outcome fact ("wins", "fork available", "lost", "safe") is emitted only with ``source``
engine, see or tablebase and its proof in ``data``; the label "verified on the board and by the engine" goes only on
facts checked that way. ``scripts/eval_prevent.py`` audits the outcome facts on the corpora.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

KINDS = ("material", "capture", "recapture", "fork", "piece_safety", "attack_balance", "focus", "check_replies",
         "rule", "opening_idea", "exchange", "textbook", "idea_verdict")
SOURCES = ("board", "see", "engine", "tablebase", "record", "book", "laws", "table")
# Kinds that state an outcome: they need a source that proves it.
OUTCOME_KINDS = ("fork", "piece_safety", "attack_balance", "recapture", "idea_verdict")
PROVING_SOURCES = ("see", "engine", "tablebase")


@dataclass(frozen=True)
class Fact:
    kind: str  # KINDS
    text: str  # the English sentence the model reads
    data: dict = field(default_factory=dict, hash=False, compare=True)  # squares, SANs, counts, eval, owner colour
    source: str = "board"  # SOURCES

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown fact kind {self.kind!r}")
        if self.source not in SOURCES:
            raise ValueError(f"unknown fact source {self.source!r}")

    @property
    def is_outcome(self) -> bool:
        return self.kind in OUTCOME_KINDS

    @property
    def proven(self) -> bool:
        """An outcome fact has a source that proves it; any other fact is proven by the board it names."""
        return not self.is_outcome or self.source in PROVING_SOURCES

    def to_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "data": dict(self.data), "source": self.source}

    @classmethod
    def from_dict(cls, d: dict) -> "Fact":
        return cls(kind=d["kind"], text=d.get("text", ""), data=dict(d.get("data") or {}),
                   source=d.get("source") or "board")


def given(ctx, kind: Optional[str] = None) -> list:
    """The facts the model was given this turn (``ctx.facts``), of *kind* when given."""
    facts = list(getattr(ctx, "facts", None) or [])
    return [f for f in facts if kind is None or getattr(f, "kind", None) == kind]


def quote(facts: Iterable[Fact], limit: int = 1) -> str:
    """« (you were given: …)» for an issue text, or "" when there is nothing to quote."""
    texts = [f.text for f in facts if getattr(f, "text", "")][:limit]
    return f" (you were given: {'; '.join(texts)})" if texts else ""


# ── providers (plan 31.10, P8) ─────────────────────────────────────────────────────────────────────────────────
# One function computes the typed facts of a board; the prompt blocks render their texts (prompt_builder.
# board_facts_block, engine_note_block) and scripts/eval_prevent.py audits them on the corpora. Every outcome fact
# carries its proof in ``data`` and a proving source (see, engine): a fork vetted by the engine's lines or by playing
# every reply out with exchange counts, a safe square counted by static exchange, a capture's net after the
# exchange on its square.
import logging  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from collections import OrderedDict  # noqa: E402

logger = logging.getLogger(__name__)

BOARD_KINDS = ("fork", "piece_safety", "attack_balance", "recapture", "check_replies", "material")
# The facts the engine line of the coach's turn gets beside it (voice_engine_note.engine_note collects them with its
# lines; prompt_builder.engine_note_block renders them).
ENGINE_KINDS = ("piece_safety", "attack_balance")
_RECENT: "OrderedDict[str, list]" = OrderedDict()
_RECENT_MAX = 256
_lock = threading.Lock()


# A caller that must keep the facts as they were before plan 31.10 — the /learn lesson tutor (its model input
# stays exactly as main's, review-wiring 01.11) — runs inside suspended(): every provider then answers as with
# COACH_TURN_FACTS=0, in that context only. A context variable: the server's engine executor carries it to the
# worker threads the lesson's searches run on (src/server._ContextExecutor).
import contextlib as _contextlib  # noqa: E402
import contextvars as _contextvars  # noqa: E402

_SUSPENDED: "_contextvars.ContextVar[bool]" = _contextvars.ContextVar("turn_facts_suspended", default=False)


@_contextlib.contextmanager
def suspended():
    """Inside the block the turn facts are off (as COACH_TURN_FACTS=0) for this context only."""
    token = _SUSPENDED.set(True)
    try:
        yield
    finally:
        _SUSPENDED.reset(token)


def without(fn):
    """*fn* wrapped to run inside suspended() (for a function submitted to another thread)."""
    def run(*args, **kwargs):
        with suspended():
            return fn(*args, **kwargs)

    run.__name__ = getattr(fn, "__name__", "run")
    run.__doc__ = getattr(fn, "__doc__", None)
    return run


def enabled() -> bool:
    """COACH_TURN_FACTS (default on); off: no provider runs and the prompts are as before. Off inside suspended()."""
    if _SUSPENDED.get():
        return False
    try:
        from src import config

        return bool(getattr(config, "COACH_TURN_FACTS", True))
    except Exception:  # noqa: BLE001
        return True


def facts_for_board(board, engine_lines=None, kinds=BOARD_KINDS) -> list:
    """The typed facts of *board* (a chess.Board) of *kinds*. *engine_lines* are the engine's lines of the turn in
    the raw analyze_* form ({pv, score, mate_in}); without them a fork is kept only when it wins by exchange count
    against every reply."""
    from src import position_facts as pf

    if board is None or not board.is_valid():
        return []
    out: list = []
    if "check_replies" in kinds:
        item = pf.check_reply_item(board)
        if item:
            out.append(Fact("check_replies", pf.check_reply_text(item, board), item, "board"))
    if "fork" in kinds:
        for move, targets, after, source in pf.vetted_forks(board, engine_lines)[:2]:
            out.append(Fact("fork", pf.fork_text(board, move, targets, after),
                            {"san": board.san(move), "uci": move.uci(),
                             "targets": [chess_name(s) for s in targets],
                             "proof": "engine line within %.1f of the best" % pf.FORK_ENGINE_MARGIN if source == "engine"
                             else "wins at least %d by exchange count against every reply" % pf.FORK_MIN_GAIN},
                            source))
    if "piece_safety" in kinds:
        for item in pf.safety_items(board, engine_lines):
            out.append(Fact("piece_safety", pf.safety_text(item), item, "see"))
    if "attack_balance" in kinds:
        for item in pf.balance_items(board):
            out.append(Fact("attack_balance", pf.balance_text(item, board), item, "see"))
    if "recapture" in kinds:
        items = pf.capture_items(board)
        if items:
            out.append(Fact("recapture", pf.capture_text(items, board), {"captures": items}, "see"))
    if "material" in kinds:
        m = pf.material_item(board)
        out.append(Fact("material", pf.material_text(m), {"white": m["white"], "black": m["black"], "diff": m["diff"],
                                                          "more": m["more"]}, "board"))
    return out


def chess_name(sq: int) -> str:
    import chess

    return chess.square_name(sq)


def collect(board, engine_lines=None, kinds=BOARD_KINDS) -> list:
    """facts_for_board behind the switch, never raising; the result is remembered by position and by whether the
    engine's lines vetted it (recent())."""
    if not enabled() or board is None:
        return []
    started = time.monotonic()
    try:
        facts = facts_for_board(board, engine_lines, kinds)
    except Exception:  # noqa: BLE001 — the facts are a bonus, never a blocker
        logger.debug("turn facts failed", exc_info=True)
        return []
    ms = (time.monotonic() - started) * 1000
    if ms > 20:
        logger.info("turn facts took %.1f ms on %s", ms, board.fen())
    try:
        key = (board.fen(), engine_lines is not None)
        with _lock:
            _RECENT[key] = facts
            _RECENT.move_to_end(key)
            while len(_RECENT) > _RECENT_MAX:
                _RECENT.popitem(last=False)
    except Exception:  # noqa: BLE001
        pass
    return facts


def recent(fen, engine: bool = False):
    """The facts last collected for *fen* — with the engine's lines when *engine* — or None when none were. A hook for
    CheckContext.facts (what the model was given on that board) and for the engine block of the coach's turn."""
    if not fen:
        return None
    try:
        import chess

        fen = chess.Board(fen).fen()
    except Exception:  # noqa: BLE001
        pass
    with _lock:
        got = _RECENT.get((fen, engine))
    return list(got) if got is not None else None


def texts(facts) -> list:
    return [f.text for f in facts if getattr(f, "text", "")]
