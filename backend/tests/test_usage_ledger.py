"""Unit tests for services/usage_ledger.py (vision token accounting)."""

import threading
from unittest.mock import patch

import pytest

from services import usage_ledger


def _join_daemons():
    for t in threading.enumerate():
        if t is not threading.main_thread() and t.daemon:
            t.join(timeout=2)


@pytest.fixture(autouse=True)
def _supabase_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")


def test_records_usage_row_with_cost():
    body = {"usage": {"prompt_tokens": 2000, "completion_tokens": 100,
                      "prompt_tokens_details": {"cached_tokens": 500}}}
    with patch("services.usage_ledger.requests.post") as post:
        post.return_value.status_code = 201
        usage_ledger.record_openrouter_usage(
            body, model="google/gemini-3.1-pro-preview", surface="vision", user_id="u1"
        )
        _join_daemons()
    assert post.called
    row = post.call_args.kwargs["json"]
    assert row["user_id"] == "u1"
    assert row["surface"] == "vision"
    assert row["prompt_tokens"] == 2000 and row["completion_tokens"] == 100
    assert row["cached_tokens"] == 500
    assert abs(row["estimated_cost_usd"] - (2000 * 2.0 + 100 * 12.0) / 1e6) < 1e-9
    assert post.call_args.args[0].endswith("/rest/v1/token_usage")


def test_anonymous_default_and_no_usage_no_row():
    with patch("services.usage_ledger.requests.post") as post:
        post.return_value.status_code = 201
        usage_ledger.record_openrouter_usage({}, model="m", surface="vision")
        usage_ledger.record_openrouter_usage({"usage": {"prompt_tokens": 0}}, model="m", surface="vision")
        _join_daemons()
        assert not post.called
        usage_ledger.record_openrouter_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 1}},
                                             model="m", surface="vision")
        _join_daemons()
    assert post.call_args.kwargs["json"]["user_id"] == "anonymous"


def test_missing_supabase_config_is_silent(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL")
    with patch("services.usage_ledger.requests.post") as post:
        usage_ledger.record_openrouter_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 1}},
                                             model="m", surface="vision")
        _join_daemons()
    assert not post.called


def test_unknown_model_uses_default_price():
    assert usage_ledger.estimate_cost_usd("nobody/model", 1_000_000, 0) == 1.0
    assert usage_ledger.estimate_cost_usd("google/gemini-3.8-flash:nitro", 1_000_000, 0) == 0.75
