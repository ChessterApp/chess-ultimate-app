"""Unit tests for the voice-minutes quota ledger + internal endpoints."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.server import app
from src import voice_quota
from src.voice_quota import (
    VoiceQuotaLedger,
    month_key,
    tier_limit_seconds,
    MAX_HEARTBEAT_DELTA,
)


@pytest.fixture(autouse=True)
def _no_supabase(monkeypatch):
    """Force the in-memory fallback: unset Supabase creds for every test."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    for tier in ("FREE", "PREMIUM", "PRO"):
        monkeypatch.delenv(f"VOICE_MINUTES_{tier}", raising=False)
    yield


@pytest.mark.unit
class TestTierLimits:
    def test_default_is_30_minutes_for_every_tier(self):
        # Billing isn't live: premium/pro intentionally match free.
        assert tier_limit_seconds("free") == 30 * 60
        assert tier_limit_seconds("premium") == 30 * 60
        assert tier_limit_seconds("pro") == 30 * 60

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("VOICE_MINUTES_PRO", "120")
        assert tier_limit_seconds("pro") == 120 * 60

    def test_zero_means_unlimited(self, monkeypatch):
        monkeypatch.setenv("VOICE_MINUTES_PREMIUM", "0")
        assert tier_limit_seconds("premium") is None

    def test_unlimited_keyword(self, monkeypatch):
        monkeypatch.setenv("VOICE_MINUTES_PRO", "unlimited")
        assert tier_limit_seconds("pro") is None

    def test_unknown_tier_falls_back_to_free(self, monkeypatch):
        monkeypatch.setenv("VOICE_MINUTES_FREE", "10")
        assert tier_limit_seconds("enterprise") == 10 * 60


@pytest.mark.unit
class TestLedgerInMemory:
    def test_accumulates_and_reports_remaining(self):
        led = VoiceQuotaLedger()
        led.record_heartbeat("u1", "s1", 60)
        led.record_heartbeat("u1", "s1", 30)
        q = led.get_quota("u1", "free")
        assert q["used_seconds"] == 90
        assert q["limit_seconds"] == 30 * 60
        assert q["remaining_seconds"] == 30 * 60 - 90
        assert q["month_key"] == month_key()
        assert q["unlimited"] is False

    def test_sums_across_sessions_same_user(self):
        led = VoiceQuotaLedger()
        led.record_heartbeat("u1", "s1", 60)
        led.record_heartbeat("u1", "s2", 90)
        assert led.get_quota("u1", "free")["used_seconds"] == 150

    def test_isolated_per_user(self):
        led = VoiceQuotaLedger()
        led.record_heartbeat("u1", "s1", 60)
        assert led.get_quota("u2", "free")["used_seconds"] == 0

    def test_single_heartbeat_delta_capped(self):
        led = VoiceQuotaLedger()
        led.record_heartbeat("u1", "s1", 10_000)
        assert led.get_quota("u1", "free")["used_seconds"] == MAX_HEARTBEAT_DELTA

    def test_negative_and_zero_delta_ignored(self):
        led = VoiceQuotaLedger()
        led.record_heartbeat("u1", "s1", -5)
        led.record_heartbeat("u1", "s1", 0)
        assert led.get_quota("u1", "free")["used_seconds"] == 0

    def test_remaining_never_negative(self):
        led = VoiceQuotaLedger()
        for _ in range(40):
            led.record_heartbeat("u1", f"s{_}", MAX_HEARTBEAT_DELTA)
        q = led.get_quota("u1", "free")
        assert q["remaining_seconds"] == 0

    def test_unlimited_tier_reports_none(self, monkeypatch):
        monkeypatch.setenv("VOICE_MINUTES_PRO", "0")
        led = VoiceQuotaLedger()
        led.record_heartbeat("u1", "s1", 60)
        q = led.get_quota("u1", "pro")
        assert q["unlimited"] is True
        assert q["limit_seconds"] is None
        assert q["remaining_seconds"] is None
        assert q["used_seconds"] == 60


@pytest.mark.unit
class TestLedgerFailOpen:
    def test_supabase_write_error_falls_back_to_memory(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")
        led = VoiceQuotaLedger()
        with patch.object(led, "_sb_record", side_effect=RuntimeError("down")):
            led.record_heartbeat("u1", "s1", 42)  # must not raise
        # Falls back to in-memory, so the read (also fail-open) still sees it.
        with patch.object(led, "_sb_used", side_effect=RuntimeError("down")):
            q = led.get_quota("u1", "free")
        assert q["used_seconds"] == 42


@pytest.mark.unit
class TestInternalEndpoints:
    def setup_method(self):
        # Isolate the shared global ledger's memory between endpoint tests.
        voice_quota.voice_quota_ledger._mem.clear()

    def test_heartbeat_then_quota(self):
        client = TestClient(app)
        r = client.post(
            "/internal/voice/heartbeat",
            json={"user_id": "u-endpoint", "session_id": "s1", "seconds_delta": 120},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

        r2 = client.get("/internal/voice/quota", params={"user_id": "u-endpoint", "tier": "free"})
        assert r2.status_code == 200
        body = r2.json()
        assert body["used_seconds"] == 120
        assert body["remaining_seconds"] == 30 * 60 - 120
        assert body["limit_seconds"] == 30 * 60

    def test_quota_defaults_tier_to_free(self):
        client = TestClient(app)
        r = client.get("/internal/voice/quota", params={"user_id": "u-notier"})
        assert r.status_code == 200
        assert r.json()["limit_seconds"] == 30 * 60

    def test_heartbeat_delta_capped_via_endpoint(self):
        client = TestClient(app)
        client.post(
            "/internal/voice/heartbeat",
            json={"user_id": "u-cap", "session_id": "s1", "seconds_delta": 99999},
        )
        r = client.get("/internal/voice/quota", params={"user_id": "u-cap", "tier": "free"})
        assert r.json()["used_seconds"] == MAX_HEARTBEAT_DELTA
