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

Owned by WP-C after WP-0 (merge policy with the legacy issues, timing in the turn log).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from src.claim_types import Claim, Verdict

logger = logging.getLogger(__name__)

MAX_CLAIMS = 8  # claims judged per sentence
MAX_ISSUE_CHARS = 220

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
    are recorded in ``ctx.relation_shadow``) and in ``off``. *prior* are the sentence's issues found so far.
    Never raises."""
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
    stats["ms"] += (time.perf_counter() - started) * 1000
    if issues:
        stats["flags"] += 1
    if current == "shadow":
        if issues:
            try:
                ctx.relation_shadow.append((text, list(issues)))
            except Exception:  # noqa: BLE001
                stats["errors"] += 1
        return []
    return issues
