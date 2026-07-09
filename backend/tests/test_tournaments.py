"""
Tests for Tournament Calendar API and Service.

Tests:
- CRUD operations (create, read, update, cancel)
- Registration (eligibility checks, deadline enforcement, max participants)
- Results upload (CSV parsing, JSON)
- Standings calculation (Buchholz, Sonneborn-Berger tiebreaks)
- Pairings entry
- Finalization
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import patch, MagicMock


USER_ID = 'user_test_123'
ADMIN_USER_ID = 'user_admin_456'
ORG_ID = '00000000-0000-0000-0000-000000000001'
TOURNAMENT_ID = '11111111-1111-1111-1111-111111111111'

SAMPLE_TOURNAMENT = {
    'id': TOURNAMENT_ID,
    'name': 'Spring Open 2026',
    'description': 'Annual open tournament',
    'location': 'Chess Club Almaty',
    'city': 'Almaty',
    'country': 'KZ',
    'start_date': '2026-06-01',
    'end_date': '2026-06-03',
    'registration_deadline': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    'time_control': '90+30',
    'format': 'swiss',
    'max_participants': 50,
    'entry_fee': '0.00',
    'currency': 'KZT',
    'prize_fund': '500000.00',
    'prize_distribution': {'1': 200000, '2': 150000, '3': 100000},
    'age_categories': ['Open'],
    'rating_category': None,
    'min_rating': None,
    'max_rating': None,
    'is_rated': False,
    'tournament_mode': 'offline',
    'organizer_org_id': ORG_ID,
    'created_by': ADMIN_USER_ID,
    'status': 'registration_open',
    'rules_url': None,
    'image_url': None,
    'created_at': '2026-04-01T00:00:00+00:00',
    'updated_at': '2026-04-01T00:00:00+00:00',
}

SAMPLE_REGISTRATION = {
    'id': '22222222-2222-2222-2222-222222222222',
    'tournament_id': TOURNAMENT_ID,
    'user_id': USER_ID,
    'player_name': 'Test Player',
    'rating_at_registration': 1500,
    'age_category': 'Open',
    'payment_status': 'waived',
    'registration_status': 'confirmed',
    'registered_at': '2026-04-15T10:00:00+00:00',
}


class FakeQueryResult:
    """Mimics Supabase query result."""
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


class FakeQueryBuilder:
    """Chainable mock for Supabase table().select()...execute() pattern."""
    def __init__(self, data=None, count=None):
        self._data = data or []
        self._count = count

    def select(self, *args, **kwargs):
        return self

    def insert(self, data, **kwargs):
        if isinstance(data, list):
            self._data = [{**row, 'id': f'new-{i}'} for i, row in enumerate(data)]
        else:
            self._data = [{**data, 'id': 'new-id'}]
        return self

    def update(self, data, **kwargs):
        if self._data:
            self._data = [{**self._data[0], **data}]
        return self

    def delete(self, **kwargs):
        return self

    def upsert(self, data, **kwargs):
        if isinstance(data, list):
            self._data = data
        else:
            self._data = [data]
        return self

    def eq(self, *args, **kwargs):
        return self

    def neq(self, *args, **kwargs):
        return self

    def gte(self, *args, **kwargs):
        return self

    def lte(self, *args, **kwargs):
        return self

    def lt(self, *args, **kwargs):
        return self

    def contains(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def range(self, *args, **kwargs):
        return self

    def single(self):
        return self

    def execute(self):
        return FakeQueryResult(data=self._data, count=self._count)


def _make_fake_table(data=None, count=None):
    """Create a fake supabase.table() that returns a FakeQueryBuilder."""
    def table(name):
        return FakeQueryBuilder(data=data, count=count)
    return table


def _make_multi_table(table_data: dict):
    """Create a fake supabase.table() that returns different data per table name."""
    def table(name):
        data, count = table_data.get(name, ([], None))
        return FakeQueryBuilder(data=data, count=count)
    return table


@pytest.fixture
def app():
    """Create a minimal Flask app with the tournaments blueprint."""
    from flask import Flask
    from routes.tournaments import tournaments_bp

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(tournaments_bp)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    """Provide Authorization header that passes verify_clerk_token."""
    return {'Authorization': 'Bearer fake-jwt-token', 'Content-Type': 'application/json'}


@pytest.fixture(autouse=True)
def mock_jwt():
    """Mock JWT decode to always return our test user."""
    with patch('utils.auth.jwt.decode', return_value={'sub': USER_ID}):
        yield


@pytest.fixture
def mock_jwt_admin():
    """Mock JWT decode to return admin user."""
    return patch('utils.auth.jwt.decode', return_value={'sub': ADMIN_USER_ID})


# ─── LIST TOURNAMENTS ────────────────────────────────────────────────────────


class TestListTournaments:
    def test_list_tournaments_success(self, client):
        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_fake_table(data=[SAMPLE_TOURNAMENT], count=1)
            resp = client.get('/api/tournaments')
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['total'] == 1
            assert body['page'] == 1
            assert len(body['tournaments']) == 1

    def test_list_tournaments_empty(self, client):
        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_fake_table(data=[], count=0)
            resp = client.get('/api/tournaments')
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['total'] == 0
            assert body['tournaments'] == []

    def test_list_tournaments_with_filters(self, client):
        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_fake_table(data=[SAMPLE_TOURNAMENT], count=1)
            resp = client.get('/api/tournaments?city=Almaty&status=registration_open&page=1&per_page=10')
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['per_page'] == 10


# ─── GET TOURNAMENT ──────────────────────────────────────────────────────────


class TestGetTournament:
    def test_get_tournament_success(self, client):
        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_fake_table(data=[SAMPLE_TOURNAMENT])
            resp = client.get(f'/api/tournaments/{TOURNAMENT_ID}')
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['name'] == 'Spring Open 2026'

    def test_get_tournament_not_found(self, client):
        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_fake_table(data=[])
            resp = client.get(f'/api/tournaments/{TOURNAMENT_ID}')
            assert resp.status_code == 404


# ─── CALENDAR VIEW ───────────────────────────────────────────────────────────


class TestCalendarView:
    def test_calendar_returns_tournaments(self, client):
        cal_data = [{
            'id': TOURNAMENT_ID,
            'name': 'Spring Open 2026',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'city': 'Almaty',
            'country': 'KZ',
            'status': 'registration_open',
            'format': 'swiss',
            'entry_fee': '0.00',
            'currency': 'KZT',
        }]
        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_fake_table(data=cal_data)
            resp = client.get('/api/tournaments/calendar?year=2026&month=6')
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['year'] == 2026
            assert body['month'] == 6
            assert len(body['tournaments']) == 1


# ─── CREATE TOURNAMENT ───────────────────────────────────────────────────────


class TestCreateTournament:
    def test_create_tournament_success(self, client, auth_headers, mock_jwt_admin):
        with mock_jwt_admin:
            with patch('services.tournament_service._get_supabase') as mock_sb:
                with patch('routes.tournaments._get_supabase') as mock_route_sb:
                    # Mock org admin check
                    mock_route_sb.return_value.table = _make_fake_table(
                        data=[{'role': 'admin'}]
                    )
                    mock_sb.return_value.table = _make_fake_table(data=[SAMPLE_TOURNAMENT])

                    resp = client.post('/api/tournaments', headers=auth_headers, json={
                        'name': 'Spring Open 2026',
                        'location': 'Chess Club Almaty',
                        'start_date': '2026-06-01',
                        'end_date': '2026-06-03',
                        'registration_deadline': '2026-05-25T23:59:59Z',
                        'time_control': '90+30',
                        'organizer_org_id': ORG_ID,
                    })
                    assert resp.status_code == 201

    def test_create_tournament_missing_fields(self, client, auth_headers):
        resp = client.post('/api/tournaments', headers=auth_headers, json={
            'name': 'Incomplete Tournament',
        })
        assert resp.status_code == 400
        body = resp.get_json()
        assert 'Missing required fields' in body['error']

    def test_create_tournament_no_auth(self, client):
        resp = client.post('/api/tournaments', json={'name': 'Test'})
        assert resp.status_code == 401


# ─── REGISTRATION ────────────────────────────────────────────────────────────


class TestRegistration:
    def test_register_success(self, client, auth_headers):
        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_multi_table({
                'tournaments': ([SAMPLE_TOURNAMENT], None),
                'tournament_registrations': ([SAMPLE_REGISTRATION], 0),
            })
            resp = client.post(
                f'/api/tournaments/{TOURNAMENT_ID}/register',
                headers=auth_headers,
                json={'player_name': 'Test Player', 'rating': 1500},
            )
            assert resp.status_code == 201

    def test_register_missing_player_name(self, client, auth_headers):
        resp = client.post(
            f'/api/tournaments/{TOURNAMENT_ID}/register',
            headers=auth_headers,
            json={'rating': 1500},
        )
        assert resp.status_code == 400
        assert 'player_name is required' in resp.get_json()['error']

    def test_register_deadline_passed(self, client, auth_headers):
        expired_tournament = {
            **SAMPLE_TOURNAMENT,
            'registration_deadline': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        }
        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_fake_table(data=[expired_tournament])
            resp = client.post(
                f'/api/tournaments/{TOURNAMENT_ID}/register',
                headers=auth_headers,
                json={'player_name': 'Late Player'},
            )
            assert resp.status_code == 400
            assert 'deadline' in resp.get_json()['error'].lower()

    def test_register_tournament_full(self, client, auth_headers):
        full_tournament = {**SAMPLE_TOURNAMENT, 'max_participants': 2}
        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_multi_table({
                'tournaments': ([full_tournament], None),
                'tournament_registrations': ([], 2),  # count=2 means full
            })
            resp = client.post(
                f'/api/tournaments/{TOURNAMENT_ID}/register',
                headers=auth_headers,
                json={'player_name': 'Overflow Player'},
            )
            assert resp.status_code == 400
            assert 'full' in resp.get_json()['error'].lower()

    def test_register_rating_below_minimum(self, client, auth_headers):
        rated_tournament = {**SAMPLE_TOURNAMENT, 'min_rating': 1800}
        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_multi_table({
                'tournaments': ([rated_tournament], None),
                'tournament_registrations': ([], 0),
            })
            resp = client.post(
                f'/api/tournaments/{TOURNAMENT_ID}/register',
                headers=auth_headers,
                json={'player_name': 'Low Rated', 'rating': 1200},
            )
            assert resp.status_code == 400
            assert 'below minimum' in resp.get_json()['error'].lower()

    def test_cancel_registration_success(self, client, auth_headers):
        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_fake_table(data=[SAMPLE_TOURNAMENT])
            resp = client.delete(
                f'/api/tournaments/{TOURNAMENT_ID}/register',
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.get_json()['status'] == 'cancelled'

    def test_cancel_registration_after_deadline(self, client, auth_headers):
        expired_tournament = {
            **SAMPLE_TOURNAMENT,
            'registration_deadline': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        }
        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = _make_fake_table(data=[expired_tournament])
            resp = client.delete(
                f'/api/tournaments/{TOURNAMENT_ID}/register',
                headers=auth_headers,
            )
            assert resp.status_code == 400
            assert 'deadline' in resp.get_json()['error'].lower()


# ─── LEAGUE C LEVEL GATE (Chess Empire Level 2+) ─────────────────────────────


class TestLeagueCLevelGate:
    """League C tournaments require the student to be at Chess Empire Level 2+."""

    LEAGUE_C = {**SAMPLE_TOURNAMENT, 'league': 'C'}

    def _tables(self, level=None, linked=True):
        members = [{'external_student_id': 'stu-1'}] if linked else []
        return _make_multi_table({
            'tournaments': ([self.LEAGUE_C], None),
            'tournament_registrations': ([], 0),
            'organization_members': (members, None),
        })

    def _ce_client(self, level):
        client = MagicMock()
        client.get_student_profile.return_value = {'current_level': level}
        return client

    def test_level_1_blocked(self):
        from services.tournament_service import register_player

        with patch('services.tournament_service._get_supabase') as mock_sb, \
             patch('services.tournament_service._get_chess_empire_client',
                   return_value=self._ce_client(1)):
            mock_sb.return_value.table = self._tables()
            record, error = register_player(TOURNAMENT_ID, USER_ID, 'Test Player', rating=1500)

        assert record == {}
        assert isinstance(error, dict)
        assert error['code'] == 'level_too_low'
        assert 'Level 2' in error['message']

    def test_level_2_allowed(self):
        from services.tournament_service import register_player

        with patch('services.tournament_service._get_supabase') as mock_sb, \
             patch('services.tournament_service._get_chess_empire_client',
                   return_value=self._ce_client(2)):
            mock_sb.return_value.table = self._tables()
            record, error = register_player(TOURNAMENT_ID, USER_ID, 'Test Player', rating=1500)

        assert error is None
        assert record.get('player_name') == 'Test Player'

    def test_unlinked_student_allowed(self):
        """No Chess Empire link → level is a school concept we cannot resolve →
        do not block (CE client should never be consulted)."""
        from services.tournament_service import register_player

        ce_client = MagicMock()
        with patch('services.tournament_service._get_supabase') as mock_sb, \
             patch('services.tournament_service._get_chess_empire_client',
                   return_value=ce_client):
            mock_sb.return_value.table = self._tables(linked=False)
            record, error = register_player(TOURNAMENT_ID, USER_ID, 'Unlinked Player')

        assert error is None
        assert record.get('player_name') == 'Unlinked Player'
        ce_client.get_student_profile.assert_not_called()

    def test_no_level_allowed(self):
        """Linked student whose CE profile has no level → do not block."""
        from services.tournament_service import register_player

        client = MagicMock()
        client.get_student_profile.return_value = {'id': 'stu-1'}  # no current_level
        with patch('services.tournament_service._get_supabase') as mock_sb, \
             patch('services.tournament_service._get_chess_empire_client', return_value=client):
            mock_sb.return_value.table = self._tables()
            record, error = register_player(TOURNAMENT_ID, USER_ID, 'No Level Player')

        assert error is None

    def test_non_league_c_ignores_level(self):
        """A Level 1 student registers fine for a non-League-C tournament; the
        Chess Empire client is never consulted."""
        from services.tournament_service import register_player

        ce_client = MagicMock()
        tables = _make_multi_table({
            'tournaments': ([SAMPLE_TOURNAMENT], None),  # league is None
            'tournament_registrations': ([], 0),
            'organization_members': ([{'external_student_id': 'stu-1'}], None),
        })
        with patch('services.tournament_service._get_supabase') as mock_sb, \
             patch('services.tournament_service._get_chess_empire_client',
                   return_value=ce_client):
            mock_sb.return_value.table = tables
            record, error = register_player(TOURNAMENT_ID, USER_ID, 'Test Player')

        assert error is None
        ce_client.get_student_profile.assert_not_called()

    def test_league_b_ignores_level(self):
        from services.tournament_service import register_player

        ce_client = MagicMock()
        league_b = {**SAMPLE_TOURNAMENT, 'league': 'B'}
        tables = _make_multi_table({
            'tournaments': ([league_b], None),
            'tournament_registrations': ([], 0),
            'organization_members': ([{'external_student_id': 'stu-1'}], None),
        })
        with patch('services.tournament_service._get_supabase') as mock_sb, \
             patch('services.tournament_service._get_chess_empire_client',
                   return_value=ce_client):
            mock_sb.return_value.table = tables
            record, error = register_player(TOURNAMENT_ID, USER_ID, 'Test Player')

        assert error is None
        ce_client.get_student_profile.assert_not_called()

    def test_route_exposes_structured_error(self, client, auth_headers):
        """The registration API returns {code, message} for the level gate."""
        with patch('services.tournament_service._get_supabase') as mock_sb, \
             patch('services.tournament_service._get_chess_empire_client',
                   return_value=self._ce_client(1)):
            mock_sb.return_value.table = self._tables()
            resp = client.post(
                f'/api/tournaments/{TOURNAMENT_ID}/register',
                headers=auth_headers,
                json={'player_name': 'Level One'},
            )

        assert resp.status_code == 400
        body = resp.get_json()
        assert body['code'] == 'level_too_low'
        assert 'message' in body

    def test_eligibility_endpoint_reports_block(self, client, auth_headers):
        with patch('services.tournament_service._get_supabase') as mock_sb, \
             patch('services.tournament_service._get_chess_empire_client',
                   return_value=self._ce_client(1)):
            mock_sb.return_value.table = self._tables()
            resp = client.get(
                f'/api/tournaments/{TOURNAMENT_ID}/eligibility',
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body['eligible'] is False
        assert body['code'] == 'level_too_low'
        assert body['league'] == 'C'

    def test_eligibility_endpoint_allows_level_2(self, client, auth_headers):
        with patch('services.tournament_service._get_supabase') as mock_sb, \
             patch('services.tournament_service._get_chess_empire_client',
                   return_value=self._ce_client(2)):
            mock_sb.return_value.table = self._tables()
            resp = client.get(
                f'/api/tournaments/{TOURNAMENT_ID}/eligibility',
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.get_json()['eligible'] is True


class TestLeagueColumnMigration:
    def test_league_check_constraint_present(self):
        import os

        migration_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'supabase', 'migrations',
            '20260709_023_tournament_league.sql',
        )
        with open(migration_path, 'r', encoding='utf-8') as f:
            sql = f.read()

        assert 'ADD COLUMN IF NOT EXISTS league TEXT' in sql
        assert "CHECK (league IN ('C', 'B', 'A', 'Master'))" in sql


# ─── RESULTS UPLOAD ──────────────────────────────────────────────────────────


class TestResultsUpload:
    def test_upload_json_results(self, client, auth_headers, mock_jwt_admin):
        with mock_jwt_admin:
            with patch('routes.tournaments._check_tournament_admin', return_value=True):
                with patch('services.tournament_service._get_supabase') as mock_sb:
                    mock_sb.return_value.table = _make_fake_table(data=[])
                    resp = client.post(
                        f'/api/tournaments/{TOURNAMENT_ID}/results',
                        headers=auth_headers,
                        json={
                            'results': [
                                {
                                    'round': 1,
                                    'board': 1,
                                    'white_player_id': 'player_a',
                                    'black_player_id': 'player_b',
                                    'result': '1-0',
                                },
                            ],
                        },
                    )
                    assert resp.status_code == 200
                    body = resp.get_json()
                    assert body['count'] == 1

    def test_upload_csv_results(self, client, mock_jwt_admin):
        csv_text = "round,board,white_player_id,black_player_id,result\n1,1,player_a,player_b,1-0\n1,2,player_c,player_d,0-1\n"
        with mock_jwt_admin:
            with patch('routes.tournaments._check_tournament_admin', return_value=True):
                with patch('services.tournament_service._get_supabase') as mock_sb:
                    mock_sb.return_value.table = _make_fake_table(data=[])
                    resp = client.post(
                        f'/api/tournaments/{TOURNAMENT_ID}/results',
                        headers={
                            'Authorization': 'Bearer fake-jwt-token',
                            'Content-Type': 'application/json',
                        },
                        json={'csv': csv_text, 'format': 'csv'},
                    )
                    assert resp.status_code == 200
                    body = resp.get_json()
                    assert body['count'] == 2

    def test_upload_invalid_result(self, client, auth_headers, mock_jwt_admin):
        with mock_jwt_admin:
            with patch('routes.tournaments._check_tournament_admin', return_value=True):
                with patch('services.tournament_service._get_supabase') as mock_sb:
                    mock_sb.return_value.table = _make_fake_table(data=[])
                    resp = client.post(
                        f'/api/tournaments/{TOURNAMENT_ID}/results',
                        headers=auth_headers,
                        json={
                            'results': [
                                {
                                    'round': 1,
                                    'board': 1,
                                    'white_player_id': 'player_a',
                                    'black_player_id': 'player_b',
                                    'result': 'invalid',
                                },
                            ],
                        },
                    )
                    assert resp.status_code == 400
                    assert 'Invalid result' in resp.get_json()['error']


# ─── PAIRINGS ────────────────────────────────────────────────────────────────


class TestPairings:
    def test_enter_pairings_success(self, client, auth_headers, mock_jwt_admin):
        with mock_jwt_admin:
            with patch('routes.tournaments._check_tournament_admin', return_value=True):
                with patch('services.tournament_service._get_supabase') as mock_sb:
                    mock_sb.return_value.table = _make_fake_table(data=[])
                    resp = client.post(
                        f'/api/tournaments/{TOURNAMENT_ID}/pairings',
                        headers=auth_headers,
                        json={
                            'round': 1,
                            'pairings': [
                                {'white_player_id': 'p1', 'black_player_id': 'p2', 'board': 1},
                                {'white_player_id': 'p3', 'black_player_id': 'p4', 'board': 2},
                            ],
                        },
                    )
                    assert resp.status_code == 201
                    body = resp.get_json()
                    assert body['count'] == 2

    def test_enter_pairings_missing_round(self, client, auth_headers, mock_jwt_admin):
        with mock_jwt_admin:
            with patch('routes.tournaments._check_tournament_admin', return_value=True):
                resp = client.post(
                    f'/api/tournaments/{TOURNAMENT_ID}/pairings',
                    headers=auth_headers,
                    json={
                        'pairings': [
                            {'white_player_id': 'p1', 'black_player_id': 'p2'},
                        ],
                    },
                )
                assert resp.status_code == 400
                assert 'round is required' in resp.get_json()['error']

    def test_enter_pairings_invalid_pairing(self, client, auth_headers, mock_jwt_admin):
        with mock_jwt_admin:
            with patch('routes.tournaments._check_tournament_admin', return_value=True):
                resp = client.post(
                    f'/api/tournaments/{TOURNAMENT_ID}/pairings',
                    headers=auth_headers,
                    json={
                        'round': 1,
                        'pairings': [
                            {'white_player_id': 'p1'},  # Missing black_player_id
                        ],
                    },
                )
                assert resp.status_code == 400
                assert 'white_player_id and black_player_id' in resp.get_json()['error']


# ─── STANDINGS CALCULATION ───────────────────────────────────────────────────


class TestStandingsCalculation:
    """Test the standings calculation logic directly via the service."""

    def test_calculate_standings_basic(self):
        """Test basic standings with wins/draws/losses."""
        from services.tournament_service import calculate_standings

        games = [
            {'white_player_id': 'p1', 'black_player_id': 'p2', 'result': '1-0', 'tournament_id': TOURNAMENT_ID, 'round': 1, 'board': 1},
            {'white_player_id': 'p3', 'black_player_id': 'p4', 'result': '1/2-1/2', 'tournament_id': TOURNAMENT_ID, 'round': 1, 'board': 2},
            {'white_player_id': 'p1', 'black_player_id': 'p3', 'result': '1-0', 'tournament_id': TOURNAMENT_ID, 'round': 2, 'board': 1},
            {'white_player_id': 'p2', 'black_player_id': 'p4', 'result': '0-1', 'tournament_id': TOURNAMENT_ID, 'round': 2, 'board': 2},
        ]

        with patch('services.tournament_service.get_games', return_value=games):
            standings = calculate_standings(TOURNAMENT_ID)

        assert len(standings) == 4

        # p1 won both games: score=2.0
        p1 = next(s for s in standings if s['user_id'] == 'p1')
        assert p1['score'] == 2.0
        assert p1['wins'] == 2
        assert p1['draws'] == 0
        assert p1['losses'] == 0
        assert p1['rank'] == 1

        # p4 has 1 win + 1 draw: score=1.5
        p4 = next(s for s in standings if s['user_id'] == 'p4')
        assert p4['score'] == 1.5
        assert p4['wins'] == 1
        assert p4['draws'] == 1
        assert p4['rank'] == 2

        # p3 has 0.5 (draw) + 0 (loss): score=0.5
        p3 = next(s for s in standings if s['user_id'] == 'p3')
        assert p3['score'] == 0.5
        assert p3['rank'] == 3

        # p2 lost both: score=0.0
        p2 = next(s for s in standings if s['user_id'] == 'p2')
        assert p2['score'] == 0.0
        assert p2['rank'] == 4

    def test_buchholz_calculation(self):
        """Test Buchholz tiebreak: sum of opponents' scores."""
        from services.tournament_service import calculate_standings

        # Round robin: p1 beats p2, p2 beats p3, p3 beats p1
        games = [
            {'white_player_id': 'p1', 'black_player_id': 'p2', 'result': '1-0', 'tournament_id': TOURNAMENT_ID, 'round': 1, 'board': 1},
            {'white_player_id': 'p2', 'black_player_id': 'p3', 'result': '1-0', 'tournament_id': TOURNAMENT_ID, 'round': 2, 'board': 1},
            {'white_player_id': 'p3', 'black_player_id': 'p1', 'result': '1-0', 'tournament_id': TOURNAMENT_ID, 'round': 3, 'board': 1},
        ]

        with patch('services.tournament_service.get_games', return_value=games):
            standings = calculate_standings(TOURNAMENT_ID)

        # All have score=1.0 (one win each)
        for s in standings:
            assert s['score'] == 1.0

        # Buchholz for each: opponent's score
        # p1 played p2(score=1) and p3(score=1): buchholz=2
        p1 = next(s for s in standings if s['user_id'] == 'p1')
        assert p1['buchholz'] == 2.0

    def test_sonneborn_berger_calculation(self):
        """Test Sonneborn-Berger: score_against_opp * opp_total_score."""
        from services.tournament_service import calculate_standings

        # p1 beats p2 (score=0), draws p3 (score=1.5)
        # p3 beats p2 (score=0), draws p1 (score=1.5)
        # p2 loses to both
        games = [
            {'white_player_id': 'p1', 'black_player_id': 'p2', 'result': '1-0', 'tournament_id': TOURNAMENT_ID, 'round': 1, 'board': 1},
            {'white_player_id': 'p3', 'black_player_id': 'p2', 'result': '1-0', 'tournament_id': TOURNAMENT_ID, 'round': 1, 'board': 2},
            {'white_player_id': 'p1', 'black_player_id': 'p3', 'result': '1/2-1/2', 'tournament_id': TOURNAMENT_ID, 'round': 2, 'board': 1},
        ]

        with patch('services.tournament_service.get_games', return_value=games):
            standings = calculate_standings(TOURNAMENT_ID)

        # p1: beat p2(score=0) → 1*0=0, drew p3(score=1.5) → 0.5*1.5=0.75 → SB=0.75
        p1 = next(s for s in standings if s['user_id'] == 'p1')
        assert p1['sonneborn_berger'] == 0.75

        # p3: beat p2(score=0) → 1*0=0, drew p1(score=1.5) → 0.5*1.5=0.75 → SB=0.75
        p3 = next(s for s in standings if s['user_id'] == 'p3')
        assert p3['sonneborn_berger'] == 0.75

    def test_forfeits_counted(self):
        """Test that forfeits (+/- and -/+) are counted correctly."""
        from services.tournament_service import calculate_standings

        games = [
            {'white_player_id': 'p1', 'black_player_id': 'p2', 'result': '+/-', 'tournament_id': TOURNAMENT_ID, 'round': 1, 'board': 1},
            {'white_player_id': 'p3', 'black_player_id': 'p4', 'result': '-/+', 'tournament_id': TOURNAMENT_ID, 'round': 1, 'board': 2},
        ]

        with patch('services.tournament_service.get_games', return_value=games):
            standings = calculate_standings(TOURNAMENT_ID)

        p1 = next(s for s in standings if s['user_id'] == 'p1')
        assert p1['score'] == 1.0
        assert p1['wins'] == 1

        p4 = next(s for s in standings if s['user_id'] == 'p4')
        assert p4['score'] == 1.0
        assert p4['wins'] == 1

    def test_unplayed_games_ignored(self):
        """Games with result '*' should be ignored."""
        from services.tournament_service import calculate_standings

        games = [
            {'white_player_id': 'p1', 'black_player_id': 'p2', 'result': '1-0', 'tournament_id': TOURNAMENT_ID, 'round': 1, 'board': 1},
            {'white_player_id': 'p3', 'black_player_id': 'p4', 'result': '*', 'tournament_id': TOURNAMENT_ID, 'round': 1, 'board': 2},
        ]

        with patch('services.tournament_service.get_games', return_value=games):
            standings = calculate_standings(TOURNAMENT_ID)

        # Only p1 and p2 should appear (p3 and p4 have no results)
        assert len(standings) == 2


# ─── CSV PARSING ─────────────────────────────────────────────────────────────


class TestCSVParsing:
    def test_parse_valid_csv(self):
        from services.tournament_service import _parse_csv_results

        csv_text = "round,board,white_player_id,black_player_id,result\n1,1,player_a,player_b,1-0\n1,2,player_c,player_d,1/2-1/2\n"
        games, error = _parse_csv_results(csv_text, TOURNAMENT_ID)

        assert error is None
        assert len(games) == 2
        assert games[0]['round'] == 1
        assert games[0]['board'] == 1
        assert games[0]['white_player_id'] == 'player_a'
        assert games[0]['result'] == '1-0'
        assert games[1]['result'] == '1/2-1/2'

    def test_parse_csv_missing_fields_skipped(self):
        from services.tournament_service import _parse_csv_results

        csv_text = "round,board,white_player_id,black_player_id,result\n1,1,player_a,player_b,1-0\n,,,,\n"
        games, error = _parse_csv_results(csv_text, TOURNAMENT_ID)

        assert error is None
        assert len(games) == 1

    def test_parse_csv_whitespace_stripped(self):
        from services.tournament_service import _parse_csv_results

        csv_text = "round,board,white_player_id,black_player_id,result\n1,1, player_a , player_b , 1-0 \n"
        games, error = _parse_csv_results(csv_text, TOURNAMENT_ID)

        assert error is None
        assert games[0]['white_player_id'] == 'player_a'
        assert games[0]['black_player_id'] == 'player_b'
        assert games[0]['result'] == '1-0'


# ─── FINALIZE ────────────────────────────────────────────────────────────────


class TestFinalize:
    def test_finalize_success(self, client, auth_headers, mock_jwt_admin):
        games = [
            {'white_player_id': 'p1', 'black_player_id': 'p2', 'result': '1-0', 'tournament_id': TOURNAMENT_ID, 'round': 1, 'board': 1},
        ]
        with mock_jwt_admin:
            with patch('routes.tournaments._check_tournament_admin', return_value=True):
                with patch('services.tournament_service._get_supabase') as mock_sb:
                    mock_sb.return_value.table = _make_multi_table({
                        'tournaments': ([SAMPLE_TOURNAMENT], None),
                        'tournament_games': (games, None),
                        'tournament_standings': ([], None),
                    })
                    resp = client.post(
                        f'/api/tournaments/{TOURNAMENT_ID}/finalize',
                        headers=auth_headers,
                    )
                    assert resp.status_code == 200
                    body = resp.get_json()
                    assert body['status'] == 'finalized'

    def test_finalize_already_completed(self, client, auth_headers, mock_jwt_admin):
        completed_tournament = {**SAMPLE_TOURNAMENT, 'status': 'completed'}
        with mock_jwt_admin:
            with patch('routes.tournaments._check_tournament_admin', return_value=True):
                with patch('services.tournament_service._get_supabase') as mock_sb:
                    mock_sb.return_value.table = _make_fake_table(data=[completed_tournament])
                    resp = client.post(
                        f'/api/tournaments/{TOURNAMENT_ID}/finalize',
                        headers=auth_headers,
                    )
                    assert resp.status_code == 400
                    assert 'already finalized' in resp.get_json()['error'].lower()


# ─── TOURNAMENT MODE (offline default + DB validation) ───────────────────────


class TestTournamentMode:
    def test_tournament_default_mode_offline(self):
        """Newly created tournaments default to tournament_mode='offline'."""
        from services.tournament_service import create_tournament

        captured = {}

        class CaptureBuilder(FakeQueryBuilder):
            def insert(self, data, **kwargs):
                captured['record'] = data
                return super().insert(data, **kwargs)

        def table(name):
            return CaptureBuilder(data=[SAMPLE_TOURNAMENT])

        with patch('services.tournament_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = table
            create_tournament(
                {
                    'name': 'Default Mode Tournament',
                    'location': 'Almaty',
                    'start_date': '2026-06-01',
                    'end_date': '2026-06-03',
                    'registration_deadline': '2026-05-25T23:59:59Z',
                    'time_control': '90+30',
                },
                user_id=ADMIN_USER_ID,
            )

        assert captured['record']['tournament_mode'] == 'offline'

    def test_tournament_mode_validation(self):
        """The migration declares a CHECK constraint that rejects invalid modes
        (e.g. 'live'). Validate the constraint is present in the migration SQL."""
        import os

        migration_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'supabase', 'migrations',
            '20260506_007_local_app_rating.sql',
        )
        with open(migration_path, 'r', encoding='utf-8') as f:
            sql = f.read()

        assert "tournament_mode TEXT NOT NULL DEFAULT 'offline'" in sql
        assert "CHECK (tournament_mode IN ('offline', 'online'))" in sql
        # 'live' is not in the allowed set, so an INSERT with 'live' would
        # raise a DB-level CheckViolation under Postgres.
        assert "'live'" not in sql
