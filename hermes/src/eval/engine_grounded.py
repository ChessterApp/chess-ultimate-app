"""Task B — engine-grounded auto-eval (the L1 assertion suite).

Takes one coach turn ``{fen, user_text, assistant_text}``, extracts the factual
chess claims from the assistant reply, and adjudicates each against Stockfish
(reusing ``src/tools/stockfish.py``) and python-chess legality (reusing
``src/tools/check_moves.py``). Produces a structured, deterministic
``EngineVerdict``.

Two things are graded, both in the **correctness** channel (never pedagogy):
  * **Move claims** — a move the coach presents as a move (recommended or merely
    referenced). Illegal → hard fail (the hallucination label, now first-class).
    Legal + recommended → scored by centipawn-loss vs the engine best move,
    tiered best/good/inaccuracy/mistake/blunder.
  * **Eval claims** — "winning / equal / losing / +2 …" → compared against the
    engine evaluation (sign + magnitude), agree/disagree.

Deterministic given a fixed engine depth. Degrades gracefully to
``status="skipped"`` if Stockfish is missing — it never raises.
"""

import os
import re
from dataclasses import asdict, dataclass, field
from typing import Optional

import chess

# Reuse the coach's own engine + legality tools (see src/eval/__init__.py for the
# registry bootstrap that makes these importable without the framework).
from src.tools.check_moves import check_moves
from src.tools.stockfish import STOCKFISH_PATH, analyze_position

# Default search depth. Held constant across the golden-set builder, the runner,
# and the committed baseline so re-scoring the frozen answers is reproducible.
DEFAULT_DEPTH = 12

# Centipawn-loss tier thresholds (5-tier). cp_loss is measured from the mover's
# perspective: best_move_eval - played_move_eval, both in centipawns.
_TIERS = (
    (10, "best", 1.0),
    (50, "good", 0.85),
    (100, "inaccuracy", 0.6),
    (200, "mistake", 0.3),
)
_BLUNDER = ("blunder", 0.0)

# Cap raw evals (mate = ±10000 from the engine) before cp-loss arithmetic.
_EVAL_CAP = 3000

# ── Move extraction ────────────────────────────────────────────────────

# SAN: optional piece, disambiguation, capture, destination, promotion, check.
_SAN_RE = re.compile(
    r"\b(O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?)[+#]?"
)
# UCI: e.g. g1f3, e7e8q.
_UCI_RE = re.compile(r"\b([a-h][1-8][a-h][1-8][qrbnQRBN]?)\b")

# Words that mark a nearby move token as a *recommendation* (coach telling the
# player to make that move) rather than an incidental reference.
_CUE_BEFORE = (
    "play", "best", "recommend", "suggest", "should", "consider", "try",
    "go for", "go with", "strongest", "the move is", "i'd", "i would",
    "you want", "look at", "prefer", "correct move", "right move",
)
_CUE_AFTER = (
    "is best", "is the best", "is strong", "is strongest", "is winning",
    "is correct", "is the move", "wins", "is right",
)


def _has_cue(text: str, start: int, end: int) -> bool:
    """True if a recommendation cue sits just before/after a token span."""
    before = text[max(0, start - 45):start].lower()
    after = text[end:end + 25].lower()
    if any(c in before for c in _CUE_BEFORE):
        return True
    if any(c in after for c in _CUE_AFTER):
        return True
    return False


def _extract_move_tokens(text: str, board: chess.Board) -> list[dict]:
    """Find move-shaped tokens, dedupe, and tag each as cued or not.

    Returns ``[{token, cued}]`` in first-appearance order. Legality is resolved
    later (in bulk, via check_moves) so this stays pure string work.
    """
    seen: dict[str, dict] = {}
    for regex in (_SAN_RE, _UCI_RE):
        for m in regex.finditer(text):
            token = m.group(1)
            cued = _has_cue(text, m.start(1), m.end(1))
            if token not in seen:
                seen[token] = {"token": token, "cued": cued}
            elif cued:  # a later cued mention upgrades an earlier bare one
                seen[token]["cued"] = True
    return list(seen.values())


def _legality_map(fen: str, tokens: list[str]) -> dict[str, dict]:
    """Legality per token via check_moves, batched (its cap is 10 per call)."""
    out: dict[str, dict] = {}
    for i in range(0, len(tokens), 10):
        batch = tokens[i:i + 10]
        res = check_moves(fen, batch)
        if "results" not in res:  # invalid FEN etc. — treat all as unresolved
            for t in batch:
                out[t] = {"legal": False, "reason": res.get("error", "unknown")}
            continue
        for r in res["results"]:
            out[str(r["move"])] = r
    return out


# ── Eval-claim extraction ──────────────────────────────────────────────

# Each entry: (regex, predicate(eval_pawns) -> bool, label). Evals are read from
# the side-to-move's perspective (positive = good for the player to move, which
# is the player the coach is addressing).
_EVAL_PATTERNS = [
    (re.compile(r"\bwinning\b|\bdecisive\b|\bmuch better\b|\bclearly better\b|\bwinning advantage\b", re.I),
     lambda e: e >= 1.5, "winning"),
    (re.compile(r"\blosing\b|\blost\b|\bmuch worse\b|\bdecisively worse\b", re.I),
     lambda e: e <= -1.5, "losing"),
    (re.compile(r"\bequal\b|\bbalanced\b|\blevel\b|\broughly equal\b|\bequal(?:ity)?\b", re.I),
     lambda e: abs(e) <= 0.6, "equal"),
    (re.compile(r"\b(?:slightly |a bit )?better\b|\badvantage\b|\bedge\b|\bupper hand\b", re.I),
     lambda e: e >= 0.4, "better"),
    (re.compile(r"\bworse\b|\bstruggling\b|\bpassive\b|\bunder pressure\b", re.I),
     lambda e: e <= -0.4, "worse"),
]
# Explicit numeric eval like "+2", "-1.5", "+0.5".
_NUM_EVAL_RE = re.compile(r"(?<![\w.])([+-]\d+(?:\.\d+)?)(?!\d)")


def _clip(cp: float) -> float:
    return max(-_EVAL_CAP, min(_EVAL_CAP, cp))


# ── Public data model ──────────────────────────────────────────────────


@dataclass
class Claim:
    text: str
    kind: str            # recommended_move | move_reference | illegal_move | eval_claim
    verdict: str         # tier / legal / illegal / agree / disagree
    score: Optional[float]
    detail: dict = field(default_factory=dict)


@dataclass
class EngineVerdict:
    status: str                         # ok | skipped
    correctness_score: Optional[float]  # mean of scored claims, [0,1]
    illegal_move_rate: float
    claims: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _stockfish_available(stockfish_path: str) -> bool:
    return os.path.exists(stockfish_path)


def _eval_after_move(fen: str, move: chess.Move, depth: int, path: str) -> Optional[float]:
    """Centipawns from the mover's perspective after playing ``move``."""
    board = chess.Board(fen)
    board.push(move)
    res = analyze_position(board.fen(), depth=depth, multipv=1, stockfish_path=path)
    if "error" in res:
        return None
    # analyze returns eval from the new side-to-move (the opponent). Negate to
    # express it from the original mover's perspective.
    return -_clip(res["evaluation"] * 100.0)


def _grade_move(
    fen: str, token: str, leg: dict, best_uci: str, best_eval_cp: float,
    depth: int, path: str,
) -> Claim:
    """Grade a legal, cued move by centipawn loss vs the engine best move."""
    uci = leg.get("uci", "")
    if uci == best_uci:
        cp_loss = 0.0
    else:
        move = chess.Move.from_uci(uci)
        played_cp = _eval_after_move(fen, move, depth, path)
        if played_cp is None:
            return Claim(token, "recommended_move", "skipped", None,
                         {"reason": "engine unavailable"})
        cp_loss = max(0.0, best_eval_cp - played_cp)

    for thresh, label, score in _TIERS:
        if cp_loss <= thresh:
            tier, sc = label, score
            break
    else:
        tier, sc = _BLUNDER

    return Claim(
        token, "recommended_move", tier, sc,
        {"cp_loss": round(cp_loss, 1), "engine_best": best_uci, "played_uci": uci},
    )


def _grade_eval_claims(text: str, engine_eval_pawns: float) -> list[Claim]:
    """Compare textual/numeric eval claims against the engine evaluation."""
    claims: list[Claim] = []
    for regex, predicate, label in _EVAL_PATTERNS:
        m = regex.search(text)
        if not m:
            continue
        agree = predicate(engine_eval_pawns)
        claims.append(Claim(
            m.group(0), "eval_claim", "agree" if agree else "disagree",
            1.0 if agree else 0.0,
            {"claim": label, "engine_eval": round(engine_eval_pawns, 2)},
        ))
    # Explicit numeric eval — agree if within ±0.75 pawns of the engine.
    for m in _NUM_EVAL_RE.finditer(text):
        try:
            stated = float(m.group(1))
        except ValueError:
            continue
        if abs(stated) > 50:  # not a chess eval (e.g. a year, move count)
            continue
        agree = abs(stated - engine_eval_pawns) <= 0.75
        claims.append(Claim(
            m.group(0), "eval_claim", "agree" if agree else "disagree",
            1.0 if agree else 0.0,
            {"claim": "numeric", "stated": stated, "engine_eval": round(engine_eval_pawns, 2)},
        ))
    return claims


def evaluate_turn(
    fen: str,
    assistant_text: str,
    user_text: str = "",
    depth: int = DEFAULT_DEPTH,
    stockfish_path: str = STOCKFISH_PATH,
) -> EngineVerdict:
    """Adjudicate one coach turn against the engine. Never raises.

    ``depth`` is the single deterministic knob — a fixed depth makes the verdict
    reproducible across machines, which the frozen golden labels and the CI gate
    rely on. (A time-based knob would make scores machine-dependent.)
    """
    notes: list = []

    # Validate FEN up front — an unparseable board can't be adjudicated.
    try:
        board = chess.Board(fen)
        if not board.is_valid():
            raise ValueError
    except (ValueError, IndexError):
        return EngineVerdict("skipped", None, 0.0, [], ["invalid_fen"])

    if not _stockfish_available(stockfish_path):
        # Legality still works without the engine, but the primary metric can't
        # be computed — report skipped so aggregation ignores this case.
        return EngineVerdict("skipped", None, 0.0, [], ["stockfish_missing"])

    tokens = _extract_move_tokens(assistant_text, board)
    leg_map = _legality_map(fen, [t["token"] for t in tokens]) if tokens else {}

    # Engine baseline for the position (best move + eval), computed once.
    base = analyze_position(fen, depth=depth, multipv=1, stockfish_path=stockfish_path)
    if "error" in base:
        return EngineVerdict("skipped", None, 0.0, [], ["engine_error: " + base["error"]])
    best_uci = base.get("best_move", "")
    best_eval_cp = _clip(base.get("evaluation", 0.0) * 100.0)
    engine_eval_pawns = base.get("evaluation", 0.0)

    claims: list[Claim] = []
    move_claim_count = 0
    illegal_count = 0

    for t in tokens:
        token, cued = t["token"], t["cued"]
        leg = leg_map.get(token, {"legal": False, "reason": "unresolved"})
        if leg.get("legal"):
            move_claim_count += 1
            if cued:
                claims.append(_grade_move(
                    fen, token, leg, best_uci, best_eval_cp, depth, stockfish_path))
            else:
                claims.append(Claim(token, "move_reference", "legal", None,
                                    {"san": leg.get("san"), "uci": leg.get("uci")}))
        elif cued:
            # Illegal move presented as a move → hallucination hard fail.
            move_claim_count += 1
            illegal_count += 1
            claims.append(Claim(token, "illegal_move", "illegal", 0.0,
                                {"reason": leg.get("reason", "illegal")}))
        # illegal + uncued → almost certainly a square/file reference, not a
        # move claim. Skip it rather than false-flag.

    claims.extend(_grade_eval_claims(assistant_text, engine_eval_pawns))

    scored = [c.score for c in claims if c.score is not None]
    correctness = round(sum(scored) / len(scored), 4) if scored else None
    if correctness is None:
        notes.append("no_verifiable_claims")
    illegal_rate = (illegal_count / move_claim_count) if move_claim_count else 0.0

    return EngineVerdict(
        status="ok",
        correctness_score=correctness,
        illegal_move_rate=round(illegal_rate, 4),
        claims=[asdict(c) for c in claims],
        notes=notes,
    )
