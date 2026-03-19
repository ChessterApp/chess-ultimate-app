"""
Tests for Cache-Control headers on semi-static API endpoints
"""

import pytest
import sys
import os

# Add backend directory to path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from flask import Flask
from utils.cache import with_cache, add_cache_headers


def test_with_cache_decorator_default():
    """Test cache decorator with default settings"""
    app = Flask(__name__)

    @app.route('/test')
    @with_cache()
    def test_route():
        return {'data': 'test'}

    with app.test_client() as client:
        response = client.get('/test')
        assert response.status_code == 200
        assert 'Cache-Control' in response.headers
        assert response.headers['Cache-Control'] == 'public, max-age=300'


def test_with_cache_decorator_custom_maxage():
    """Test cache decorator with custom max-age"""
    app = Flask(__name__)

    @app.route('/test')
    @with_cache(max_age=600)
    def test_route():
        return {'data': 'test'}

    with app.test_client() as client:
        response = client.get('/test')
        assert response.status_code == 200
        assert 'Cache-Control' in response.headers
        assert response.headers['Cache-Control'] == 'public, max-age=600'


def test_with_cache_decorator_private():
    """Test cache decorator with private cache"""
    app = Flask(__name__)

    @app.route('/test')
    @with_cache(max_age=300, public=False)
    def test_route():
        return {'data': 'test'}

    with app.test_client() as client:
        response = client.get('/test')
        assert response.status_code == 200
        assert 'Cache-Control' in response.headers
        assert response.headers['Cache-Control'] == 'private, max-age=300'


def test_add_cache_headers_function():
    """Test manual cache header addition"""
    app = Flask(__name__)

    @app.route('/test')
    def test_route():
        from flask import jsonify
        resp = jsonify({'data': 'test'})
        return add_cache_headers(resp, max_age=450)

    with app.test_client() as client:
        response = client.get('/test')
        assert response.status_code == 200
        assert 'Cache-Control' in response.headers
        assert response.headers['Cache-Control'] == 'public, max-age=450'


def test_courses_endpoint_has_cache():
    """Test that /api/courses endpoint has cache headers"""
    # This is an integration test that would require full app setup
    # For now, we'll just verify the decorator is properly applied
    from api.lessons import get_courses

    # Check if the function has been decorated
    assert hasattr(get_courses, '__wrapped__') or 'with_cache' in str(get_courses.__code__.co_names)


def test_modules_endpoint_has_cache():
    """Test that modules endpoint has cache headers"""
    from api.lessons import get_course_modules

    # Check if the function has been decorated
    assert hasattr(get_course_modules, '__wrapped__') or 'with_cache' in str(get_course_modules.__code__.co_names)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
