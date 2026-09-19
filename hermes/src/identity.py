"""Resolve the authenticated student's id inside tool handlers.

The voice path forces identity args to the authenticated user in
``tool_bridge`` before dispatch. The text path runs tools inside the
framework's ``AIAgent``, which forwards only the coach ``session_id`` to
handlers — the model had to guess ``user_id`` itself, and student-scoped
tools either got an empty id or an invented one.

Student-scoped handlers call :func:`resolve_user_id` so the id always comes
from the request (session → user, or the per-request context var) and the
model-supplied argument is only a last resort.
"""

import contextvars
import logging

logger = logging.getLogger(__name__)

# Set by the request handler for the duration of a coach turn.
current_user_id: contextvars.ContextVar = contextvars.ContextVar(
    "coach_user_id", default=""
)

_ANONYMOUS = frozenset({"", "anonymous", "unknown", "user_id", "the user's id"})


def resolve_user_id(args: dict, kwargs: dict) -> str:
    """Return the student's id for a tool call.

    Order: the coach session the framework dispatched from (``session_id`` in
    *kwargs*) → the request-scoped context var → the model-supplied
    ``args["user_id"]``.
    """
    session_id = kwargs.get("session_id") if kwargs else None
    if session_id:
        try:
            from src.sessions import session_store

            session = session_store.get(str(session_id))
        except Exception:  # pragma: no cover - persistence hiccup; fall through
            logger.exception("identity: session lookup failed for %s", session_id)
            session = None
        if session is not None and session.user_id not in _ANONYMOUS:
            return session.user_id

    ctx_user = current_user_id.get()
    if ctx_user and ctx_user not in _ANONYMOUS:
        return ctx_user

    supplied = str((args or {}).get("user_id") or "").strip()
    if supplied and supplied.lower() not in _ANONYMOUS:
        logger.warning("identity: falling back to model-supplied user_id")
        return supplied
    return ""
