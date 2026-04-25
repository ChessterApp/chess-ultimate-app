"""Tool 5: analyze_position — Stockfish engine analysis."""

import json
import logging
import re
import subprocess

import chess

from tools.registry import registry

logger = logging.getLogger(__name__)

STOCKFISH_PATH = "/usr/games/stockfish"
DEFAULT_DEPTH = 20
DEFAULT_MULTIPV = 3
TIMEOUT_SECONDS = 30

ANALYZE_SCHEMA = {
    "name": "analyze_position",
    "description": "Analyze a chess position using Stockfish. Provide a FEN string and get evaluation, best move, and top lines.",
    "parameters": {
        "type": "object",
        "properties": {
            "fen": {"type": "string", "description": "FEN string of the position to analyze."},
            "depth": {"type": "integer", "description": "Search depth (default 20)."},
            "multipv": {"type": "integer", "description": "Number of principal variations (default 3)."},
        },
        "required": ["fen"],
    },
}


def _validate_fen(fen: str) -> bool:
    """Validate a FEN string using python-chess."""
    try:
        board = chess.Board(fen)
        return board.is_valid()
    except (ValueError, IndexError):
        return False


def _parse_info_line(line: str) -> dict | None:
    """Parse a Stockfish info line into a structured dict."""
    if not line.startswith("info"):
        return None

    result = {}

    # Extract multipv
    m = re.search(r"multipv (\d+)", line)
    if m:
        result["multipv"] = int(m.group(1))

    # Extract depth
    m = re.search(r" depth (\d+)", line)
    if m:
        result["depth"] = int(m.group(1))

    # Extract score
    m = re.search(r"score cp (-?\d+)", line)
    if m:
        result["score"] = int(m.group(1)) / 100.0
    else:
        m = re.search(r"score mate (-?\d+)", line)
        if m:
            mate_in = int(m.group(1))
            result["score"] = 10000 * (1 if mate_in > 0 else -1)
            result["mate_in"] = mate_in

    # Extract PV (principal variation)
    m = re.search(r" pv (.+)", line)
    if m:
        result["pv"] = m.group(1).strip()

    return result if result else None


def analyze_position(
    fen: str,
    depth: int = DEFAULT_DEPTH,
    multipv: int = DEFAULT_MULTIPV,
    stockfish_path: str = STOCKFISH_PATH,
    timeout: int = TIMEOUT_SECONDS,
) -> dict:
    """Run Stockfish analysis on a FEN position."""
    if not _validate_fen(fen):
        return {"error": f"Invalid FEN: {fen}"}

    try:
        proc = subprocess.Popen(
            [stockfish_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return {"error": f"Stockfish not found at {stockfish_path}."}

    try:
        proc.stdin.write("uci\n")
        proc.stdin.write("isready\n")
        proc.stdin.write(f"setoption name MultiPV value {multipv}\n")
        proc.stdin.write(f"position fen {fen}\n")
        proc.stdin.write(f"go depth {depth}\n")
        proc.stdin.flush()

        lines = []
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            lines.append(line)
            if line.startswith("bestmove"):
                break
        else:
            proc.kill()
            return {"error": "Stockfish analysis timed out."}

        proc.stdin.write("quit\n")
        proc.stdin.flush()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"error": "Stockfish analysis timed out."}
    except BrokenPipeError:
        pass  # Stockfish already exited

    # Parse info lines — keep only the deepest for each multipv
    best_lines: dict[int, dict] = {}
    for line in lines:
        parsed = _parse_info_line(line)
        if parsed and "multipv" in parsed and "pv" in parsed:
            pv_num = parsed["multipv"]
            if pv_num not in best_lines or parsed.get("depth", 0) >= best_lines[pv_num].get("depth", 0):
                best_lines[pv_num] = parsed

    # Parse bestmove
    best_move = ""
    for line in lines:
        if line.startswith("bestmove"):
            parts = line.split()
            if len(parts) >= 2:
                best_move = parts[1]

    # Build result
    evaluation = best_lines.get(1, {}).get("score", 0.0)
    result_lines = []
    for pv_num in sorted(best_lines.keys()):
        entry = best_lines[pv_num]
        result_lines.append({
            "pv": entry.get("pv", ""),
            "score": entry.get("score", 0.0),
            "depth": entry.get("depth", 0),
        })

    return {
        "evaluation": evaluation,
        "best_move": best_move,
        "lines": result_lines,
    }


def _handle_analyze_position(args: dict, **kwargs) -> str:
    result = analyze_position(
        fen=args.get("fen", ""),
        depth=args.get("depth", DEFAULT_DEPTH),
        multipv=args.get("multipv", DEFAULT_MULTIPV),
    )
    return json.dumps(result, indent=2)


registry.register(
    name="analyze_position",
    toolset="chess",
    schema=ANALYZE_SCHEMA,
    handler=_handle_analyze_position,
    description="Analyze a chess position with Stockfish engine.",
    emoji="🔬",
)
