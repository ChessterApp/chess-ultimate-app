"""
Tests for the Clerk `user.created` webhook — Phase 5 Chess Empire
onboarding completion.

Covers:
  - happy path: verify → upsert member → create Clerk membership → consume JWT
  - replay: JWT already consumed → short-circuit, no writes
  - non-CE signup: no inviteJwt in unsafe_metadata → skip, no writes
  - invalid JWT: silent warning, no writes
  - revoked branch token: refuse, no writes
  - Clerk create_membership 422: still succeed (already-member)
  - Clerk create_membership 500: raise so Svix retries; JWT stays unconsumed
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _invite_secret(monkeypatch):
    monkeypatch.setenv('INVITE_JWT_SECRET', 'phase5-user-created-secret')


@pytest.fixture
def app():
    from flask import Flask
    from routes.webhooks import webhooks_bp

    app = Flask(__name__)
    app.register_blueprint(webhooks_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _sign_payload(payload: bytes, secret: str) -> dict:
    """Generate Svix headers so the webhook signature check accepts the body."""
    svix_id = 'msg_test_user_created'
    svix_timestamp = str(int(time.time()))
    raw_secret = secret[len('whsec_'):] if secret.startswith('whsec_') else secret
    secret_bytes = base64.b64decode(raw_secret)
    signed_content = f'{svix_id}.{svix_timestamp}.'.encode() + payload
    signature = hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    return {
        'svix-id': svix_id,
        'svix-timestamp': svix_timestamp,
        'svix-signature': f'v1,{base64.b64encode(signature).decode()}',
    }


def _make_event(invite_jwt: str | None, *, user_id: str = 'user_2test') -> dict:
    """Construct a Clerk-shape `user.created` event body."""
    unsafe = {'inviteJwt': invite_jwt} if invite_jwt is not None else {}
    return {
        'type': 'user.created',
        'data': {
            'id': user_id,
            'email_addresses': [
                {'id': 'em_1', 'email_address': 'parent@example.com'},
            ],
            'primary_email_address_id': 'em_1',
            'first_name': 'Kirill',
            'last_name': 'Ivanov',
            'unsafe_metadata': unsafe,
            'created_at': 1_700_000_000,
        },
    }


def _make_supabase(*, consumed_hits: list, token_row, org_row):
    """Build a MagicMock chain that mimics the supabase-py builder pattern.

    ``consumed_hits`` — list injected into the first `.limit(1).execute()` on
    invite_jwts_consumed. Provide `[]` for a fresh JWT, `[{...}]` for a
    replay.

    ``token_row`` / ``org_row`` — single-row payloads returned by the
    branch_invite_tokens + organizations lookups (None simulates missing).
    """
    supabase = MagicMock()
    calls = {'upsert': [], 'insert_consumed': []}

    def table(name):
        tbl = MagicMock()

        if name == 'invite_jwts_consumed':
            def select_chain(*_a, **_k):
                sel = MagicMock()
                sel.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=consumed_hits,
                )
                return sel
            tbl.select.side_effect = select_chain

            def insert(payload):
                calls['insert_consumed'].append(payload)
                ins = MagicMock()
                ins.execute.return_value = MagicMock()
                return ins
            tbl.insert.side_effect = insert

        elif name == 'branch_invite_tokens':
            def select_chain(*_a, **_k):
                sel = MagicMock()
                data = [token_row] if token_row is not None else []
                sel.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=data,
                )
                return sel
            tbl.select.side_effect = select_chain

        elif name == 'organizations':
            def select_chain(*_a, **_k):
                sel = MagicMock()
                data = [org_row] if org_row is not None else []
                sel.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=data,
                )
                return sel
            tbl.select.side_effect = select_chain

        elif name == 'organization_members':
            def upsert(payload, on_conflict=None):
                calls['upsert'].append({'payload': payload, 'on_conflict': on_conflict})
                up = MagicMock()
                up.execute.return_value = MagicMock()
                return up
            tbl.upsert.side_effect = upsert

        return tbl

    supabase.table.side_effect = table
    supabase._calls = calls
    return supabase


def _post_event(client, event, webhook_secret):
    payload = json.dumps(event).encode()
    headers = _sign_payload(payload, webhook_secret)
    return client.post(
        '/api/webhooks/clerk',
        data=payload,
        content_type='application/json',
        headers=headers,
    )


def _sign_invite(payload_overrides: dict | None = None) -> str:
    """Sign a real invite JWT using the test secret."""
    from services.invite_jwt import sign_invite_jwt
    payload = {
        'student_id': 'stu-xyz',
        'branch_id': 'br-xyz',
        'branch_token_id': 'tok-uuid',
        'org_id': 'org-uuid',
    }
    if payload_overrides:
        payload.update(payload_overrides)
    return sign_invite_jwt(payload)


WEBHOOK_SECRET = 'whsec_' + base64.b64encode(b'user-created-secret').decode()


class TestUserCreatedHappyPath:
    def test_fresh_signup_links_member_and_creates_membership(self, client):
        jwt_token = _sign_invite()
        event = _make_event(jwt_token)
        supabase = _make_supabase(
            consumed_hits=[],
            token_row={'id': 'tok-uuid', 'revoked_at': None},
            org_row={'id': 'org-uuid', 'clerk_org_id': 'clerk-org-abc'},
        )
        mock_clerk = MagicMock()
        mock_clerk.create_membership.return_value = {}
        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', WEBHOOK_SECRET), \
             patch('routes.webhooks._get_supabase', return_value=supabase), \
             patch('services.clerk_client.get_client', return_value=mock_clerk):
            resp = _post_event(client, event, WEBHOOK_SECRET)

        assert resp.status_code == 200
        # organization_members upsert executed with the linkage fields
        assert len(supabase._calls['upsert']) == 1
        payload = supabase._calls['upsert'][0]['payload']
        assert payload['user_id'] == 'user_2test'
        assert payload['external_student_id'] == 'stu-xyz'
        assert payload['external_source'] == 'chess_empire'
        assert payload['link_status'] == 'verified'
        assert payload['email'] == 'parent@example.com'
        assert payload['name'] == 'Kirill Ivanov'
        assert supabase._calls['upsert'][0]['on_conflict'] == (
            'organization_id,external_student_id,external_source'
        )
        # Clerk membership requested with basic_member role
        mock_clerk.create_membership.assert_called_once_with(
            'clerk-org-abc', 'user_2test', 'basic_member',
        )
        # JWT consumption row inserted with the sha256 hash PK
        assert len(supabase._calls['insert_consumed']) == 1
        consumed = supabase._calls['insert_consumed'][0]
        assert consumed['jti_hash'] == hashlib.sha256(jwt_token.encode()).hexdigest()
        assert consumed['clerk_user_id'] == 'user_2test'
        assert consumed['external_student_id'] == 'stu-xyz'


class TestUserCreatedReplay:
    def test_already_consumed_short_circuits(self, client):
        jwt_token = _sign_invite()
        event = _make_event(jwt_token)
        supabase = _make_supabase(
            consumed_hits=[{'jti_hash': 'existing'}],
            token_row={'id': 'tok-uuid', 'revoked_at': None},
            org_row={'id': 'org-uuid', 'clerk_org_id': 'clerk-org-abc'},
        )
        mock_clerk = MagicMock()
        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', WEBHOOK_SECRET), \
             patch('routes.webhooks._get_supabase', return_value=supabase), \
             patch('services.clerk_client.get_client', return_value=mock_clerk):
            resp = _post_event(client, event, WEBHOOK_SECRET)

        assert resp.status_code == 200
        assert supabase._calls['upsert'] == []
        assert supabase._calls['insert_consumed'] == []
        mock_clerk.create_membership.assert_not_called()


class TestUserCreatedNonCE:
    def test_missing_invite_metadata_skips_silently(self, client):
        event = _make_event(invite_jwt=None)
        supabase = _make_supabase(consumed_hits=[], token_row=None, org_row=None)
        mock_clerk = MagicMock()
        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', WEBHOOK_SECRET), \
             patch('routes.webhooks._get_supabase', return_value=supabase), \
             patch('services.clerk_client.get_client', return_value=mock_clerk):
            resp = _post_event(client, event, WEBHOOK_SECRET)

        assert resp.status_code == 200
        assert supabase._calls['upsert'] == []
        assert supabase._calls['insert_consumed'] == []
        # No supabase.table() calls at all — short-circuits before touching DB
        supabase.table.assert_not_called()


class TestUserCreatedInvalidJWT:
    def test_invalid_jwt_logs_and_returns_ok(self, client):
        event = _make_event('this.is.not-a-real-jwt')
        supabase = _make_supabase(consumed_hits=[], token_row=None, org_row=None)
        mock_clerk = MagicMock()
        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', WEBHOOK_SECRET), \
             patch('routes.webhooks._get_supabase', return_value=supabase), \
             patch('services.clerk_client.get_client', return_value=mock_clerk):
            resp = _post_event(client, event, WEBHOOK_SECRET)

        assert resp.status_code == 200
        assert supabase._calls['upsert'] == []
        assert supabase._calls['insert_consumed'] == []
        mock_clerk.create_membership.assert_not_called()


class TestUserCreatedRevokedToken:
    def test_revoked_branch_token_refuses(self, client):
        jwt_token = _sign_invite()
        event = _make_event(jwt_token)
        supabase = _make_supabase(
            consumed_hits=[],
            token_row={'id': 'tok-uuid', 'revoked_at': '2026-01-01T00:00:00Z'},
            org_row={'id': 'org-uuid', 'clerk_org_id': 'clerk-org-abc'},
        )
        mock_clerk = MagicMock()
        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', WEBHOOK_SECRET), \
             patch('routes.webhooks._get_supabase', return_value=supabase), \
             patch('services.clerk_client.get_client', return_value=mock_clerk):
            resp = _post_event(client, event, WEBHOOK_SECRET)

        assert resp.status_code == 200
        assert supabase._calls['upsert'] == []
        assert supabase._calls['insert_consumed'] == []
        mock_clerk.create_membership.assert_not_called()

    def test_missing_org_refuses(self, client):
        jwt_token = _sign_invite()
        event = _make_event(jwt_token)
        supabase = _make_supabase(
            consumed_hits=[],
            token_row={'id': 'tok-uuid', 'revoked_at': None},
            org_row=None,
        )
        mock_clerk = MagicMock()
        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', WEBHOOK_SECRET), \
             patch('routes.webhooks._get_supabase', return_value=supabase), \
             patch('services.clerk_client.get_client', return_value=mock_clerk):
            resp = _post_event(client, event, WEBHOOK_SECRET)

        assert resp.status_code == 200
        assert supabase._calls['upsert'] == []
        assert supabase._calls['insert_consumed'] == []
        mock_clerk.create_membership.assert_not_called()


class TestUserCreatedClerk422:
    def test_already_member_still_consumes_jwt(self, client):
        from services.clerk_client import ClerkAPIError
        jwt_token = _sign_invite()
        event = _make_event(jwt_token)
        supabase = _make_supabase(
            consumed_hits=[],
            token_row={'id': 'tok-uuid', 'revoked_at': None},
            org_row={'id': 'org-uuid', 'clerk_org_id': 'clerk-org-abc'},
        )
        mock_clerk = MagicMock()
        mock_clerk.create_membership.side_effect = ClerkAPIError(422, 'already a member')
        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', WEBHOOK_SECRET), \
             patch('routes.webhooks._get_supabase', return_value=supabase), \
             patch('services.clerk_client.get_client', return_value=mock_clerk):
            resp = _post_event(client, event, WEBHOOK_SECRET)

        assert resp.status_code == 200
        assert len(supabase._calls['upsert']) == 1
        assert len(supabase._calls['insert_consumed']) == 1


class TestUserCreatedClerk500:
    def test_upstream_failure_returns_500_leaves_jwt_unconsumed(self, client):
        from services.clerk_client import ClerkAPIError
        jwt_token = _sign_invite()
        event = _make_event(jwt_token)
        supabase = _make_supabase(
            consumed_hits=[],
            token_row={'id': 'tok-uuid', 'revoked_at': None},
            org_row={'id': 'org-uuid', 'clerk_org_id': 'clerk-org-abc'},
        )
        mock_clerk = MagicMock()
        mock_clerk.create_membership.side_effect = ClerkAPIError(500, 'boom')
        with patch('routes.webhooks.CLERK_WEBHOOK_SECRET', WEBHOOK_SECRET), \
             patch('routes.webhooks._get_supabase', return_value=supabase), \
             patch('services.clerk_client.get_client', return_value=mock_clerk):
            resp = _post_event(client, event, WEBHOOK_SECRET)

        # Route handler catches the exception and returns 500 (Svix will retry).
        assert resp.status_code == 500
        # Upsert already ran (idempotent), but the JWT-consumed row did NOT.
        assert len(supabase._calls['upsert']) == 1
        assert supabase._calls['insert_consumed'] == []


class TestExtractHelpers:
    def test_extract_primary_email_picks_primary(self):
        from routes.webhooks import _extract_primary_email
        data = {
            'email_addresses': [
                {'id': 'a', 'email_address': 'first@x.com'},
                {'id': 'b', 'email_address': 'primary@x.com'},
            ],
            'primary_email_address_id': 'b',
        }
        assert _extract_primary_email(data) == 'primary@x.com'

    def test_extract_primary_email_falls_back_to_first(self):
        from routes.webhooks import _extract_primary_email
        data = {
            'email_addresses': [{'id': 'a', 'email_address': 'only@x.com'}],
        }
        assert _extract_primary_email(data) == 'only@x.com'

    def test_extract_name_composes(self):
        from routes.webhooks import _extract_name
        assert _extract_name({'first_name': 'Aiya', 'last_name': 'K'}) == 'Aiya K'
        assert _extract_name({'first_name': 'Solo'}) == 'Solo'
        assert _extract_name({}) is None
