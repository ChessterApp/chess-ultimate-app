"""Arrows and highlights written inline in the text coach's answer.

A board_control call costs the text coach a whole model round trip before it
writes a word — 5-7 s with DeepSeek's reasoning (bench 2026-09-27: "draw the
arrows" and "write the answer" were two steps on most position questions). The
prompt has the model mark arrows and squares inside its answer instead:

    [[arrows: d2d4 green, c5d4 red]]   [[squares: d4 e5]]

and MarkupFilter cuts the marks out of the streamed text and turns them into
board actions the moment they are complete. The web and the mobile app replace
the arrows (and highlights) on every draw_arrows (highlight_squares) action, so
each action carries every arrow of the answer so far.

Voice keeps board_control: a spoken answer cannot carry marks.
"""

import re
from typing import Optional

_COLORS = ("green", "red", "blue", "yellow")
_MARK = re.compile(r"\[\[\s*(arrows?|squares?|highlights?)\s*:?\s*(.*?)\s*\]\]", re.IGNORECASE | re.DOTALL)
_ARROW = re.compile(
    r"\b([a-h][1-8])\s*(?:->|-|–|—|>)?\s*([a-h][1-8])\b(?:\s*\(?\s*(green|red|blue|yellow)\b)?",
    re.IGNORECASE,
)
_SQUARE = re.compile(r"\b([a-h][1-8])\b", re.IGNORECASE)
# An opened "[[" that has not closed within this many characters is not a mark.
MAX_MARK_CHARS = 400


class MarkupFilter:
    """Streaming filter for one answer: ``feed`` text deltas, get clean text and board actions."""

    def __init__(self) -> None:
        self._pending = ""
        self._arrows: list[dict] = []
        self._squares: list[str] = []
        self._last = ""          # last character let through
        self._eat_space = False  # a mark was cut after a space: drop the space after it

    def _emit(self, out: list[str], text: str) -> None:
        if not text:
            return
        if self._eat_space:
            self._eat_space = False
            if text[0] == " ":
                text = text[1:]
                if not text:
                    return
        out.append(text)
        self._last = text[-1]

    def feed(self, text: str) -> tuple[str, list[dict]]:
        self._pending += text
        out: list[str] = []
        actions: list[dict] = []
        while True:
            start = self._pending.find("[[")
            if start < 0:
                # A trailing "[" may open a mark in the next delta.
                keep = 1 if self._pending.endswith("[") else 0
                self._emit(out, self._pending[: len(self._pending) - keep])
                self._pending = self._pending[len(self._pending) - keep:]
                break
            self._emit(out, self._pending[:start])
            end = self._pending.find("]]", start)
            if end < 0:
                rest = self._pending[start:]
                if len(rest) > MAX_MARK_CHARS:
                    self._emit(out, rest)
                    self._pending = ""
                else:
                    self._pending = rest
                break
            mark = self._pending[start:end + 2]
            self._pending = self._pending[end + 2:]
            parsed = self._parse(mark)
            if parsed is None:
                self._emit(out, mark)  # some other [[...]]: leave it in the text
                continue
            if parsed:
                actions.append(parsed)
            self._eat_space = self._last in (" ", "\n")
        return "".join(out), actions

    def flush(self) -> str:
        """The text still held back (an unfinished mark) — as plain text."""
        out: list[str] = []
        self._emit(out, self._pending)
        self._pending = ""
        return "".join(out)

    def _parse(self, mark: str) -> Optional[dict]:
        """A board action for *mark*; {} for a known mark with nothing usable; None if not ours."""
        m = _MARK.fullmatch(mark)
        if not m:
            return None
        kind, body = m.group(1).lower(), m.group(2)
        if kind.startswith("arrow"):
            added = False
            for a, b, color in _ARROW.findall(body):
                arrow = {"from": a.lower(), "to": b.lower(), "brush": (color or "green").lower()}
                if a.lower() != b.lower() and arrow not in self._arrows:
                    self._arrows.append(arrow)
                    added = True
            return {"type": "draw_arrows", "arrows": list(self._arrows)} if added else {}
        squares = [s.lower() for s in _SQUARE.findall(body)]
        new = [s for s in dict.fromkeys(squares) if s not in self._squares]
        if not new:
            return {}
        self._squares.extend(new)
        color = next((c for c in _COLORS if re.search(rf"\b{c}\b", body, re.IGNORECASE)), "yellow")
        return {"type": "highlight_squares", "squares": list(self._squares), "color": color}


def strip_markup(text: str) -> tuple[str, list[dict]]:
    """Whole-text version of the filter (for an answer that was not streamed)."""
    f = MarkupFilter()
    clean, actions = f.feed(text)
    return clean + f.flush(), actions
