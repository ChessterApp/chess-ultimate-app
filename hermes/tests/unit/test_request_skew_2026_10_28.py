"""Fields a coach request carries that this Hermes does not know are logged, not lost silently (28.10).

Rollout skew: the site and Hermes ship separately. A newer site sending a field an older Hermes
does not know (session_id on voice/idea, context_note on analysis) was dropped without a trace,
and the coach answered without it. The request still succeeds; one WARNING per endpoint + field
says so (rate-limited, field names only, never values).
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from src import request_skew
from src.middleware.rate_limiter import rate_limiter, voice_tool_rate_limiter
from src.server import app
from src.user_profile import UserProfile

H = {"X-User-Id": "u-skew-1028"}
FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
SECRET = "the student's own words 4815162342"


@pytest.fixture(autouse=True)
def _fresh():
    request_skew.reset()
    voice_tool_rate_limiter.reset()
    rate_limiter.reset()
    yield
    request_skew.reset()


def _skew_warnings(caplog):
    return [r for r in caplog.records if r.name == "src.request_skew" and r.levelno == logging.WARNING]


@pytest.mark.unit
def test_an_unknown_field_is_logged_once_per_endpoint_and_field_without_its_value(caplog):
    client = TestClient(app)
    body = {"text": "дай мне задачу", "fen": FEN, "future_field": SECRET}
    with caplog.at_level(logging.WARNING, logger="src.request_skew"):
        assert client.post("/api/coach/voice/intent", headers=H, json=body).status_code == 200
        assert client.post("/api/coach/voice/intent", headers=H, json=body).status_code == 200
    logged = _skew_warnings(caplog)
    assert len(logged) == 1  # rate-limited: the second request adds nothing
    line = logged[0].getMessage()
    assert "future_field" in line and "/api/coach/voice/intent" in line
    assert SECRET not in line and "4815162342" not in line

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="src.request_skew"):
        # the same field on another endpoint is its own skew
        r = client.post("/api/coach/voice/idea", headers=H, json={"text": "а если конём", "fen": FEN,
                                                                  "future_field": SECRET})
        assert r.status_code == 200
        # a known body warns nothing
        assert client.post("/api/coach/voice/intent", headers=H, json={"text": "привет"}).status_code == 200
    logged = _skew_warnings(caplog)
    assert len(logged) == 1 and "/api/coach/voice/idea" in logged[0].getMessage()


@pytest.mark.unit
def test_the_route_template_names_the_endpoint_not_the_session_id(caplog):
    client = TestClient(app)
    sid = client.post("/api/coach/sessions", headers=H, json={}).json()["id"]
    with caplog.at_level(logging.WARNING, logger="src.request_skew"):
        r = client.post(f"/api/coach/sessions/{sid}/messages", headers=H,
                        json={"role": "user", "content": "e4", "new_field": 1})
    assert r.status_code == 200
    line = _skew_warnings(caplog)[0].getMessage()
    assert "/api/coach/sessions/{session_id}/messages" in line and sid not in line


@pytest.mark.unit
@patch("src.server._create_agent")
@patch("src.server.load_user_profile")
def test_the_analysis_endpoints_read_raw_json_and_log_unknown_fields_too(mock_profile, mock_agent, caplog):
    mock_profile.return_value = UserProfile(user_id=H["X-User-Id"])
    agent = MagicMock()
    agent.chat.return_value = "Solid."
    mock_agent.return_value = agent
    client = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="src.request_skew"):
        r = client.post("/api/coach/analysis", headers=H,
                        json={"fen": FEN, "query": "Explain", "context_type": "position", "board_markup": SECRET})
    assert r.status_code == 200
    logged = _skew_warnings(caplog)
    assert len(logged) == 1 and "board_markup" in logged[0].getMessage()
    assert SECRET not in logged[0].getMessage()


@pytest.mark.unit
def test_every_coach_request_body_model_reports_unknown_fields():
    """A new endpoint's model must not slip back into silent dropping."""
    def walk(routes):
        for route in routes:
            inner = getattr(route, "original_router", None)  # an included router (the voice tool bridge)
            if inner is not None:
                yield from walk(inner.routes)
            elif isinstance(route, APIRoute):
                yield route

    checked, missing = [], []
    for route in walk(app.routes):
        if not route.path.startswith("/api/coach") or route.body_field is None:
            continue
        body = route.body_field
        model = getattr(body, "type_", None) or body.field_info.annotation
        checked.append(route.path)
        if isinstance(model, type) and not issubclass(model, request_skew.CoachRequest):
            missing.append(f"{route.path}: {model.__name__}")
    assert "/api/coach/tool/{name}" in checked and "/api/coach/chat" in checked
    assert missing == []


@pytest.mark.unit
def test_field_names_are_bounded_and_the_table_does_not_grow_without_limit(caplog):
    with caplog.at_level(logging.WARNING, logger="src.request_skew"):
        request_skew.note_unknown_fields(["bad\nname" + "x" * 500], endpoint="POST /api/coach/x", model="M")
        for i in range(request_skew.MAX_KEYS + 50):
            request_skew.note_unknown_fields([f"f{i}"], endpoint="POST /api/coach/x", model="M")
    lines = [r.getMessage() for r in _skew_warnings(caplog)]
    assert "\n" not in lines[0] and len(lines[0]) < 400
    assert len(request_skew._seen) <= request_skew.MAX_KEYS
