"""Tool: find_critical_moments — Analyze a game for turning points."""

import json
import os
import re
import shutil
import logging
import subprocess
import time

import chess
import chess.pgn
import io

from tools.registry import registry

logger = logging.getLogger(__name__)

# STOCKFISH_PATH env overrides the Debian default (macOS/brew installs it elsewhere).
STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish") or "/usr/games/stockfish"
DEFAULT_THRESHOLD = 1.5
# The scan looks for swings of 1.5+ pawns, which depth 12 sees; depth 15 took
# 17-26 s for a 25-move game (the bench's reviews spent ~30 s here), depth 12
# 2-5 s. The coach analyses the moments it explains at full depth.
ANALYSIS_DEPTH = int(os.environ.get("CRITICAL_MOMENTS_DEPTH", "12"))
TIMEOUT_PER_MOVE = 10
MATE_SCORE = 10000.0
# Beyond this many pawns a position is simply won: +12 → +9 is not a mistake.
EVAL_CAP = 10.0

CRITICAL_MOMENTS_SCHEMA = {
    "name": "find_critical_moments",
    "description": (
        "Analyze a game move-by-move to find turning points where the evaluation "
        "swung significantly (blunders, mistakes, missed mates)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pgn": {
                "type": "string",
                "description": "PGN string of the game to analyze.",
            },
            "threshold": {
                "type": "number",
                "description": "Eval swing threshold in pawns (default 1.5).",
            },
        },
        "required": ["pgn"],
    },
}


def _quick_eval(proc, fen: str, depth: int = ANALYSIS_DEPTH) -> dict | None:
    """Evaluate *fen* on an already-running Stockfish process.

    The score is from the side to move's point of view, as UCI reports it; the
    deepest scored line before ``bestmove`` wins (a found mate can end the
    search below the requested depth).
    """
    try:
        proc.stdin.write(f"position fen {fen}\n")
        proc.stdin.write(f"go depth {depth}\n")
        proc.stdin.flush()
    except BrokenPipeError:
        return None

    deadline = time.monotonic() + TIMEOUT_PER_MOVE
    result = {}
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if line.startswith("bestmove"):
            break
        if not line.startswith("info") or " score " not in line or "bound" in line:
            continue
        m = re.search(r"score cp (-?\d+)", line)
        if m:
            result = {"score": int(m.group(1)) / 100.0}
            continue
        m = re.search(r"score mate (-?\d+)", line)
        if m:
            mate_in = int(m.group(1))
            result = {"score": MATE_SCORE * (1 if mate_in > 0 else -1), "mate_in": mate_in}
    return result if result else None


def _white_eval(board: chess.Board, proc) -> float:
    """Evaluation of *board* from White's side: engine score, or the result for a finished game."""
    if board.is_checkmate():
        return -MATE_SCORE if board.turn == chess.WHITE else MATE_SCORE
    if board.is_stalemate() or board.is_insufficient_material():
        return 0.0
    ev = _quick_eval(proc, board.fen(), ANALYSIS_DEPTH)
    score = ev.get("score", 0.0) if ev else 0.0
    return score if board.turn == chess.WHITE else -score


def _for_mover(white_eval: float, mover: chess.Color) -> float:
    """White-side eval as the mover sees it, capped; a forced mate sits beyond the cap."""
    v = white_eval if mover == chess.WHITE else -white_eval
    if v >= MATE_SCORE:
        return EVAL_CAP + 5
    if v <= -MATE_SCORE:
        return -(EVAL_CAP + 5)
    return max(-EVAL_CAP, min(EVAL_CAP, v))


def find_critical_moments(
    pgn: str,
    threshold: float = DEFAULT_THRESHOLD,
    stockfish_path: str = STOCKFISH_PATH,
    _proc=None,
) -> dict:
    """Analyze a game move-by-move to find turning points."""
    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except Exception:
        return {"error": "Could not parse PGN."}

    if game is None:
        return {"error": "Could not parse PGN."}

    # Collect all positions
    board = game.board()
    positions = [board.copy(stack=False)]
    moves_san = []
    for move in game.mainline_moves():
        moves_san.append(board.san(move))
        board.push(move)
        positions.append(board.copy(stack=False))

    if len(positions) < 2:
        return {"error": "Game has no moves."}

    # Start Stockfish (or use provided proc for testing)
    own_proc = _proc is None
    proc = _proc
    if own_proc:
        try:
            proc = subprocess.Popen(
                [stockfish_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            proc.stdin.write("uci\n")
            proc.stdin.write("isready\n")
            proc.stdin.write(f"setoption name MultiPV value 1\n")
            proc.stdin.flush()
            # Wait for readyok
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                line = proc.stdout.readline().strip()
                if line == "readyok":
                    break
        except FileNotFoundError:
            return {"error": f"Stockfish not found at {stockfish_path}."}

    try:
        # Every eval from White's side: UCI scores are the side to move's, and
        # comparing them raw across a move flips the sign each ply — a won game
        # came back with nearly every move a "blunder".
        evals = [_white_eval(b, proc) for b in positions]

        # A move is critical when the mover's own evaluation drops by the threshold.
        critical = []
        for i in range(len(moves_san)):
            eval_before = evals[i]
            eval_after = evals[i + 1]
            mover = positions[i].turn
            before = _for_mover(eval_before, mover)
            after = _for_mover(eval_after, mover)
            loss = before - after
            if loss < threshold:
                continue

            if before > EVAL_CAP and after <= EVAL_CAP:
                moment_type = "missed_mate"
            elif after < -EVAL_CAP:
                moment_type = "blunder"  # walked into a forced mate
            else:
                moment_type = "blunder" if loss >= 3.0 else "mistake"

            critical.append({
                "move_number": positions[i].fullmove_number,
                "side": "white" if mover == chess.WHITE else "black",
                "move": moves_san[i],
                "eval_before": round(eval_before, 2),
                "eval_after": round(eval_after, 2),
                "eval_change": round(eval_after - eval_before, 2),
                "type": moment_type,
            })
    finally:
        if own_proc and proc:
            try:
                proc.stdin.write("quit\n")
                proc.stdin.flush()
                proc.wait(timeout=5)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                proc.kill()

    return {
        "total_moves": len(moves_san),
        "evals_from": "white",  # eval_* fields: + good for White; ±10000 = forced mate
        "critical_moments": critical,
    }


def _handle_find_critical_moments(args: dict, **kwargs) -> str:
    result = find_critical_moments(
        pgn=args.get("pgn", ""),
        threshold=args.get("threshold", DEFAULT_THRESHOLD),
    )
    return json.dumps(result, indent=2)


registry.register(
    name="find_critical_moments",
    toolset="chess",
    schema=CRITICAL_MOMENTS_SCHEMA,
    handler=_handle_find_critical_moments,
    description="Find critical turning points in a chess game.",
    emoji="⚡",
)
