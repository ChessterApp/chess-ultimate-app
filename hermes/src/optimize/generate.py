"""O2 — generation adapter with a disk cache and a hard call budget.

``generate_reply(soul_text, case, model, ...)`` builds the coach system prompt
the SAME way :mod:`src.prompt_builder` does for the base (text) coach turn — same
SOUL persona, same static tool instructions, same board-state block — then asks
OpenRouter for one reply. The plain httpx call mirrors
``memory_writer._call_reflector_llm`` (fail-soft, ``OPENROUTER_API_KEY`` env).

Two invariants keep an optimization run cheap and resumable:

  * **Disk cache** — keyed on ``sha256(prompt_variant_hash, case_id, model)``.
    A cached key is NEVER re-called, so a re-run resumes for free and re-scoring
    a variant costs nothing.
  * **Hard budget** — a per-run counter (persisted to disk) caps live LLM calls.
    Exceeding it raises :class:`BudgetExceeded` so the caller can stop cleanly
    and still emit a partial report. Cache hits never spend budget.
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

from src.prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = 60.0
DEFAULT_MAX_LLM_CALLS = 250

# Rough per-call cost estimate (USD) for the plan/report printout. Deliberately
# coarse — it exists to warn before a paid run, not to bill. Keyed by a substring
# of the OpenRouter model id; falls back to the default.
_COST_PER_CALL_USD = {
    "gemini-2.5-flash": 0.002,
    "claude-sonnet": 0.02,
    "claude-opus": 0.10,
}
_DEFAULT_COST_PER_CALL_USD = 0.01


class BudgetExceeded(RuntimeError):
    """Raised when a live LLM call would exceed the run's ``--max-llm-calls``."""


def prompt_variant_hash(soul_text: str) -> str:
    """Stable fingerprint of the optimizable variable (the SOUL text).

    The board-state block and user text are per-case and identical across
    variants, so the variant identity is exactly the SOUL text — that is what
    the cache key must key on.
    """
    return hashlib.sha256(soul_text.encode("utf-8")).hexdigest()[:16]


def cache_key(soul_text: str, case_id: str, model: str) -> str:
    """``sha256(prompt_variant_hash, case_id, model)`` — the disk cache key."""
    raw = f"{prompt_variant_hash(soul_text)}\x00{case_id}\x00{model}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def estimate_cost(n_calls: int, model: str) -> float:
    """Rough USD estimate for ``n_calls`` live calls on ``model``."""
    rate = _DEFAULT_COST_PER_CALL_USD
    for frag, r in _COST_PER_CALL_USD.items():
        if frag in model:
            rate = r
            break
    return round(n_calls * rate, 4)


class DiskCache:
    """Content-addressed reply cache under ``eval/prompt_opt/cache/``."""

    def __init__(self, cache_dir: str):
        self.dir = Path(cache_dir)

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> Optional[str]:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))["reply"]
        except Exception:
            logger.debug("cache read failed for %s", key, exc_info=True)
            return None

    def put(self, key: str, reply: str, meta: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {"reply": reply, **meta}
        self._path(key).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class Budget:
    """A per-run live-call counter, persisted so a resumed run keeps counting."""

    def __init__(self, max_calls: int, state_path: Optional[str] = None):
        self.max_calls = max_calls
        self.state_path = Path(state_path) if state_path else None
        self.count = 0
        if self.state_path and self.state_path.exists():
            try:
                self.count = int(json.loads(self.state_path.read_text())["count"])
            except Exception:
                logger.debug("budget state read failed", exc_info=True)

    @property
    def remaining(self) -> int:
        return max(0, self.max_calls - self.count)

    def exceeded(self) -> bool:
        return self.count >= self.max_calls

    def _persist(self) -> None:
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"count": self.count, "max_calls": self.max_calls}),
            encoding="utf-8",
        )

    def record(self) -> None:
        """Register one live call. Raises if it would breach the cap."""
        if self.exceeded():
            raise BudgetExceeded(
                f"live LLM call budget exhausted ({self.count}/{self.max_calls})"
            )
        self.count += 1
        self._persist()


def build_case_prompt(soul_text: str, case: dict) -> tuple[str, str]:
    """Return ``(system_prompt, user_message)`` for one case.

    Reuses :func:`src.prompt_builder.build_system_prompt` (the exact serving-path
    assembly) with the candidate SOUL text and the case's board FEN — no profile,
    no locale, matching the base coach turn the golden set was built from.
    """
    system = build_system_prompt(
        soul_content=soul_text,
        user_profile=None,
        board_fen=case.get("fen"),
        move_history=case.get("move_history"),
        locale=case.get("locale"),
    )
    return system, case.get("user_text", "")


def call_openrouter(system: str, user: str, model: str) -> Optional[str]:
    """One OpenRouter chat completion. Returns reply text, or None on any failure.

    Mirrors ``memory_writer._call_reflector_llm`` (plain httpx, ``OPENROUTER_API_KEY``,
    temperature 0). Never raises — the caller treats None as an empty reply.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return None
    try:
        resp = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        logger.debug("OpenRouter generation call failed", exc_info=True)
        return None


def generate_reply(
    soul_text: str,
    case: dict,
    model: str,
    cache: DiskCache,
    budget: Budget,
) -> str:
    """Generate (or replay from cache) one coach reply for ``case``.

    Cache hit → return immediately, no budget spent. Cache miss → charge the
    budget (raising :class:`BudgetExceeded` if the cap is hit), call the model,
    persist the reply, and return it. A model failure caches ``""`` so the dead
    key is not re-attempted within the run.
    """
    case_id = str(case.get("id", ""))
    key = cache_key(soul_text, case_id, model)
    cached = cache.get(key)
    if cached is not None:
        return cached

    budget.record()  # miss ⇒ this is a real call — charge it first.
    system, user = build_case_prompt(soul_text, case)
    reply = call_openrouter(system, user, model) or ""
    cache.put(key, reply, {"case_id": case_id, "model": model})
    return reply
