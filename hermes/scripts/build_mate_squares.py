"""Build src/data/mate_squares.json: where a bare king can be mated, ending by ending (plan 31.10, P5 C7).

Production check of 29.10 (set 30, «two-knights»): «Мат случается только если чёрный король сам забредёт в угол» —
with K+N+N against K the king can be mated on an edge square far from any corner as well (3k4/1K6/2N2N2/8/8/8/8/8 b
is mate on d8). A claim «mate (happens | can be forced) only in the corner / on the edge» is a statement about the
ending, not about one position, so it is judged against this table (src/endgame_claims.mate_square_issues).

For each ending — KQK, KRK, KBBK (bishops on opposite colours), KBNK, KNNK; the stronger side has the pieces, the
other a bare king — the script records, from python-chess alone:

  * ``possible``: every square of the bare king on which some legal position is checkmate (all placements of the
    pieces are enumerated for the 10 squares of the a1–d1–d4 triangle; the 8 symmetries of the board give the rest —
    reflections and rotations keep every piece's moves, and both bishop colours are enumerated);
  * ``example``: one mate per square of ``possible`` (a FEN with the bare king to move), so an issue can show it;
  * ``forced_outside``: for each region ("corner", "edge") whether the stronger side can *force* the mate outside it
    from a normal winning position — True / False, or null when not computed. KQK and KRK are solved here by
    retrograde analysis of the game "mate with the king outside the region" (the defender wins that game by a mate
    inside the region, stalemate, a capture, or by lasting for ever); the share of the positions with the bare king
    in the centre (d4, e4, d5, e5) and the stronger side to move that the stronger side still wins decides it
    (≥ 90 % True, ≤ 10 % False, else null). The four-piece endings are too large for this script: null (a claim
    with a verb of forcing about them is not judged), except KNNK, where mate cannot be forced at all (a draw in the
    tablebase from every normal position): False for every region.

Regions: "corner" is the 3×3 block at each corner (a8, b8, c8, a7 … c6 — «в углу» in a coach's mouth is the
corner area, not the corner square alone: a claim is judged false only when the mate lies outside every block);
"edge" is the first and eighth ranks and the a- and h-files.

Usage: python scripts/build_mate_squares.py [out.json]      (about 3–5 minutes; deterministic)
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from collections import deque
from pathlib import Path

import chess

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "src" / "data" / "mate_squares.json"

ENDINGS = {
    "KQK": [chess.QUEEN],
    "KRK": [chess.ROOK],
    "KBBK": [chess.BISHOP, chess.BISHOP],
    "KBNK": [chess.BISHOP, chess.KNIGHT],
    "KNNK": [chess.KNIGHT, chess.KNIGHT],
}
NAMES = {"KQK": "king and queen against king", "KRK": "king and rook against king",
         "KBBK": "king and two bishops against king", "KBNK": "king, bishop and knight against king",
         "KNNK": "king and two knights against king"}


def _corner_block() -> set:
    out = set()
    for f0, r0 in ((0, 0), (0, 5), (5, 0), (5, 5)):
        for f in range(f0, f0 + 3):
            for r in range(r0, r0 + 3):
                out.add(chess.square(f, r))
    return out


REGIONS = {
    "corner": _corner_block(),
    "edge": {sq for sq in chess.SQUARES if chess.square_file(sq) in (0, 7) or chess.square_rank(sq) in (0, 7)},
}
TRIANGLE = [chess.square(f, r) for r in range(4) for f in range(r, 4)]  # a1 b1 c1 d1 b2 c2 d2 c3 d3 d4


def _symmetries(sq: int) -> set:
    f, r = chess.square_file(sq), chess.square_rank(sq)
    out = set()
    for ff, rr in ((f, r), (r, f)):
        for a, b in ((ff, rr), (7 - ff, rr), (ff, 7 - rr), (7 - ff, 7 - rr)):
            out.add(chess.square(a, b))
    return out


def _mates_on(bk: int, pieces: list) -> tuple[bool, str]:
    """(mate possible with the bare (black) king on *bk*, an example FEN)."""
    others = [sq for sq in chess.SQUARES if sq != bk]
    for wk in others:
        if chess.square_distance(wk, bk) < 2:
            continue
        rest = [sq for sq in others if sq != wk]
        for placed in itertools.permutations(rest, len(pieces)):
            if len(pieces) == 2 and pieces[0] == pieces[1] and placed[0] > placed[1]:
                continue  # the same piece twice: one order is enough
            if pieces == [chess.BISHOP, chess.BISHOP] and \
                    (chess.square_file(placed[0]) + chess.square_rank(placed[0])) % 2 == \
                    (chess.square_file(placed[1]) + chess.square_rank(placed[1])) % 2:
                continue  # the bishop pair stands on both colours
            b = chess.Board(None)
            b.set_piece_at(wk, chess.Piece(chess.KING, chess.WHITE))
            b.set_piece_at(bk, chess.Piece(chess.KING, chess.BLACK))
            for sq, pt in zip(placed, pieces):
                b.set_piece_at(sq, chess.Piece(pt, chess.WHITE))
            b.turn = chess.BLACK
            if not b.is_check():
                continue
            if b.is_valid() and b.is_checkmate():
                return True, b.fen()
    return False, ""


def possible_squares(pieces: list) -> dict:
    """{square name: example FEN} of every square the bare king can be mated on."""
    out = {}
    for bk in TRIANGLE:
        ok, fen = _mates_on(bk, pieces)
        if not ok:
            continue
        base = chess.Board(fen)
        for sq in sorted(_symmetries(bk)):
            out[chess.square_name(sq)] = _transform_to(base, bk, sq)
    return dict(sorted(out.items(), key=lambda kv: chess.parse_square(kv[0])))


def _transform_to(board: chess.Board, src: int, dst: int) -> str:
    """The mate on *board* (bare king on *src*) moved by the symmetry that takes *src* to *dst*."""
    for t in _TRANSFORMS:
        if t(src) == dst:
            b = chess.Board(None)
            for sq, p in board.piece_map().items():
                b.set_piece_at(t(sq), p)
            b.turn = board.turn
            assert b.is_checkmate(), b.fen()
            return b.fen()
    raise AssertionError((src, dst))


def _t(fn):
    return lambda sq: chess.square(*fn(chess.square_file(sq), chess.square_rank(sq)))


_TRANSFORMS = [_t(lambda f, r: (f, r)), _t(lambda f, r: (7 - f, r)), _t(lambda f, r: (f, 7 - r)),
               _t(lambda f, r: (7 - f, 7 - r)), _t(lambda f, r: (r, f)), _t(lambda f, r: (7 - r, f)),
               _t(lambda f, r: (r, 7 - f)), _t(lambda f, r: (7 - r, 7 - f))]


# ── the three-piece endings solved: can the mate be forced outside a region? ──────────────────────────────────────
def _index(turn: int, wk: int, wp: int, bk: int) -> int:
    return ((turn * 64 + wk) * 64 + wp) * 64 + bk


def forced_outside(piece: int) -> dict:
    """{region: True/False/None} for K + *piece* against K (see the module docstring)."""
    n = 2 * 64 ** 3
    legal = bytearray(n)
    succ: list = [None] * n
    mate_sq = [-1] * n
    for turn in (0, 1):  # 0 white to move, 1 black to move
        for wk, wp, bk in itertools.product(range(64), repeat=3):
            if len({wk, wp, bk}) < 3 or chess.square_distance(wk, bk) < 2:
                continue
            b = chess.Board(None)
            b.set_piece_at(wk, chess.Piece(chess.KING, chess.WHITE))
            b.set_piece_at(wp, chess.Piece(piece, chess.WHITE))
            b.set_piece_at(bk, chess.Piece(chess.KING, chess.BLACK))
            b.turn = chess.WHITE if turn == 0 else chess.BLACK
            if not b.is_valid():
                continue
            i = _index(turn, wk, wp, bk)
            legal[i] = 1
            kids = []
            for mv in b.legal_moves:
                if turn == 1 and mv.to_square == wp:
                    kids.append(-1)  # the piece is taken: a draw
                    continue
                if turn == 0:
                    nwk, nwp = (mv.to_square, wp) if mv.from_square == wk else (wk, mv.to_square)
                    kids.append(_index(1, nwk, nwp, bk))
                else:
                    kids.append(_index(0, wk, wp, mv.to_square))
            if not kids and turn == 1 and b.is_check():
                mate_sq[i] = bk
            succ[i] = kids
    preds: dict = {}
    for i in range(n):
        if legal[i]:
            for k in succ[i]:
                if k >= 0:
                    preds.setdefault(k, []).append(i)

    def solve(region: set) -> bytearray:
        win = bytearray(n)
        left = [0] * n
        q = deque()
        for i in range(n):
            if not legal[i]:
                continue
            if i >= 64 ** 3:  # black to move
                left[i] = len(succ[i])
                if mate_sq[i] >= 0 and mate_sq[i] not in region:
                    win[i] = 1
                    q.append(i)
        while q:
            i = q.popleft()
            for p in preds.get(i, ()):
                if win[p]:
                    continue
                if p < 64 ** 3:  # white to move: one winning move is enough
                    win[p] = 1
                    q.append(p)
                else:
                    if -1 in succ[p]:
                        continue  # black can take the piece
                    left[p] -= 1
                    if left[p] == 0:
                        win[p] = 1
                        q.append(p)
        return win

    normal = solve(set())
    centre = {chess.D4, chess.E4, chess.D5, chess.E5}
    starts = [i for i in range(64 ** 3) if legal[i] and normal[i] and (i % 64) in centre]
    out = {}
    for name, region in REGIONS.items():
        won = solve(region)
        share = sum(won[i] for i in starts) / max(1, len(starts))
        out[name] = True if share >= 0.9 else (False if share <= 0.1 else None)
        out[name + "_share"] = round(share, 4)
    return out


def main() -> None:
    t0 = time.time()
    data = {
        "doc": ("Where a bare king can be mated, ending by ending — built by scripts/build_mate_squares.py "
                "(python-chess); read by src/endgame_claims.py (plan 31.10, P5 C7). 'possible': every square of the "
                "bare king with a legal mate; 'forced_outside': whether the stronger side can force the mate outside "
                "the region from a normal winning position (null: not computed)."),
        "regions": {k: sorted(chess.square_name(s) for s in v) for k, v in REGIONS.items()},
        "endings": {},
    }
    for name, pieces in ENDINGS.items():
        poss = possible_squares(pieces)
        entry = {"name": NAMES[name], "possible": sorted(poss, key=chess.parse_square), "example": poss}
        if len(pieces) == 1:
            entry["forced_outside"] = forced_outside(pieces[0])
        elif name == "KNNK":
            entry["forced_outside"] = {"corner": False, "edge": False, "never_forced": True}
        else:
            entry["forced_outside"] = {"corner": None, "edge": None}
        data["endings"][name] = entry
        print(f"{name}: {len(poss)} squares, forced_outside {entry['forced_outside']}  ({time.time() - t0:.0f} s)",
              flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"written {OUT} ({os.path.getsize(OUT)} bytes)")


if __name__ == "__main__":
    main()
