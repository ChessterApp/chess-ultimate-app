"""
Clerk Backend API client.

Thin wrapper around the org + membership endpoints we need for the
Clerk-Organizations wiring (PRD: docs/prd/clerk-orgs-wiring.md, Phase 4 of
the white-label arc).

Endpoints covered:

  - POST   /v1/organizations
  - DELETE /v1/organizations/{id}
  - POST   /v1/organizations/{id}/memberships
  - DELETE /v1/organizations/{id}/memberships/{user_id}
  - PATCH  /v1/organizations/{id}/memberships/{user_id}

Auth: Bearer ``CLERK_SECRET_KEY``.

Timeout: 10 seconds on every call (no retries — caller decides on failure).

All methods raise :class:`ClerkAPIError` on non-2xx responses; 404 on a
delete is treated as a no-op (idempotent remove).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CLERK_API_BASE = 'https://api.clerk.com/v1'
DEFAULT_TIMEOUT = 10.0


class ClerkAPIError(Exception):
    """Raised when the Clerk Backend API returns a non-2xx response."""

    def __init__(self, status_code: int, body: Any = None) -> None:
        super().__init__(f'Clerk API {status_code}: {body!r}')
        self.status_code = status_code
        self.body = body


def map_role_to_clerk(internal_role: str) -> str:
    """Map our internal role enum to one of Clerk's two defaults."""
    return 'admin' if internal_role in ('owner', 'admin') else 'basic_member'


class ClerkClient:
    """Client for the Clerk Backend API (org + membership endpoints)."""

    def __init__(self, secret_key: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.secret_key = secret_key if secret_key is not None else os.getenv('CLERK_SECRET_KEY', '')
        self.timeout = timeout

    # ── organizations ─────────────────────────────────────────────────────

    def create_organization(self, name: str, slug: str, created_by_user_id: str) -> dict:
        """POST /organizations — returns the Clerk org row (incl. ``id``)."""
        return self._request(
            'POST', '/organizations',
            json={
                'name': name,
                'slug': slug,
                'created_by': created_by_user_id,
            },
        )

    def delete_organization(self, clerk_org_id: str) -> None:
        """DELETE /organizations/{id}. 404 is a no-op."""
        self._request('DELETE', f'/organizations/{clerk_org_id}', allow_404=True)

    # ── memberships ───────────────────────────────────────────────────────

    def create_membership(self, clerk_org_id: str, user_id: str, role: str) -> dict:
        """POST /organizations/{id}/memberships."""
        if role not in ('admin', 'basic_member'):
            raise ValueError(f'role must be admin or basic_member, got {role!r}')
        return self._request(
            'POST', f'/organizations/{clerk_org_id}/memberships',
            json={'user_id': user_id, 'role': role},
        )

    def delete_membership(self, clerk_org_id: str, user_id: str) -> None:
        """DELETE /organizations/{id}/memberships/{user_id}. 404 is a no-op."""
        self._request(
            'DELETE',
            f'/organizations/{clerk_org_id}/memberships/{user_id}',
            allow_404=True,
        )

    def update_membership_role(self, clerk_org_id: str, user_id: str, role: str) -> dict:
        """PATCH /organizations/{id}/memberships/{user_id}."""
        if role not in ('admin', 'basic_member'):
            raise ValueError(f'role must be admin or basic_member, got {role!r}')
        return self._request(
            'PATCH',
            f'/organizations/{clerk_org_id}/memberships/{user_id}',
            json={'role': role},
        )

    # ── internal ──────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        allow_404: bool = False,
    ) -> dict:
        if not self.secret_key:
            raise ClerkAPIError(500, 'CLERK_SECRET_KEY not configured')

        url = CLERK_API_BASE + path
        headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
        }
        try:
            resp = httpx.request(
                method, url,
                headers=headers, json=json,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            logger.exception('Clerk API network error: %s %s', method, path)
            raise ClerkAPIError(502, str(exc)) from exc

        if allow_404 and resp.status_code == 404:
            return {}

        if 200 <= resp.status_code < 300:
            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError:
                return {}

        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        raise ClerkAPIError(resp.status_code, body)


# Module-level convenience client for route handlers. Lazy so unit tests can
# patch ``CLERK_SECRET_KEY`` before first use without re-importing.
_default_client: ClerkClient | None = None


def get_client() -> ClerkClient:
    global _default_client
    if _default_client is None:
        _default_client = ClerkClient()
    return _default_client


def reset_client() -> None:
    """Test hook — discard the cached default client so envs reload."""
    global _default_client
    _default_client = None
