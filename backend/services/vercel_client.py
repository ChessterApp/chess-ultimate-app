"""
Vercel Domains API client.

Thin wrapper around the four endpoints we need for the custom-domain flow:

  - POST   /v10/projects/{projectId}/domains          → add
  - GET    /v9/projects/{projectId}/domains/{domain}  → status / DNS instructions
  - POST   /v9/projects/{projectId}/domains/{domain}/verify  → trigger verify
  - DELETE /v9/projects/{projectId}/domains/{domain}  → remove

Auth: Bearer `VERCEL_TOKEN`. Optional `VERCEL_TEAM_ID` is forwarded as the
`teamId` query param when present (required for team-scoped projects).

Retry: HTTP 429 honours `Retry-After` (single retry, then propagates).

All public methods raise :class:`VercelAPIError` on non-2xx responses; the
caller is expected to translate that into a Flask response (see
backend/routes/admin.py).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

VERCEL_API_BASE = 'https://api.vercel.com'
DEFAULT_TIMEOUT = 10.0

APEX_DOMAIN = 'chesster.io'


def subdomain_for_slug(slug: str) -> str:
    """Compose the canonical tenant subdomain for a given org slug."""
    return f'{slug}.{APEX_DOMAIN}'


class VercelAPIError(Exception):
    """Raised when the Vercel API returns a non-2xx response."""

    def __init__(self, status_code: int, code: str | None, message: str,
                 payload: dict | None = None) -> None:
        super().__init__(f'Vercel API {status_code} ({code}): {message}')
        self.status_code = status_code
        self.code = code or ''
        self.message = message
        self.payload = payload or {}


class VercelClient:
    """Client for the Vercel Domains API."""

    def __init__(
        self,
        token: str | None = None,
        project_id: str | None = None,
        team_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.token = token or os.getenv('VERCEL_TOKEN', '')
        self.project_id = project_id or os.getenv('VERCEL_PROJECT_ID', '')
        self.team_id = team_id or os.getenv('VERCEL_TEAM_ID', '') or None
        self.timeout = timeout

    # ── public methods ────────────────────────────────────────────────────

    def add_domain(self, domain: str) -> dict[str, Any]:
        """POST /v10/projects/{projectId}/domains  → add a custom domain."""
        path = f'/v10/projects/{self.project_id}/domains'
        return self._request('POST', path, json={'name': domain})

    def get_domain(self, domain: str) -> dict[str, Any]:
        """GET /v9/projects/{projectId}/domains/{domain}  → status."""
        path = f'/v9/projects/{self.project_id}/domains/{domain}'
        return self._request('GET', path)

    def verify_domain(self, domain: str) -> dict[str, Any]:
        """POST /v9/projects/{projectId}/domains/{domain}/verify."""
        path = f'/v9/projects/{self.project_id}/domains/{domain}/verify'
        return self._request('POST', path)

    def remove_domain(self, domain: str) -> dict[str, Any]:
        """DELETE /v9/projects/{projectId}/domains/{domain}."""
        path = f'/v9/projects/{self.project_id}/domains/{domain}'
        return self._request('DELETE', path)

    # ── internal helpers ──────────────────────────────────────────────────

    def _request(self, method: str, path: str, json: dict | None = None) -> dict[str, Any]:
        if not self.token or not self.project_id:
            raise VercelAPIError(
                500, 'misconfigured',
                'Vercel client missing VERCEL_TOKEN or VERCEL_PROJECT_ID',
            )

        url = VERCEL_API_BASE + path
        params: dict[str, str] = {}
        if self.team_id:
            params['teamId'] = self.team_id

        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
        }

        for attempt in (1, 2):  # one retry on 429
            try:
                resp = requests.request(
                    method, url,
                    headers=headers, params=params, json=json,
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                raise VercelAPIError(502, 'network', f'Vercel API request failed: {e}') from e

            if resp.status_code == 429 and attempt == 1:
                wait = _parse_retry_after(resp.headers.get('Retry-After'))
                logger.warning(
                    'Vercel API 429 on %s %s — retrying after %.1fs',
                    method, path, wait,
                )
                time.sleep(wait)
                continue

            if 200 <= resp.status_code < 300:
                # DELETE typically returns 200 + small JSON, but be defensive
                if resp.content:
                    try:
                        return resp.json()
                    except ValueError:
                        return {}
                return {}

            # Non-2xx: extract Vercel's error envelope
            code: str | None = None
            message = resp.text
            payload: dict | None = None
            try:
                body = resp.json()
                payload = body
                err = body.get('error') or {}
                code = err.get('code')
                message = err.get('message') or message
            except ValueError:
                pass
            raise VercelAPIError(resp.status_code, code, message, payload)

        # Unreachable — both attempts either return or raise.
        raise VercelAPIError(502, 'exhausted', 'Vercel API retries exhausted')


def _parse_retry_after(raw: str | None, default: float = 1.0) -> float:
    """Honour Retry-After (seconds form only; HTTP-date form falls back to default)."""
    if not raw:
        return default
    try:
        val = float(raw)
    except ValueError:
        return default
    # Clamp to a sensible upper bound so a hostile header can't block us forever.
    return max(0.0, min(val, 30.0))


# Module-level convenience client for the route handlers. Lazy so unit tests
# can patch envs before first use without re-importing.
_default_client: VercelClient | None = None


def get_client() -> VercelClient:
    global _default_client
    if _default_client is None:
        _default_client = VercelClient()
    return _default_client


def reset_client() -> None:
    """Test hook — discard the cached default client so envs reload."""
    global _default_client
    _default_client = None
