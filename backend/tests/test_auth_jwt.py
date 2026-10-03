"""
Tests for Clerk JWT signature verification (utils/auth.py).

`_decode_clerk_token` verifies RS256 signatures against Clerk's JWKS. These
tests generate a throwaway RSA keypair and patch the module's JWKS client so
`get_signing_key_from_jwt` returns the test public key — no network IO.
"""

import time
from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask, jsonify, request

from utils.auth import verify_clerk_token

USER_ID = "user_test_123"


@pytest.fixture
def rsa_key():
    """A throwaway RSA private key for signing test tokens."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def app():
    flask_app = Flask(__name__)

    @flask_app.route("/protected")
    @verify_clerk_token
    def protected():
        return jsonify({"user_id": request.user_id})

    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _make_token(private_key, claims=None, **overrides):
    payload = {
        "sub": USER_ID,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    if claims:
        payload.update(claims)
    payload.update(overrides)
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "test"})


def _patch_jwks(public_key):
    """Patch the module JWKS client so get_signing_key_from_jwt returns our key."""
    fake_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_key)
    )
    return patch("utils.auth._get_jwks_client", return_value=fake_client)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_sets_user_id(client, rsa_key):
    token = _make_token(rsa_key)
    with _patch_jwks(rsa_key.public_key()):
        resp = client.get("/protected", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.get_json()["user_id"] == USER_ID


def test_tampered_signature_rejected(client, rsa_key):
    token = _make_token(rsa_key)
    # Corrupt the signature segment.
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload}.{sig[:-4]}AAAA"
    with _patch_jwks(rsa_key.public_key()):
        resp = client.get("/protected", headers=_auth(tampered))
    assert resp.status_code == 401


def test_expired_token_rejected(client, rsa_key):
    token = _make_token(rsa_key, exp=int(time.time()) - 3600)
    with _patch_jwks(rsa_key.public_key()):
        resp = client.get("/protected", headers=_auth(token))
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Token expired"


def test_wrong_key_rejected(client, rsa_key):
    # Sign with a different key than the one the JWKS client serves.
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _make_token(other_key)
    with _patch_jwks(rsa_key.public_key()):
        resp = client.get("/protected", headers=_auth(token))
    assert resp.status_code == 401


def test_missing_header_rejected(client):
    resp = client.get("/protected")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "No token provided"


def test_malformed_token_rejected(client, rsa_key):
    with _patch_jwks(rsa_key.public_key()):
        resp = client.get("/protected", headers=_auth("not-a-jwt"))
    assert resp.status_code == 401


def test_token_without_sub_rejected(client, rsa_key):
    payload = {"iat": int(time.time()), "exp": int(time.time()) + 3600}
    token = jwt.encode(payload, rsa_key, algorithm="RS256", headers={"kid": "test"})
    with _patch_jwks(rsa_key.public_key()):
        resp = client.get("/protected", headers=_auth(token))
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Invalid token: no user ID"


def test_jwks_fetch_failure_returns_503(client, rsa_key):
    token = _make_token(rsa_key)

    def _boom(_token):
        raise jwt.PyJWKClientError("JWKS endpoint unreachable")

    fake_client = SimpleNamespace(get_signing_key_from_jwt=_boom)
    with patch("utils.auth._get_jwks_client", return_value=fake_client):
        resp = client.get("/protected", headers=_auth(token))
    assert resp.status_code == 503
