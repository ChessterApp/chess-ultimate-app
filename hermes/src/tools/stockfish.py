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
# Depth alone does not bound the time: a sharp middlegame at depth 16 with three
# lines took 24 s in a game review on the bench of 2026-09-28. The search stops
# at the depth or after this many milliseconds, whichever comes first (0 = no cap).
MAX_MS = int(os.environ.get("STOCKFISH_MAX_MS", "3000"))
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
    movetime_ms: int | None = None,
) -> dict:
    """Run Stockfish analysis on a FEN position — to *depth*, or for *movetime_ms* when given."""
    if not _validate_fen(fen):
        return {"error": f"Invalid FEN: {fen}"}

    # The site's own engine server (engine.chesster.io) when ENGINE_API_URL is set:
    # no Stockfish process on the coach host, its cache and pool instead. Any
    # failure falls back to the local engine, so the turn never waits in vain.
    if ENGINE_API_URL:
        try:
            remote = _analyze_remote(fen, depth, multipv, movetime_ms)
            if remote and remote.get("lines"):
                return remote
        except Exception as exc:  # noqa: BLE001
            logger.warning("engine server %s failed (%s); using the local engine", ENGINE_API_URL, exc)
    with _running_lock:
        global _running
        _running += 1
    try:
        return _analyze_position(fen, depth, multipv, stockfish_path, timeout, movetime_ms)
    finally:
        with _running_lock:
            _running -= 1


ENGINE_API_URL = os.environ.get("ENGINE_API_URL", "").strip().rstrip("/")
ENGINE_API_TOKEN = os.environ.get("ENGINE_API_TOKEN", "").strip()
ENGINE_API_MAX_MULTIPV = 4
ENGINE_API_MAX_MOVETIME_S = 2.0


def _analyze_remote(fen: str, depth: int, multipv: int, movetime_ms: int | None) -> dict | None:
    """POST /analyze on the engine server, in the shape analyze_position returns.

    The server answers from White's side with SAN lines; here the score is for
    the side to move and the pv is UCI, as the local parser gives them.
    """
    import httpx
    import chess

    body: dict = {"fen": fen, "multipv": max(1, min(int(multipv or 1), ENGINE_API_MAX_MULTIPV))}
    if movetime_ms:
        body["movetime"] = min(movetime_ms / 1000.0, ENGINE_API_MAX_MOVETIME_S)
    else:
        body["depth"] = max(1, min(int(depth or DEFAULT_DEPTH), 30))
    wait = (body.get("movetime") or 4.0) + 3.0
    headers = {"X-Engine-Token": ENGINE_API_TOKEN} if ENGINE_API_TOKEN else {}
    resp = httpx.post(f"{ENGINE_API_URL}/analyze", json=body, headers=headers, timeout=wait)
    resp.raise_for_status()
    data = resp.json() or {}
    board = chess.Board(fen)
    sign = 1 if board.turn == chess.WHITE else -1
    raw_lines = data.get("lines") or [data]
    lines = []
    for i, ln in enumerate(raw_lines[: body["multipv"]]):
        ev = ln.get("evaluation") or data.get("evaluation") or {}
        b = board.copy(stack=False)
        uci = []
        for san in ln.get("pv") or []:
            try:
                mv = b.parse_san(san)
            except ValueError:
                break
            uci.append(mv.uci())
            b.push(mv)
        if not uci and ln.get("bestMove"):
            uci = [ln["bestMove"]]
        entry = {"multipv": i + 1, "depth": ln.get("depth") or data.get("depth"), "pv": " ".join(uci)}
        value = ev.get("value", 0) or 0
        if ev.get("type") == "mate":
            mate = int(value) * sign
            entry["mate_in"] = mate
            entry["score"] = 10000 * (1 if mate > 0 else -1)
        else:
            entry["score"] = float(value) / 100.0 * sign
        lines.append(entry)
    return {"lines": lines, "depth": data.get("depth"), "remote": True} if lines else None


_running = 0
_running_lock = __import__("threading").Lock()


def engines_running() -> int:
    """Stockfish processes at work right now — the turn shortens its searches
    when several students ask at once (local stand, 8 turns at once, 2026-10-05:
    every engine line missed its 2.5 s wait and the answers went out without facts)."""
    with _running_lock:
        return _running


def _analyze_position(fen, depth, multipv, stockfish_path, timeout, movetime_ms) -> dict:
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
        if movetime_ms:
            proc.stdin.write(f"go movetime {movetime_ms}\n")
        elif MAX_MS > 0:
            proc.stdin.write(f"go depth {depth} movetime {MAX_MS}\n")
        else:
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

    result = {
        "evaluation": evaluation,
        "best_move": best_move,
        "lines": result_lines,
    }
    # Stopped by the time cap short of the requested depth (a found mate also
    # ends early, but then the line is already decided).
    reached = result_lines[0]["depth"] if result_lines else 0
    if not movetime_ms and MAX_MS > 0 and reached < depth and "mate_in" not in (result_lines[0] if result_lines else {}):
        result["time_capped"] = True
    return result


# Results shared by the analyze_position tool and the voice [Engine] line
# (src/voice_engine_note.py): the board is usually analysed the moment it
# changes, so the model's own call for the same position is answered from here.
_CACHE_MAX = 256
# Position (clocks ignored) → the deepest analysis of it so far.
_cache: "OrderedDict[str, dict]" = OrderedDict()
_cache_lock = threading.Lock()


def clear_analysis_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _result_depth(result: dict) -> int:
    lines = result.get("lines") or []
    return int(lines[0].get("depth") or 0) if lines else 0


def _cache_get(fen: str, depth: int, multipv: int) -> dict | None:
    """A cached analysis at least *depth* deep with at least *multipv* lines."""
    key = " ".join(fen.split()[:4])
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None or len(hit.get("lines", [])) < multipv:
            return None
        # A run the time cap stopped is as deep as this host gets in the budget;
        # searching again would spend the same seconds for the same answer.
        if _result_depth(hit) < depth and not hit.get("time_capped"):
            return None
        _cache.move_to_end(key)
        return {**hit, "lines": hit["lines"][:multipv]}


def _cache_put(fen: str, result: dict) -> None:
    """Keep *result* unless the cache already holds a deeper (or as deep and wider) run."""
    if "error" in result or not result.get("lines"):
        return
    key = " ".join(fen.split()[:4])
    with _cache_lock:
        old = _cache.get(key)
        if old is None or (_result_depth(result), len(result["lines"])) >= (_result_depth(old), len(old["lines"])):
            _cache[key] = result
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)


def analyze_cached(fen: str, depth: int = DEFAULT_DEPTH, multipv: int = DEFAULT_MULTIPV) -> dict:
    """analyze_position behind a small LRU keyed by position (clocks ignored).

    A cached run at least as deep, with at least as many lines, serves the
    request. Errors are never cached.
    """
    hit = _cache_get(fen, depth, multipv)
    if hit is not None:
        return hit
    result = analyze_position(fen, depth=depth, multipv=multipv)
    _cache_put(fen, result)
    return result


def analyze_timed(fen: str, movetime_ms: int, multipv: int = DEFAULT_MULTIPV, min_depth: int = 12) -> dict:
    """Analysis bounded by time rather than depth, through the same cache.

    Depth then follows the host's speed and the result is ready on time — the
    text turn waits for it. A cached run at least *min_depth* deep serves it.
    """
    hit = _cache_get(fen, min_depth, multipv)
    if hit is not None:
        return hit
    result = analyze_position(fen, multipv=multipv, movetime_ms=movetime_ms)
    _cache_put(fen, result)
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
