"""Request fields this Hermes does not know, made visible (28.10).

The site and Hermes ship separately. A newer site sending a field an older Hermes does not know
(session_id on voice/idea, context_note on analysis) had it dropped without a trace, and the coach
answered without it. The request still succeeds; one WARNING per endpoint + field says so, at most
once per WINDOW_S, with the field's name only (values may be the student's words).
"""

from __future__ import annotations

import contextvars
import logging
import re
import threading
import time
from functools import lru_cache
from typing import Any, Iterable, Optional

from pydantic import BaseModel, ConfigDict, model_validator

logger = logging.getLogger(__name__)

WINDOW_S = 3600.0
# Field names come from the client: a bound on the table, so random names cannot grow it.
MAX_KEYS = 512
_NAME_MAX = 64

# The ASGI scope of the request being handled (set by the server's middleware): the router puts
# the matched route into it, so the log names the template, not a path with a session id.
current_scope: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("request_skew_scope", default=None)

_seen: dict[tuple[str, str], float] = {}
_lock = threading.Lock()


def reset() -> None:
    with _lock:
        _seen.clear()


def current_endpoint() -> str:
    scope = current_scope.get()
    if not scope:
        return "?"
    path = getattr(scope.get("route"), "path", None) or scope.get("path") or "?"
    return f"{scope.get('method', '')} {path}".strip()


def _safe(name: Any) -> str:
    return re.sub(r"[^\w.-]", "?", str(name))[:_NAME_MAX]


def _claim(key: tuple[str, str], now: float) -> bool:
    """True when *key* may be logged now (first time, or its window passed) and the table has room."""
    with _lock:
        last = _seen.get(key)
        if last is not None and now - last < WINDOW_S:
            return False
        if last is None and len(_seen) >= MAX_KEYS:
            for k, t in list(_seen.items()):
                if now - t >= WINDOW_S:
                    del _seen[k]
            if len(_seen) >= MAX_KEYS:
                return False
        _seen[key] = now
        return True


def note_unknown_fields(names: Iterable[Any], endpoint: Optional[str] = None, model: str = "the request") -> None:
    endpoint = endpoint or current_endpoint()
    now = time.monotonic()
    for name in names:
        field = _safe(name)
        if _claim((endpoint, field), now):
            logger.warning("request field %r is unknown to %s on %s and was ignored: the site is newer "
                           "than this Hermes (or sends a field nobody reads)", field, model, endpoint)


@lru_cache(maxsize=None)
def _known_keys(model: type[BaseModel]) -> frozenset[str]:
    keys: set[str] = set()
    for name, info in model.model_fields.items():
        keys.add(name)
        for alias in (info.alias, info.validation_alias):
            if isinstance(alias, str):
                keys.add(alias)
    return frozenset(keys)


class CoachRequest(BaseModel):
    """Base of the coach endpoints' bodies: unknown fields are ignored as before, but logged.

    extra stays "ignore" rather than "allow": an unknown field never lands on the model, so a
    later model_dump() cannot pass it on to a board or a database row.
    """

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _note_unknown(cls, data: Any) -> Any:
        if isinstance(data, dict):
            known = _known_keys(cls)
            unknown = [k for k in data if k not in known]
            if unknown:
                note_unknown_fields(unknown, model=cls.__name__)
        return data
