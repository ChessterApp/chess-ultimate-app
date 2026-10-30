"""The relation checker in the answer check (plan 30.10): who attacks, defends, pins, holds what — said in a
sentence, judged on the board the sentence is about.

    text ─► extract_claims (claim_grammar + claim_rules) ─► judge_claim (claim_scene.boards_for → claim_judge.decide)
         ─► issue strings, by the mode COACH_RELATION_CHECK:
              off     not run;
              shadow  computed and recorded in ctx.relation_shadow, never shown (returns []);
              on      the issues cut the sentence and go to the rewrite like any other.

Fail-open: an exception anywhere in the path is swallowed and counted in ``ctx.relation_stats['errors']``; the
sentence is then judged by the other checks alone. ``extract_claims`` and ``judge_claim`` are the seams the
evaluation harness (scripts/eval_relations.py) swaps for the recorded claims and the reference judge.

Wiring (WP-C):
  merge     a relation issue that repeats one the other checks already gave is dropped; for the rewrite the relation
            issues go first (they carry the board truth) and at most MAX_FIX_ISSUES go (``issues_for_fix``).
  timing    ``relation_stats['ms']`` (all calls of the turn) and ``['ms_max']`` (the slowest call).
  log       ``turn_summary`` (counters for the turn_end event) and ``shadow_entries`` (the shadow records, bounded
            for one coach_events row) — src/server.py writes them; collected by
            ``jq -c 'select(.event_type=="relation_check")' hermes/metrics/coach-events-*.jsonl``.
  solution  ``solution_lines``: the lines that solve the task on the board, from the current position — the
            puzzle's solution, the site lesson's solution, the engine's best line of the turn when the question asks
            for a move or a lesson task is on the board. Their first moves give the boards an answer about an
            unnamed solution move describes (claim_scene's alternatives; plan §1.2).
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Iterable, Optional

import chess

from src.claim_types import Claim, Verdict

logger = logging.getLogger(__name__)

MAX_CLAIMS = 8  # claims judged per sentence
MAX_ISSUE_CHARS = 220
MAX_FIX_ISSUES = 3  # issues of one sentence that go to the rewrite (src/answer_check.fix_messages)
MAX_ISSUED = 64  # relation issues of a turn remembered for the rewrite's order
SHADOW_BYTES = 6000  # the shadow records of one turn in one coach_events row (the logger stubs payloads > 8 KB)
SOLUTION_PLIES = 6  # plies of a solution line kept (the resolver plays its first one or two)

_OFF = ("off", "0", "false", "no", "")
_ON = ("on", "1", "true", "yes")


def mode() -> str:
    """'off' | 'shadow' | 'on', read from src.config at call time (tests and the harness patch it)."""
    from src import config

    raw = str(getattr(config, "COACH_RELATION_CHECK", "on") or "").strip().lower()
    if raw in _OFF:
        return "off"
    if raw in _ON:
        return "on"
    return "shadow"  # 'shadow', or a value nobody meant: computed, never shown


def extract_claims(text: str, ctx: Any, state: dict) -> list[Claim]:
    """The claims of *text*: the grammar's and the board rules'."""
    from src import claim_grammar, claim_rules

    return list(claim_grammar.extract(text, state, getattr(ctx, "language", None))) + list(claim_rules.extract(text, state))


def judge_claim(claim: Claim, ctx: Any, state: dict) -> Optional[Verdict]:
    """The verdict on *claim*, or None when its boards cannot be built (never reported)."""
    from src import claim_judge, claim_scene

    boards = claim_scene.boards_for(claim, ctx, state)
    if boards is None:
        return None
    return claim_judge.decide(claim, boards, ctx)


def remember(text: str, claims: list[Claim], ctx: Any, state: dict) -> None:
    from src import claim_scene

    claim_scene.remember(text, claims, ctx, state)


def issue_text(claim: Claim, verdict: Verdict) -> str:
    """One English line, truth first, at most MAX_ISSUE_CHARS: «after 4.e5: White's pawn on e5 attacks d6 and f6 —
    not Black's knight on g8»."""
    truth = (verdict.truth or "").strip() or f"the {claim.rel} claim is not true on the board"
    line = f"{verdict.where}: {truth}" if verdict.where else truth
    line = " ".join(line.split())
    return line if len(line) <= MAX_ISSUE_CHARS else line[:MAX_ISSUE_CHARS - 1].rstrip() + "…"


def _stats(ctx: Any) -> dict:
    stats = getattr(ctx, "relation_stats", None)
    if stats is None:
        stats = {}
        try:
            ctx.relation_stats = stats
        except Exception:  # noqa: BLE001
            pass
    for key in ("calls", "claims", "flags", "errors"):
        stats.setdefault(key, 0)
    stats.setdefault("ms", 0.0)
    stats.setdefault("ms_max", 0.0)
    return stats


def _issues(text: str, ctx: Any, stats: dict) -> list[str]:
    state = ctx.relation_state
    claims = list(extract_claims(text, ctx, state))[:MAX_CLAIMS]
    stats["claims"] += len(claims)
    out = []
    for claim in claims:
        try:
            verdict = judge_claim(claim, ctx, state)
        except Exception:  # noqa: BLE001 — one broken claim never hides the others, never blocks the sentence
            stats["errors"] += 1
            logger.debug("relation check: judging %r failed", claim, exc_info=True)
            continue
        if verdict is not None and verdict.status == "false":
            out.append(issue_text(claim, verdict))
    try:
        remember(text, claims, ctx, state)
    except Exception:  # noqa: BLE001
        stats["errors"] += 1
        logger.debug("relation check: remembering the sentence failed", exc_info=True)
    return list(dict.fromkeys(out))


def relation_issues(text: str, ctx: Any, prior: list[str]) -> list[str]:
    """The relation claims of *text* that are false on their board, as issues (``on``); [] in ``shadow`` (they
    are recorded in ``ctx.relation_shadow``) and in ``off``. *prior* are the sentence's issues found so far: an
    issue they already hold is not given twice. Never raises."""
    current = mode()
    if current == "off":
        return []
    stats = _stats(ctx)
    stats["calls"] += 1
    started = time.perf_counter()
    try:
        issues = _issues(text, ctx, stats)
    except Exception:  # noqa: BLE001 — fail-open: the relation check never blocks an answer
        stats["errors"] += 1
        logger.debug("relation check failed", exc_info=True)
        issues = []
    try:
        given = set(prior or ())
        issues = [i for i in issues if i not in given]
    except Exception:  # noqa: BLE001 — an odd *prior* never hides the verdicts
        stats["errors"] += 1
    took = (time.perf_counter() - started) * 1000
    stats["ms"] += took
    stats["ms_max"] = max(stats["ms_max"], took)
    if issues:
        stats["flags"] += 1
    if current == "shadow":
        if issues:
            try:
                ctx.relation_shadow.append((text, list(issues)))
            except Exception:  # noqa: BLE001
                stats["errors"] += 1
        return []
    if issues:
        issued = stats.setdefault("issued", [])
        issued.extend(i for i in issues if i not in issued)
        del issued[:-MAX_ISSUED]
    return issues


# ── merge with the other checks' issues, for the rewrite ─────────────────────────────────────────────────────────
def issues_for_fix(issues: Iterable[str], ctx: Any, limit: int = MAX_FIX_ISSUES) -> list[str]:
    """The issues of one cut sentence as the rewrite gets them: each once, the relation checker's first (one line
    of board truth each, «after 4.e5: White's pawn on e5 attacks d6 and f6 — not …»), then the others in their
    order; at most *limit*. The full list stays in the logs. With the checker ``off`` the list goes as it is (the
    rewrite as before the checker). Never raises."""
    if mode() == "off":
        return list(issues or [])
    try:
        ordered = list(dict.fromkeys(i for i in issues or () if isinstance(i, str) and i.strip()))
        stats = getattr(ctx, "relation_stats", None) or {}
        issued = set(stats.get("issued") or ())
        ordered = [i for i in ordered if i in issued] + [i for i in ordered if i not in issued]
        return ordered[:max(1, limit)]
    except Exception:  # noqa: BLE001
        logger.debug("relation check: ordering the issues failed", exc_info=True)
        return list(issues or [])[:max(1, limit)]


# ── the turn's log record ───────────────────────────────────────────────────────────────────────────────────────
def turn_summary(ctx: Any) -> dict:
    """The counters for the turn's log record (src/server.py: the turn_end event and the relation_check event):
    relation_mode, relation_calls, relation_claims, relation_flags, relation_errors, relation_ms, relation_ms_max."""
    stats = getattr(ctx, "relation_stats", None) or {}
    return {
        "relation_mode": mode(),
        "relation_calls": int(stats.get("calls", 0)),
        "relation_claims": int(stats.get("claims", 0)),
        "relation_flags": int(stats.get("flags", 0)),
        "relation_errors": int(stats.get("errors", 0)),
        "relation_ms": round(float(stats.get("ms", 0.0)), 2),
        "relation_ms_max": round(float(stats.get("ms_max", 0.0)), 2),
    }


def shadow_entries(ctx: Any, max_bytes: int = SHADOW_BYTES) -> list[dict]:
    """``ctx.relation_shadow`` as ``[{sentence, issues}]`` for one log row: the sentences cut to 300 characters, the
    list cut from the end until it serializes within *max_bytes* (the event logger replaces a payload over 8 KB by a
    stub). Never raises."""
    try:
        out = [{"sentence": " ".join(str(sentence).split())[:300], "issues": [str(i)[:MAX_ISSUE_CHARS] for i in issues]}
               for sentence, issues in list(getattr(ctx, "relation_shadow", None) or [])]
        while out and len(json.dumps(out, ensure_ascii=False).encode("utf-8")) > max_bytes:
            out.pop()
        return out
    except Exception:  # noqa: BLE001
        return []


def log_record(ctx: Any) -> Optional[dict]:
    """The payload of the turn's ``relation_check`` event, or None when there is nothing to review (no flag, no
    error): the counters, the shadow records (shadow) and the relation issues that cut sentences (on)."""
    summary = turn_summary(ctx)
    if not summary["relation_flags"] and not summary["relation_errors"]:
        return None
    stats = getattr(ctx, "relation_stats", None) or {}
    record = dict(summary)
    record["relation_shadow"] = shadow_entries(ctx)
    record["relation_issued"] = [str(i)[:MAX_ISSUE_CHARS] for i in list(stats.get("issued") or [])[:12]]
    record["relation_shadow_total"] = len(getattr(ctx, "relation_shadow", None) or [])
    return record


# ── solution lines ──────────────────────────────────────────────────────────────────────────────────────────────
# The question asks for a move to play (or how to solve the position): «Какой здесь первый ход?», «что играть?»,
# «как белым выиграть?», «чем ходить», "best move", "what should I play", «қандай жүріс». A move named by the
# student («стоит ли брать f4?») is not a request for one: its own board is added by the turn (named_moves).
_ASKS_MOVE = re.compile(
    r"(?<![\w-])(?:"
    r"как(?:ой|ую|им|ие)\s+(?:[\w-]+\s+){0,3}?ход\w*|"
    r"(?:перв|лучш|сильнейш|следующ|правильн|верн)\w+\s+ход\w*|"
    r"чем\s+(?:мне\s+|белым\s+|ч[её]рным\s+)?(?:ходить|пойти|сходить|играть|сыграть|бить)|"
    r"куда\s+(?:мне\s+|белым\s+|ч[её]рным\s+)?(?:ходить|пойти|сходить|идти|ставить)|"
    r"что\s+(?:мне\s+|тут\s+|здесь\s+|теперь\s+|сейчас\s+|белым\s+|ч[её]рным\s+){0,2}"
    r"(?:играть|сыграть|делать|ходить|предпринять)|"
    r"как\s+(?:мне\s+|тут\s+|здесь\s+|белым\s+|ч[её]рным\s+){0,2}"
    r"(?:решить|выиграть|победить|спастись|защититься|поставить\s+мат|заматовать|матовать|реализовать)|"
    r"(?:найди|подскажи|покажи)\s+(?:мне\s+)?(?:ход|решение|лучший\s+ход)|"
    r"best\s+move|first\s+move|next\s+move|which\s+move|what\s+move|"
    r"what\s+(?:should|do|can|would)\s+(?:i|we|white|black)\s+(?:play|do)|"
    r"how\s+(?:do|can|should|would)\s+(?:i|we|white|black)\s+(?:solve|win|mate|play)|how\s+to\s+(?:solve|win|mate)|"
    r"қандай\s+жүріс\w*|ең\s+жақсы\s+жүріс\w*|не\s+ойна\w*|қалай\s+(?:шешу|ұту|жеңу)\w*"
    r")(?![\w-])",
    re.IGNORECASE)
# A task of a lesson named in the question («Задача из урока «Вилка» … Какой здесь первый ход?» — the site's
# lesson page sends it so; «упражнение 3 из урока»).
_LESSON_TASK = re.compile(r"(?<![\w-])(?:задач\w*|упражнени\w*|пример\w*)\s+(?:\d+\s+)?из\s+урок\w*|"
                          r"(?:task|exercise|puzzle)\s+(?:\d+\s+)?(?:from|of)\s+(?:the\s+)?lesson", re.IGNORECASE)


def asks_for_a_move(question: Optional[str]) -> bool:
    return bool(question) and bool(_ASKS_MOVE.search(question.replace("ё", "е")))


def names_a_lesson_task(question: Optional[str]) -> bool:
    return bool(question) and bool(_LESSON_TASK.search(question))


def _key(board: chess.Board) -> str:
    return board.board_fen() + (" w" if board.turn else " b")


def line_from(start_fen: Optional[str], moves: Iterable[str], current: Optional[chess.Board],
              plies: int = SOLUTION_PLIES) -> Optional[list[str]]:
    """The part of the line *moves* (SAN or UCI, played from *start_fen*) that is still to come from *current*: the
    moves after the point where the line stands on *current*'s position, as SAN, at most *plies*; None when the
    line never reaches *current*, is over there, or cannot be played. Never raises."""
    if current is None:
        return None
    try:
        board = chess.Board(start_fen) if start_fen else current.copy(stack=False)
    except (ValueError, TypeError):
        return None
    target = _key(current)
    out: Optional[list[str]] = [] if _key(board) == target else None
    for raw in moves or ():
        token = str(raw).strip()
        token = re.sub(r"^\d+\.(?:\.\.)?\s*", "", token)
        if not token:
            continue
        try:
            move = board.parse_san(token)
        except ValueError:
            try:
                move = chess.Move.from_uci(token)
            except ValueError:
                break
            if move not in board.legal_moves:
                break
        if out is not None:
            out.append(board.san(move))
            if len(out) >= plies:
                break
        board.push(move)
        if out is None and _key(board) == target:
            out = []
    return out or None


def add_solution_line(ctx: Any, line: Optional[list[str]]) -> None:
    """Add *line* (SAN from the current position) to ``ctx.solution_lines`` once."""
    if not line:
        return
    lines = getattr(ctx, "solution_lines", None)
    if lines is None:
        return
    if list(line) not in [list(x) for x in lines]:
        lines.append(list(line))


def engine_solution_line(note: Optional[dict], ctx: Any, question: Optional[str], task_on_board: bool = False,
                         ) -> Optional[list[str]]:
    """The engine's best line of the turn (``engine_note``'s first line, already computed — no new engine call) as
    a solution line, when the question asks for a move or a task is on the board, and only when the line is from the
    position the answer is about (``ctx.current``; not a hidden or other board). Never raises."""
    try:
        if not note or ctx is None or getattr(ctx, "current", None) is None:
            return None
        if not (task_on_board or asks_for_a_move(question) or names_a_lesson_task(question)):
            return None
        first = (note.get("lines") or [None])[0] or {}
        moves = first.get("moves") or []
        if isinstance(moves, str):
            moves = moves.split()
        fen = note.get("fen")
        if not fen or _key(chess.Board(fen)) != _key(ctx.current):
            return None
        return line_from(fen, moves, ctx.current)
    except Exception:  # noqa: BLE001 — bookkeeping never breaks a turn
        logger.debug("relation check: the engine's solution line failed", exc_info=True)
        return None
