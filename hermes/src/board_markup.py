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

import chess

_COLORS = ("green", "red", "blue", "yellow")
_MARK = re.compile(r"\[\[\s*(.*?)\s*\]\]", re.DOTALL)
_KIND = re.compile(r"(arrows?|squares?|highlights?)\b\s*:?\s*", re.IGNORECASE)
_COLOR_ONLY = re.compile(r"(?:green|red|blue|yellow)", re.IGNORECASE)
# A tool call written out as text instead of made — «[[board_control: set_fen, fen="…"]]».
_TOOLISH = re.compile(
    r"(board_control|set_fen|load_pgn|set_puzzle|navigate|flip_board|clear_board|draw_arrows|highlight_squares)\b",
    re.IGNORECASE,
)
# A bare [[…]] (no "arrows:" / "squares:") is ours only when it is this short.
_BARE_MAX = 40
_ARROW = re.compile(
    r"\b([a-h][1-8])\s*(?:->|-|–|—|>)?\s*([a-h][1-8])\b(?:\s*\(?\s*(green|red|blue|yellow)\b)?",
    re.IGNORECASE,
)
_SQUARE = re.compile(r"\b([a-h][1-8])\b", re.IGNORECASE)
# Words after which the next thing is a move: «лучший ход [[…]]», «сыграй [[…]]», «начни с шаха [[…]]».
_EXPECTS_MOVE = re.compile(
    r"(?<![а-яa-z])(?:ход|ходом|ходы|сыграй|сыграть|играй|играть|играешь|играем|играет|сделай|начни\s+с\s+шаха|"
    r"(?:начни|начинаем|начнём|начнем|начинай|начать|начинается)\s+с|шах|шахом|"
    r"ответ|ответь|отвечай|продолжение|продолжай|move|moves|play|playing|plays|reply|answer|with|is|"
    r"start\s+with|begin\s+with|you\s+play)$", re.IGNORECASE)
# An opened "[[" that has not closed within this many characters is not a mark.
MAX_MARK_CHARS = 400


class MarkupFilter:
    """Streaming filter for one answer: ``feed`` text deltas, get clean text and board actions."""

    def __init__(self, fen: Optional[str] = None) -> None:
        self._pending = ""
        self._arrows: list[dict] = []
        self._squares: list[str] = []
        self._last = ""  # last character let through
        # The board the answer is about: an arrow mark standing where the move's
        # words should be («Начни с шаха — [[arrows: c1d1]].») is written out as
        # the move (production, 2026-10-06: «Начни с шаха —.», «Правильный первый
        # ход — » — the move was cut with the mark).
        self._fen = fen
        self._tail = ""  # the last characters let through, to see whether the move is already named
        self._sub: Optional[str] = None  # the move to write if the next text shows the mark was the words
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
        self._tail = (self._tail + text)[-60:]

    def _settle_sub(self, out: list[str], upcoming: str, final: bool = False) -> None:
        """Write the held move when the text after the mark shows it stood for the words."""
        if self._sub is None:
            return
        nxt = upcoming.lstrip(" ")
        if not nxt and not final:
            return  # decide when the next text comes
        if final or nxt[0] in ".,;!?)\n" or nxt.startswith(("—", "–")):
            gap = self._gap
            self._gap = None
            self._emit(out, (" " if gap == "held" or self._last not in (" ", "\n", "(") else "") + self._sub)
            if nxt and nxt[0] not in ".,;!?)\n" and not upcoming.startswith(" "):
                self._gap = "held"
        self._sub = None

    def _words_for(self, parsed: dict, before: str) -> Optional[str]:
        """The move an arrow mark names, when the words before it leave the move out."""
        if not parsed or parsed.get("type") != "draw_arrows" or not parsed.get("arrows"):
            return None
        stripped = (self._tail + before).rstrip()
        if not stripped or stripped[-1] in ".!?\n":
            return None
        # Only where a move is expected: after a dash or a colon, or a word that
        # asks for one — not a decoration after «на доске сейчас эта позиция».
        if not (stripped[-1] in "—–-:," or _EXPECTS_MOVE.search(stripped)):
            return None
        arrow = parsed["arrows"][-1]
        a, b = arrow["from"], arrow["to"]
        tail = (self._tail + before)[-40:].lower()
        if b in tail:
            return None  # «Играй Nf3 [[arrows: g1f3]].» — the move is already in the words
        san = None
        if self._fen:
            try:
                board = chess.Board(self._fen)
                move = chess.Move(chess.parse_square(a), chess.parse_square(b))
                if board.piece_type_at(move.from_square) == chess.PAWN and chess.square_rank(move.to_square) in (0, 7):
                    move.promotion = chess.QUEEN
                if move in board.legal_moves:
                    san = board.san(move)
            except (ValueError, IndexError):
                san = None
        return san or f"{a}–{b}"

    def feed(self, text: str) -> tuple[str, list[dict]]:
        self._pending += text
        out: list[str] = []
        actions: list[dict] = []
        self._settle_sub(out, self._pending)
        while True:
            start = self._pending.find("[[")
            if start < 0 and self._sub is not None and not self._pending.strip(" "):
                break  # spaces after a mark that may stand for the move: wait for what follows
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
            # «arrows=[h5e5 red]]]»: brackets opened inside the mark close after its "]]".
            mark_end = end + 2
            unclosed = self._pending.count("[", start + 2, end) - self._pending.count("]", start + 2, end)
            while unclosed > 0 and mark_end < len(self._pending) and self._pending[mark_end] == "]":
                mark_end += 1
                unclosed -= 1
            if unclosed > 0 and mark_end == len(self._pending) and len(self._pending) - start <= MAX_MARK_CHARS:
                hold = 1 if pre.endswith(" ") else 0
                self._emit(out, pre[: len(pre) - hold])
                self._pending = self._pending[start - hold:]
                break  # the closing "]" may be in the next delta
            mark = self._pending[start:mark_end]
            self._pending = self._pending[mark_end:]
            parsed = self._parse(mark)
            if parsed is None:
                self._emit(out, pre + mark)  # some other [[...]]: leave it in the text
                continue
            self._settle_sub(out, pre)
            words = self._words_for(parsed, pre)
            if pre.endswith(" "):
                self._emit(out, pre[:-1])
                self._gap = "held"
            else:
                self._emit(out, pre)
                if self._gap is None:
                    self._gap = "emitted" if self._last in (" ", "\n") else None
            if parsed:
                actions.append(parsed)
            if words:
                self._sub = words
                self._settle_sub(out, self._pending)
        return "".join(out), actions

    def flush(self) -> str:
        """The text still held back (an unfinished mark) — as plain text."""
        out: list[str] = []
        self._settle_sub(out, self._pending, final=not self._pending)
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
        elif _TOOLISH.match(body):
            # Without thinking the model sometimes writes the call instead of making
            # it. Its arrows / squares still count; a position change is dropped —
            # set_fen comes only from tools.
            if re.search(r"draw_arrows", body, re.IGNORECASE) and _ARROW.search(body):
                kind = "arrows"
            elif re.search(r"highlight", body, re.IGNORECASE) and _SQUARE.search(body):
                kind = "squares"
            else:
                return {}
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


def strip_markup(text: str, fen: Optional[str] = None) -> tuple[str, list[dict]]:
    """Whole-text version of the filter (for an answer that was not streamed)."""
    f = MarkupFilter(fen)
    clean, actions = f.feed(text)
    return clean + f.flush(), actions


def _arrow_fits(piece: chess.Piece, a: int, b: int) -> bool:
    """Can *piece* on a go to b at all (an empty board)? Pawns: one or two
    squares ahead or one diagonal step, their own way."""
    if a == b:
        return False
    dx = chess.square_file(b) - chess.square_file(a)
    dy = chess.square_rank(b) - chess.square_rank(a)
    adx, ady = abs(dx), abs(dy)
    pt = piece.piece_type
    if pt == chess.KNIGHT:
        return {adx, ady} == {1, 2}
    if pt == chess.BISHOP:
        return adx == ady
    if pt == chess.ROOK:
        return adx == 0 or ady == 0
    if pt == chess.QUEEN:
        return adx == ady or adx == 0 or ady == 0
    if pt == chess.KING:
        return max(adx, ady) == 1 or (ady == 0 and adx == 2)
    forward = 1 if piece.color == chess.WHITE else -1
    return (dx == 0 and dy * forward in (1, 2)) or (adx == 1 and dy * forward == 1)


def prune_arrows(action: dict, fen: Optional[str]) -> dict:
    """*action* with the arrows a piece on the board cannot draw removed.

    The game tester (2026-10-01) got an arrow g1→h4 for a rook: the sentence
    with the claim is checked and withheld, the arrow in it had already gone
    to the board. An arrow from a square with a piece on it must follow that
    piece's way of moving; an arrow from an empty square (a line of play) is
    kept. Returns {} when nothing is left to draw.
    """
    if not isinstance(action, dict) or action.get("type") != "draw_arrows" or not fen:
        return action
    try:
        board = chess.Board(fen)
    except ValueError:
        return action
    kept = []
    for arrow in action.get("arrows") or []:
        try:
            a, b = chess.parse_square(str(arrow.get("from"))), chess.parse_square(str(arrow.get("to")))
        except (ValueError, TypeError, AttributeError):
            continue
        piece = board.piece_at(a)
        if piece is None or _arrow_fits(piece, a, b):
            kept.append(arrow)
    if not kept:
        return {}
    return {**action, "arrows": kept}
