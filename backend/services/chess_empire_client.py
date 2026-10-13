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
# students-api (Puzzle Rush school ranking) sits on the run-finish path: keep it short.
STUDENTS_API_TIMEOUT = 4.0
SURVIVAL_SCORE_MAX = 200

_write_key_warned = False


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
        write_key: str | None = None,
    ) -> None:
        self._service_key_override = service_key
        self._write_key_override = write_key
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

    def get_students(self, student_ids: list[str]) -> list[dict]:
        """Names + branch for a handful of students (one REST call)."""
        if not student_ids:
            return []
        params = urlencode([
            ('id', f'in.({",".join(student_ids)})'),
            ('select', 'id,first_name,last_name,branch_id'),
        ])
        url = f'{self._rest_base()}/students?{params}'
        return self._request_json('GET', url, rest=True)

    # ── students-api: Puzzle Rush survival (CHESS_EMPIRE_WRITE_KEY) ───────

    def write_enabled(self) -> bool:
        """False when CHESS_EMPIRE_WRITE_KEY is unset (school ranking is off)."""
        global _write_key_warned
        if self._write_key():
            return True
        if not _write_key_warned:
            logger.warning('CHESS_EMPIRE_WRITE_KEY not configured: Puzzle Rush school ranking disabled')
            _write_key_warned = True
        return False

    def survival_best(self, student_id: str) -> dict:
        """The student's CE survival bests: ``{week, month, all}`` (None when none)."""
        body = self._students_api('GET', 'survival-best', params={'student_id': student_id})
        best = body.get('best') if isinstance(body, dict) else None
        return best if isinstance(best, dict) else {}

    def push_survival_score(
        self, student_id: str, score: int, run_id: str, achieved_at: str | None = None,
    ) -> dict:
        """Push one survival run. Idempotent on the run id (``external_ref``)."""
        payload: dict[str, Any] = {
            'student_id': student_id,
            'score': max(0, min(int(score), SURVIVAL_SCORE_MAX)),
            'external_ref': survival_external_ref(run_id),
        }
        if achieved_at:
            payload['achieved_at'] = achieved_at
        return self._students_api('POST', 'survival-score', json=payload)

    def survival_leaderboard(
        self,
        scope: str,
        period: str,
        branch_id: str | None = None,
        student_id: str | None = None,
        limit: int = 50,
    ) -> dict:
        params = {'scope': scope, 'period': period, 'limit': str(max(1, min(limit, 500)))}
        if branch_id:
            params['branch_id'] = branch_id
        if student_id:
            params['student_id'] = student_id
        return self._students_api('GET', 'survival-leaderboard', params=params)

    # ── internal ──────────────────────────────────────────────────────────

    def _write_key(self) -> str:
        if self._write_key_override is not None:
            return self._write_key_override
        return os.getenv('CHESS_EMPIRE_WRITE_KEY', '')

    def _students_api(
        self, method: str, action: str, params: dict | None = None, json: dict | None = None,
    ) -> Any:
        key = self._write_key()
        if not key:
            raise ChessEmpireAPIError(503, 'CHESS_EMPIRE_WRITE_KEY not configured')
        query = urlencode([('action', action), *(params or {}).items()])
        url = f'{self._functions_base()}/students-api?{query}'
        headers = {'x-api-key': key, 'Accept': 'application/json'}
        try:
            resp = httpx.request(method, url, headers=headers, json=json,
                                 timeout=min(self.timeout, STUDENTS_API_TIMEOUT))
        except httpx.HTTPError as exc:
            logger.warning('Chess Empire students-api network error: %s %s: %s', method, action, exc)
            raise ChessEmpireAPIError(502, str(exc)) from exc
        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = resp.text
        if not (200 <= resp.status_code < 300):
            raise ChessEmpireAPIError(resp.status_code, body)
        return body if isinstance(body, dict) else {}


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
        key = self._service_key()
        return {
            'Authorization': f'Bearer {key}',
            'x-api-key': key,
            'Accept': 'application/json',
        }

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


def survival_external_ref(run_id: str) -> str:
    """CE ``external_ref`` for a Chesster run — the same on every retry."""
    return f'chesster-rush:{run_id}'


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
