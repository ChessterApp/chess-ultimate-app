"""
Tests for services.invite_jwt.jwt_jti_hash — deterministic sha256 hex of
the raw JWT string. Used by the user.created webhook to record single-use
consumption without persisting the raw token.
"""

from __future__ import annotations

import hashlib

from services.invite_jwt import jwt_jti_hash


def test_jwt_jti_hash_is_stable():
    """Same input → same hex digest across calls."""
    token = 'eyJhbGciOiJIUzI1NiJ9.eyJ0ZXN0Ijp0cnVlfQ.signature'
    assert jwt_jti_hash(token) == jwt_jti_hash(token)


def test_jwt_jti_hash_is_sha256_hex():
    """Value matches the reference sha256 hex we expect the DB PK to store."""
    token = 'sample.jwt.token'
    expected = hashlib.sha256(token.encode('utf-8')).hexdigest()
    got = jwt_jti_hash(token)
    assert got == expected
    assert len(got) == 64
    assert all(c in '0123456789abcdef' for c in got)


def test_jwt_jti_hash_different_tokens_different_hashes():
    """Different tokens produce different hashes — collision would defeat single-use."""
    a = jwt_jti_hash('token-a.header.sig')
    b = jwt_jti_hash('token-b.header.sig')
    assert a != b
