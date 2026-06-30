"""
Tests for backend/services/invite_jwt.py — sign/verify round-trip, expiry,
wrong-secret rejection, missing-claim rejection.
"""

from __future__ import annotations

import time

import pytest

from services.invite_jwt import (
    INVITE_JWT_TTL_SECONDS,
    InviteJwtError,
    sign_invite_jwt,
    verify_invite_jwt,
)


PAYLOAD = {
    'student_id': 'stu-1',
    'branch_id': 'br-1',
    'branch_token_id': 'tok-1',
    'org_id': 'org-1',
}


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch):
    monkeypatch.setenv('INVITE_JWT_SECRET', 'unit-test-secret')


def test_round_trip():
    now = 1_700_000_000
    token = sign_invite_jwt(PAYLOAD, now=now)
    claims = verify_invite_jwt(token, now=now)
    assert claims['student_id'] == 'stu-1'
    assert claims['branch_id'] == 'br-1'
    assert claims['branch_token_id'] == 'tok-1'
    assert claims['org_id'] == 'org-1'
    assert claims['exp'] == now + INVITE_JWT_TTL_SECONDS
    assert claims['iat'] == now


def test_expired_rejected():
    now = int(time.time())
    token = sign_invite_jwt(PAYLOAD, ttl_seconds=1, now=now - 3600)
    with pytest.raises(InviteJwtError):
        verify_invite_jwt(token)


def test_wrong_secret_rejected(monkeypatch):
    now = 1_700_000_000
    token = sign_invite_jwt(PAYLOAD, now=now)
    monkeypatch.setenv('INVITE_JWT_SECRET', 'a-different-secret')
    with pytest.raises(InviteJwtError):
        verify_invite_jwt(token, now=now)


def test_missing_secret_rejected(monkeypatch):
    monkeypatch.delenv('INVITE_JWT_SECRET', raising=False)
    with pytest.raises(InviteJwtError):
        sign_invite_jwt(PAYLOAD)


def test_missing_claim_rejected():
    now = 1_700_000_000
    token = sign_invite_jwt({**PAYLOAD, 'org_id': ''}, now=now)
    with pytest.raises(InviteJwtError, match='required claim'):
        verify_invite_jwt(token, now=now)
