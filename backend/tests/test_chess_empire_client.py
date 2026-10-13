"""
Tests for backend/services/chess_empire_client.py.

Mocks httpx at the request boundary; asserts each method hits the right URL,
sends the right auth header, and raises ChessEmpireAPIError on non-2xx.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import httpx
import pytest

from services.chess_empire_client import (
    CE_DEFAULT_SUPABASE_URL,
    STUDENTS_API_TIMEOUT,
    ChessEmpireAPIError,
    ChessEmpireClient,
    survival_external_ref,
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


class TestStudentsApiSurvival:
    @pytest.fixture
    def writer(self):
        return ChessEmpireClient(
            service_key='ce-test-key',
            base_url='https://ce.example.com',
            write_key='ce-write-key',
        )

    def test_survival_best(self, writer):
        best = {'week': 3, 'month': None, 'all': 9}
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(200, {'ok': True, 'best': best}),
        ) as mock_req:
            assert writer.survival_best('stu-1') == best
        args, kwargs = mock_req.call_args
        assert args == (
            'GET',
            'https://ce.example.com/functions/v1/students-api?action=survival-best&student_id=stu-1',
        )
        assert kwargs['headers']['x-api-key'] == 'ce-write-key'
        assert 'Authorization' not in kwargs['headers']
        assert kwargs['timeout'] == STUDENTS_API_TIMEOUT == 4.0
        assert kwargs['json'] is None

    def test_push_survival_score(self, writer):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(200, {'ok': True, 'id': 'row-1'}),
        ) as mock_req:
            writer.push_survival_score('stu-1', 250, 'run-1', '2026-10-13T10:00:00+00:00')
        args, kwargs = mock_req.call_args
        assert args == ('POST', 'https://ce.example.com/functions/v1/students-api?action=survival-score')
        assert kwargs['json'] == {
            'student_id': 'stu-1',
            'score': 200,  # CE caps survival scores at 200
            'external_ref': 'chesster-rush:run-1',
            'achieved_at': '2026-10-13T10:00:00+00:00',
        }
        assert survival_external_ref('run-1') == 'chesster-rush:run-1'

    def test_survival_leaderboard(self, writer):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(200, {'ok': True, 'rows': []}),
        ) as mock_req:
            writer.survival_leaderboard('branch', 'month', 'br-1', 'stu-1', limit=20)
        url = mock_req.call_args.args[1]
        assert url == (
            'https://ce.example.com/functions/v1/students-api?action=survival-leaderboard'
            '&scope=branch&period=month&limit=20&branch_id=br-1&student_id=stu-1'
        )

    def test_short_timeout_never_exceeds_client_timeout(self):
        c = ChessEmpireClient(base_url='https://ce.example.com', write_key='k', timeout=1.0)
        with patch(
            'services.chess_empire_client.httpx.request', return_value=_resp(200, {'best': {}}),
        ) as mock_req:
            c.survival_best('stu-1')
        assert mock_req.call_args.kwargs['timeout'] == 1.0

    def test_missing_key_disables(self, monkeypatch, caplog):
        monkeypatch.delenv('CHESS_EMPIRE_WRITE_KEY', raising=False)
        monkeypatch.setattr('services.chess_empire_client._write_key_warned', False)
        c = ChessEmpireClient(base_url='https://ce.example.com')
        with caplog.at_level('WARNING'):
            assert c.write_enabled() is False
            assert c.write_enabled() is False
        assert caplog.text.count('CHESS_EMPIRE_WRITE_KEY not configured') == 1
        with patch('services.chess_empire_client.httpx.request') as mock_req:
            with pytest.raises(ChessEmpireAPIError) as exc:
                c.survival_best('stu-1')
        assert exc.value.status_code == 503
        mock_req.assert_not_called()

    def test_key_read_from_env(self, monkeypatch):
        monkeypatch.setenv('CHESS_EMPIRE_WRITE_KEY', 'env-key')
        assert ChessEmpireClient().write_enabled() is True

    def test_non_2xx_and_network_errors_raise(self, writer):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(409, {'ok': False, 'reason': 'student_inactive'}),
        ):
            with pytest.raises(ChessEmpireAPIError) as exc:
                writer.push_survival_score('stu-1', 5, 'run-1')
        assert exc.value.status_code == 409
        with patch(
            'services.chess_empire_client.httpx.request',
            side_effect=httpx.ConnectTimeout('slow'),
        ):
            with pytest.raises(ChessEmpireAPIError) as exc:
                writer.survival_best('stu-1')
        assert exc.value.status_code == 502

    def test_get_students(self, client):
        with patch(
            'services.chess_empire_client.httpx.request',
            return_value=_resp(200, [{'id': 'a'}]),
        ) as mock_req:
            assert client.get_students(['a', 'b']) == [{'id': 'a'}]
        url = mock_req.call_args.args[1]
        assert url.startswith('https://ce.example.com/rest/v1/students?')
        assert 'id=in.%28a%2Cb%29' in url
        assert client.get_students([]) == []
