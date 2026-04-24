"""Integration tests for Hermes Chess Coach service.

These tests require the hermes-chess PM2 service to be running on port 8642.
"""

import os

import httpx
import pytest

BASE_URL = "http://localhost:8642"
API_KEY = os.environ.get("HERMES_API_KEY", "rYwnma1sIfhC8GF880Ie1M325qj4p9KA-CVvDeOPXGU")
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}


@pytest.mark.integration
def test_hermes_starts_and_responds():
    """Health endpoint returns 200 with expected body."""
    resp = httpx.get(f"{BASE_URL}/health", timeout=10)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "hermes-chess-coach"


@pytest.mark.integration
@pytest.mark.slow
def test_hermes_chat_completions_basic():
    """POST chat completions with a chess question returns valid response."""
    resp = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers=HEADERS,
        json={"messages": [{"role": "user", "content": "What is castling in chess? One sentence."}]},
        timeout=60,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "choices" in body
    assert len(body["choices"]) > 0
    content = body["choices"][0]["message"]["content"]
    assert isinstance(content, str)
    assert len(content) > 10


@pytest.mark.integration
@pytest.mark.slow
def test_hermes_session_id_header():
    """X-Hermes-Session-Id header is accepted without error."""
    resp = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={**HEADERS, "X-Hermes-Session-Id": "test-session-header-001"},
        json={"messages": [{"role": "user", "content": "Name a chess piece."}]},
        timeout=60,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["choices"]) > 0


@pytest.mark.integration
@pytest.mark.slow
def test_hermes_persona_applied():
    """Response reflects chess coach persona, not generic assistant."""
    resp = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers=HEADERS,
        json={
            "messages": [
                {"role": "user", "content": "I just lost a game because I blundered my queen on move 10. What should I do?"}
            ]
        },
        timeout=60,
    )
    assert resp.status_code == 200
    content = resp.json()["choices"][0]["message"]["content"].lower()
    # Coach should give chess-relevant advice, not generic help
    chess_terms = ["blunder", "queen", "game", "move", "tactic", "check", "position", "calculate", "pattern", "practice", "mistake"]
    assert any(term in content for term in chess_terms), f"Response doesn't seem chess-related: {content[:200]}"


@pytest.mark.integration
def test_hermes_invalid_api_key():
    """Wrong API key returns 401."""
    resp = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer totally-wrong-key-12345",
        },
        json={"messages": [{"role": "user", "content": "test"}]},
        timeout=10,
    )
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.slow
def test_hermes_model_override():
    """Explicit model param is accepted and reflected in response."""
    resp = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers=HEADERS,
        json={
            "messages": [{"role": "user", "content": "Say hi."}],
            "model": "google/gemini-2.5-flash",
        },
        timeout=60,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "google/gemini-2.5-flash"
