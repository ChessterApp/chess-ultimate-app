"""Stockfish as the coach's playing hand: limited-strength moves and quick evals.

One engine process per server, serialised with a lock (a game move needs the
engine for a few hundred milliseconds). The process is restarted transparently
if it dies. With the analysis engine pool on (STOCKFISH_POOL, plan 31.10 P7a)
the annotation evals run there, outside this lock, and only the opponent's
moves — with their strength options — stay on this process.

Strength is set with UCI_LimitStrength / UCI_Elo (Stockfish accepts 1320–3190)
and, below 1320, with Skill Level plus a shorter think, which is how club-level
and beginner opponents are produced without Maia.
"""

from __future__ import annotations

import atexit
import logging
import os
import random
import threading
from typing import Optional

import chess
import chess.engine

from src.tools.stockfish import STOCKFISH_PATH

logger = logging.getLogger(__name__)

ELO_MIN, ELO_MAX = 400, 3190
STOCKFISH_ELO_MIN = 1320
EVAL_DEPTH = 12          # annotation eval: ~0.1–0.3 s, enough to tell a blunder
MATE_CP = 10000


def clamp_elo(elo) -> int:
    try:
        return max(ELO_MIN, min(ELO_MAX, int(elo)))
    except (TypeError, ValueError):
        return 1500


def think_time_for(elo: int) -> float:
    """Seconds per move for the full-strength (UCI_Elo) opponents."""
    return 0.5 if elo < 2600 else 0.8


# Below this the opponent is built from the engine's candidate list, not from
# Stockfish's own UCI_Elo: at its floor (1320) Stockfish drops whole queens,
# which no human of that rating does. Above it Stockfish's Elo scale is fine.
STRENGTH_LIMIT_FROM = 2200
CANDIDATES = 5


def search_depth_for(elo: int) -> int:
    """Shallower for weaker opponents — that is where the tactical misses come from."""
    return max(6, min(16, 6 + (elo - ELO_MIN) // 180))   # 400→6, 1000→9, 1500→12, 2100→15


def tolerance_cp_for(elo: int) -> int:
    """How much worse than the best move a candidate may be and still be played.
    A 600 opponent plays second-rate moves; nobody here hangs a queen."""
    return int(round(260 - (elo - ELO_MIN) * 0.13))      # 400→260, 1000→182, 1500→117, 2100→39


def pick_candidate(candidates: list[tuple[str, int]], elo: int, rng: random.Random) -> str:
    """Choose among (uci, cp-from-mover's-view) sorted best first.

    The best move wins with a probability that grows with Elo (0.5 at the
    floor, ~0.9 near the limit); otherwise one of the candidates within the
    tolerance is played, nearer ones more often. A mate for the mover is
    always played; a move that allows mate is never chosen when another exists.
    """
    if not candidates:
        raise RuntimeError("no candidate moves")
    best_uci, best_cp = candidates[0]
    if best_cp >= MATE_CP - 100:
        return best_uci
    tol = tolerance_cp_for(elo)
    pool = [(u, cp) for u, cp in candidates if best_cp - cp <= tol and cp > -MATE_CP + 100] or [candidates[0]]
    if len(pool) == 1:
        return pool[0][0]
    p_best = 0.5 + 0.4 * (elo - ELO_MIN) / (STRENGTH_LIMIT_FROM - ELO_MIN)
    if rng.random() < p_best:
        return best_uci
    others = pool[1:]
    weights = [max(1, tol - (best_cp - cp) + 1) for _, cp in others]
    return rng.choices([u for u, _ in others], weights=weights, k=1)[0]


def _score_cp(score: chess.engine.PovScore, pov: chess.Color) -> int:
    return score.pov(pov).score(mate_score=MATE_CP)


# With the analysis pool on (src/engine_pool.py: two resident processes), the game's own process is closed after this
# long without a move or an eval: Stockfish's memory is the pool's ~2 × 156 MB again between games, not 3 × 157 MB
# for as long as the server runs (review-wiring 01.11). A new move opens it again (~0.1 s, inside the think time).
IDLE_CLOSE_S = float(os.environ.get("GAME_ENGINE_IDLE_CLOSE_S", "180"))


class GameEngine:
    def __init__(self, path: Optional[str] = None):
        self._path = path or STOCKFISH_PATH
        self._lock = threading.Lock()
        self._engine: Optional[chess.engine.SimpleEngine] = None
        self._idle_timer: Optional[threading.Timer] = None

    # ── lifecycle ────────────────────────────────────────────────────────
    def _open(self) -> chess.engine.SimpleEngine:
        if self._engine is None:
            self._engine = chess.engine.SimpleEngine.popen_uci(self._path)
        return self._engine

    def _reset(self) -> None:
        try:
            if self._engine is not None:
                self._engine.close()
        except Exception:  # noqa: BLE001
            pass
        self._engine = None

    def close(self) -> None:
        with self._lock:
            self._reset()

    def _run(self, fn):
        """Run *fn(engine)* under the lock, retrying once on a dead engine."""
        with self._lock:
            try:
                for attempt in (1, 2):
                    try:
                        return fn(self._open())
                    except (chess.engine.EngineTerminatedError, chess.engine.EngineError, BrokenPipeError) as exc:
                        logger.warning("game engine failed (%s), restarting (attempt %d)", exc, attempt)
                        self._reset()
                raise RuntimeError("Stockfish is not available for the game")
            finally:
                self._arm_idle_close()

    def _arm_idle_close(self) -> None:
        """(Under the lock) close the process after IDLE_CLOSE_S unused — only beside the analysis pool, so
        STOCKFISH_POOL=0 keeps today's process for the server's life."""
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None
        if self._engine is None or IDLE_CLOSE_S <= 0:
            return
        try:
            from src.tools.stockfish import pool_on

            if not pool_on():
                return
        except Exception:  # noqa: BLE001
            return
        timer = threading.Timer(IDLE_CLOSE_S, self._close_if_idle, args=(None,))
        timer.args = (timer,)
        timer.daemon = True
        self._idle_timer = timer
        timer.start()

    def _close_if_idle(self, timer) -> None:
        with self._lock:
            if self._idle_timer is not timer:
                return  # used again since: a newer timer is armed
            self._idle_timer = None
            self._reset()

    # ── moves and evals ─────────────────────────────────────────────────
    def choose_move(self, fen: str, elo: int, rng: Optional[random.Random] = None) -> str:
        """The opponent's move (UCI) at the given strength (see pick_candidate)."""
        board = chess.Board(fen)
        elo = clamp_elo(elo)
        rng = rng or random.Random()

        def _strong(engine: chess.engine.SimpleEngine):
            options = {"UCI_LimitStrength": True, "UCI_Elo": max(STOCKFISH_ELO_MIN, elo)}
            engine.configure({k: v for k, v in options.items() if k in engine.options})
            result = engine.play(board, chess.engine.Limit(time=think_time_for(elo)))
            if result.move is None:
                raise RuntimeError("engine returned no move")
            return result.move.uci()

        def _human(engine: chess.engine.SimpleEngine):
            engine.configure({k: v for k, v in {"UCI_LimitStrength": False}.items() if k in engine.options})
            infos = engine.analyse(board, chess.engine.Limit(depth=search_depth_for(elo)), multipv=CANDIDATES)
            candidates = []
            for info in infos:
                pv = info.get("pv") or []
                if pv:
                    candidates.append((pv[0].uci(), _score_cp(info["score"], board.turn)))
            candidates.sort(key=lambda c: -c[1])
            return pick_candidate(candidates, elo, rng)

        return self._run(_strong if elo >= STRENGTH_LIMIT_FROM else _human)

    def evaluate(self, fen: str, pov: chess.Color, depth: int = EVAL_DEPTH) -> tuple[int, Optional[str]]:
        """(centipawns from *pov*'s point of view, best move in SAN for the side to move)."""
        board = chess.Board(fen)
        if board.is_game_over():
            outcome = board.outcome()
            if outcome is None or outcome.winner is None:
                return 0, None
            return (MATE_CP if outcome.winner == pov else -MATE_CP), None

        pooled = _pooled_eval(board, pov, depth)
        if pooled is not None:
            return pooled

        def _go(engine: chess.engine.SimpleEngine):
            engine.configure({k: v for k, v in {"UCI_LimitStrength": False}.items() if k in engine.options})
            info = engine.analyse(board, chess.engine.Limit(depth=depth))
            cp = _score_cp(info["score"], pov)
            pv = info.get("pv") or []
            best = board.san(pv[0]) if pv else None
            return cp, best

        return self._run(_go)


def _pooled_eval(board: chess.Board, pov: chess.Color, depth: int) -> Optional[tuple[int, Optional[str]]]:
    """The annotation eval on the analysis engine pool (plan 31.10 P7a), or None to use the game's own process.

    Outside the game engine's lock, so one student's eval no longer waits behind another's move. A search to
    *depth* from an empty hash (src/tools/stockfish.analyze_exact): the before and after evals of a move are the
    same kind of number on every run, and a position analysed while the student thought (src/engine_precompute.py)
    is served from the store. The opponent's moves stay on the game's own process: their strength options must
    never reach an analysis search."""
    from src.tools import stockfish

    if not stockfish.pool_on():
        return None
    try:
        res = stockfish.analyze_exact(board.fen(), depth, 1)
    except Exception:  # noqa: BLE001 — the game's own process is the fallback
        return None
    lines = res.get("lines") if isinstance(res, dict) and "error" not in res else None
    if not lines:
        return None
    top = lines[0]
    mate = top.get("mate_in")
    if mate is not None:
        mover_cp = MATE_CP - mate if mate > 0 else -MATE_CP - mate
    else:
        mover_cp = int(round(float(top.get("score") or 0.0) * 100))
    cp = mover_cp if pov == board.turn else -mover_cp
    best = None
    try:
        first = (top.get("pv") or "").split()[0]
        move = chess.Move.from_uci(first)
        best = board.san(move) if move in board.legal_moves else None
    except (IndexError, ValueError):
        best = None
    return cp, best


_default: Optional[GameEngine] = None
_default_lock = threading.Lock()


def get_engine() -> GameEngine:
    global _default
    with _default_lock:
        if _default is None:
            _default = GameEngine()
        return _default


def _close_default() -> None:
    """At exit: python-chess's engine thread is not a daemon, so an open game process kept the interpreter from
    exiting (review-wiring 01.11, on main too)."""
    engine = _default
    if engine is not None:
        try:
            engine.close()
        except Exception:  # noqa: BLE001
            pass


# threading's own exit hook runs before the interpreter waits for non-daemon threads (atexit runs after: too late).
try:
    threading._register_atexit(_close_default)  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001 — older Pythons: the plain hook
    atexit.register(_close_default)
