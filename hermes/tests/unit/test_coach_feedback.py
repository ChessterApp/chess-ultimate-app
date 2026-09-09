"""Unit tests for coach feedback — POST /api/coach/feedback + the Supabase
best-effort helper. All offline (Supabase REST mocked). LOG-ONLY signal."""

import os
from unittest.mock import patch, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from src.server import app
import src.coach_feedback as cf


USER_HEADERS = {"X-User-Id": "fb-user-1"}


@pytest.mark.unit
class TestFeedbackEndpoint:
    """POST /api/coach/feedback — auth, validation, upsert/retract, fail-open."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_requires_user_id(self):
        resp = self.client.post(
            "/api/coach/feedback", json={"turn_id": "t1", "rating": 1}
        )
        assert resp.status_code == 401

    def test_missing_turn_id_is_400(self):
        resp = self.client.post(
            "/api/coach/feedback", headers=USER_HEADERS, json={"rating": 1}
        )
        assert resp.status_code == 400

    def test_turn_id_too_long_is_400(self):
        resp = self.client.post(
            "/api/coach/feedback",
            headers=USER_HEADERS,
            json={"turn_id": "x" * 65, "rating": 1},
        )
        assert resp.status_code == 400

    def test_invalid_rating_is_400(self):
        resp = self.client.post(
            "/api/coach/feedback",
            headers=USER_HEADERS,
            json={"turn_id": "t1", "rating": 2},
        )
        assert resp.status_code == 400

    def test_invalid_surface_is_400(self):
        resp = self.client.post(
            "/api/coach/feedback",
            headers=USER_HEADERS,
            json={"turn_id": "t1", "rating": 1, "surface": "bogus"},
        )
        assert resp.status_code == 400

    def test_oversized_comment_is_400(self):
        resp = self.client.post(
            "/api/coach/feedback",
            headers=USER_HEADERS,
            json={"turn_id": "t1", "rating": -1, "comment": "x" * 2001},
        )
        assert resp.status_code == 400

    def test_thumbs_up_upserts(self):
        with patch("src.server.upsert_feedback", return_value=True) as up, \
             patch("src.server.delete_feedback") as dele, \
             patch("src.server.log_event") as log:
            resp = self.client.post(
                "/api/coach/feedback",
                headers=USER_HEADERS,
                json={"turn_id": "t1", "rating": 1, "session_id": "s1"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "persisted": True}
        up.assert_called_once()
        _, kwargs = up.call_args
        args = up.call_args.args
        assert args[0] == "fb-user-1" and args[1] == "t1" and args[2] == 1
        assert kwargs["session_id"] == "s1" and kwargs["surface"] == "text"
        dele.assert_not_called()
        # Event logged with rating/surface/has_comment only (no comment text).
        assert log.call_args.args[0] == "feedback"
        assert log.call_args.kwargs["payload"] == {
            "rating": 1, "surface": "text", "has_comment": False
        }

    def test_rating_zero_retracts(self):
        with patch("src.server.upsert_feedback") as up, \
             patch("src.server.delete_feedback", return_value=True) as dele, \
             patch("src.server.log_event"):
            resp = self.client.post(
                "/api/coach/feedback",
                headers=USER_HEADERS,
                json={"turn_id": "t1", "rating": 0},
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "persisted": True}
        dele.assert_called_once_with("fb-user-1", "t1")
        up.assert_not_called()

    def test_comment_truncated_to_500_before_persist(self):
        with patch("src.server.upsert_feedback", return_value=True) as up, \
             patch("src.server.log_event"):
            resp = self.client.post(
                "/api/coach/feedback",
                headers=USER_HEADERS,
                json={"turn_id": "t1", "rating": 1, "comment": "y" * 1500},
            )
        assert resp.status_code == 200
        assert len(up.call_args.kwargs["comment"]) == 500

    def test_fail_open_when_sink_down(self):
        # Supabase write returns False (down) → still 200, persisted False.
        with patch("src.server.upsert_feedback", return_value=False), \
             patch("src.server.log_event") as log:
            resp = self.client.post(
                "/api/coach/feedback",
                headers=USER_HEADERS,
                json={"turn_id": "t1", "rating": 1},
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "persisted": False}
        # Event still spooled even though the row did not persist.
        log.assert_called_once()


@pytest.mark.unit
class TestFeedbackHelper:
    """The Supabase best-effort upsert/delete helper (httpx mocked)."""

    def test_upsert_disabled_without_config(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        assert cf.upsert_feedback("u", "t", 1) is False

    def test_upsert_posts_merge_duplicates(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        with patch("httpx.post", return_value=resp) as post:
            ok = cf.upsert_feedback(
                "u", "t", 1, session_id="s", comment="c", surface="text"
            )
        assert ok is True
        _, kwargs = post.call_args
        assert kwargs["params"] == {"on_conflict": "user_id,turn_id"}
        assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates"
        assert kwargs["json"]["rating"] == 1
        assert kwargs["json"]["user_id"] == "u"
        assert kwargs["json"]["turn_id"] == "t"

    def test_upsert_returns_false_on_http_error(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")
        with patch("httpx.post", side_effect=httpx.HTTPError("boom")):
            assert cf.upsert_feedback("u", "t", 1) is False

    def test_delete_issues_eq_filters(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        with patch("httpx.delete", return_value=resp) as dele:
            ok = cf.delete_feedback("u", "t")
        assert ok is True
        _, kwargs = dele.call_args
        assert kwargs["params"] == {"user_id": "eq.u", "turn_id": "eq.t"}

    def test_delete_returns_false_on_error(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")
        with patch("httpx.delete", side_effect=httpx.HTTPError("boom")):
            assert cf.delete_feedback("u", "t") is False
