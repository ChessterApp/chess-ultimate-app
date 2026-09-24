"""Tool 5: analyze_position — Stockfish engine analysis."""

import json
import os
import shutil
import logging
import re
import subprocess
import threading
from collections import OrderedDict

import chess

from tools.registry import registry

logger = logging.getLogger(__name__)

# STOCKFISH_PATH env overrides the Debian default (macOS/brew installs it elsewhere).
STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish") or "/usr/games/stockfish"
# Depth 20 costs ~6 s per position on the coach host and the model calls the engine
# 2-5 times per turn (bench 2026-09-23); depth 16 is ~2 s with the same top move in
# coaching positions. STOCKFISH_DEPTH overrides without a deploy.
DEFAULT_DEPTH = int(os.environ.get("STOCKFISH_DEPTH", "16"))
# The models pass `depth` explicitly (the old schema text said "default 20", and
# the voice bench of 2026-09-24 caught Gemini Live asking for 20 → 5 s of
# silence), so the default alone does not bound the cost — the ceiling does.
MAX_DEPTH = max(DEFAULT_DEPTH, int(os.environ.get("STOCKFISH_MAX_DEPTH", str(DEFAULT_DEPTH))))
DEFAULT_MULTIPV = 3
MAX_MULTIPV = 5
TIMEOUT_SECONDS = 30

ANALYZE_SCHEMA = {
    "name": "analyze_position",
    "description": "Analyze a chess position using Stockfish. Provide a FEN string and get evaluation, best move, and top lines.",
    "parameters": {
        "type": "object",
        "properties": {
            "fen": {"type": "string", "description": "FEN string of the position to analyze."},
            "depth": {"type": "integer", "description": f"Search depth; leave unset (default {DEFAULT_DEPTH}, max {MAX_DEPTH})."},
            "multipv": {"type": "integer", "description": f"Number of principal variations (default {DEFAULT_MULTIPV}, max {MAX_MULTIPV})."},
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
        line = {
            "pv": entry.get("pv", ""),
            "score": entry.get("score", 0.0),
            "depth": entry.get("depth", 0),
        }
        if "mate_in" in entry:
            line["mate_in"] = entry["mate_in"]
        result_lines.append(line)

    return {
        "evaluation": evaluation,
        "best_move": best_move,
        "lines": result_lines,
    }


# Results shared by the analyze_position tool and the voice [Engine] line
# (src/voice_engine_note.py): the board is usually analysed the moment it
# changes, so the model's own call for the same position is answered from here.
_CACHE_MAX = 256
_cache: "OrderedDict[tuple[str, int], dict]" = OrderedDict()
_cache_lock = threading.Lock()


def clear_analysis_cache() -> None:
    with _cache_lock:
        _cache.clear()


def analyze_cached(fen: str, depth: int = DEFAULT_DEPTH, multipv: int = DEFAULT_MULTIPV) -> dict:
    """analyze_position behind a small LRU keyed by position (clocks ignored) and depth.

    A cached run with at least as many lines serves a narrower request.
    Errors are never cached.
    """
    key = (" ".join(fen.split()[:4]), depth)
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and len(hit.get("lines", [])) >= multipv:
            _cache.move_to_end(key)
            return {**hit, "lines": hit["lines"][:multipv]}
    result = analyze_position(fen, depth=depth, multipv=multipv)
    if "error" not in result:
        with _cache_lock:
            _cache[key] = result
            _cache.move_to_end(key)
            while len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)
    return result


def _bounded_int(value, default: int, low: int, high: int) -> int:
    """Model-supplied int arg clamped to [low, high]; junk falls back to default."""
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _handle_analyze_position(args: dict, **kwargs) -> str:
    result = analyze_cached(
        fen=args.get("fen", ""),
        depth=_bounded_int(args.get("depth"), DEFAULT_DEPTH, 1, MAX_DEPTH),
        multipv=_bounded_int(args.get("multipv"), DEFAULT_MULTIPV, 1, MAX_MULTIPV),
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
