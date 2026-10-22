"""A known opening trap recognised by the position on the board, not by its name (2026-10-22).

Production 19.10 («Можно мне взять пешку e5 конём?» after 1.e4 e5 2.Nf3 Nc6 3.Bc4 Nd4): the engine
note said Nxe5 was a serious mistake and the reply Qg5 punishes it, and the coach still answered «да,
можно взять» with an invented exchange on e5. The trap is in the openings book (src/openings_book.TRAPS,
every line checked with python-chess), but only a question that names it got the block. Here the
positions along every trap line are indexed, and a board standing on one gets the lines from that
point: the move that walks into the trap and how it is punished, and the sound continuation.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

import chess

from src.openings_book import TRAPS, _split_moves

_SIDE_LINE = re.compile(r"defen[cs]e|declined|avoided|refuted", re.IGNORECASE)


def _key(board: chess.Board) -> str:
    return board.board_fen() + (" w" if board.turn else " b")


@lru_cache(maxsize=1)
def _index() -> dict:
    """position key → [(name, eco, sans, ply)]: every position along every trap line (not the start)."""
    out: dict = {}
    for eco, name, pgn in TRAPS:
        board = chess.Board()
        sans = []
        for san in _split_moves(pgn):
            try:
                move = board.parse_san(san)
            except ValueError:
                break
            sans.append(board.san(move))
            board.push(move)
        board = chess.Board()
        for ply, san in enumerate(sans):
            if ply > 0:
                out.setdefault(_key(board), []).append((name, eco, tuple(sans), ply))
            board.push_san(san)
    return out


def _numbered(sans: list, board: chess.Board) -> str:
    """«4.Nxe5 Qg5 5.Nxf7 …» from the position *board* (the side to move starts)."""
    out = []
    b = board.copy(stack=False)
    for san in sans:
        if b.turn == chess.WHITE:
            out.append(f"{b.fullmove_number}.{san}")
        elif not out:
            out.append(f"{b.fullmove_number}...{san}")
        else:
            out.append(san)
        try:
            b.push_san(san)
        except ValueError:
            break
    return " ".join(out)


def traps_at(fen: Optional[str]) -> list[dict]:
    """The trap lines passing through the position in *fen*, from this point on.

    Each: name, eco, rest (SAN from here), numbered text, ``mates`` (the line ends in mate), ``loser``
    ('white'/'black', the side mated), ``trap_move`` (the first move from here) and ``walks_in`` — the
    side to move is the one that gets mated, so that first move is the mistake."""
    if not fen:
        return []
    try:
        board = chess.Board(fen)
    except ValueError:
        return []
    hits = []
    for name, eco, sans, ply in _index().get(_key(board), []):
        rest = list(sans[ply:])
        if not rest:
            continue
        end = board.copy(stack=False)
        for san in rest:
            end.push_san(san)
        mates = end.is_checkmate()
        loser = ("white" if end.turn == chess.WHITE else "black") if mates else None
        hits.append({
            "name": name, "eco": eco, "rest": rest, "text": _numbered(rest, board), "mates": mates,
            "loser": loser, "trap_move": rest[0],
            "walks_in": bool(mates and ((end.turn == chess.WHITE) == (board.turn == chess.WHITE))),
            "side_line": bool(_SIDE_LINE.search(name)),
            "fens": _fens(board, rest),
        })
    return hits


def _fens(board: chess.Board, rest: list) -> list[str]:
    b = board.copy(stack=False)
    out = []
    for san in rest:
        b.push_san(san)
        out.append(b.fen())
    return out


def trap_block(fen: Optional[str], ru_names: Optional[dict] = None) -> str:
    """The block for the turn, or "" when no trap passes through the position."""
    hits = traps_at(fen)
    if not hits:
        return ""
    if ru_names is None:
        try:
            from src.opening_knowledge import RU_NAMED

            ru_names = RU_NAMED
        except Exception:  # noqa: BLE001
            ru_names = {}
    try:
        mover = "White" if chess.Board(fen).turn else "Black"
    except ValueError:
        mover = "The side to move"
    lines = []
    for h in sorted(hits, key=lambda x: (x["side_line"], not x["walks_in"])):
        base = re.split(r",\s", h["name"], 1)[0]
        ru = ru_names.get(base) or ru_names.get(h["name"])
        title = f"«{h['name']}»" + (f" ({ru})" if ru else "")
        if h["walks_in"]:
            lines.append(f"- {title}: the tempting {h['trap_move']} here LOSES — {h['text']} and {mover} is mated. "
                         "Never recommend it; if the student asks whether to play it, say no and show this line.")
        elif h["mates"]:
            lines.append(f"- {title}: from here {h['text']} — mate; this is the punishment line {mover} plays.")
        else:
            lines.append(f"- {title}: the sound continuation from here is {h['text']}.")
    return ("## A known opening trap passes through THIS position (verified lines)\n" + "\n".join(lines)
            + "\nName the trap and answer from these lines, not from a count of exchanges.")
