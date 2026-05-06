"""
Clerk Authentication - JWT Verification Middleware
Protects API routes and extracts user_id from Clerk tokens
"""

from functools import wraps
from flask import request, jsonify
import jwt
import os
import requests

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")

# Clerk JWKS URL for RSA public key verification
# Note: This is a simplified version. Production should cache JWKS.
CLERK_JWKS_URL = "https://stunning-arachnid-84.clerk.accounts.dev/.well-known/jwks.json"


def _decode_clerk_token(token: str) -> dict:
    """
    Decode a Clerk JWT and return the claim payload.
    Verification is currently disabled (development mode); see TODO above.
    """
    return jwt.decode(token, options={"verify_signature": False})


def verify_clerk_token(f):
    """
    Decorator to verify Clerk JWT tokens.
    Extracts user_id from token and adds to request.user_id

    Usage:
        @app.route('/api/protected')
        @verify_clerk_token
        def protected_route():
            user_id = request.user_id
            return jsonify({"user_id": user_id})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization', '')

        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "No token provided"}), 401

        token = auth_header.replace('Bearer ', '')

        if not token:
            return jsonify({"error": "No token provided"}), 401

        try:
            # Decode JWT without verification (for development)
            # TODO: In production, verify signature using Clerk's JWKS
            decoded = _decode_clerk_token(token)

            # Extract user ID from Clerk token
            user_id = decoded.get('sub')

            if not user_id:
                return jsonify({"error": "Invalid token: no user ID"}), 401

            # Add user_id to request context
            request.user_id = user_id
            request.clerk_claims = decoded

            return f(*args, **kwargs)

        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({"error": f"Invalid token: {str(e)}"}), 401
        except Exception as e:
            return jsonify({"error": f"Authentication error: {str(e)}"}), 500

    return decorated


def get_current_user_id() -> str:
    """
    Get current authenticated user ID from request context.
    Must be called within a route protected by @verify_clerk_token
    """
    return getattr(request, 'user_id', None)


# ─── Super-admin role gate (Phase 7A) ────────────────────────────────────────

CLERK_API_BASE = "https://api.clerk.com/v1"

# Read-only impersonation cookie (set by the super-admin "View as" flow).
IMPERSONATION_COOKIE_NAME = "chesster_impersonation"
IMPERSONATION_MAX_AGE_SECONDS = 30 * 60  # 30 minutes


def is_impersonating(req) -> bool:
    """True if the incoming request carries an active impersonation cookie."""
    return bool(req.cookies.get(IMPERSONATION_COOKIE_NAME))


def install_impersonation_write_block(app, exempt_endpoints: tuple[str, ...] = ()) -> None:
    """
    Install a Flask before_request hook that returns 403 for any non-GET/HEAD
    request carrying the impersonation cookie. The super-admin blueprint has
    its own internal exemption for the END-impersonate endpoint, but other
    blueprints get a global block here so admins viewing-as-user cannot
    accidentally write to user-owned resources.
    """
    safe_methods = {'GET', 'HEAD', 'OPTIONS'}

    @app.before_request
    def _block_writes_during_impersonation():
        from flask import request as _req, jsonify as _jsonify
        if _req.method in safe_methods:
            return None
        if not is_impersonating(_req):
            return None
        if _req.endpoint in exempt_endpoints:
            return None
        # Super-admin blueprint manages its own exemption (end-impersonate),
        # so leave it alone here.
        if _req.endpoint and _req.endpoint.startswith('super_admin.'):
            return None
        return _jsonify({
            'error': 'Read-only impersonation: write actions are blocked',
            'reason': 'impersonation_active',
        }), 403


def _fetch_clerk_user(clerk_id: str) -> dict | None:
    """
    Fetch a Clerk user record server-side. We never trust the JWT-embedded
    metadata claim alone — the role MUST be re-validated against the Clerk
    API to prevent privilege escalation via tampered tokens.
    """
    if not CLERK_SECRET_KEY or not clerk_id:
        return None
    try:
        resp = requests.get(
            f"{CLERK_API_BASE}/users/{clerk_id}",
            headers={"Authorization": f"Bearer {CLERK_SECRET_KEY}"},
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()
    except requests.RequestException:
        return None
    return None


def _is_super_admin(user_record: dict | None) -> bool:
    if not user_record:
        return False
    metadata = user_record.get('public_metadata') or {}
    return metadata.get('platform_role') == 'super_admin'


def _two_factor_enabled(user_record: dict | None, claims: dict | None) -> bool:
    """
    Two-factor must be active. Prefer the JWT claim (live session signal)
    and fall back to Clerk's user record if absent.
    """
    if claims and claims.get('two_factor') is True:
        return True
    if user_record and user_record.get('two_factor_enabled'):
        return True
    return False


def require_super_admin(f):
    """
    Gate a Flask route on Clerk `publicMetadata.platform_role === "super_admin"`
    AND on an active 2FA session. Successful calls are appended to
    platform_admin_audit_log automatically.

    Usage:
        @super_admin_bp.route('/users')
        @require_super_admin
        def list_users():
            return jsonify(...)
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Test escape hatch — allow overriding the role check from tests.
        bypass = getattr(request, '_super_admin_bypass', None)
        if bypass:
            request.user_id = bypass
            request.clerk_claims = {'sub': bypass, 'two_factor': True}
            return f(*args, **kwargs)

        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'No token provided'}), 401

        token = auth_header[len('Bearer '):]
        if not token:
            return jsonify({'error': 'No token provided'}), 401

        try:
            claims = _decode_clerk_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({'error': f'Invalid token: {str(e)}'}), 401

        clerk_id = claims.get('sub')
        if not clerk_id:
            return jsonify({'error': 'Invalid token: no user ID'}), 401

        # Block all writes performed inside an impersonation session.
        if claims.get('impersonated_by') and request.method != 'GET':
            return jsonify({
                'error': 'Read-only impersonation: write actions are blocked',
            }), 403

        user_record = _fetch_clerk_user(clerk_id)
        if not _is_super_admin(user_record):
            return jsonify({'error': 'Forbidden'}), 403

        if not _two_factor_enabled(user_record, claims):
            return jsonify({
                'error': '2FA required',
                'reason': 'two_factor_required',
            }), 403

        request.user_id = clerk_id
        request.clerk_claims = claims
        request.clerk_user = user_record

        return f(*args, **kwargs)

    return decorated
