#!/usr/bin/env python3
"""Check the knowledge-base positions against Stockfish.

For every position with a ``best_move`` the engine's top move at a modest depth
must agree (or the claimed move must be within a small margin of the best);
for every position the side to move must not already be checkmated/stalemated.
Prints a table and exits 1 on any disagreement, so an author sees at once when
a diagram or a claim is wrong.

    STOCKFISH_PATH=/opt/homebrew/bin/stockfish python scripts/check_kb_topics.py [--depth 18]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import chess
import chess.engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import knowledge_base as kb  # noqa: E402

MARGIN_CP = 60  # a claimed move within this many centipawns of the best is accepted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth", type=int, default=18)
    args = ap.parse_args()

    path = os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish")
    if not path:
        print("Stockfish not found: set STOCKFISH_PATH", file=sys.stderr)
        return 2
    topics = kb.load_topics(force=True)
    print(f"{len(topics)} topics, {sum(len(t['positions']) for t in topics.values())} positions")
    failures = 0
    with chess.engine.SimpleEngine.popen_uci(path) as engine:
        for t in topics.values():
            for p in t["positions"]:
                board = chess.Board(p["fen"])
                if board.is_game_over():
                    # A mating diagram whose FEN is already mate would be a bug; a
                    # position given "after the mate" is allowed only without best_move.
                    status = "game over"
                    ok = p["best_move"] is None
                else:
                    info = engine.analyse(board, chess.engine.Limit(depth=args.depth), multipv=3)
                    lines = [(i["pv"][0], i["score"].pov(board.turn)) for i in info if i.get("pv")]
                    best_move, best_score = lines[0]
                    status = f"engine {board.san(best_move)} {best_score}"
                    ok = True
                    if p["best_move"]:
                        claimed = board.parse_san(p["best_move"])
                        if claimed != best_move:
                            claimed_score = next((s for m, s in lines if m == claimed), None)
                            if claimed_score is None:
                                info_c = engine.analyse(board, chess.engine.Limit(depth=args.depth),
                                                        root_moves=[claimed])
                                claimed_score = info_c["score"].pov(board.turn)
                            best_cp = best_score.score(mate_score=100000)
                            claimed_cp = claimed_score.score(mate_score=100000)
                            ok = (best_cp - claimed_cp) <= MARGIN_CP
                            status += f" | claimed {p['best_move']} {claimed_score}"
                mark = "ok " if ok else "BAD"
                if not ok:
                    failures += 1
                print(f"{mark} {t['slug']:34s} {p['title_ru'][:40]:40s} {status}")
    print(f"\n{failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
