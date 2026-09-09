"""
Persist a completed Game Review as ONE durable coach insight row.

Game reviews (services/game_review.py) compute per-move Stockfish ground truth on
demand and never persist it — the analysis evaporates after each review. This
module distills a completed review into a single ``coach_game_insights`` row
(opening, result, accuracy, the worst blunders/mistakes, a short summary) so the
coach can later retrieve a student's own games and reason over them.

Design invariants:
  * Fail-open EVERYWHERE — persisting an insight must never affect the review
    response. Any exception is logged and swallowed.
  * Anonymous reviews (no real user id) are skipped silently.
  * Gated behind ``REVIEW_PERSIST_INSIGHTS`` (default ON) as a kill-switch.
  * Upsert on the (user_id, game_ref, source) unique key so re-reviews replace
    the previous digest instead of duplicating it.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# How many worst moves to keep on a single insight row.
MAX_BLUNDERS = 5
# Classifications worth surfacing to the coach, worst-first.
_KEEP_CLASSES = ("blunder", "mistake")
# Plain-text summary hard cap (matches the coach_game_insights.summary intent).
SUMMARY_CHAR_LIMIT = 400
# Mate evals are converted to this centipawn magnitude for cp-loss ranking.
_MATE_CP = 100_000


def _persist_enabled() -> bool:
    """``REVIEW_PERSIST_INSIGHTS`` kill-switch, default ON."""
    raw = os.environ.get("REVIEW_PERSIST_INSIGHTS")
    if raw is None:
        return True
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _eval_to_cp(eval_dict, mover_is_white: bool):
    """A White-POV ``{"type","value"}`` eval → centipawns from the MOVER's POV.
    Mate is mapped to a large signed magnitude. Returns None on a bad shape."""
    if not isinstance(eval_dict, dict):
        return None
    etype = eval_dict.get("type")
    value = eval_dict.get("value")
    if not isinstance(value, (int, float)):
        return None
    if etype == "mate":
        cp = _MATE_CP if value > 0 else -_MATE_CP
    elif etype == "cp":
        cp = float(value)
    else:
        return None
    return cp if mover_is_white else -cp


def _cp_loss(move: dict, mover_is_white: bool):
    """Centipawns the mover lost relative to the engine's best move.

    ``move["best"]["eval"]`` is the position eval BEFORE the ply (playing best
    yields it); ``move["eval"]`` is the eval AFTER the played move. Both are
    White-POV. The loss is measured in the mover's POV and clamped at >= 0."""
    best = move.get("best") or {}
    best_cp = _eval_to_cp(best.get("eval"), mover_is_white)
    played_cp = _eval_to_cp(move.get("eval"), mover_is_white)
    if best_cp is None or played_cp is None:
        return None
    return max(0.0, best_cp - played_cp)


def _norm_color(color):
    """Normalize a color to 'w'/'b', or None if unknown."""
    if not isinstance(color, str):
        return None
    c = color.strip().lower()
    if c in ("w", "white"):
        return "w"
    if c in ("b", "black"):
        return "b"
    return None


def select_blunders(review_dict: dict, color=None, limit: int = MAX_BLUNDERS) -> list[dict]:
    """Pick the worst <=``limit`` blunders/mistakes, worst cp-loss first.

    When ``color`` is known only that player's moves are considered; otherwise
    every move is eligible. Each entry is
    ``{fen, move_played, best_move, cp_loss, classification, theme}``."""
    want = _norm_color(color)
    scored: list[tuple[float, dict]] = []
    for move in review_dict.get("moves") or []:
        if not isinstance(move, dict):
            continue
        if move.get("classification") not in _KEEP_CLASSES:
            continue
        mover_is_white = int(move.get("ply", 0)) % 2 == 1
        if want is not None and want != ("w" if mover_is_white else "b"):
            continue
        loss = _cp_loss(move, mover_is_white)
        if loss is None:
            continue
        best = move.get("best") or {}
        scored.append(
            (
                loss,
                {
                    "fen": move.get("fen"),
                    "move_played": move.get("san") or move.get("uci"),
                    "best_move": best.get("uci"),
                    "cp_loss": round(loss),
                    "classification": move.get("classification"),
                    "theme": move.get("phase"),
                },
            )
        )
    scored.sort(key=lambda t: t[0], reverse=True)
    return [entry for _, entry in scored[: max(0, limit)]]


def build_summary(opening, accuracy, result, blunders: list[dict]) -> str:
    """A <=``SUMMARY_CHAR_LIMIT``-char plain-text digest of the game."""
    parts: list[str] = []
    if opening:
        parts.append(f"Opening: {opening}.")
    if result:
        parts.append(f"Result: {result}.")
    if isinstance(accuracy, (int, float)):
        parts.append(f"Accuracy {round(accuracy, 1)}.")
    if blunders:
        worst = blunders[0]
        parts.append(
            f"{len(blunders)} critical error(s); worst: {worst.get('classification')} "
            f"{worst.get('move_played')} (best {worst.get('best_move')}, "
            f"-{worst.get('cp_loss')}cp)."
        )
    else:
        parts.append("No blunders or mistakes flagged.")
    return " ".join(parts).strip()[:SUMMARY_CHAR_LIMIT]


def distill_insight(
    user_id: str,
    game_ref: str,
    review_dict: dict,
    *,
    color=None,
    result=None,
    played_at=None,
    source: str = "review",
) -> dict:
    """Turn a completed review into a single ``coach_game_insights`` row dict."""
    want = _norm_color(color)
    opening = None
    opening_obj = review_dict.get("opening")
    if isinstance(opening_obj, dict):
        opening = opening_obj.get("name")

    accuracy = None
    acc_obj = review_dict.get("accuracy")
    if isinstance(acc_obj, dict) and want is not None:
        val = acc_obj.get(want)
        if isinstance(val, (int, float)):
            accuracy = val

    blunders = select_blunders(review_dict, color=color)
    summary = build_summary(opening, accuracy, result, blunders)

    return {
        "user_id": str(user_id),
        "game_ref": game_ref,
        "source": source,
        "color": want,
        "opening": opening,
        "result": result,
        "accuracy": accuracy,
        "blunders": blunders,
        "summary": summary,
        "played_at": played_at,
    }


def persist_review_insight(
    user_id,
    review_id: str,
    review_dict: dict,
    *,
    color=None,
    result=None,
    played_at=None,
    source: str = "review",
) -> bool:
    """Distill ``review_dict`` into one ``coach_game_insights`` row and upsert it.

    Returns True on a successful write, False otherwise (disabled, anonymous, or
    any error). Never raises — the caller's review response must be unaffected."""
    if not _persist_enabled():
        return False
    if not user_id or not str(user_id).strip():
        return False  # anonymous review — skip silently
    if not isinstance(review_dict, dict):
        return False

    try:
        row = distill_insight(
            user_id,
            review_id,
            review_dict,
            color=color,
            result=result,
            played_at=played_at,
            source=source,
        )
        from services.supabase_client import get_supabase_client

        client = get_supabase_client()
        (
            client.table("coach_game_insights")
            .upsert(row, on_conflict="user_id,game_ref,source")
            .execute()
        )
        return True
    except Exception:
        logger.warning("persist_review_insight failed for %s", review_id, exc_info=True)
        return False
