"""Stockfish as the coach's playing hand: limited-strength moves and quick evals.

One engine process per server, serialised with a lock (a game move needs the
engine for a few hundred milliseconds; the analysis tool spawns its own
process and is unaffected). The process is restarted transparently if it dies.

Strength is set with UCI_LimitStrength / UCI_Elo (Stockfish accepts 1320–3190)
and, below 1320, with Skill Level plus a shorter think, which is how club-level
and beginner opponents are produced without Maia.
"""

from __future__ import annotations

import logging
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


class GameEngine:
    def __init__(self, path: Optional[str] = None):
        self._path = path or STOCKFISH_PATH
        self._lock = threading.Lock()
        self._engine: Optional[chess.engine.SimpleEngine] = None

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
            for attempt in (1, 2):
                try:
                    return fn(self._open())
                except (chess.engine.EngineTerminatedError, chess.engine.EngineError, BrokenPipeError) as exc:
                    logger.warning("game engine failed (%s), restarting (attempt %d)", exc, attempt)
                    self._reset()
            raise RuntimeError("Stockfish is not available for the game")

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

        def _go(engine: chess.engine.SimpleEngine):
            engine.configure({k: v for k, v in {"UCI_LimitStrength": False}.items() if k in engine.options})
            info = engine.analyse(board, chess.engine.Limit(depth=depth))
            cp = _score_cp(info["score"], pov)
            pv = info.get("pv") or []
            best = board.san(pv[0]) if pv else None
            return cp, best

        return self._run(_go)


_default: Optional[GameEngine] = None
_default_lock = threading.Lock()


def get_engine() -> GameEngine:
    global _default
    with _default_lock:
        if _default is None:
            _default = GameEngine()
        return _default
