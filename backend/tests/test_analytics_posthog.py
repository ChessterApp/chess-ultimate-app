"""Tests for services/analytics_posthog.py — server-side PostHog capture."""

import os
import re
from unittest.mock import MagicMock, patch

import pytest

from services import analytics_posthog as ap

EVENTS_TS = os.path.join(
    os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'lib', 'analytics', 'events.ts'
)


@pytest.fixture(autouse=True)
def _reset_client(monkeypatch):
    monkeypatch.setattr(ap, '_client', None)
    monkeypatch.delenv('POSTHOG_PROJECT_KEY', raising=False)
    monkeypatch.delenv('NEXT_PUBLIC_POSTHOG_KEY', raising=False)
    yield


def _ts_registry() -> set[str]:
    with open(EVENTS_TS, encoding='utf-8') as fh:
        src = fh.read()
    block = src.split('export const ANALYTICS_EVENTS = {', 1)[1].split('} as const;', 1)[0]
    return set(re.findall(r":\s*'([a-z0-9_]+)'", block))


def _ts_denylist() -> set[str]:
    with open(EVENTS_TS, encoding='utf-8') as fh:
        src = fh.read()
    block = src.split('export const PII_DENYLIST', 1)[1].split('] as const;', 1)[0]
    return set(re.findall(r"'([a-z_]+)'", block))


def test_server_events_are_registered_in_ts_registry():
    registry = _ts_registry()
    assert registry, 'failed to parse ANALYTICS_EVENTS from events.ts'
    assert ap.SERVER_EVENTS <= registry, ap.SERVER_EVENTS - registry


def test_pii_denylist_mirrors_ts():
    assert ap.PII_DENYLIST == _ts_denylist()


def test_strip_pii_drops_denylisted_and_birth_prefixed_keys_recursively():
    out = ap.strip_pii({
        'email': 'a@b.c', 'Phone': '+7', 'birth_date': 'x', 'message': 'hi',
        'transcript': 't', 'content': 'c', 'fen': 'f',
        'starting_level': 2, '$set': {'skill_tier': 'beginner', 'dob': 'x'},
    })
    assert out == {'starting_level': 2, '$set': {'skill_tier': 'beginner'}}


def test_capture_noop_without_key():
    with patch('posthog.Posthog') as cls:
        ap.capture('user_1', ap.LEVEL_ASSIGNED, {'starting_level': 1})
    cls.assert_not_called()


def test_capture_noop_without_distinct_id(monkeypatch):
    monkeypatch.setenv('POSTHOG_PROJECT_KEY', 'phc_test')
    with patch('posthog.Posthog') as cls:
        ap.capture(None, ap.LEVEL_ASSIGNED)
    cls.assert_not_called()


def test_capture_sends_scrubbed_props(monkeypatch):
    monkeypatch.setenv('POSTHOG_PROJECT_KEY', 'phc_test')
    client = MagicMock()
    with patch('posthog.Posthog', return_value=client) as cls:
        ap.capture('user_1', ap.LEVEL_ASSIGNED, {'starting_level': 3, 'email': 'x@y.z'})
    cls.assert_called_once_with('phc_test', host=ap.POSTHOG_CAPTURE_HOST)
    client.capture.assert_called_once_with(
        'level_assigned', distinct_id='user_1', properties={'starting_level': 3}
    )


def test_capture_falls_back_to_next_public_key(monkeypatch):
    monkeypatch.setenv('NEXT_PUBLIC_POSTHOG_KEY', 'phc_public')
    with patch('posthog.Posthog', return_value=MagicMock()) as cls:
        ap.capture('user_1', ap.LEVEL_ASSIGNED)
    assert cls.call_args[0][0] == 'phc_public'


def test_capture_never_raises(monkeypatch):
    monkeypatch.setenv('POSTHOG_PROJECT_KEY', 'phc_test')
    client = MagicMock()
    client.capture.side_effect = RuntimeError('boom')
    with patch('posthog.Posthog', return_value=client):
        ap.capture('user_1', ap.LEVEL_ASSIGNED)  # must not raise
