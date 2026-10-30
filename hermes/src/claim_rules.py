"""Board-rule relations (WP-D): «единственный ход», «нет выхода», «можно взять e5», «поле занято», «шахи по
линии d» — claims judged by the legal moves rather than by the attack map.

Stub from WP-0: the signatures are frozen; until WP-D lands it finds no claim and judges none.
"""
from __future__ import annotations

from typing import Any, Callable

import chess

from src.claim_types import Claim, Verdict

# relation → its judge on one board (claim_judge.decide dispatches the RULE_RELATIONS here).
RULE_JUDGES: dict[str, Callable[[Claim, chess.Board, Any], Verdict]] = {}


def extract(text: str, state: dict) -> list[Claim]:
    """The board-rule claims *text* makes (``Claim.source == 'rules'``)."""
    return []
