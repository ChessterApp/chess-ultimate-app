"""
Invite-flow JWT (HS256, Python mirror).

Phase 1 of the Chess Empire → Chesster onboarding arc. Mirror of
``frontend/src/lib/invite-jwt.ts``. Used by the Clerk webhook completion
path (Phase 2/3) to verify the JWT a parent picked up on the sign-up page,
before writing the ``external_student_id`` linkage onto the freshly created
``organization_members`` row.

Uses ``pyjwt`` (already in requirements.txt for Clerk JWT verification).
15-minute TTL by default. Single-use enforcement (``consumed_at``) is the
webhook's responsibility, not this module's.
"""

from __future__ import annotations

import hashlib
import os
import time
from typing import TypedDict

import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError

INVITE_JWT_TTL_SECONDS = 15 * 60
INVITE_JWT_ALGORITHM = 'HS256'

REQUIRED_CLAIMS = ('student_id', 'branch_id', 'branch_token_id', 'org_id')


class InviteJwtPayload(TypedDict):
    student_id: str
    branch_id: str
    branch_token_id: str
    org_id: str


class InviteJwtClaims(InviteJwtPayload):
    iat: int
    exp: int


class InviteJwtError(Exception):
    """Raised on any signing/verification failure."""


def _get_secret() -> str:
    secret = os.getenv('INVITE_JWT_SECRET', '')
    if not secret:
        raise InviteJwtError('INVITE_JWT_SECRET not configured')
    return secret


def sign_invite_jwt(
    payload: InviteJwtPayload,
    ttl_seconds: int = INVITE_JWT_TTL_SECONDS,
    now: int | None = None,
) -> str:
    """Sign a 15-min HS256 JWT carrying the invite context."""
    now_seconds = int(time.time()) if now is None else now
    claims = {
        **payload,
        'iat': now_seconds,
        'exp': now_seconds + ttl_seconds,
    }
    return jwt.encode(claims, _get_secret(), algorithm=INVITE_JWT_ALGORITHM)


def verify_invite_jwt(token: str, now: int | None = None) -> InviteJwtClaims:
    """Verify signature + expiry. Raises InviteJwtError on any failure."""
    secret = _get_secret()
    # When the caller supplies `now` (tests), do exp validation manually so we
    # aren't locked to wall-clock time. Otherwise let pyjwt enforce it.
    verify_exp = now is None
    try:
        decoded = jwt.decode(
            token,
            secret,
            algorithms=[INVITE_JWT_ALGORITHM],
            options={'require': ['exp'], 'verify_exp': verify_exp},
            leeway=0,
        )
    except ExpiredSignatureError as exc:
        raise InviteJwtError('Token expired') from exc
    except InvalidTokenError as exc:
        raise InviteJwtError(str(exc) or 'Invalid token') from exc

    if now is not None:
        exp = decoded.get('exp')
        if not isinstance(exp, int) or exp < now:
            raise InviteJwtError('Token expired')

    for claim in REQUIRED_CLAIMS:
        if not decoded.get(claim):
            raise InviteJwtError(f'Missing required claim: {claim}')

    return decoded  # type: ignore[return-value]


def jwt_jti_hash(token: str) -> str:
    """Deterministic sha256 hex of the raw JWT string.

    Used by the ``user.created`` webhook to record single-use consumption in
    ``invite_jwts_consumed`` without ever writing the raw token to the DB.
    Same token → same hash → PK conflict → replay is a no-op.
    """
    return hashlib.sha256(token.encode('utf-8')).hexdigest()
