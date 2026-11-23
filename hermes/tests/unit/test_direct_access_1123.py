"""The voice pipeline's direct path (src/direct_access.py, 23.11): the page sends the two hot requests to Hermes itself
with a pass the site signed; only the pass says who the student is and what plan they have."""

import time

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src import direct_access as da

SECRET = "test-secret-1123"


def _app():
    app = FastAPI()

    @app.post("/api/coach/chat")
    async def chat(request: Request):
        return {"user": request.headers.get("x-user-id"), "tier": request.headers.get("x-subscription-tier"),
                "auth": request.headers.get("authorization"), "clerk": request.headers.get("x-clerk-user-id"),
                "body": (await request.json())}

    @app.post("/api/coach/voice/stt")
    async def stt(request: Request):
        return {"user": request.headers.get("x-user-id"), "locale": request.headers.get("x-voice-locale"),
                "bytes": len(await request.body())}

    @app.get("/api/coach/sessions")
    async def sessions(request: Request):
        return {"user": request.headers.get("x-user-id")}

    app.add_middleware(da.DirectAccess)
    return TestClient(app)


def _pass(**over):
    payload = {"sub": "user_a", "tier": "pro", "exp": int(time.time()) + 300, "aud": da.AUDIENCE, **over}
    return da.sign(payload, SECRET.encode())


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("COACH_DIRECT_SECRET", SECRET)
    monkeypatch.setenv("COACH_DIRECT_ORIGINS", "https://chesster.io,http://localhost:3000")


@pytest.mark.unit
def test_a_valid_pass_reaches_the_route_as_its_student_whatever_the_headers_claim(on):
    res = _app().post("/direct/chat", json={"message": "привет"}, headers={
        "Authorization": f"Bearer {_pass()}", "X-User-Id": "user_b", "x-subscription-tier": "enterprise",
        "X-Clerk-User-Id": "user_b", "Origin": "https://chesster.io"})
    assert res.status_code == 200
    assert res.json() == {"user": "user_a", "tier": "pro", "auth": None, "clerk": None, "body": {"message": "привет"}}
    assert res.headers["access-control-allow-origin"] == "https://chesster.io"


@pytest.mark.unit
def test_the_hearing_gets_its_audio_and_language(on):
    res = _app().post("/direct/voice/stt", content=b"\x00" * 1000,
                      headers={"Authorization": f"Bearer {_pass()}", "X-Voice-Locale": "kk", "Content-Type": "audio/wav"})
    assert res.json() == {"user": "user_a", "locale": "kk", "bytes": 1000}


@pytest.mark.unit
@pytest.mark.parametrize("token", [
    None, "", "garbage", "v1.e30.AAAA",
    "forged",  # signed with another secret
    "expired", "wrong-audience", "no-user",
])
def test_no_valid_pass_no_way_in(on, token):
    tokens = {
        "forged": da.sign({"sub": "user_a", "tier": "pro", "exp": int(time.time()) + 300, "aud": da.AUDIENCE}, b"other"),
        "expired": _pass(exp=int(time.time()) - 120),
        "wrong-audience": _pass(aud="something-else"),
        "no-user": _pass(sub=""),
    }
    token = tokens.get(token, token)
    headers = {"X-User-Id": "user_a", "x-subscription-tier": "pro"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    res = _app().post("/direct/chat", json={"message": "x"}, headers=headers)
    assert res.status_code == 401


@pytest.mark.unit
def test_a_pass_edited_after_signing_is_refused(on):
    head, body, mac = _pass().split(".")
    payload = da._unb64(body).replace(b'"pro"', b'"max"')
    res = _app().post("/direct/chat", json={"message": "x"},
                      headers={"Authorization": f"Bearer {head}.{da._b64(payload)}.{mac}"})
    assert res.status_code == 401


@pytest.mark.unit
def test_only_the_two_routes_are_served_under_the_prefix(on):
    client = _app()
    for path in ("/direct/sessions", "/direct/api/coach/sessions", "/direct/", "/direct/chat/../sessions"):
        assert client.post(path, headers={"Authorization": f"Bearer {_pass()}"}).status_code == 404, path
        assert client.get(path, headers={"Authorization": f"Bearer {_pass()}"}).status_code == 404, path


@pytest.mark.unit
def test_without_the_secret_the_path_is_off(monkeypatch):
    monkeypatch.delenv("COACH_DIRECT_SECRET", raising=False)
    res = _app().post("/direct/chat", json={"message": "x"}, headers={"Authorization": f"Bearer {_pass()}"})
    assert res.status_code == 404


@pytest.mark.unit
def test_the_preflight_names_the_page_origin_only(on):
    client = _app()
    ok = client.options("/direct/chat", headers={"Origin": "https://chesster.io", "Access-Control-Request-Method": "POST"})
    assert ok.status_code == 204 and ok.headers["access-control-allow-origin"] == "https://chesster.io"
    assert "authorization" in ok.headers["access-control-allow-headers"]
    other = client.options("/direct/chat", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in other.headers


@pytest.mark.unit
def test_other_paths_are_untouched(on):
    assert _app().get("/api/coach/sessions", headers={"X-User-Id": "user_c"}).json() == {"user": "user_c"}


@pytest.mark.unit
def test_the_server_runs_the_check(on):
    from src import server

    assert any(m.cls is da.DirectAccess for m in server.app.user_middleware)
    client = TestClient(server.app)
    assert client.post("/direct/chat", json={"message": "x"}, headers={"X-User-Id": "user_a"}).status_code == 401
    assert client.get("/direct/sessions").status_code == 404


# The same pass frontend/src/lib/coach/__tests__/direct-pass.test.ts makes: what the site signs, Hermes takes.
VECTOR = ("v1.eyJzdWIiOiJ1c2VyX3ZlY3RvciIsInRpZXIiOiJwcmVtaXVtIiwiZXhwIjoxNzk1NDMwMDAwLCJhdWQiOiJjb2FjaC1kaXJlY3QifQ"
          ".FaWCHfhP0mTe9xhUSAt9z3voO-wAoAgH5fJznOkoGbg")


@pytest.mark.unit
def test_the_sites_pass_is_taken(monkeypatch):
    monkeypatch.setenv("COACH_DIRECT_SECRET", "vector-secret")
    assert da.verify(VECTOR, now=1795430000 - 10) == {
        "sub": "user_vector", "tier": "premium", "exp": 1795430000, "aud": "coach-direct"}
    assert da.verify(VECTOR, now=1795430000 + da.LEEWAY_S + 1) is None
