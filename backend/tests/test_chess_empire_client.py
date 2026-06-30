"""
Tests for backend/services/chess_empire_client.py.

Mocks httpx at the request boundary; asserts each method hits the right URL,
sends the right auth header, and raises ChessEmpireAPIError on non-2xx.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from services.chess_empire_client import (
    CE_DEFAULT_SUPABASE_URL,
    ChessEmpireAPIError,
    ChessEmpireClient,
)


def _resp(
    status: int,
    body=None,
    content: bytes | None = None,
    headers: dict | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.content = content if content is not None else (b'' if body is None else b'{}')
    resp.json.return_value = body if body is not None else {}
    resp.text = '' if body is None else 'body'
    resp.headers = headers or {}
    return resp


@pytest.fixture
def client():
    return ChessEmpireClient(
        service_key='ce-test-key',
        base_url='https://ce.example.com',
        timeout=1.0,
    )


class TestSearchStudents:
    def test_hits_rest_endpoint_with_filters(self, client):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(200, [{'id': 'stu-1', 'first_name': 'Aiman'}]),
        ) as mock_req:
            result = client.search_students_by_branch('br-1', 'aim', limit=5)
        assert result == [{'id': 'stu-1', 'first_name': 'Aiman'}]
        args, kwargs = mock_req.call_args
        assert args[0] == 'GET'
        url = args[1]
        assert url.startswith('https://ce.example.com/rest/v1/students')
        assert 'branch_id=eq.br-1' in url
        assert 'status=eq.active' in url
        assert 'first_name.ilike.' in url
        assert 'limit=5' in url
        headers = kwargs['headers']
        assert headers['apikey'] == 'ce-test-key'
        assert headers['Authorization'] == 'Bearer ce-test-key'

    def test_omits_or_filter_when_empty_query(self, client):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(200, []),
        ) as mock_req:
            client.search_students_by_branch('br-1', '   ')
        url = mock_req.call_args.args[1]
        assert 'first_name.ilike' not in url

    def test_raises_on_4xx(self, client):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(400, {'message': 'bad'}),
        ):
            with pytest.raises(ChessEmpireAPIError) as exc:
                client.search_students_by_branch('br-1', 'q')
        assert exc.value.status_code == 400

    def test_raises_when_key_missing(self):
        c = ChessEmpireClient(service_key='', base_url='https://x', timeout=1.0)
        with pytest.raises(ChessEmpireAPIError):
            c.search_students_by_branch('br-1', 'q')

    def test_clamps_huge_limit(self, client):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(200, []),
        ) as mock_req:
            client.search_students_by_branch('br-1', 'q', limit=999)
        assert 'limit=50' in mock_req.call_args.args[1]


class TestGetStudentProfile:
    def test_hits_analytics_endpoint(self, client):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(200, {'profile': {'id': 'stu-1', 'status': 'active'}}),
        ) as mock_req:
            profile = client.get_student_profile('stu-1')
        assert profile['id'] == 'stu-1'
        url = mock_req.call_args.args[1]
        assert url.startswith('https://ce.example.com/functions/v1/analytics-students')
        assert 'action=profile' in url
        assert 'student_id=stu-1' in url
        headers = mock_req.call_args.kwargs['headers']
        assert headers['x-api-key'] == 'ce-test-key'

    def test_accepts_flat_profile_response(self, client):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(200, {'id': 'stu-1', 'first_name': 'A'}),
        ):
            profile = client.get_student_profile('stu-1')
        assert profile['id'] == 'stu-1'


class TestGetBranches:
    def test_hits_branches_rest(self, client):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(200, [{'id': 'br-1', 'name': 'Debut'}]),
        ) as mock_req:
            result = client.get_branches()
        assert result[0]['name'] == 'Debut'
        url = mock_req.call_args.args[1]
        assert '/rest/v1/branches' in url
        assert 'order=name.asc' in url


class TestCountActive:
    def test_reads_count_from_content_range(self, client):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(206, [{'id': 'x'}], headers={'content-range': '0-0/262'}),
        ):
            count = client.count_active_students_in_branch('br-1')
        assert count == 262

    def test_falls_back_to_row_length(self, client):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(200, [], headers={'content-range': '0-0/*'}),
        ):
            count = client.count_active_students_in_branch('br-1')
        assert count == 0


class TestNetworkErrors:
    def test_httpx_error_wraps_as_chess_empire_error(self, client):
        import httpx
        with patch(
            'services.chess_empire_client.httpx.request',
            side_effect=httpx.ConnectError('network down'),
        ):
            with pytest.raises(ChessEmpireAPIError) as exc:
                client.get_branches()
        assert exc.value.status_code == 502


class TestDefaultBaseUrl:
    def test_uses_env_var_when_no_override(self, monkeypatch):
        monkeypatch.delenv('CHESS_EMPIRE_SUPABASE_URL', raising=False)
        monkeypatch.setenv('CHESS_EMPIRE_SERVICE_KEY', 'k')
        c = ChessEmpireClient(timeout=1.0)
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(200, []),
        ) as mock_req:
            c.get_branches()
        url = mock_req.call_args.args[1]
        assert url.startswith(f'{CE_DEFAULT_SUPABASE_URL}/rest/v1/branches')
