#!/usr/bin/env python3
"""Build tests/fixtures/detect1031/game_positions.json: every position of the game corpus's games, ply by ply.

scripts/eval_prevent.py (a) audits the facts given on the corpus positions. Its game file held only the boards the
student asked on (79, all of them already among the 318 corpus positions), so the audit ran on 318 positions, not on
the games (review-wiring 01.11). Here every ply of every game the corpus's sessions played is a position (the stand
recordings: their ``steps`` with ``notation_after``), deduplicated by EPD; the boards already in the file are kept
first, under their old names.

Usage (from hermes/):
  python scripts/build_game_positions.py <session.json> [<session.json> ...]
  (validate.sh's game corpus: live1028/t1.json, t2.json, stand*/st*.json, prod1029/st*.json)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import chess

H = Path(__file__).resolve().parents[1]
OUT = H / "tests" / "fixtures" / "detect1031" / "game_positions.json"
_TOKEN = re.compile(r"^[KQRBNO]?[a-hx1-8=QRBN+#O-]+$")


def _moves(notation: str) -> list:
    return [t for t in re.sub(r"\d+\.", " ", notation or "").split() if _TOKEN.match(t)]


def main(paths: list) -> int:
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"positions": []}
    positions = [p for p in old.get("positions") or []]
    seen = {chess.Board(p["fen"]).epd() for p in positions}
    added = 0
    for path in paths:
        try:
            session = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tag = "/".join(Path(path).parts[-2:])
        for step in session.get("steps") or []:
            board = chess.Board()
            played = []
            for san in _moves(step.get("notation_after") or ""):
                try:
                    board.push_san(san)
                except ValueError:
                    break
                played.append(san)
                epd = board.epd()
                if epd in seen or board.is_game_over():
                    continue
                seen.add(epd)
                positions.append({"name": f"{tag}:ply{len(played)}", "fen": board.fen(), "game_moves": list(played)})
                added += 1
    doc = ("The boards of the game corpus of plan 31.10 (validate.sh's corpus_game.py files: t1, t2, stand*/st*, "
           "prod1029/st*): the boards the student asked on, then every ply of every game played in them "
           "(scripts/build_game_positions.py) — scripts/eval_prevent.py audits the facts given on them.")
    OUT.write_text(json.dumps({"doc": doc, "positions": positions}, ensure_ascii=False, indent=0) + "\n",
                   encoding="utf-8")
    print(f"{len(positions)} positions ({added} added) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
