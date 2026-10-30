"""The position resolver (WP-B): a claim's textual ``Pos`` → the boards it can mean, built from the
CheckContext (the board now, the shown board, the game, the lines of the turn, the scene the answer wrote, the
solution lines), and the memory of what the sentence set up for the next one.

Stub from WP-0: the signatures are frozen; until WP-B lands no claim has a board, so nothing is judged.
"""
from __future__ import annotations

from typing import Any, Optional

from src.claim_types import BoardSet, Claim


def boards_for(claim: Claim, ctx: Any, state: dict) -> Optional[BoardSet]:
    """The boards *claim* is about, or None when its position cannot be built (an unplayable move, the past
    with no history, a skipped claim): an unresolved claim is never reported."""
    return None


def remember(text: str, claims: list[Claim], ctx: Any, state: dict) -> None:
    """Record in *state* what the next sentence may refer to (antecedents, the end position of a told line).
    Only immutable values go into *state*: ``check_sentence`` restores a shallow copy when the sentence is cut."""
    return None
