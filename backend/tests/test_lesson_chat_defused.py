"""Tests for the defused legacy Flask lesson-chat path.

Two guarantees:
1. `OpenRouterLLM.generate` RAISES on an API error instead of returning the
   error text as content (so error strings can never be persisted as a reply).
2. `lesson_chat_by_slug` POST persists the friendly fallback — never a raw
   error string — when the LLM fails.
"""

import pytest
from unittest.mock import patch, MagicMock

USER_ID = 'user_lesson_chat_test'

LESSON = {'id': 'lesson-1', 'title': 'Pins', 'content': 'A pin restricts a piece.'}
COURSE = {'id': 'course-1', 'title': 'Tactics'}


# ── OpenRouterLLM.generate ────────────────────────────────────────────────


def _llm_with_client(client):
    with patch('llm.openrouter_llm.OpenAI', return_value=client):
        from llm.openrouter_llm import OpenRouterLLM
        return OpenRouterLLM(api_key='test-key')


def test_generate_raises_on_api_error():
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError('404 model not found')
    llm = _llm_with_client(client)
    with pytest.raises(Exception):
        llm.generate('hello')


def test_generate_raises_on_none_content():
    client = MagicMock()
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=None))]
    client.chat.completions.create.return_value = resp
    llm = _llm_with_client(client)
    with pytest.raises(Exception):
        llm.generate('hello')


def test_generate_returns_content_on_success():
    client = MagicMock()
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content='  A pin is a tactic.  '))]
    client.chat.completions.create.return_value = resp
    llm = _llm_with_client(client)
    assert llm.generate('hello') == 'A pin is a tactic.'


# ── lesson_chat_by_slug POST never persists error strings ─────────────────


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    """Chainable per-table mock. `lessons` serves the lesson row; the
    `lesson_chat_history` table records the upsert payload."""

    def __init__(self, name, lessons_rows, upserts):
        self._name = name
        self._lessons_rows = lessons_rows
        self._upserts = upserts

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def upsert(self, payload, **k):
        self._last_upsert = payload
        return self

    def execute(self):
        if self._name == 'lessons':
            return FakeResult(list(self._lessons_rows))
        if getattr(self, '_last_upsert', None) is not None:
            self._upserts.append(self._last_upsert)
            return FakeResult([self._last_upsert])
        # lesson_chat_history select -> no prior history
        return FakeResult([])


def make_supabase(upserts):
    class FakeSupabase:
        def table(self, name):
            return FakeTable(name, [LESSON], upserts)

    return FakeSupabase()


@pytest.fixture
def app():
    from flask import Flask
    from api.lessons import lessons_bp

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(lessons_bp)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {'Authorization': 'Bearer fake-jwt-token', 'Content-Type': 'application/json'}


@pytest.fixture(autouse=True)
def mock_jwt():
    with patch('utils.auth.jwt.decode', return_value={'sub': USER_ID}):
        yield


def test_lesson_chat_persists_no_error_string_on_llm_failure(client, auth_headers):
    upserts = []
    failing_llm = MagicMock()
    failing_llm.generate.side_effect = RuntimeError('404 model not found')

    with patch('api.lessons.supabase', make_supabase(upserts)), \
         patch('api.lessons.resolve_course_and_lesson', return_value=(COURSE, LESSON)), \
         patch('llm.openrouter_llm.OpenRouterLLM', return_value=failing_llm):
        resp = client.post(
            '/api/learn/tactics/pins/chat',
            headers=auth_headers,
            json={'message': 'What is a pin?'},
        )

    assert resp.status_code == 200
    body = resp.get_json()
    # The reply is the friendly fallback, not an error string.
    assert not body['response'].startswith('Error:')
    assert 'OpenRouter API issue' not in body['response']

    # And nothing containing an error string was persisted.
    assert len(upserts) == 1
    persisted = upserts[0]['messages']
    assistant_msgs = [m for m in persisted if m['role'] == 'assistant']
    assert assistant_msgs
    for m in assistant_msgs:
        assert not m['content'].startswith('Error:')
        assert 'OpenRouter API issue' not in m['content']


def test_lesson_chat_persists_reply_on_success(client, auth_headers):
    upserts = []
    ok_llm = MagicMock()
    ok_llm.generate.return_value = 'A pin is a powerful tactic.'

    with patch('api.lessons.supabase', make_supabase(upserts)), \
         patch('api.lessons.resolve_course_and_lesson', return_value=(COURSE, LESSON)), \
         patch('llm.openrouter_llm.OpenRouterLLM', return_value=ok_llm):
        resp = client.post(
            '/api/learn/tactics/pins/chat',
            headers=auth_headers,
            json={'message': 'What is a pin?'},
        )

    assert resp.status_code == 200
    assert resp.get_json()['response'] == 'A pin is a powerful tactic.'
    assert upserts[0]['messages'][-1]['content'] == 'A pin is a powerful tactic.'
