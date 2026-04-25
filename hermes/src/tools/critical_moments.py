"""Tool: find_critical_moments — Analyze a game for turning points."""

import json
import logging
import subprocess
import time

import chess
import chess.pgn
import io

from tools.registry import registry

logger = logging.getLogger(__name__)

STOCKFISH_PATH = "/usr/games/stockfish"
DEFAULT_THRESHOLD = 1.5
ANALYSIS_DEPTH = 15
TIMEOUT_PER_MOVE = 10

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
    """Get a quick evaluation from an already-running Stockfish process."""
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
        if line.startswith("info") and f" depth {depth} " in line:
            import re
            m = re.search(r"score cp (-?\d+)", line)
            if m:
                result["score"] = int(m.group(1)) / 100.0
            else:
                m = re.search(r"score mate (-?\d+)", line)
                if m:
                    mate_in = int(m.group(1))
                    result["score"] = 10000 * (1 if mate_in > 0 else -1)
                    result["mate_in"] = mate_in
    return result if result else None


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
    positions = [board.fen()]
    moves_san = []
    for move in game.mainline_moves():
        moves_san.append(board.san(move))
        board.push(move)
        positions.append(board.fen())

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
        # Evaluate all positions
        evals = []
        for fen in positions:
            ev = _quick_eval(proc, fen, ANALYSIS_DEPTH)
            evals.append(ev.get("score", 0.0) if ev else 0.0)

        # Find critical moments
        critical = []
        for i in range(len(moves_san)):
            eval_before = evals[i]
            eval_after = evals[i + 1]
            # Normalize to white's perspective
            change = eval_after - eval_before

            move_number = (i // 2) + 1
            side = "white" if i % 2 == 0 else "black"

            # For black moves, a positive change is bad for black
            # For white moves, a negative change is bad for white
            if side == "white":
                swing = -change  # negative change = white lost advantage
            else:
                swing = change  # positive change = black lost advantage

            if abs(swing) >= threshold or (evals[i + 1] is not None and abs(eval_after) >= 9000):
                moment_type = "blunder" if abs(swing) >= 3.0 else "mistake"
                if abs(eval_after) >= 9000 and abs(eval_before) < 9000:
                    moment_type = "missed_mate" if swing > 0 else "blunder"

                critical.append({
                    "move_number": move_number,
                    "side": side,
                    "move": moves_san[i],
                    "eval_before": round(eval_before, 2),
                    "eval_after": round(eval_after, 2),
                    "eval_change": round(change, 2),
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
