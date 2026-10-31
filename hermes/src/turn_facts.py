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
