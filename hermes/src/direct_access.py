"""The voice pipeline's direct path (23.11): the page talks to Hermes itself, not through the site's proxy.

Every request reaches Hermes through the site (Vercel), which checks the student's sign-in, access and plan and
passes them as headers (X-User-Id, x-subscription-tier) that Hermes trusts — Hermes itself has no public address.
That hop cost ~0.5 s a request, two a spoken turn, more when the function woke up (prod 23.11: a phrase's
recognition 1.8 s, the provider's own share 0.9 s).

Here the site mints a short pass instead (frontend/src/lib/coach/direct-pass.ts: who, plan, expiry, signed with
COACH_DIRECT_SECRET), and the page sends the two hot requests straight to Hermes under ``/direct/``:

    POST /direct/voice/stt  → /api/coach/voice/stt
    POST /direct/chat       → /api/coach/chat

The middleware below checks the pass and only then hands the request to the same route, with the identity and the
plan taken from the pass — the ones a request brings in its own headers are dropped. Nothing else is served under
``/direct/``; the server's proxy (nginx) exposes only that prefix, port 8642 stays closed. Without the secret the
prefix answers 404: the path is off and the page goes through the site as before.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

PREFIX = "/direct/"
ROUTES = {
    "/direct/voice/stt": "/api/coach/voice/stt",
    "/direct/chat": "/api/coach/chat",
}
AUDIENCE = "coach-direct"
# A clock a little apart on the two servers does not refuse a fresh pass.
LEEWAY_S = 30
# The identity and the plan come from the pass alone on this path.
DROPPED_HEADERS = {b"x-user-id", b"x-clerk-user-id", b"x-subscription-tier", b"x-learn-floor", b"authorization",
                   b"cookie"}
DEFAULT_ORIGINS = "https://chesster.io,https://www.chesster.io"


def _secret() -> bytes:
    return (os.environ.get("COACH_DIRECT_SECRET") or "").strip().encode()


def _origins() -> set[str]:
    raw = os.environ.get("COACH_DIRECT_ORIGINS") or DEFAULT_ORIGINS
    return {o.strip().rstrip("/") for o in raw.split(",") if o.strip()}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(payload: dict, secret: Optional[bytes] = None) -> str:
    """A pass for *payload* — what the site mints (tests and the check script use it here)."""
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    mac = hmac.new(secret if secret is not None else _secret(), f"v1.{body}".encode(), hashlib.sha256).digest()
    return f"v1.{body}.{_b64(mac)}"


def verify(token: str, now: Optional[float] = None) -> Optional[dict]:
    """The pass's payload {sub, tier, exp, aud[, floor]} when its signature, audience and expiry hold, else None."""
    secret = _secret()
    if not secret or not token:
        return None
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        return None
    try:
        expected = hmac.new(secret, f"v1.{parts[1]}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(parts[2])):
            return None
        payload = json.loads(_unb64(parts[1]))
    except Exception:  # noqa: BLE001 — a malformed pass is no pass
        return None
    if not isinstance(payload, dict) or payload.get("aud") != AUDIENCE:
        return None
    sub, tier, exp = payload.get("sub"), payload.get("tier"), payload.get("exp")
    if not isinstance(sub, str) or not sub or not isinstance(tier, str) or not tier:
        return None
    if not isinstance(exp, (int, float)) or (now if now is not None else time.time()) > exp + LEEWAY_S:
        return None
    return payload


def _cors_headers(origin: str) -> list:
    if origin and origin in _origins():
        return [(b"access-control-allow-origin", origin.encode()), (b"vary", b"Origin")]
    return [(b"vary", b"Origin")]


async def _reply(send, status: int, body: dict, extra: list) -> None:
    data = json.dumps(body).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode()),
                            (b"cache-control", b"no-store"), *extra]})
    await send({"type": "http.response.body", "body": data})


class DirectAccess:
    """ASGI middleware: ``/direct/…`` requests with a valid pass go on to their route as the pass's student."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not str(scope.get("path", "")).startswith(PREFIX):
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope.get("headers") or []}
        origin = headers.get(b"origin", b"").decode("latin-1")
        cors = _cors_headers(origin)
        target = ROUTES.get(scope["path"])
        if not _secret() or target is None:
            return await _reply(send, 404, {"detail": "Not Found"}, cors)
        if scope.get("method") == "OPTIONS":
            # The browser's preflight: the page's origin may send these headers.
            await send({"type": "http.response.start", "status": 204, "headers": [
                *cors, (b"access-control-allow-methods", b"POST"),
                (b"access-control-allow-headers", b"authorization, content-type, x-voice-locale"),
                (b"access-control-max-age", b"600")]})
            return await send({"type": "http.response.body", "body": b""})
        auth = headers.get(b"authorization", b"").decode("latin-1")
        payload = verify(auth[7:].strip()) if auth[:7].lower() == "bearer " else None
        if payload is None:
            return await _reply(send, 401, {"detail": "A valid pass is required"}, cors)
        inner = dict(scope)
        inner["path"] = target
        inner["raw_path"] = target.encode()
        inner["headers"] = [(k, v) for k, v in scope.get("headers") or [] if k.lower() not in DROPPED_HEADERS] + [
            (b"x-user-id", payload["sub"].encode()), (b"x-subscription-tier", payload["tier"].encode())]
        floor = payload.get("floor")
        if isinstance(floor, int) and not isinstance(floor, bool) and 1 <= floor <= 99:
            # The student's Chess Empire level (src/learn_access.py): from the pass, as the identity.
            inner["headers"].append((b"x-learn-floor", str(floor).encode()))

        async def send_cors(message):
            if message.get("type") == "http.response.start":
                # The chat streams: the proxy in front (nginx) passes each frame on as it comes.
                message = {**message, "headers": [*(message.get("headers") or []), *cors,
                                                  (b"x-accel-buffering", b"no")]}
            await send(message)

        await self.app(inner, receive, send_cors)
