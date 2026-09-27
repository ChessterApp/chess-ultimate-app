"""Inline [[arrows: …]] / [[squares: …]] marks: the stream filter and the SSE turn."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.board_markup import MarkupFilter, strip_markup
from src.server import app
from src.sessions import session_store
from src.middleware.rate_limiter import rate_limiter
from src.user_profile import UserProfile


def _run(chunks):
    f = MarkupFilter()
    text, actions = [], []
    for c in chunks:
        t, a = f.feed(c)
        text.append(t)
        actions += a
    text.append(f.flush())
    return "".join(text), actions


@pytest.mark.unit
class TestMarkupFilter:
    def test_mark_split_across_deltas_is_cut_and_drawn(self):
        text, actions = _run(["Лучший ход — d4 [", "[arrows: d2d4 green, c5-d4 red]] — центр."])
        assert text == "Лучший ход — d4 — центр."
        assert actions == [{"type": "draw_arrows", "arrows": [
            {"from": "d2", "to": "d4", "brush": "green"},
            {"from": "c5", "to": "d4", "brush": "red"},
        ]}]

    def test_every_arrows_action_carries_the_answers_arrows_so_far(self):
        """The clients replace the arrows on each draw_arrows — a later mark must not erase an earlier one."""
        _, actions = _run(["[[arrows: e2e4]] и [[arr", "ows: g1f3 blue]]"])
        assert [len(a["arrows"]) for a in actions] == [1, 2]
        assert actions[-1]["arrows"][1] == {"from": "g1", "to": "f3", "brush": "blue"}

    def test_squares(self):
        text, actions = _run(["Поле [[squares: d5, e5 red]] ключевое"])
        assert text == "Поле ключевое"
        assert actions == [{"type": "highlight_squares", "squares": ["d5", "e5"], "color": "red"}]

    def test_other_brackets_stay_and_an_unfinished_mark_is_text(self):
        text, actions = _run(["Сноска [[1]] и хвост [[arrows: e2"])
        assert text == "Сноска [[1]] и хвост [[arrows: e2"
        assert actions == []

    def test_a_mark_with_nothing_usable_is_dropped_silently(self):
        text, actions = _run(["Смотри [[arrows: сюда]] дальше"])
        assert text == "Смотри дальше" and actions == []

    def test_bare_marks_models_write_anyway(self):
        """Bench 2026-09-27: DeepSeek wrote «возьмут [[red]] ...cxd4» — a colour next to a move."""
        text, actions = _run(["Если возьмут [[red]] ...cxd4, бей конём [[f3d4 blue]], поле [[d5]]."])
        assert text == "Если возьмут ...cxd4, бей конём, поле."
        assert actions == [
            {"type": "draw_arrows", "arrows": [{"from": "f3", "to": "d4", "brush": "blue"}]},
            {"type": "highlight_squares", "squares": ["d5"], "color": "yellow"},
        ]

    def test_whole_text(self):
        clean, actions = strip_markup("x [[arrows: e2 e4]] y")
        assert clean == "x y" and actions[0]["arrows"][0]["to"] == "e4"


@pytest.fixture
def _clean_state():
    session_store._sessions.clear()
    rate_limiter.reset()
    yield
    session_store._sessions.clear()
    rate_limiter.reset()


@pytest.mark.unit
@pytest.mark.usefixtures("_clean_state")
@patch("src.server.log_event")
@patch("src.server.load_user_profile")
@patch("src.server._create_agent")
def test_marks_become_board_frames_and_never_reach_the_text(mock_agent, mock_profile, mock_log):
    mock_profile.return_value = UserProfile(user_id="markup-user")
    agent = MagicMock()
    agent.tools = []
    agent.model = "deepseek/deepseek-v4.1-flash"
    agent._api_call_count = 1
    agent.max_iterations = 5
    agent.session_prompt_tokens = agent.session_completion_tokens = agent.session_cache_read_tokens = 0

    def _chat(message, stream_callback=None):
        for chunk in ["Играй d4 [[arr", "ows: d2d4 green]] — ", "центр твой."]:
            stream_callback(chunk)
        return "центр твой."

    agent.chat.side_effect = _chat
    mock_agent.return_value = agent

    resp = TestClient(app).post("/api/coach/chat", headers={"X-User-Id": "markup-user"},
                                json={"message": "Что играть?"})
    frames = [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]
    text = "".join(f["delta"] for f in frames if "delta" in f)
    assert text == "Играй d4 — центр твой."
    [board] = [f for f in frames if "board_actions" in f]
    [action] = board["board_actions"]
    assert action["type"] == "draw_arrows" and action["board_id"]
    assert action["arrows"] == [{"from": "d2", "to": "d4", "brush": "green"}]
    # The arrow went out before the rest of the text.
    kinds = [next(iter(f)) for f in frames]
    assert kinds.index("board_actions") < max(i for i, k in enumerate(kinds) if k == "delta")
    session = session_store.get(frames[-1]["session_id"], "markup-user")
    assert [m for m in session.messages if m.role == "assistant"][-1].content == "Играй d4 — центр твой."
