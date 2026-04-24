"""End-to-end smoke tests for Hermes Chess Coach.

These tests exercise the full system: API → Hermes Agent → LLM → response.
Requires the hermes-chess PM2 service to be running on port 8642.
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import pytest

BASE_URL = "http://localhost:8642"
API_KEY = os.environ.get("HERMES_API_KEY", "rYwnma1sIfhC8GF880Ie1M325qj4p9KA-CVvDeOPXGU")
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}


def _chat(messages, session_id=None, timeout=60):
    """Helper: send a chat completion request."""
    headers = {**HEADERS}
    if session_id:
        headers["X-Hermes-Session-Id"] = session_id
    resp = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers=headers,
        json={"messages": messages},
        timeout=timeout,
    )
    return resp


@pytest.mark.e2e
@pytest.mark.slow
def test_full_coaching_exchange():
    """Three messages in sequence — verify the service handles multi-turn."""
    session_id = f"e2e-coaching-{uuid.uuid4().hex[:8]}"

    exchanges = [
        "I want to learn the Italian Game. Where should I start?",
        "What are the key ideas for White in this opening?",
        "Can you show me a typical pawn structure?",
    ]

    for msg_text in exchanges:
        resp = _chat(
            [{"role": "user", "content": msg_text}],
            session_id=session_id,
            timeout=60,
        )
        assert resp.status_code == 200, f"Failed on message: {msg_text}"
        content = resp.json()["choices"][0]["message"]["content"]
        assert isinstance(content, str)
        assert len(content) > 5, f"Response too short for: {msg_text}"


@pytest.mark.e2e
@pytest.mark.slow
def test_session_isolation():
    """Two different session IDs get independent responses."""
    session_a = f"e2e-iso-a-{uuid.uuid4().hex[:8]}"
    session_b = f"e2e-iso-b-{uuid.uuid4().hex[:8]}"

    resp_a = _chat(
        [{"role": "user", "content": "I play the Sicilian Najdorf. What should I know?"}],
        session_id=session_a,
        timeout=60,
    )
    resp_b = _chat(
        [{"role": "user", "content": "I play the Queen's Gambit Declined. What should I know?"}],
        session_id=session_b,
        timeout=60,
    )

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    content_a = resp_a.json()["choices"][0]["message"]["content"].lower()
    content_b = resp_b.json()["choices"][0]["message"]["content"].lower()

    # Each response should reference its own opening
    assert "sicilian" in content_a or "najdorf" in content_a, f"Session A doesn't mention Sicilian: {content_a[:200]}"
    assert "queen" in content_b or "gambit" in content_b or "qgd" in content_b, f"Session B doesn't mention QGD: {content_b[:200]}"


@pytest.mark.e2e
@pytest.mark.slow
def test_daemon_stability_under_load():
    """10 concurrent requests all return 200."""
    def send_request(i):
        resp = httpx.post(
            f"{BASE_URL}/v1/chat/completions",
            headers=HEADERS,
            json={
                "messages": [{"role": "user", "content": f"Name chess opening #{i}. Just the name."}],
            },
            timeout=120,
        )
        return i, resp.status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(send_request, i) for i in range(10)]
        results = [f.result() for f in as_completed(futures)]

    statuses = {i: code for i, code in results}
    failures = {i: code for i, code in statuses.items() if code != 200}
    assert not failures, f"Some requests failed: {failures}"
