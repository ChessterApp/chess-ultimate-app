"""Automatic curriculum — CL Phase 2, Slice 2 (engine-measured learnability).

A per-student training curriculum, DERIVED offline from engine-verified data:
the coach reads the current curriculum row on a turn, but never computes it
in-turn. Learnability is measured from two objective signals only — engine-
verified blunders (``coach_game_insights.blunders``) and objective puzzle solve
outcomes (``puzzle_attempts``). NO user feedback or ratings feed the score
anywhere here (feedback is never a reward). No LLM calls: this slice is pure,
deterministic aggregation + scoring, so it is cheap and fully auditable.

Learnability score per theme (see :func:`score_themes`)::

    score = normalized_blunder_frequency * cp_loss_weight * proximity_to_50pct

  * ``normalized_blunder_frequency`` — the theme's engine-verified blunder count
    divided by the max blunder count across the student's themes (top theme → 1).
  * ``cp_loss_weight`` — ``clamp(avg_cp_loss / CP_LOSS_REF, 0.1, 1.0)``; a theme
    where blunders cost more centipawns matters more. Unknown avg → neutral 0.5.
  * ``proximity_to_50pct`` — ``clamp(1 - abs(solve_rate - 0.5) * 2, 0.1, 1.0)``.
    Maximally learnable is near a 50% solve rate — not too easy, not too hard.
    An unknown solve rate is treated as the neutral 0.5 (→ proximity 1.0).

Design invariants (see HERMES_CL_PHASE2_CURRICULUM_SPEC.md):
  * Flag-gated behind ``COACH_CURRICULUM`` (default OFF). Computation is OFFLINE
    (a batch script); only *injection* (reading the current row) touches the
    turn path, and it is fail-open + TTL-cached (~5 min).
  * The audit trail is the source of truth; the live curriculum is derived state.
  * Caps: ≤ 3 focus themes per student; injection block ≤ 500 chars; every DB
    string is DATA (length-capped, delimited), never an instruction.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Scoring constants (Design rule 4: deterministic, documented) ─────────
MAX_FOCUS_THEMES = 3          # cap on focus themes per student (Design rule 6)
CP_LOSS_REF = 300.0           # centipawns of a "serious" blunder → cp_loss_weight 1.0
CP_WEIGHT_FLOOR = 0.1         # floor so a theme is never fully zeroed on cp_loss
NEUTRAL_CP_WEIGHT = 0.5       # avg cp_loss unknown → neutral weight
NEUTRAL_SOLVE_RATE = 0.5      # solve rate unknown → neutral (proximity 1.0)
PROXIMITY_FLOOR = 0.1         # floor so an easy/hard theme still scores > 0
THEME_CHAR_LIMIT = 40         # cap on any theme label pulled from the DB

# Puzzle difficulty bucketing for the target-difficulty frontier.
RATING_BAND = 200             # rating band width (cp/elo units)
MIN_BAND_ATTEMPTS = 3         # a band needs this many attempts to be trusted

# ── Injection knobs (P3) ─────────────────────────────────────────────────
CURRICULUM_BLOCK_CAP = 500    # total chars of the injected prompt block
CACHE_TTL_SECONDS = 300       # in-process per-user cache (~5 min)

# Windowing default: learnability is measured over recent play.
DEFAULT_WINDOW_DAYS = 90
CURRICULUM_VALID_DAYS = 14    # how long a computed curriculum stays "current"

# Candidate column names on puzzle_attempts (the live schema varies by
# deployment — inspect the actual rows and degrade gracefully, Design rule /
# spec P2). Theme-level solve rate is a bonus, not a requirement.
PUZZLE_THEME_KEYS = ("theme", "themes", "puzzle_theme", "tag", "tags", "category")
PUZZLE_RATING_KEYS = ("rating", "puzzle_rating", "difficulty", "elo")

_HTTP_TIMEOUT = 10.0


# ── Aggregation: engine-verified blunders by theme (pure) ────────────────


def _coerce_blunders(row: dict) -> list[dict]:
    """Return the blunders list from an insight row (JSONB may arrive as str)."""
    blunders = (row or {}).get("blunders")
    if isinstance(blunders, str):
        try:
            blunders = json.loads(blunders)
        except (json.JSONDecodeError, ValueError):
            return []
    return [b for b in blunders if isinstance(b, dict)] if isinstance(blunders, list) else []


def _blunder_theme(blunder: dict) -> str:
    """Theme key for a blunder: its ``theme``, falling back to ``classification``.

    Length-capped and lowercased (DB text is DATA). '' when neither is present."""
    theme = str(blunder.get("theme") or "").strip()
    if not theme:
        theme = str(blunder.get("classification") or "").strip()
    return theme[:THEME_CHAR_LIMIT].strip().lower()


def aggregate_blunders(insights: list[dict]) -> dict[str, dict]:
    """Aggregate engine-verified blunders across a student's reviewed games.

    Returns ``{theme: {"blunder_count": int, "avg_cp_loss": float|None}}``.
    ``avg_cp_loss`` averages only blunders that carried a numeric ``cp_loss``
    (missing cp_loss still counts toward ``blunder_count`` — a blunder is a
    blunder — but does not distort the average). Pure — the caller supplies the
    rows. Fail-open on malformed rows (skipped)."""
    agg: dict[str, dict] = {}
    for row in insights or []:
        for b in _coerce_blunders(row):
            theme = _blunder_theme(b)
            if not theme:
                continue
            slot = agg.setdefault(theme, {"blunder_count": 0, "_cp_sum": 0.0, "_cp_n": 0})
            slot["blunder_count"] += 1
            cp = b.get("cp_loss")
            try:
                if cp is not None:
                    slot["_cp_sum"] += abs(float(cp))
                    slot["_cp_n"] += 1
            except (TypeError, ValueError):
                pass
    out: dict[str, dict] = {}
    for theme, slot in agg.items():
        avg_cp = slot["_cp_sum"] / slot["_cp_n"] if slot["_cp_n"] else None
        out[theme] = {"blunder_count": slot["blunder_count"], "avg_cp_loss": avg_cp}
    return out


# ── Aggregation: puzzle solve rates (defensive schema, pure) ─────────────


def detect_key(rows: list[dict], candidates: tuple[str, ...]) -> Optional[str]:
    """First candidate column that appears with a non-null value in any row.

    Lets the aggregator adapt to whatever the live ``puzzle_attempts`` schema
    actually carries (spec P2: inspect columns, degrade gracefully)."""
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for c in candidates:
            if row.get(c) is not None:
                return c
    return None


def _theme_tokens(value) -> list[str]:
    """Normalize a puzzle theme field into a list of theme tokens.

    Handles a list (JSON array), a space/comma-separated string (Lichess-style),
    or a single label. Length-capped + lowercased (DB text is DATA)."""
    tokens: list[str] = []
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        raw = value.replace(",", " ").split()
    else:
        return []
    for t in raw:
        s = str(t).strip()[:THEME_CHAR_LIMIT].strip().lower()
        if s:
            tokens.append(s)
    return tokens


def _is_solved(row: dict) -> bool:
    return bool(row.get("solved"))


def solve_rates_by_theme(attempts: list[dict], theme_key: Optional[str]) -> dict[str, float]:
    """Per-theme solve rate from ``puzzle_attempts``. ``{}`` when no theme column.

    A single attempt tagged with multiple themes contributes to each theme's
    rate. Pure — the caller supplies the rows."""
    if not theme_key:
        return {}
    tally: dict[str, list[int]] = {}   # theme -> [solved, total]
    for row in attempts or []:
        if not isinstance(row, dict):
            continue
        for theme in _theme_tokens(row.get(theme_key)):
            slot = tally.setdefault(theme, [0, 0])
            slot[1] += 1
            if _is_solved(row):
                slot[0] += 1
    return {t: (s / n) for t, (s, n) in tally.items() if n}


def overall_solve_rate(attempts: list[dict]) -> Optional[float]:
    """Overall solve rate across all attempts, or None when there are none."""
    rows = [r for r in (attempts or []) if isinstance(r, dict)]
    if not rows:
        return None
    return sum(1 for r in rows if _is_solved(r)) / len(rows)


def compute_target_difficulty(attempts: list[dict], rating_key: Optional[str]) -> str:
    """The rating band where the student's recent solve rate is nearest 50%.

    Buckets attempts into ``RATING_BAND``-wide bands and returns ``"~<midpoint>"``
    for the band closest to a 50% solve rate (the maximally-learnable frontier).
    Returns ``"adaptive"`` when there is no rating/difficulty signal or no band
    has enough attempts to trust (spec P2)."""
    if not rating_key:
        return "adaptive"
    bands: dict[int, list[int]] = {}   # band_floor -> [solved, total]
    for row in attempts or []:
        if not isinstance(row, dict):
            continue
        try:
            rating = float(row.get(rating_key))
        except (TypeError, ValueError):
            continue
        band_floor = int(rating // RATING_BAND) * RATING_BAND
        slot = bands.setdefault(band_floor, [0, 0])
        slot[1] += 1
        if _is_solved(row):
            slot[0] += 1
    best_floor: Optional[int] = None
    best_gap = 999.0
    for floor, (solved, total) in sorted(bands.items()):
        if total < MIN_BAND_ATTEMPTS:
            continue
        gap = abs((solved / total) - 0.5)
        if gap < best_gap:
            best_gap = gap
            best_floor = floor
    if best_floor is None:
        return "adaptive"
    return f"~{best_floor + RATING_BAND // 2}"


# ── Scoring: learnability per theme (pure, unit-tested) ──────────────────


def proximity_to_50pct(solve_rate: Optional[float]) -> float:
    """``clamp(1 - abs(solve_rate - 0.5) * 2, 0.1, 1.0)``.

    1.0 at a 50% solve rate (maximally learnable); floors at 0.1 for a fully
    solved or fully failed theme. Unknown solve rate → neutral 0.5 → 1.0."""
    rate = NEUTRAL_SOLVE_RATE if solve_rate is None else solve_rate
    value = 1.0 - abs(rate - 0.5) * 2.0
    return max(PROXIMITY_FLOOR, min(1.0, value))


def cp_loss_weight(avg_cp_loss: Optional[float]) -> float:
    """``clamp(avg_cp_loss / CP_LOSS_REF, 0.1, 1.0)``; unknown → neutral 0.5."""
    if avg_cp_loss is None:
        return NEUTRAL_CP_WEIGHT
    return max(CP_WEIGHT_FLOOR, min(1.0, avg_cp_loss / CP_LOSS_REF))


def _rationale(theme: str, blunder_count: int, avg_cp_loss: Optional[float],
               solve_rate: Optional[float]) -> str:
    """One-line, template-built rationale (NOT LLM — Design rule 4)."""
    parts = [f"{blunder_count} engine-verified blunder{'s' if blunder_count != 1 else ''}"]
    if avg_cp_loss is not None:
        parts[0] += f" (avg {round(avg_cp_loss)}cp)"
    if solve_rate is not None:
        pct = round(solve_rate * 100)
        near = " — near your ~50% learning frontier" if abs(solve_rate - 0.5) <= 0.15 else ""
        parts.append(f"puzzle solve rate {pct}%{near}")
    else:
        parts.append("solve rate not yet measured")
    return "; ".join(parts) + "."


def score_themes(
    blunder_agg: dict[str, dict],
    solve_rates: Optional[dict[str, float]] = None,
    overall_rate: Optional[float] = None,
    target_difficulty: str = "adaptive",
) -> list[dict]:
    """Rank a student's blunder themes by learnability; return the top ≤3.

    Each focus dict carries ``{theme, score, blunder_count, avg_cp_loss,
    solve_rate, target_difficulty, rationale}``. A theme's solve rate is its
    theme-level rate when known, else the student's overall rate, else unknown
    (neutral in scoring). Deterministic — no randomness, no LLM, no clock."""
    solve_rates = solve_rates or {}
    if not blunder_agg:
        return []
    max_count = max(v["blunder_count"] for v in blunder_agg.values()) or 1

    scored: list[dict] = []
    for theme, agg in blunder_agg.items():
        count = agg["blunder_count"]
        avg_cp = agg.get("avg_cp_loss")
        solve_rate = solve_rates.get(theme)
        if solve_rate is None:
            solve_rate = overall_rate
        norm_freq = count / max_count
        score = norm_freq * cp_loss_weight(avg_cp) * proximity_to_50pct(solve_rate)
        scored.append({
            "theme": theme,
            "score": round(score, 4),
            "blunder_count": count,
            "avg_cp_loss": round(avg_cp, 1) if avg_cp is not None else None,
            "solve_rate": round(solve_rate, 3) if solve_rate is not None else None,
            "target_difficulty": target_difficulty,
            "rationale": _rationale(theme, count, avg_cp, solve_rate),
        })
    # Deterministic tie-break: score desc, then more blunders, then theme name.
    scored.sort(key=lambda f: (-f["score"], -f["blunder_count"], f["theme"]))
    return scored[:MAX_FOCUS_THEMES]


def compute_curriculum(
    insights: list[dict],
    attempts: list[dict],
    since: Optional[str] = None,
) -> dict:
    """Compute one student's curriculum from engine data. Pure orchestration.

    Returns ``{"focus": [...≤3], "computed_from": {...}}``. ``focus`` is empty
    when there are no engine-verified blunders to key on (nothing to learn from
    yet). Never raises on malformed input."""
    blunder_agg = aggregate_blunders(insights)
    theme_key = detect_key(attempts, PUZZLE_THEME_KEYS)
    rating_key = detect_key(attempts, PUZZLE_RATING_KEYS)
    solve_rates = solve_rates_by_theme(attempts, theme_key)
    overall = overall_solve_rate(attempts)
    target = compute_target_difficulty(attempts, rating_key)
    focus = score_themes(blunder_agg, solve_rates, overall, target)
    computed_from = {
        "games": len(insights or []),
        "blunders": sum(v["blunder_count"] for v in blunder_agg.values()),
        "attempts": len([a for a in (attempts or []) if isinstance(a, dict)]),
        "themes_scored": len(blunder_agg),
        "theme_key": theme_key,
        "rating_key": rating_key,
        "overall_solve_rate": round(overall, 3) if overall is not None else None,
        "target_difficulty": target,
        "since": since,
        "window_days": DEFAULT_WINDOW_DAYS,
    }
    return {"focus": focus, "computed_from": computed_from}


# ── Supabase access (fail-open) ──────────────────────────────────────────


def _supabase_creds() -> tuple[str, str]:
    return os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_KEY", "")


def _headers(key: str, *, write: bool = False, upsert: bool = False) -> dict:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if write:
        headers["Content-Type"] = "application/json"
    if upsert:
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    return headers


def default_since(days: int = DEFAULT_WINDOW_DAYS) -> str:
    """ISO timestamp ``days`` ago (UTC) — the default learnability window start."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def list_users(since: Optional[str], limit: int = 1000) -> list[str]:
    """Distinct ``user_id``s with engine-verified insights in the window.

    The blunder signal (``coach_game_insights``) is the curriculum's anchor, so
    users are drawn from there. Fail-open → []."""
    url, key = _supabase_creds()
    if not url or not key:
        return []
    params = {"select": "user_id", "order": "created_at.desc", "limit": str(limit)}
    if since:
        params["created_at"] = f"gte.{since}"
    try:
        resp = httpx.get(f"{url}/rest/v1/coach_game_insights", params=params,
                         headers=_headers(key), timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        logger.debug("list_users failed", exc_info=True)
        return []
    seen: list[str] = []
    seen_set: set[str] = set()
    for r in rows if isinstance(rows, list) else []:
        uid = (r or {}).get("user_id")
        if uid and uid not in seen_set:
            seen_set.add(uid)
            seen.append(uid)
    return seen


def fetch_insights(user_id: str, since: Optional[str], limit: int = 500) -> list[dict]:
    """A student's reviewed-game insight rows in the window. Fail-open → []."""
    url, key = _supabase_creds()
    if not url or not key:
        return []
    params = {
        "user_id": f"eq.{user_id}",
        "select": "blunders,created_at,played_at",
        "order": "created_at.desc",
        "limit": str(limit),
    }
    if since:
        params["created_at"] = f"gte.{since}"
    try:
        resp = httpx.get(f"{url}/rest/v1/coach_game_insights", params=params,
                         headers=_headers(key), timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        rows = resp.json()
        return rows if isinstance(rows, list) else []
    except Exception:
        logger.debug("fetch_insights failed for %s", user_id, exc_info=True)
        return []


def fetch_attempts(user_id: str, since: Optional[str], limit: int = 2000) -> list[dict]:
    """A student's puzzle attempts (all columns, so the aggregator can inspect
    the live schema defensively). Windowing is applied client-side on
    ``solved_at`` when present so an unknown time column never drops all rows.
    Fail-open → []."""
    url, key = _supabase_creds()
    if not url or not key:
        return []
    params = {"user_id": f"eq.{user_id}", "select": "*", "limit": str(limit)}
    try:
        resp = httpx.get(f"{url}/rest/v1/puzzle_attempts", params=params,
                         headers=_headers(key), timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        logger.debug("fetch_attempts failed for %s", user_id, exc_info=True)
        return []
    if not isinstance(rows, list):
        return []
    if since:
        kept = []
        for r in rows:
            ts = (r or {}).get("solved_at") or (r or {}).get("created_at")
            if ts is None or str(ts) >= since:   # ISO strings sort lexicographically
                kept.append(r)
        return kept
    return rows


def upsert_curriculum(user_id: str, focus: list[dict], computed_from: dict,
                      valid_until: Optional[str]) -> bool:
    """Upsert the student's ONE current curriculum row (on_conflict user_id)."""
    url, key = _supabase_creds()
    if not url or not key:
        return False
    row = {"user_id": user_id, "focus": focus, "computed_from": computed_from,
           "valid_until": valid_until}
    try:
        httpx.post(
            f"{url}/rest/v1/coach_curriculum",
            params={"on_conflict": "user_id"},
            json=row,
            headers=_headers(key, write=True, upsert=True),
            timeout=_HTTP_TIMEOUT,
        ).raise_for_status()
        return True
    except Exception:
        logger.debug("upsert_curriculum failed for %s", user_id, exc_info=True)
        return False


def write_audit(user_id: str, focus: list[dict], computed_from: dict) -> bool:
    """Append one immutable coach_curriculum_audit row."""
    url, key = _supabase_creds()
    if not url or not key:
        return False
    try:
        httpx.post(
            f"{url}/rest/v1/coach_curriculum_audit",
            json={"user_id": user_id, "focus": focus, "computed_from": computed_from},
            headers=_headers(key, write=True),
            timeout=_HTTP_TIMEOUT,
        ).raise_for_status()
        return True
    except Exception:
        logger.debug("write_audit failed for %s", user_id, exc_info=True)
        return False


def persist_curriculum(user_id: str, result: dict) -> bool:
    """Upsert the current row + append the audit row for one recompute.

    ``valid_until`` is stamped here (not in the pure compute) so the scoring
    stays clock-free and unit-testable. Returns True only when the upsert
    succeeded."""
    focus = result.get("focus") or []
    computed_from = result.get("computed_from") or {}
    valid_until = (datetime.now(timezone.utc)
                   + timedelta(days=CURRICULUM_VALID_DAYS)).isoformat()
    ok = upsert_curriculum(user_id, focus, computed_from, valid_until)
    write_audit(user_id, focus, computed_from)
    return ok


# ── Injection: load current row → render → per-user TTL cache (P3) ────────


def load_current_curriculum(user_id: str) -> list[dict]:
    """Load the student's current focus list. Fail-open → []."""
    url, key = _supabase_creds()
    if not url or not key or not user_id:
        return []
    try:
        resp = httpx.get(
            f"{url}/rest/v1/coach_curriculum",
            params={"user_id": f"eq.{user_id}", "select": "focus", "limit": "1"},
            headers=_headers(key),
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        logger.debug("load_current_curriculum failed for %s", user_id, exc_info=True)
        return []
    if not isinstance(rows, list) or not rows:
        return []
    focus = (rows[0] or {}).get("focus")
    if isinstance(focus, str):
        try:
            focus = json.loads(focus)
        except (json.JSONDecodeError, ValueError):
            return []
    return [f for f in focus if isinstance(f, dict)] if isinstance(focus, list) else []


def render_curriculum_block(focus: list[dict], cap: int = CURRICULUM_BLOCK_CAP) -> str:
    """Render the 'Training focus (engine-measured)' block, hard-capped.

    One line per theme: the theme, the engine-measured 'why', and a concrete
    suggested action. Returns '' when there is nothing to render. Every field is
    DATA — the theme/rationale come from the DB and are already length-capped
    upstream, but are re-truncated here defensively."""
    lines: list[str] = []
    for f in (focus or [])[:MAX_FOCUS_THEMES]:
        if not isinstance(f, dict):
            continue
        theme = str(f.get("theme") or "").strip()[:THEME_CHAR_LIMIT].strip()
        if not theme:
            continue
        why = str(f.get("rationale") or "").strip()[:200].strip()
        why_part = f" — {why}" if why else ""
        lines.append(
            f"- {theme}{why_part} Offer puzzles on this theme via set_puzzle."
        )
    if not lines:
        return ""
    block = ("## Training focus (engine-measured)\n"
             "Target these themes with the student — chosen by engine-measured "
             "learnability (high blunder rate near their ~50% solve frontier):\n"
             + "\n".join(lines))
    return block[:cap]


# In-process per-user cache so injection adds no per-turn DB latency spike.
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, list[dict]]] = {}   # user_id -> (expires_at, focus)


def clear_curriculum_cache() -> None:
    """Reset the in-process curriculum cache (used by tests)."""
    with _cache_lock:
        _cache.clear()


def get_cached_curriculum(user_id: str, ttl: float = CACHE_TTL_SECONDS) -> list[dict]:
    """Return the student's focus list from the per-user cache, refreshing on
    expiry. Fail-open: any load failure yields [] (never raises)."""
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(user_id)
        if hit is not None and now < hit[0]:
            return hit[1]
    focus = load_current_curriculum(user_id)
    with _cache_lock:
        _cache[user_id] = (now + ttl, focus)
    return focus


def load_curriculum_block(user_id: str) -> str:
    """Top-level injection helper: cached current focus → rendered, capped block.
    Fail-open → '' on any failure."""
    try:
        return render_curriculum_block(get_cached_curriculum(user_id))
    except Exception:
        logger.debug("load_curriculum_block failed for %s", user_id, exc_info=True)
        return ""
