"""The judge (WP-B): one claim on its boards → true / false / undecided, with the board truth for the rewrite.
A claim is false only when false on the primary board, true on no alternative board and judgeable on the board
the coach showed (plan §3.1). The board-rule relations go to ``claim_rules.RULE_JUDGES``.

Stub from WP-0: the signature is frozen; until WP-B lands every claim is undecided.
"""
from __future__ import annotations

from typing import Any

from src.claim_types import UNDECIDED, BoardSet, Claim, Verdict


def decide(claim: Claim, boards: BoardSet, ctx: Any) -> Verdict:
    """The verdict on *claim* over *boards*."""
    return UNDECIDED
