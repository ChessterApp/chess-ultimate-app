"""The older part of a session, in brief, so the coach remembers what was discussed before the recent
exchanges it sees in full.

The text turn hands the model the last ten exchanges verbatim (src/server.py, «Previous conversation»);
everything before that was simply gone, and a long voice session (the pipeline, 25.10) makes twenty-turn
conversations ordinary: «а что ты говорил про тот план?» fifteen turns back drew a blank. Here the older
exchanges become one line each — the student's words and the coach's first words, QUOTED, never
paraphrased by a model — so nothing said in the session is forgotten, and nothing is invented about it.
The newest older exchanges stay when the character cap cuts; the model is told how many are not shown."""

from __future__ import annotations

import re
from typing import Iterable, Protocol

KEEP_MESSAGES = 20      # the recent messages the turn shows in full (ten exchanges)
MAX_CHARS = 3500        # the digest's budget: the newest older exchanges first
QUESTION_CHARS = 160
ANSWER_CHARS = 220


class _Message(Protocol):
    role: str
    content: str


def _brief(text: str, limit: int) -> str:
    """The first *limit* characters of *text* as plain words: markup off, cut at a word, an ellipsis after."""
    t = text or ""
    t = re.sub(r"\[\[[^\]]*\]\]", " ", t)                           # [[arrows: …]] board markup
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)                      # images
    t = re.sub(r"\[([^\]]+)\]\((?:https?://|/)[^)]*\)", r"\1", t)    # [text](url) → text
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"(^|\n)\s{0,3}#{1,6}\s+", r"\1", t)                 # headings
    t = re.sub(r"(^|\n)\s{0,3}(?:[-*•]|\d+[.)])\s+", r"\1", t)      # list bullets
    t = re.sub(r"\*\*|__|`+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limit:
        cut = t[:limit]
        space = cut.rfind(" ")
        t = (cut[:space] if space > limit // 2 else cut).rstrip(" ,;:—–-") + "…"
    return t


def conversation_digest(messages: Iterable[_Message], keep: int = KEEP_MESSAGES, max_chars: int = MAX_CHARS) -> str:
    """One line per exchange before the last *keep* messages, oldest first, under *max_chars*; "" when none."""
    items = list(messages)
    older = items[:-keep] if keep > 0 else items
    if not older:
        return ""
    lines: list[str] = []
    i = 0
    while i < len(older):
        m = older[i]
        role = getattr(m, "role", "")
        if role == "user":
            q = _brief(getattr(m, "content", ""), QUESTION_CHARS)
            a = ""
            if i + 1 < len(older) and getattr(older[i + 1], "role", "") == "assistant":
                a = _brief(getattr(older[i + 1], "content", ""), ANSWER_CHARS)
                i += 1
            if q or a:
                lines.append(f"- student: «{q}»" + (f" — coach: «{a}»" if a else ""))
        elif role == "assistant":
            a = _brief(getattr(m, "content", ""), ANSWER_CHARS)
            if a:
                lines.append(f"- coach: «{a}»")
        i += 1
    kept: list[str] = []
    total = 0
    for line in reversed(lines):
        if total + len(line) + 1 > max_chars:
            break
        kept.append(line)
        total += len(line) + 1
    kept.reverse()
    if not kept:
        return ""
    hidden = len(lines) - len(kept)
    head = ("Earlier in this conversation (before the recent messages below; oldest first"
            + (f"; {hidden} earlier exchange(s) not shown" if hidden else "")
            + "). When the student refers back to it, go by these lines — quote them, never invent what was said:")
    return head + "\n" + "\n".join(kept)
