"""
Cache utilities for API responses
"""

from functools import wraps
from flask import make_response


def with_cache(max_age=300, public=True):
    """
    Decorator to add Cache-Control headers to Flask route responses.

    Args:
        max_age: Cache duration in seconds (default: 300 = 5 minutes)
        public: If True, cache can be shared by CDNs/proxies (default: True)

    Usage:
        @app.route('/api/courses')
        @with_cache(max_age=300)
        def get_courses():
            return jsonify(courses)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            response = make_response(f(*args, **kwargs))

            # Build Cache-Control header
            visibility = 'public' if public else 'private'
            response.headers['Cache-Control'] = f'{visibility}, max-age={max_age}'

            return response
        return decorated_function
    return decorator


def add_cache_headers(response, max_age=300, public=True):
    """
    Manually add cache headers to a response object.

    Args:
        response: Flask response object
        max_age: Cache duration in seconds
        public: If True, cache can be shared by CDNs/proxies

    Returns:
        Modified response object

    Usage:
        resp = jsonify(data)
        return add_cache_headers(resp, max_age=300)
    """
    visibility = 'public' if public else 'private'
    response.headers['Cache-Control'] = f'{visibility}, max-age={max_age}'
    return response
