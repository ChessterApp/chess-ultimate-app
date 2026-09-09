"""
Game Review — Phase 1 engine pipeline.

Server-side analysis: PGN in → per-ply Stockfish evals (MultiPV=2) → win% →
per-move accuracy → game accuracy → JSON out. Async job queue (one analysis at
a time, this box has 2 vCPUs) plus an on-disk JSON cache so results survive
restarts.

No classification cascade (that is Phase 2) and no UI.

Math references (Lichess, public):
  winPercent   = 100 / (1 + exp(-0.00368208 * cp))          # White POV
  moveAccuracy = 103.1668 * exp(-0.04354 * (winBefore - winAfter)) - 3.1669
Game accuracy per player = mean of (volatility-weighted mean, harmonic mean) of
that player's move accuracies.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import os
import queue
import threading

import chess
import chess.engine
import chess.pgn

from services import move_classify

logger = logging.getLogger(__name__)

STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH", "/usr/games/stockfish")
DEPTH = 14  # constant, easy to tune
MULTIPV = 2  # 2nd-best line is needed by Phase 2 classification

# Result schema version. Phase 1 caches lack classification/aggregates and are
# treated as cache misses (re-analyzed) so every stored result matches the
# frozen Phase 2 contract.
VERSION = 2

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_BACKEND_DIR, "data", "game_reviews")

# Win% logistic constant (Lichess).
_WIN_K = 0.00368208


# ---------------------------------------------------------------------------
# Pure math helpers (unit-tested)
# ---------------------------------------------------------------------------
def win_percent_white(eval_dict: dict) -> float:
    """Win probability (0..100) from White's POV for a White-POV eval dict."""
    if eval_dict["type"] == "mate":
        return 100.0 if eval_dict["value"] > 0 else 0.0
    cp = eval_dict["value"]
    return 100.0 / (1.0 + math.exp(-_WIN_K * cp))


def move_accuracy(win_before: float, win_after: float) -> float:
    """Per-move accuracy (0..100). Both inputs are in the MOVER's win% space."""
    raw = 103.1668 * math.exp(-0.04354 * (win_before - win_after)) - 3.1669
    return max(0.0, min(100.0, raw))


def accuracy_for_move(
    win_before_white: float, win_after_white: float, mover_is_white: bool
) -> float:
    """
    Accuracy of a move given the resulting position's win% BEFORE and AFTER the
    move, both expressed from White's POV. Flips to the mover's POV first — this
    is the sign that makes Black-move accuracy correct.
    """
    if mover_is_white:
        wb, wa = win_before_white, win_after_white
    else:
        wb, wa = 100.0 - win_before_white, 100.0 - win_after_white
    return move_accuracy(wb, wa)


def _stdev(xs: list[float]) -> float:
    if not xs:
        return 0.0
    mean = sum(xs) / len(xs)
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))


def _harmonic_mean(xs: list[float]) -> float:
    safe = [max(x, 1e-9) for x in xs]
    return len(safe) / sum(1.0 / x for x in safe)


def game_accuracy(
    all_win_white: list[float], color_accuracies: dict[str, list[tuple[int, float]]]
) -> dict[str, float]:
    """
    Per-player game accuracy = mean of a volatility-weighted mean and a harmonic
    mean of that player's move accuracies (Lichess method). ``all_win_white`` is
    the White-POV win% for every position P0..PN (length plies+1). Each entry in
    ``color_accuracies[color]`` is ``(position_index, accuracy)`` where the move
    landed on position P_index.
    """
    n_pos = len(all_win_white)
    window_size = max(2, min(8, n_pos // 10))

    # Volatility weight per landing position index (1..N): stdev of the win%
    # values in the window ending at that position.
    weight_by_index: dict[int, float] = {}
    for i in range(1, n_pos):
        start = max(0, i - window_size + 1)
        weight_by_index[i] = max(_stdev(all_win_white[start : i + 1]), 0.5)

    result: dict[str, float] = {}
    for color, accs in color_accuracies.items():
        if not accs:
            result[color] = 0.0
            continue
        vals = [a for (_, a) in accs]
        weights = [weight_by_index[idx] for (idx, _) in accs]
        weighted = sum(v * w for v, w in zip(vals, weights)) / sum(weights)
        harmonic = _harmonic_mean(vals)
        result[color] = round((weighted + harmonic) / 2.0, 1)
    return result


# ---------------------------------------------------------------------------
# Engine analysis
# ---------------------------------------------------------------------------
def _score_to_eval(score: chess.engine.Score) -> dict:
    """chess.engine Score (already White-POV) → {"type","value"} dict."""
    if score.is_mate():
        return {"type": "mate", "value": score.mate()}
    return {"type": "cp", "value": score.score()}


def _terminal_eval_white(board: chess.Board) -> dict:
    """Eval for a game-over position from White's POV (no engine call)."""
    if board.is_checkmate():
        # Side to move is checkmated → the other side wins.
        white_wins = board.turn == chess.BLACK
        return {"type": "mate", "value": 1 if white_wins else -1}
    return {"type": "cp", "value": 0}  # stalemate / draw


def _parse_game(pgn: str) -> chess.pgn.Game:
    game = chess.pgn.read_game(io.StringIO(pgn or ""))
    if game is None:
        raise ValueError("Could not parse PGN")
    if not list(game.mainline_moves()):
        raise ValueError("PGN contains no moves")
    return game


def analyze_game(pgn: str, depth: int = DEPTH, progress_cb=None) -> dict:
    """
    Run the full pipeline on a PGN and return the result JSON.

    ``progress_cb(evaluated, total)`` is called after each position is
    evaluated (``total`` = number of plies).
    """
    game = _parse_game(pgn)
    moves = list(game.mainline_moves())
    n = len(moves)

    # Build the per-ply SAN/UCI list and the FENs of every position P0..PN.
    board = game.board()
    fens = [board.fen()]
    sans: list[str] = []
    ucis: list[str] = []
    for mv in moves:
        sans.append(board.san(mv))
        ucis.append(mv.uci())
        board.push(mv)
        fens.append(board.fen())

    # Evaluate every position P0..PN once with MultiPV=2. The best-line eval of a
    # position IS that position's eval; playing the best move yields it.
    pos_eval_white: list[dict] = [None] * (n + 1)
    pos_best: list[dict | None] = [None] * (n + 1)
    pos_second: list[dict | None] = [None] * (n + 1)

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    try:
        for j, fen in enumerate(fens):
            bd = chess.Board(fen)
            if bd.is_game_over():
                pos_eval_white[j] = _terminal_eval_white(bd)
            else:
                infos = engine.analyse(
                    bd, chess.engine.Limit(depth=depth), multipv=MULTIPV
                )
                best_info = infos[0]
                best_white = best_info["score"].white()
                pos_eval_white[j] = _score_to_eval(best_white)
                pos_best[j] = {
                    "uci": best_info["pv"][0].uci(),
                    "eval": _score_to_eval(best_white),
                }
                if len(infos) > 1 and infos[1].get("pv"):
                    second_white = infos[1]["score"].white()
                    pos_second[j] = {
                        "uci": infos[1]["pv"][0].uci(),
                        "eval": _score_to_eval(second_white),
                    }
            if progress_cb:
                progress_cb(min(j, n), n)
    finally:
        engine.quit()

    all_win_white = [win_percent_white(e) for e in pos_eval_white]

    def _mover_win(win_white: float, mover_is_white: bool) -> float:
        return win_white if mover_is_white else 100.0 - win_white

    # Opening / book detection from the position EPDs.
    epds = [chess.Board(f).epd() for f in fens]
    opening = move_classify.detect_opening(epds)
    last_book_ply = opening["lastBookPly"]

    # Build per-ply context and run the stateful classification cascade.
    ply_contexts: list[dict] = []
    for i in range(1, n + 1):
        mover_is_white = i % 2 == 1  # ply 1 is White
        board_before = chess.Board(fens[i - 1])
        best = pos_best[i - 1]
        second = pos_second[i - 1]
        second_win = None
        if second is not None:
            second_win = _mover_win(
                win_percent_white(second["eval"]), mover_is_white
            )
        ply_contexts.append(
            {
                "is_book": i <= last_book_ply,
                "board_before": board_before,
                "move": chess.Move.from_uci(ucis[i - 1]),
                "played_uci": ucis[i - 1],
                "best_uci": best["uci"] if best else None,
                "win_before_mover": _mover_win(all_win_white[i - 1], mover_is_white),
                "win_after_mover": _mover_win(all_win_white[i], mover_is_white),
                "second_win_mover": second_win,
                "n_legal": board_before.legal_moves.count(),
            }
        )
    classifications = move_classify.classify_game(ply_contexts)

    # Assemble moves + aggregates. Book plies carry accuracy=null and are
    # excluded from every accuracy mean; forced plies keep their accuracy value
    # but are also excluded from the means (Chess.com behaviour).
    result_moves: list[dict] = []
    color_accuracies: dict[str, list[tuple[int, float]]] = {"w": [], "b": []}
    tally = move_classify.empty_tally()
    phase_accs: dict[str, dict[str, list[float]]] = {
        p: {"w": [], "b": []} for p in ("opening", "middlegame", "endgame")
    }
    key_moments: list[int] = []
    move_counts = {"w": 0, "b": 0}

    for i in range(1, n + 1):
        mover_is_white = i % 2 == 1
        color = "w" if mover_is_white else "b"
        move_counts[color] += 1
        cls = classifications[i - 1]
        phase = move_classify.phase_for_ply(i, last_book_ply, chess.Board(fens[i]))
        acc = accuracy_for_move(all_win_white[i - 1], all_win_white[i], mover_is_white)

        tally[color][cls] += 1
        if cls in move_classify.KEY_MOMENT_CLASSES:
            key_moments.append(i)

        scored = cls not in ("book", "forced")
        if scored:
            color_accuracies[color].append((i, acc))
            phase_accs[phase][color].append(acc)

        result_moves.append(
            {
                "ply": i,
                "san": sans[i - 1],
                "uci": ucis[i - 1],
                "fen": fens[i],
                "eval": pos_eval_white[i],
                "best": pos_best[i - 1],  # best move in the position before the ply
                "second": pos_second[i - 1],
                "winPercent": round(all_win_white[i], 1),
                "accuracy": None if cls == "book" else round(acc, 1),
                "classification": cls,
                "phase": phase,
            }
        )

    accuracy = game_accuracy(all_win_white, color_accuracies)
    phases = {
        p: {
            c: (round(sum(v) / len(v), 1) if v else None)
            for c, v in colors.items()
        }
        for p, colors in phase_accs.items()
    }
    est_rating = {
        c: move_classify.est_rating(accuracy[c], move_counts[c]) for c in ("w", "b")
    }

    return {
        "moves": result_moves,
        "accuracy": accuracy,
        "tally": tally,
        "estRating": est_rating,
        "phases": phases,
        "keyMoments": key_moments,
        "opening": opening,
        "engine": f"sf-d{depth}",
        "plies": n,
        "version": VERSION,
    }


# ---------------------------------------------------------------------------
# Hashing / cache / job queue
# ---------------------------------------------------------------------------
def pgn_hash(pgn: str) -> str:
    """sha256 of the normalized move sequence — independent of headers/whitespace."""
    game = _parse_game(pgn)
    ucis = [mv.uci() for mv in game.mainline_moves()]
    return hashlib.sha256(" ".join(ucis).encode()).hexdigest()


def _cache_path(review_id: str) -> str:
    return os.path.join(CACHE_DIR, f"{review_id}.json")


def _read_cache(review_id: str) -> dict | None:
    path = _cache_path(review_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            cached = json.load(fh)
    except (OSError, ValueError):
        return None
    # Phase 1 results (no version / older version) lack the Phase 2 fields —
    # treat them as misses so the game is re-analyzed against the new contract.
    if cached.get("version") != VERSION:
        return None
    return cached


def _write_cache(review_id: str, result: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = _cache_path(review_id) + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(result, fh)
    os.replace(tmp, _cache_path(review_id))


# --- Cross-worker status sidecar -------------------------------------------
# gunicorn runs several worker processes and ``_JOBS`` is a per-process dict, so
# a poll can land on a worker that never received the job → a spurious 404 while
# analysis is still running. This sidecar records {status, progress} on disk so
# EVERY worker reports a consistent in-flight status. It is deleted once the full
# result cache lands (that file then becomes the single source of truth), which
# means a 404 reliably means "genuinely unknown id".
def _status_path(review_id: str) -> str:
    return os.path.join(CACHE_DIR, f"{review_id}.status.json")


def _write_status(
    review_id: str, status: str, progress: float, error: str | None = None
) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    payload: dict = {"status": status, "progress": progress}
    if error is not None:
        payload["error"] = error
    tmp = _status_path(review_id) + ".tmp"
    try:
        with open(tmp, "w") as fh:
            json.dump(payload, fh)
        os.replace(tmp, _status_path(review_id))
    except OSError:
        logger.warning("Could not write review status sidecar for %s", review_id)


def _read_status(review_id: str) -> dict | None:
    path = _status_path(review_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _delete_status(review_id: str) -> None:
    try:
        os.remove(_status_path(review_id))
    except OSError:
        pass


# In-memory job state: review_id -> {status, progress, result, error, user_id}.
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_QUEUE: "queue.Queue[tuple[str, str, int, str | None]]" = queue.Queue()


def _set_job(review_id: str, **fields) -> None:
    with _JOBS_LOCK:
        job = _JOBS.setdefault(
            review_id, {"status": "queued", "progress": 0.0, "result": None, "error": None}
        )
        job.update(fields)


def _persist_insight(review_id: str, user_id: str | None, result: dict) -> None:
    """Fire-and-forget: distill the finished review into a coach insight row.
    Fully fail-open and off the response path — a failure here never touches the
    review result. Anonymous jobs (no user_id) are skipped by the callee."""
    try:
        from services.review_insights import persist_review_insight

        persist_review_insight(user_id, review_id, result)
    except Exception:
        logger.debug("persist_review_insight hook failed for %s", review_id, exc_info=True)


def _worker_loop() -> None:
    while True:
        review_id, pgn, depth, user_id = _QUEUE.get()
        try:
            _set_job(review_id, status="running", progress=0.0)
            _write_status(review_id, "running", 0.0)

            last_step = -1

            def _progress(evaluated: int, total: int, _id=review_id) -> None:
                nonlocal last_step
                frac = (evaluated / total) if total else 0.0
                _set_job(_id, progress=frac)
                # Throttle disk writes to ~5% steps so sibling workers can show
                # progress without a filesystem write on every ply.
                step = int(frac * 20)
                if step != last_step:
                    last_step = step
                    _write_status(_id, "running", frac)

            result = analyze_game(pgn, depth=depth, progress_cb=_progress)
            _write_cache(review_id, result)
            _set_job(review_id, status="done", progress=1.0, result=result)
            _delete_status(review_id)  # full cache is now the source of truth
            _persist_insight(review_id, user_id, result)  # fail-open, off-path
        except Exception as exc:  # noqa: BLE001 — surface any analysis failure
            logger.exception("Game review %s failed", review_id)
            _set_job(review_id, status="error", error=str(exc))
            _write_status(review_id, "error", 0.0, error=str(exc))
        finally:
            _QUEUE.task_done()


_WORKER = threading.Thread(target=_worker_loop, name="game-review-worker", daemon=True)
_WORKER.start()


def submit_review(pgn: str, depth: int = DEPTH, user_id: str | None = None) -> tuple[str, str]:
    """
    Validate + dedupe a PGN and enqueue analysis.

    ``user_id`` (optional) is carried on the job so the completed review can be
    persisted as a coach insight for that student; anonymous submits skip it.

    Returns ``(review_id, status)`` where status is ``"done"`` on a cache hit or
    ``"queued"`` otherwise. Raises ``ValueError`` for an invalid PGN.
    """
    review_id = pgn_hash(pgn)  # raises ValueError on bad PGN

    # Cache hit (survives restarts).
    cached = _read_cache(review_id)
    if cached is not None:
        _set_job(review_id, status="done", progress=1.0, result=cached)
        _persist_insight(review_id, user_id, cached)  # fail-open, off-path
        return review_id, "done"

    with _JOBS_LOCK:
        existing = _JOBS.get(review_id)
        if existing and existing["status"] in ("queued", "running", "done"):
            return review_id, existing["status"]
        # Another gunicorn worker may already be analyzing this exact game — the
        # sidecar is the only cross-process signal we have. Honour it so a
        # duplicate POST doesn't kick off a second identical analysis.
        sidecar = _read_status(review_id)
        if sidecar and sidecar.get("status") in ("queued", "running"):
            return review_id, sidecar["status"]
        _JOBS[review_id] = {
            "status": "queued",
            "progress": 0.0,
            "result": None,
            "error": None,
        }

    _write_status(review_id, "queued", 0.0)
    _QUEUE.put((review_id, pgn, depth, user_id))
    return review_id, "queued"


def get_review(review_id: str) -> dict | None:
    """Return ``{status, progress, result?}`` for a review, or None if unknown."""
    with _JOBS_LOCK:
        job = _JOBS.get(review_id)
        if job is not None:
            job = dict(job)

    if job is None:
        cached = _read_cache(review_id)
        if cached is not None:
            _set_job(review_id, status="done", progress=1.0, result=cached)
            job = {"status": "done", "progress": 1.0, "result": cached, "error": None}
        else:
            # No in-memory job and no cached result on this worker: the job may be
            # in-flight on a sibling worker. Fall back to the shared status
            # sidecar so we report queued/running instead of a spurious 404.
            sidecar = _read_status(review_id)
            if sidecar is None:
                return None
            out: dict = {
                "status": sidecar.get("status", "running"),
                "progress": round(sidecar.get("progress", 0.0), 4),
            }
            if sidecar.get("status") == "error" and sidecar.get("error"):
                out["error"] = sidecar["error"]
            return out

    out: dict = {"status": job["status"], "progress": round(job["progress"], 4)}
    if job["status"] == "done" and job.get("result") is not None:
        out["result"] = job["result"]
    if job["status"] == "error" and job.get("error"):
        out["error"] = job["error"]
    return out
