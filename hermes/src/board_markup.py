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
_MARK = re.compile(r"\[\[\s*(.*?)\s*\]\]", re.DOTALL)
_KIND = re.compile(r"(arrows?|squares?|highlights?)\b\s*:?\s*", re.IGNORECASE)
_COLOR_ONLY = re.compile(r"(?:green|red|blue|yellow)", re.IGNORECASE)
# A bare [[…]] (no "arrows:" / "squares:") is ours only when it is this short.
_BARE_MAX = 40
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
        self._last = ""  # last character let through
        # After a cut mark: "held" — the space before it was kept back and goes
        # back only if a word follows; "emitted" — that space already went out,
        # so a space right after the mark is dropped.
        self._gap: Optional[str] = None

    def _emit(self, out: list[str], text: str) -> None:
        if not text:
            return
        if self._gap == "held":
            if text[0].isalnum():
                text = " " + text
        elif self._gap == "emitted" and text[0] == " ":
            text = text[1:]
            if not text:
                self._gap = None
                return
        self._gap = None
        out.append(text)
        self._last = text[-1]

    def feed(self, text: str) -> tuple[str, list[dict]]:
        self._pending += text
        out: list[str] = []
        actions: list[dict] = []
        while True:
            start = self._pending.find("[[")
            if start < 0:
                # A trailing "[" (and the space before it) may open a mark in the next delta.
                keep = 0
                if self._pending.endswith("["):
                    keep = 2 if self._pending.endswith(" [") else 1
                self._emit(out, self._pending[: len(self._pending) - keep])
                self._pending = self._pending[len(self._pending) - keep:]
                break
            pre = self._pending[:start]
            end = self._pending.find("]]", start)
            if end < 0:
                hold = 1 if pre.endswith(" ") else 0  # the space travels with the mark
                rest = self._pending[start - hold:]
                if len(rest) > MAX_MARK_CHARS:
                    self._emit(out, self._pending)
                    self._pending = ""
                else:
                    self._emit(out, pre[: len(pre) - hold])
                    self._pending = rest
                break
            mark = self._pending[start:end + 2]
            self._pending = self._pending[end + 2:]
            parsed = self._parse(mark)
            if parsed is None:
                self._emit(out, pre + mark)  # some other [[...]]: leave it in the text
                continue
            if pre.endswith(" "):
                self._emit(out, pre[:-1])
                self._gap = "held"
            else:
                self._emit(out, pre)
                if self._gap is None:
                    self._gap = "emitted" if self._last in (" ", "\n") else None
            if parsed:
                actions.append(parsed)
        return "".join(out), actions

    def flush(self) -> str:
        """The text still held back (an unfinished mark) — as plain text."""
        out: list[str] = []
        self._emit(out, self._pending)
        self._pending = ""
        return "".join(out)

    def _parse(self, mark: str) -> Optional[dict]:
        """A board action for *mark*; {} for a mark of ours with nothing usable; None if not ours.

        Besides the documented [[arrows: …]] / [[squares: …]], models write bare
        marks — [[red]] next to a move, [[d2d4]] — which are ours too: a bare
        colour is dropped, bare squares become arrows or highlights.
        """
        m = _MARK.fullmatch(mark)
        if not m:
            return None
        body = m.group(1)
        k = _KIND.match(body)
        if k:
            kind, body = k.group(1).lower(), body[k.end():]
        elif _COLOR_ONLY.fullmatch(body.strip()):
            return {}
        elif len(body) <= _BARE_MAX and _ARROW.search(body):
            kind = "arrows"
        elif len(body) <= _BARE_MAX and _SQUARE.search(body):
            kind = "squares"
        else:
            return None
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
