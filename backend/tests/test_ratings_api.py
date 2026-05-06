"""
Tests for the Ratings API blueprint.

Uses Flask test client with mocked Supabase.
"""

import json
import sys
import os

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class MockQueryBuilder:
    """Minimal mock for Supabase query chaining."""

    def __init__(self, data=None):
        self._data = data or []

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def neq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def insert(self, data):
        return self

    def update(self, data):
        return self

    def upsert(self, data, **kwargs):
        return self

    def execute(self):
        result = MagicMock()
        result.data = self._data
        return result


def _make_mock_supabase(table_data=None):
    """Create a mock supabase client that returns configured data per table."""
    table_data = table_data or {}
    mock = MagicMock()

    def table_fn(name):
        data = table_data.get(name, [])
        return MockQueryBuilder(data)

    mock.table = table_fn
    return mock


@pytest.fixture
def app():
    """Create Flask app with ratings blueprint."""
    from flask import Flask
    from routes.ratings import ratings_bp

    app = Flask(__name__)
    app.register_blueprint(ratings_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestGetLeaderboard:
    def test_leaderboard_returns_sorted(self, client):
        """GET /api/ratings/leaderboard returns data sorted by rating desc."""
        mock_data = [
            {'user_id': 'u1', 'rating': 2100, 'is_provisional': False, 'league': 'A'},
            {'user_id': 'u2', 'rating': 1900, 'is_provisional': False, 'league': 'A'},
            {'user_id': 'u3', 'rating': 1500, 'is_provisional': False, 'league': 'B'},
        ]
        mock_sb = _make_mock_supabase({'player_ratings': mock_data})

        with patch('routes.ratings._get_supabase', return_value=mock_sb):
            resp = client.get('/api/ratings/leaderboard')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'leaderboard' in data
            assert len(data['leaderboard']) == 3
            # First entry should be highest rated
            assert data['leaderboard'][0]['rating'] == 2100

    def test_leaderboard_empty(self, client):
        """GET /api/ratings/leaderboard with no data returns empty list."""
        mock_sb = _make_mock_supabase({'player_ratings': []})

        with patch('routes.ratings._get_supabase', return_value=mock_sb):
            resp = client.get('/api/ratings/leaderboard')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['leaderboard'] == []


class TestGetRatingHistory:
    def test_history_returns_chronological(self, client):
        """GET /api/ratings/<userId>/history returns entries."""
        mock_data = [
            {'user_id': 'u1', 'rating_before': 1200, 'rating_after': 1220, 'calculated_at': '2026-01-01T00:00:00'},
            {'user_id': 'u1', 'rating_before': 1220, 'rating_after': 1250, 'calculated_at': '2026-01-02T00:00:00'},
        ]
        mock_sb = _make_mock_supabase({'rating_history': mock_data})

        with patch('routes.ratings._get_supabase', return_value=mock_sb):
            resp = client.get('/api/ratings/u1/history')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'history' in data
            assert len(data['history']) == 2

    def test_history_empty(self, client):
        """GET /api/ratings/<userId>/history returns empty for unknown user."""
        mock_sb = _make_mock_supabase({'rating_history': []})

        with patch('routes.ratings._get_supabase', return_value=mock_sb):
            resp = client.get('/api/ratings/unknown_user/history')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['history'] == []


class TestGetPlayerRating:
    def test_player_found(self, client):
        """GET /api/ratings/<userId> returns the local rating only."""
        mock_sb = _make_mock_supabase({
            'player_ratings': [{'user_id': 'u1', 'rating': 1500, 'league': 'B'}],
        })

        with patch('routes.ratings._get_supabase', return_value=mock_sb):
            resp = client.get('/api/ratings/u1')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['rating']['rating'] == 1500

    def test_player_not_found(self, client):
        """GET /api/ratings/<userId> returns 404 for unknown player."""
        mock_sb = _make_mock_supabase({'player_ratings': []})

        with patch('routes.ratings._get_supabase', return_value=mock_sb):
            resp = client.get('/api/ratings/nonexistent')
            assert resp.status_code == 404

    def test_get_player_rating_no_fide_key(self, client):
        """GET /api/ratings/<userId> response has no 'fide' key."""
        mock_sb = _make_mock_supabase({
            'player_ratings': [{'user_id': 'u1', 'rating': 1500, 'league': 'B'}],
        })

        with patch('routes.ratings._get_supabase', return_value=mock_sb):
            resp = client.get('/api/ratings/u1')
            assert resp.status_code == 200
            data = resp.get_json()
            assert set(data.keys()) == {'rating'}
            assert 'fide' not in data


class TestGetProvisional:
    def test_provisional_list(self, client):
        """GET /api/ratings/provisional returns provisional players."""
        mock_data = [
            {'user_id': 'u1', 'rating': 1300, 'is_provisional': True, 'games_played': 5},
            {'user_id': 'u2', 'rating': 1100, 'is_provisional': True, 'games_played': 10},
        ]
        mock_sb = _make_mock_supabase({'player_ratings': mock_data})

        with patch('routes.ratings._get_supabase', return_value=mock_sb):
            resp = client.get('/api/ratings/provisional')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'provisional' in data
            assert len(data['provisional']) == 2


class TestNoFideRoute:
    """The /fide/link endpoint must no longer exist."""

    def test_fide_link_route_removed(self, client):
        """POST /api/ratings/fide/link/<userId> returns 404 — endpoint deleted."""
        resp = client.post(
            '/api/ratings/fide/link/u1',
            data=json.dumps({'fide_id': '123456'}),
            content_type='application/json',
        )
        assert resp.status_code == 404
