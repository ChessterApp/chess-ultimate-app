"""
Tests for repertoire blueprint registration in app.py.

Verifies the /api/repertoire routes are registered and reachable.
Uses Flask test client with mocked auth and service dependencies.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

USER_ID = 'user_test_123'


@pytest.fixture
def app():
    """Create a minimal Flask app with the repertoire blueprint."""
    from flask import Flask
    from api.repertoire import repertoire_bp

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(repertoire_bp)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {'Authorization': 'Bearer fake-jwt-token', 'Content-Type': 'application/json'}


@pytest.fixture(autouse=True)
def mock_jwt():
    with patch('utils.auth.jwt.decode', return_value={'sub': USER_ID}):
        yield


class TestRepertoireBlueprintRegistered:
    """Verify the repertoire blueprint routes exist and respond."""

    def test_routes_registered(self, app):
        """All expected repertoire routes are registered in the app."""
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert '/api/repertoire' in rules
        assert '/api/repertoire/<opening_id>' in rules
        assert '/api/repertoire/<repertoire_id>/variations' in rules

    def test_get_repertoire_returns_200(self, client, auth_headers):
        """GET /api/repertoire responds (not 404)."""
        mock_service = MagicMock()
        mock_service.get_user_repertoire.return_value = []
        with patch('api.repertoire.get_repertoire_service', return_value=mock_service):
            resp = client.get('/api/repertoire', headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_get_repertoire_no_auth_returns_401(self, client):
        """GET /api/repertoire without auth returns 401."""
        resp = client.get('/api/repertoire')
        assert resp.status_code == 401

    def test_post_repertoire_missing_fields_returns_400(self, client, auth_headers):
        """POST /api/repertoire with empty body returns 400."""
        mock_service = MagicMock()
        with patch('api.repertoire.get_repertoire_service', return_value=mock_service):
            resp = client.post('/api/repertoire',
                               data='{}',
                               headers=auth_headers)
        assert resp.status_code == 400

    def test_delete_repertoire_responds(self, client, auth_headers):
        """DELETE /api/repertoire/<id> responds (not 404 routing error)."""
        mock_service = MagicMock()
        with patch('api.repertoire.get_repertoire_service', return_value=mock_service):
            resp = client.delete('/api/repertoire/some-opening-id', headers=auth_headers)
        assert resp.status_code == 200

    def test_get_variations_responds(self, client, auth_headers):
        """GET /api/repertoire/<id>/variations responds."""
        mock_service = MagicMock()
        mock_service.get_variations.return_value = []
        with patch('api.repertoire.get_repertoire_service', return_value=mock_service):
            resp = client.get('/api/repertoire/some-id/variations', headers=auth_headers)
        assert resp.status_code == 200


class TestRepertoireInMainApp:
    """Verify the blueprint is registered in the actual app module."""

    def test_repertoire_bp_registered_in_app(self):
        """The repertoire_bp is among the registered blueprints in app.py.

        Instead of importing the full app.py (which has heavy import-time
        side effects), we verify by reading the source file.
        """
        app_path = os.path.join(backend_dir, 'app.py')
        with open(app_path) as f:
            source = f.read()

        assert 'from api.repertoire import repertoire_bp' in source, \
            "app.py should import repertoire_bp"
        assert 'app.register_blueprint(repertoire_bp)' in source, \
            "app.py should register repertoire_bp"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
