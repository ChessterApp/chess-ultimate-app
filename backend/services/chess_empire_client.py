"""
Chess Empire API client (Python).

Phase 1 of the Chess Empire → Chesster onboarding arc. Mirror of the
TypeScript client at ``frontend/src/lib/chess-empire-client.ts``. Used by:

  - the Clerk-webhook completion path (Phase 2/3) — needs ``getStudentProfile``
    to read DOB/branch when verifying a stored invite JWT
  - the nightly lifecycle cron (Phase 5) — needs ``getStudentProfile`` for
    each tracked student to mirror CE ``status`` → Chesster ``link_status``
  - the admin panel (Phase 4) — needs ``getBranches`` for token rotation UI

Style matches ``services/clerk_client.py``: 10s timeout, no retries, raises
``ChessEmpireAPIError`` on non-2xx. Env var ``CHESS_EMPIRE_SERVICE_KEY`` is
read on each method call so test patches don't require module reimport.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote, urlencode

import httpx

logger = logging.getLogger(__name__)

CE_DEFAULT_SUPABASE_URL = 'https://papgcizhfkngubwofjuo.supabase.co'
DEFAULT_TIMEOUT = 10.0
DEFAULT_SEARCH_LIMIT = 20


class ChessEmpireAPIError(Exception):
    """Raised when the Chess Empire API returns a non-2xx response."""

    def __init__(self, status_code: int, body: Any = None) -> None:
        super().__init__(f'Chess Empire API {status_code}: {body!r}')
        self.status_code = status_code
        self.body = body


class ChessEmpireClient:
    """Client for the Chess Empire Supabase REST + Edge Functions."""

    def __init__(
        self,
        service_key: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._service_key_override = service_key
        self._base_url_override = base_url
        self.timeout = timeout

    # ── public methods ────────────────────────────────────────────────────

    def search_students_by_branch(
        self,
        branch_id: str,
        query: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[dict]:
        """Active students in a branch matching first OR last name ILIKE."""
        safe_limit = max(1, min(limit, 50))
        params: list[tuple[str, str]] = [
            ('branch_id', f'eq.{branch_id}'),
            ('status', 'eq.active'),
            ('select', 'id,first_name,last_name,branch_id,status,date_of_birth,coach_id,photo_url'),
            ('limit', str(safe_limit)),
            ('order', 'first_name.asc'),
        ]
        trimmed = (query or '').strip()
        # Strip PostgREST-meaningful characters before interpolating into `or=()`.
        cleaned = ''.join(ch if ch not in ',()*' else ' ' for ch in trimmed).strip()
        if cleaned:
            params.append(
                ('or', f'(first_name.ilike.*{cleaned}*,last_name.ilike.*{cleaned}*)')
            )
        url = f'{self._rest_base()}/students?{urlencode(params)}'
        return self._request_json('GET', url, rest=True)

    def get_student_profile(self, student_id: str) -> dict:
        """Single-student profile by id. Returns the unwrapped profile dict."""
        url = (
            f'{self._functions_base()}/analytics-students'
            f'?action=profile&student_id={quote(student_id, safe="")}'
        )
        body = self._request_json('GET', url, rest=False)
        if isinstance(body, dict) and 'profile' in body and body['profile']:
            return body['profile']
        return body

    def get_branches(self) -> list[dict]:
        """All branches in CE Supabase. Used by the generator script."""
        params = urlencode([('select', 'id,name,address'), ('order', 'name.asc')])
        url = f'{self._rest_base()}/branches?{params}'
        return self._request_json('GET', url, rest=True)

    def count_active_students_in_branch(self, branch_id: str) -> int:
        """Count active students in a branch via PostgREST exact count."""
        params = urlencode([
            ('branch_id', f'eq.{branch_id}'),
            ('status', 'eq.active'),
            ('select', 'id'),
        ])
        url = f'{self._rest_base()}/students?{params}'
        headers = self._rest_headers()
        headers['Prefer'] = 'count=exact'
        headers['Range'] = '0-0'
        try:
            resp = httpx.request('GET', url, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as exc:
            logger.exception('Chess Empire API network error: count_active')
            raise ChessEmpireAPIError(502, str(exc)) from exc

        if not (200 <= resp.status_code < 300):
            body: Any
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            raise ChessEmpireAPIError(resp.status_code, body)

        content_range = resp.headers.get('content-range', '')
        if '/' in content_range:
            total = content_range.rsplit('/', 1)[-1]
            if total.isdigit():
                return int(total)
        # Fallback: count returned rows when the server omits content-range.
        try:
            body = resp.json()
            return len(body) if isinstance(body, list) else 0
        except ValueError:
            return 0

    # ── internal ──────────────────────────────────────────────────────────

    def _service_key(self) -> str:
        key = (
            self._service_key_override
            if self._service_key_override is not None
            else os.getenv('CHESS_EMPIRE_SERVICE_KEY', '')
        )
        if not key:
            raise ChessEmpireAPIError(500, 'CHESS_EMPIRE_SERVICE_KEY not configured')
        return key

    def _base_url(self) -> str:
        return (
            self._base_url_override
            if self._base_url_override is not None
            else os.getenv('CHESS_EMPIRE_SUPABASE_URL', CE_DEFAULT_SUPABASE_URL)
        )

    def _rest_base(self) -> str:
        return f'{self._base_url()}/rest/v1'

    def _functions_base(self) -> str:
        return f'{self._base_url()}/functions/v1'

    def _rest_headers(self) -> dict:
        key = self._service_key()
        return {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Accept': 'application/json',
        }

    def _functions_headers(self) -> dict:
        return {'x-api-key': self._service_key(), 'Accept': 'application/json'}

    def _request_json(self, method: str, url: str, rest: bool) -> Any:
        headers = self._rest_headers() if rest else self._functions_headers()
        try:
            resp = httpx.request(method, url, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as exc:
            logger.exception('Chess Empire API network error: %s %s', method, url)
            raise ChessEmpireAPIError(502, str(exc)) from exc

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
        raise ChessEmpireAPIError(resp.status_code, body)


_default_client: ChessEmpireClient | None = None


def get_client() -> ChessEmpireClient:
    global _default_client
    if _default_client is None:
        _default_client = ChessEmpireClient()
    return _default_client


def reset_client() -> None:
    """Test hook — discard the cached default client so envs reload."""
    global _default_client
    _default_client = None
