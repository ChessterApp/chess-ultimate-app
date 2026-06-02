"""
Resend Domains API client.

Thin wrapper around the four endpoints we need for the branded-sender flow
(PRD §11.2 #4 — Phase 2):

  * POST   /domains              → create
  * GET    /domains/{id}         → status + DNS records
  * POST   /domains/{id}/verify  → trigger verification
  * DELETE /domains/{id}         → remove

Auth: Bearer ``RESEND_API_KEY``.

All public methods raise :class:`ResendAPIError` on non-2xx responses; the
caller is expected to translate that into a Flask response (see
``backend/routes/admin.py`` ``email-sender`` endpoints).

Mirrors the shape of ``services.vercel_client`` so the route handlers can
reuse the same try/except → status-flip pattern.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

RESEND_API_BASE = 'https://api.resend.com'
DEFAULT_TIMEOUT = 10.0


class ResendAPIError(Exception):
    def __init__(self, status_code: int, code: str | None, message: str,
                 payload: dict | None = None) -> None:
        super().__init__(f'Resend API {status_code} ({code}): {message}')
        self.status_code = status_code
        self.code = code or ''
        self.message = message
        self.payload = payload or {}


class ResendClient:
    """Client for the Resend Domains API."""

    def __init__(self, api_key: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.api_key = api_key or os.getenv('RESEND_API_KEY', '')
        self.timeout = timeout

    # ── public methods ───────────────────────────────────────────────────

    def create_domain(self, domain: str) -> dict[str, Any]:
        return self._request('POST', '/domains', body={'name': domain})

    def get_domain(self, domain_id: str) -> dict[str, Any]:
        return self._request('GET', f'/domains/{domain_id}')

    def verify_domain(self, domain_id: str) -> dict[str, Any]:
        return self._request('POST', f'/domains/{domain_id}/verify')

    def remove_domain(self, domain_id: str) -> dict[str, Any]:
        return self._request('DELETE', f'/domains/{domain_id}')

    # ── internal ─────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: dict | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise ResendAPIError(500, 'misconfigured', 'RESEND_API_KEY not configured')

        url = RESEND_API_BASE + path
        data = json.dumps(body).encode('utf-8') if body is not None else None
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode('utf-8')
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            try:
                err_raw = exc.read().decode('utf-8')
                payload = json.loads(err_raw) if err_raw else {}
            except Exception:
                payload = {}
            code = payload.get('name') if isinstance(payload, dict) else None
            message = (
                payload.get('message') if isinstance(payload, dict) else None
            ) or str(exc)
            raise ResendAPIError(exc.code, code, message, payload) from exc
        except Exception as exc:  # pragma: no cover — network-level
            raise ResendAPIError(502, 'network', f'Resend API request failed: {exc}') from exc


_default: ResendClient | None = None


def get_client() -> ResendClient:
    global _default
    if _default is None:
        _default = ResendClient()
    return _default


def reset_client() -> None:
    """Test hook — discard the cached default client so envs reload."""
    global _default
    _default = None


# ── State-machine helpers ────────────────────────────────────────────────


_TERMINAL = {'active', 'failed'}


def map_resend_status(status: str | None) -> str:
    """Translate a Resend domain status string into our four-state machine."""
    s = (status or '').lower()
    if s in ('verified', 'success'):
        return 'active'
    if s in ('failed', 'error'):
        return 'failed'
    if s in ('pending', 'not_started', 'unverified'):
        return 'pending'
    if s in ('verifying', 'in_progress', 'started'):
        return 'verifying'
    return 'pending'


def is_terminal(status: str | None) -> bool:
    return (status or '').lower() in _TERMINAL
