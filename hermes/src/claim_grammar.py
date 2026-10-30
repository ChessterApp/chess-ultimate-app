"""The parser of the relation checker (WP-A): the words of one sentence → the claims it makes, each with the
position its words point at (a textual ``Pos``; no board work here — claim_scene plays the moves).

Stub from WP-0: the signature is frozen; until WP-A lands it finds no claim, so the checker reports nothing.
"""
from __future__ import annotations

from typing import Optional

from src.claim_types import Claim


def extract(text: str, state: dict, language: Optional[str] = None) -> list[Claim]:
    """The claims *text* makes. *state* is ``ctx.relation_state`` (immutable values only: the previous
    sentence's antecedents for pronouns, «тогда»); *language* is the answer's language when known."""
    return []
