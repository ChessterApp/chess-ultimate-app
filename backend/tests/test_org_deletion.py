"""Tests for backend.services.org_deletion — self-serve delete (PRD §7)."""

from unittest.mock import MagicMock, patch

import pytest

from services import org_deletion as svc


ORG = {
    'id': 'org-1',
    'name': 'Almaty Chess Academy',
    'slug': 'almaty',
    'deletion_requested_at': None,
}


class _UpdateRecorder:
    """Captures the table().update().eq().execute() call chain."""

    def __init__(self):
        self.updates: list[dict] = []

    def table(self, name):
        recorder = self

        class _Chain:
            def update(self, payload):
                recorder.updates.append({'table': name, 'payload': payload})
                return self
            def eq(self, *a, **kw):
                return self
            def execute(self):
                return MagicMock(data=None)
            # Used by _get_org / _get_caller_role paths if hit
            def select(self, *a, **kw):
                return self
            def single(self):
                return self

        return _Chain()


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    yield


class TestRequestDeletion:
    def test_happy_path_sets_timestamp_and_notifies(self, monkeypatch):
        monkeypatch.setenv('RESEND_API_KEY', 're_test_xxx')
        recorder = _UpdateRecorder()
        with patch.object(svc, '_get_org', return_value=ORG), \
             patch.object(svc, '_get_caller_role', return_value='owner'), \
             patch.object(svc, '_get_supabase', return_value=recorder), \
             patch.object(svc, '_post_json', return_value={'id': 'em_x'}) as mock_post:
            result = svc.request_deletion('org-1', 'user-owner')
            assert result['ok'] is True
            assert result['deletion_requested_at']
            assert result['already_requested'] is False
            # Update was issued
            assert recorder.updates, 'expected an update call'
            payload = recorder.updates[0]['payload']
            assert 'deletion_requested_at' in payload
            # Ops notification was attempted
            assert mock_post.called
            url, _headers, body = mock_post.call_args[0]
            assert url == svc.RESEND_API_URL
            assert 'almaty' in body['subject']
            assert body['to'] == [svc.ALEX_EMAIL]
            assert 'Almaty Chess Academy' in body['text']

    def test_second_call_is_noop_when_already_requested(self):
        already_requested = {**ORG, 'deletion_requested_at': '2026-06-01T12:00:00+00:00'}
        recorder = _UpdateRecorder()
        with patch.object(svc, '_get_org', return_value=already_requested), \
             patch.object(svc, '_get_caller_role', return_value='owner'), \
             patch.object(svc, '_get_supabase', return_value=recorder), \
             patch.object(svc, '_post_json') as mock_post:
            result = svc.request_deletion('org-1', 'user-owner')
            assert result['ok'] is True
            assert result['deletion_requested_at'] == '2026-06-01T12:00:00+00:00'
            assert result['already_requested'] is True
            # No update + no email on a re-request.
            assert recorder.updates == []
            assert not mock_post.called

    def test_non_owner_rejected(self):
        with patch.object(svc, '_get_org', return_value=ORG), \
             patch.object(svc, '_get_caller_role', return_value='admin'):
            with pytest.raises(svc.OrgDeletionError) as excinfo:
                svc.request_deletion('org-1', 'user-admin')
            assert excinfo.value.code == 'forbidden'

    def test_teacher_rejected(self):
        with patch.object(svc, '_get_org', return_value=ORG), \
             patch.object(svc, '_get_caller_role', return_value='teacher'):
            with pytest.raises(svc.OrgDeletionError) as excinfo:
                svc.request_deletion('org-1', 'user-teacher')
            assert excinfo.value.code == 'forbidden'

    def test_unknown_org_rejected(self):
        with patch.object(svc, '_get_org', return_value=None):
            with pytest.raises(svc.OrgDeletionError) as excinfo:
                svc.request_deletion('org-missing', 'user-x')
            assert excinfo.value.code == 'org_not_found'

    def test_email_failure_does_not_block_timestamp(self, monkeypatch):
        monkeypatch.setenv('RESEND_API_KEY', 're_test_xxx')
        recorder = _UpdateRecorder()
        with patch.object(svc, '_get_org', return_value=ORG), \
             patch.object(svc, '_get_caller_role', return_value='owner'), \
             patch.object(svc, '_get_supabase', return_value=recorder), \
             patch.object(svc, '_post_json', side_effect=RuntimeError('boom')):
            result = svc.request_deletion('org-1', 'user-owner')
            # Timestamp is still set + we still return ok.
            assert result['ok'] is True
            assert result['deletion_requested_at']
            assert recorder.updates, 'timestamp must persist even when email fails'

    def test_no_api_key_does_not_block_timestamp(self):
        # RESEND_API_KEY absent (autouse fixture clears it).
        recorder = _UpdateRecorder()
        with patch.object(svc, '_get_org', return_value=ORG), \
             patch.object(svc, '_get_caller_role', return_value='owner'), \
             patch.object(svc, '_get_supabase', return_value=recorder), \
             patch.object(svc, '_post_json') as mock_post:
            result = svc.request_deletion('org-1', 'user-owner')
            assert result['ok'] is True
            assert recorder.updates
            assert not mock_post.called  # short-circuited on missing key

    def test_requester_email_included_in_body(self, monkeypatch):
        monkeypatch.setenv('RESEND_API_KEY', 're_test_xxx')
        recorder = _UpdateRecorder()
        with patch.object(svc, '_get_org', return_value=ORG), \
             patch.object(svc, '_get_caller_role', return_value='owner'), \
             patch.object(svc, '_get_supabase', return_value=recorder), \
             patch.object(svc, '_post_json') as mock_post:
            svc.request_deletion(
                'org-1', 'user-owner', requester_email='owner@school.com',
            )
            body = mock_post.call_args[0][2]
            assert 'owner@school.com' in body['text']
