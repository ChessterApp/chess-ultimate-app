"""Unit tests for the voice tool bridge (src/tool_bridge.py).

Covers schema conversion to Gemini format and the single-tool dispatch endpoint:
success, unknown-tool 404, tool-error -> 200, X-User-Id identity override, and
session board_state sync.
"""

import json
import threading
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src import tool_bridge
from src.server import app
from src.middleware.rate_limiter import voice_tool_rate_limiter
from src.sessions import session_store
from src.tool_bridge import (
    _UNSUPPORTED_SCHEMA_KEYS,
    build_tool_declarations,
    clean_gemini_schema,
    dispatch_tool_safely,
)

USER_HEADERS = {"X-User-Id": "test-user-123"}


@pytest.fixture(autouse=True)
def _clear_sessions():
    session_store._sessions.clear()
    voice_tool_rate_limiter.reset()
    yield
    session_store._sessions.clear()
    voice_tool_rate_limiter.reset()


def _walk_keys(node):
    """Yield every dict key present anywhere in a nested schema."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_keys(item)


@pytest.mark.unit
class TestSchemaConversion:
    def test_clean_strips_unsupported_keys_recursively(self):
        dirty = {
            "type": "object",
            "$schema": "http://json-schema.org/draft-07/schema#",
            "additionalProperties": False,
            "properties": {
                "arrows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {
                            "brush": {"type": "string", "default": "green"},
                        },
                    },
                },
            },
        }
        cleaned = clean_gemini_schema(dirty)
        keys = set(_walk_keys(cleaned))
        assert keys.isdisjoint(_UNSUPPORTED_SCHEMA_KEYS)
        # Non-offending structure survives.
        assert cleaned["type"] == "object"
        assert "brush" in cleaned["properties"]["arrows"]["items"]["properties"]

    def test_build_tool_declarations_shape(self):
        decls = build_tool_declarations()
        assert len(decls) >= 15
        names = {d["name"] for d in decls}
        assert "board_control" in names
        for decl in decls:
            assert isinstance(decl["name"], str) and decl["name"]
            assert "description" in decl
            assert "parameters" in decl
            # No Gemini-rejected keys anywhere in the parameter tree.
            assert set(_walk_keys(decl["parameters"])).isdisjoint(
                _UNSUPPORTED_SCHEMA_KEYS
            )


@pytest.mark.unit
class TestToolsEndpoint:
    def setup_method(self):
        self.client = TestClient(app)

    def test_get_tools_returns_declarations(self):
        resp = self.client.get("/api/coach/tools")
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        assert any(t["name"] == "board_control" for t in tools)


@pytest.mark.unit
class TestToolDispatch:
    def setup_method(self):
        self.client = TestClient(app)

    def test_requires_user_id(self):
        resp = self.client.post("/api/coach/tool/board_control", json={"args": {}})
        assert resp.status_code == 401

    def test_unknown_tool_404(self):
        resp = self.client.post(
            "/api/coach/tool/does_not_exist",
            headers=USER_HEADERS,
            json={"args": {}},
        )
        assert resp.status_code == 404

    def test_dispatch_success_with_board_actions(self):
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        resp = self.client.post(
            "/api/coach/tool/board_control",
            headers=USER_HEADERS,
            json={"args": {"action_type": "set_fen", "fen": fen}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "error" not in body
        assert body["board_actions"]
        assert body["board_actions"][0]["type"] == "set_fen"
        assert body["board_actions"][0]["fen"] == fen

    def test_tool_error_returns_200_with_error(self):
        # Unknown action_type makes board_control return an error dict, not raise.
        resp = self.client.post(
            "/api/coach/tool/board_control",
            headers=USER_HEADERS,
            json={"args": {"action_type": "bogus_action"}},
        )
        assert resp.status_code == 200
        assert "error" in resp.json()

    def test_user_id_override(self):
        captured = {}

        def _fake_dispatch(name, args, **kwargs):
            captured["args"] = args
            return json.dumps({"ok": True})

        with patch.object(tool_bridge.registry, "dispatch", side_effect=_fake_dispatch):
            resp = self.client.post(
                "/api/coach/tool/get_user_progress",
                headers=USER_HEADERS,
                json={"args": {"user_id": "attacker-999"}},
            )
        assert resp.status_code == 200
        # The model-supplied user_id must be replaced with the header identity.
        assert captured["args"]["user_id"] == "test-user-123"

    def test_voice_tool_call_event_emitted_on_success(self):
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        with patch("src.tool_bridge.log_event") as mock_log:
            resp = self.client.post(
                "/api/coach/tool/board_control",
                headers=USER_HEADERS,
                json={
                    "args": {"action_type": "set_fen", "fen": fen},
                    "session_id": "sess-evt",
                },
            )
        assert resp.status_code == 200
        assert mock_log.called
        etype = mock_log.call_args.args[0]
        kwargs = mock_log.call_args.kwargs
        assert etype == "tool_call"
        assert kwargs["surface"] == "voice"
        assert kwargs["tool_name"] == "board_control"
        assert kwargs["user_id"] == "test-user-123"
        assert kwargs["session_id"] == "sess-evt"
        assert kwargs["ok"] is True
        assert isinstance(kwargs["duration_ms"], int)

    def test_voice_tool_call_event_ok_false_on_error(self):
        with patch("src.tool_bridge.log_event") as mock_log:
            resp = self.client.post(
                "/api/coach/tool/board_control",
                headers=USER_HEADERS,
                json={"args": {"action_type": "bogus_action"}},
            )
        assert resp.status_code == 200
        assert mock_log.called
        kwargs = mock_log.call_args.kwargs
        assert kwargs["ok"] is False
        assert kwargs["error_code"]

    def test_voice_check_moves_verdict_in_event_payload(self):
        result = json.dumps({"results": [{"legal": True}, {"legal": False}]})
        with patch.object(tool_bridge.registry, "dispatch", return_value=result), \
                patch("src.tool_bridge.log_event") as mock_log:
            resp = self.client.post(
                "/api/coach/tool/check_moves",
                headers=USER_HEADERS,
                json={"args": {"fen": "x", "moves": ["e4", "Ke2"]}},
            )
        assert resp.status_code == 200
        kwargs = mock_log.call_args.kwargs
        assert kwargs["payload"]["check_moves_verdict"] == {
            "candidates": 2,
            "legal": 1,
            "illegal": 1,
        }

    def test_board_state_sync_on_set_fen(self):
        session = session_store.create(user_id="test-user-123", session_id="sess-1")
        fen = "8/8/8/8/8/8/8/K6k w - - 0 1"
        resp = self.client.post(
            "/api/coach/tool/board_control",
            headers=USER_HEADERS,
            json={
                "args": {"action_type": "set_fen", "fen": fen},
                "session_id": "sess-1",
            },
        )
        assert resp.status_code == 200
        assert session.board_state == fen

    def test_slow_dispatch_does_not_block_event_loop(self):
        # A slow synchronous tool must run off the event loop, so a concurrent
        # request (here /health) stays responsive while it's in flight.
        started = threading.Event()

        def _slow_dispatch(name, args, **kwargs):
            started.set()
            time.sleep(2.0)
            return json.dumps({"ok": True})

        health_ms = {}

        def _fire_slow():
            self.client.post(
                "/api/coach/tool/board_control",
                headers=USER_HEADERS,
                json={"args": {"action_type": "set_fen"}},
            )

        with patch.object(tool_bridge.registry, "dispatch", side_effect=_slow_dispatch):
            worker = threading.Thread(target=_fire_slow)
            worker.start()
            assert started.wait(timeout=2.0), "slow dispatch never started"
            t0 = time.perf_counter()
            resp = self.client.get("/health")
            health_ms["elapsed"] = (time.perf_counter() - t0) * 1000
            worker.join(timeout=5.0)

        assert resp.status_code == 200
        assert health_ms["elapsed"] < 500, (
            f"/health blocked for {health_ms['elapsed']:.0f}ms during slow dispatch"
        )

    def test_board_state_sync_scoped_to_user(self):
        # A session owned by another user must not be mutated.
        session = session_store.create(user_id="other-user", session_id="sess-2")
        original = session.board_state
        fen = "8/8/8/8/8/8/8/K6k w - - 0 1"
        resp = self.client.post(
            "/api/coach/tool/board_control",
            headers=USER_HEADERS,
            json={
                "args": {"action_type": "set_fen", "fen": fen},
                "session_id": "sess-2",
            },
        )
        assert resp.status_code == 200
        assert session.board_state == original


@pytest.mark.unit
class TestDispatchErrorRecovery:
    """A tool that RAISES must yield a structured error, not an unhandled 500."""

    def test_raising_tool_returns_structured_error_string(self):
        def _boom(name, args, **kwargs):
            raise RuntimeError("stockfish exploded")

        with patch.object(tool_bridge.registry, "dispatch", side_effect=_boom):
            raw = dispatch_tool_safely("analyze_position", {"fen": "x"})

        payload = json.loads(raw)
        assert payload["error"]["tool"] == "analyze_position"
        assert payload["error"]["type"] == "RuntimeError"
        assert "stockfish exploded" in payload["error"]["message"]
        assert payload["error"]["recoverable"] is True

    def test_successful_dispatch_returned_verbatim(self):
        def _ok(name, args, **kwargs):
            return json.dumps({"ok": True})

        with patch.object(tool_bridge.registry, "dispatch", side_effect=_ok):
            raw = dispatch_tool_safely("get_user_progress", {})
        assert json.loads(raw) == {"ok": True}

    def test_endpoint_returns_200_error_when_tool_raises(self):
        client = TestClient(app)

        def _boom(name, args, **kwargs):
            raise ValueError("bad args")

        with patch.object(tool_bridge.registry, "dispatch", side_effect=_boom):
            resp = client.post(
                "/api/coach/tool/get_user_progress",
                headers=USER_HEADERS,
                json={"args": {}},
            )
        # Must NOT be a 500 — the model needs a readable tool response.
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"]["type"] == "ValueError"
        assert body["error"]["recoverable"] is True


@pytest.mark.unit
class TestToolDispatchRateLimitAndMetering:
    """Task 1: voice tool path is rate limited (same mechanism/tiers as text)
    and every invocation is metered to token_usage (surface='voice')."""

    def setup_method(self):
        self.client = TestClient(app)
        voice_tool_rate_limiter.reset()

    def teardown_method(self):
        voice_tool_rate_limiter.reset()

    @patch("src.tool_bridge.record_voice_event")
    def test_dispatch_meters_voice_tool_call(self, mock_record):
        def _ok(name, args, **kwargs):
            return json.dumps({"ok": True})

        with patch.object(tool_bridge.registry, "dispatch", side_effect=_ok):
            resp = self.client.post(
                "/api/coach/tool/get_user_progress",
                headers=USER_HEADERS,
                json={"args": {}, "session_id": "s1"},
            )
        assert resp.status_code == 200
        mock_record.assert_called_once()
        pos, kwargs = mock_record.call_args
        assert pos[0] == "test-user-123"
        assert pos[1] == "s1"
        assert kwargs.get("tool_name") == "get_user_progress"

    @patch("src.tool_bridge.record_voice_event")
    def test_dispatch_rate_limited_after_tier_limit(self, mock_record):
        def _ok(name, args, **kwargs):
            return json.dumps({"ok": True})

        statuses = []
        with patch.object(tool_bridge.registry, "dispatch", side_effect=_ok):
            for _ in range(62):
                statuses.append(
                    self.client.post(
                        "/api/coach/tool/get_user_progress",
                        headers=USER_HEADERS,
                        json={"args": {}},
                    ).status_code
                )
        # Free tier: 60 voice tool calls/min, then 429 with a clear payload.
        assert statuses.count(200) == 60
        assert 429 in statuses

    @patch("src.tool_bridge.record_voice_event")
    def test_rate_limit_429_payload(self, mock_record):
        def _ok(name, args, **kwargs):
            return json.dumps({"ok": True})

        with patch.object(tool_bridge.registry, "dispatch", side_effect=_ok):
            last = None
            for _ in range(61):
                last = self.client.post(
                    "/api/coach/tool/get_user_progress",
                    headers=USER_HEADERS,
                    json={"args": {}},
                )
        assert last.status_code == 429
        detail = last.json()["detail"]
        assert detail["error"] == "rate_limit_exceeded"
        assert detail["tier"] == "free"
        assert detail["retry_after"] >= 1
