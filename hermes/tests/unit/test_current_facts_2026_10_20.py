"""2026-10-20: the present state of the chess world is fetched now, not remembered (src/current_facts.py) —
the voice coach said «загуглил: чемпион мира — Дин Лижэнь» (Alexander's screenshot)."""

import json

import pytest

from src import current_facts as cf
from src.intent import read_intent

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
EN = ("The World Chess Championship is played to determine the world champion in chess. The current world "
      "champion is Gukesh Dommaraju, who defeated the previous champion Ding Liren in the 2024 World Chess Championship.")
RU = "Чемпионат мира по шахматам — соревнование, имеющее своей целью определить чемпиона мира по шахматам."


@pytest.mark.parametrize("text,asks,topic", [
    ("Кто сейчас чемпион мира по шахматам?", True, "champion"),
    ("загугли, кто чемпион мира", True, "champion"),
    ("кто действующий чемпион мира", True, "champion"),
    ("кто чемпионка мира среди женщин", True, "women"),
    ("кто первый номер рейтинга ФИДЕ?", True, "rating"),
    ("кто выиграл турнир претендентов", True, "candidates"),
    ("who is the current world chess champion", True, "champion"),
    ("Әлем чемпионы кім?", True, "champion"),
    ("что такое вилка", False, None),
    ("покажи оперную партию", False, None),
    ("давай сыграем", False, None),
])
def test_the_words_that_ask_about_the_present(text, asks, topic):
    assert cf.asks_current_facts(text) is asks
    if asks:
        assert cf.topic_for(text) == topic


Y2026 = ("The World Chess Championship 2026 is an upcoming chess match to determine the World Chess Champion. It will be "
         "played between the defending champion, Gukesh Dommaraju, and the challenger, Javokhir Sindarov, the winner of "
         "the Candidates Tournament 2026.")


def _fetch_ok(lang, title):
    if title.endswith("2026"):
        return Y2026 if title.startswith("World Chess Championship") else None
    if title[-4:].isdigit():
        return None
    return {"en": EN, "ru": RU}[lang]


def _fetch_down(lang, title):
    return None


def test_the_facts_come_from_wikipedia_with_the_date():
    facts = cf.current_facts("кто сейчас чемпион мира?", fetch=_fetch_ok)
    assert facts["topic"] == "champion" and not facts["fallback"]
    assert [s["title"] for s in facts["sources"]] == ["World Chess Championship", "World Chess Championship 2026",
                                                      "Чемпионат мира по шахматам"]   # the newest year page too
    block = cf.facts_block(facts)
    assert "Verified current facts (Wikipedia, fetched today" in block and "Gukesh Dommaraju" in block
    assert "Javokhir Sindarov" in block
    assert "never say you googled" in block and "en.wikipedia.org/wiki/World_Chess_Championship" in block
    assert cf.facts_note(facts).startswith("[Facts] ")
    assert cf.current_facts("что такое вилка", fetch=_fetch_ok) is None and cf.facts_block(None) == ""


def test_without_wikipedia_the_known_facts_go_in_with_their_date():
    facts = cf.current_facts("who is the world champion", fetch=_fetch_down)
    assert facts["fallback"] and "Gukesh" in facts["sources"][0]["text"]
    block = cf.facts_block(facts)
    assert f"known for certain as of {cf.FALLBACK_AS_OF}" in block and "SAY the date" in block
    women = cf.current_facts("кто чемпионка мира", fetch=_fetch_down)
    assert "Ju Wenjun" in women["sources"][0]["text"]
    assert "Sindarov" in cf.current_facts("кто выиграл турнир претендентов", fetch=_fetch_down)["sources"][0]["text"]


def test_the_voice_intent_and_the_tool(monkeypatch):
    assert read_intent("Кто сейчас чемпион мира по шахматам?", fen=START) == {"kind": "fact"}
    assert read_intent("загугли тогда, кто сейчас чемпион мира по шахматам", fen=START)["kind"] == "fact"
    monkeypatch.setattr(cf, "fetch_intro", _fetch_ok)
    out = json.loads(cf._handle_current_facts({"question": "кто чемпион мира?"}))
    assert out["topic"] == "champion" and "Gukesh" in out["note"] and out["sources"][0]["lang"] == "en"
    out = json.loads(cf._handle_current_facts({}, student_message="кто сейчас первый в рейтинге?"))
    assert out["topic"] == "rating"


def test_the_tool_is_registered_in_the_chess_toolset():
    from tools.registry import registry

    assert registry.get_toolset_for_tool("current_facts") == "chess"


def test_the_intro_is_cleaned_of_template_junk():
    raw = "%5B%5BWikipedia%3ATemplates+for+discussion%5D%5D{{{CRITERION}}}\nThe current world champion is Gukesh.\n"
    assert cf._clean(raw) == "The current world champion is Gukesh."


def test_the_text_turn_carries_the_facts_block(monkeypatch):
    from unittest.mock import MagicMock, patch

    from fastapi.testclient import TestClient

    from src.server import app
    from src.user_profile import UserProfile

    monkeypatch.setattr(cf, "fetch_intro", _fetch_ok)
    client = TestClient(app)
    user = {"X-User-Id": "facts-user"}
    sid = client.post("/api/coach/sessions", headers=user).json()["id"]
    with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
        mock_profile.return_value = UserProfile(user_id="facts-user")
        agent = MagicMock()
        seen = {}

        def _chat(message, stream_callback=None):
            seen["message"] = message
            if stream_callback:
                stream_callback("Гукеш.")
            return "Гукеш."

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent
        resp = client.post("/api/coach/chat", headers=user, json={
            "message": "Кто сейчас чемпион мира по шахматам?", "session_id": sid, "fen": START})
        assert resp.status_code == 200
    assert "Verified current facts" in seen["message"] and "Gukesh Dommaraju" in seen["message"]


def test_search_web_asks_wikipedia_first(monkeypatch):
    from src.tools import web_search as ws

    class _Resp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    def _get(url, params=None, **kw):
        if "wikipedia" in url:
            return _Resp({"query": {"pages": {"1": {"index": 1, "title": "World Chess Championship", "extract": EN}}}})
        return _Resp({"AbstractText": "", "RelatedTopics": []})

    monkeypatch.setattr(ws.httpx, "get", _get)
    results = ws.search_web("current world chess champion")
    assert results and results[0]["source"] == "wikipedia-en" and "Gukesh" in results[0]["snippet"]
