"""Click-analysis on /position, /game, /puzzle (2026-10-28).

The page used to glue master stats, ChessDB candidates and every engine line
onto ``query``; with master stats the query passed 2000 characters and Hermes
answered 400 «Query too long» on every click. The grounding now travels in
``context_note`` (its own, larger cap) and reaches the model for this turn only.
The non-streaming answer also came back with raw ``[[arrows: …]]`` marks.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.middleware.rate_limiter import rate_limiter
from src.server import ANALYSIS_CONTEXT_MAX, app
from src.sessions import session_store
from src.user_profile import UserProfile

USER = "test-user-ctx"
HEADERS = {"X-User-Id": USER}
FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# The page's openingMove template (frontend/src/hooks/useChesster.ts), ~1.1k chars.
QUERY = """<chess_analysis_request>

<analysis_type>Opening Move Analysis</analysis_type>

<position_context>
Current FEN: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1
Opening: Unknown (N/A)
Side to Move: White
</position_context>

<move_information>
Move: e4
Games played: 1234567
Average rating: 2410
White wins: 33.1%
Draws: 45.2%
Black wins: 21.7%
</move_information>

<analysis_instructions>
Please follow this structure in your analysis:
1. First, describe the board state and key features of the position before the move (pawn structure, piece activity, king safety, imbalances, threats, etc).
2. Next, analyze the move itself: what does it change in the position, and what are its immediate tactical or strategic consequences?
3. Then, understand the opening stats, the win, draw, loss rates and amount of games that were played by masters.
4. Then, consider the engine lines and candidate moves: what alternatives were available, and how do they compare to the move played?
5. Take account of 1, 2, 3, 4 and provide the analysis for this move.

Be concise but thorough, and use clear chess language.
</analysis_instructions>
</chess_analysis_request>"""

# Master stats (12 moves, 3 top games) + 3 engine lines: what made the old query ~2.8k.
_MOVES = "\n".join(
    f"{san}: played {1000 - i * 60} times, white wins {33 + i}%, draws {45 - i}%, "
    f"black wins {22}%, average rating {2410 + i}"
    for i, san in enumerate(["e4", "d4", "Nf3", "c4", "g3", "b3", "f4", "Nc3", "b4", "e3", "d3", "a3"])
)
_GAMES = "\n".join(
    "Carlsen, Magnus (2863) vs Caruana, Fabiano (2820), 2019-03, result 1-0" for _ in range(3)
)
_ENGINE = "\n\n".join(
    f"  Line {i}: +0.3{i}\n    Moves: 1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6"
    for i in range(1, 4)
)
CONTEXT = (
    f"<opening_information>\n{_MOVES}\n\nTop games:\n{_GAMES}\n</opening_information>\n\n"
    f"<engine_analysis>\nDepth: 18\n{_ENGINE}\n</engine_analysis>"
)


@pytest.fixture(autouse=True)
def _clean():
    session_store._sessions.clear()
    rate_limiter.reset()
    yield
    session_store._sessions.clear()
    rate_limiter.reset()


def _agent(reply="Solid choice."):
    agent = MagicMock()
    agent.chat.return_value = reply
    return agent


@pytest.mark.unit
class TestAnalysisContextNote:
    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_long_click_request_succeeds_with_context_note(self, mock_profile, mock_agent):
        assert len(QUERY) + len(CONTEXT) > 2000  # the old single-query size was rejected
        mock_profile.return_value = UserProfile(user_id=USER)
        agent = _agent()
        mock_agent.return_value = agent

        resp = self.client.post(
            "/api/coach/analysis",
            headers=HEADERS,
            json={"fen": FEN, "query": QUERY, "context_note": CONTEXT, "context_type": "position"},
        )
        assert resp.status_code == 200, resp.text
        sent = agent.chat.call_args[0][0]
        # The model gets the grounding this turn …
        assert "<opening_information>" in sent and "<engine_analysis>" in sent
        assert "Opening Move Analysis" in sent
        # … but history keeps only the request itself.
        session = session_store.get(resp.json()["conversation_id"], USER)
        assert session.messages[0].content == QUERY

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_stream_long_click_request_succeeds_with_context_note(self, mock_profile, mock_agent):
        mock_profile.return_value = UserProfile(user_id=USER)
        agent = _agent()
        mock_agent.return_value = agent

        resp = self.client.post(
            "/api/coach/analysis/stream",
            headers=HEADERS,
            json={"fen": FEN, "query": QUERY, "context_note": CONTEXT},
        )
        assert resp.status_code == 200
        frames = [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]
        assert frames[-1].get("done") is True
        assert "<opening_information>" in agent.chat.call_args[0][0]

    def test_context_note_over_cap_400(self):
        resp = self.client.post(
            "/api/coach/analysis",
            headers=HEADERS,
            json={"fen": FEN, "query": "Explain", "context_note": "x" * (ANALYSIS_CONTEXT_MAX + 1)},
        )
        assert resp.status_code == 400
        assert "context" in resp.json()["error"].lower()

    def test_context_note_not_a_string_400(self):
        resp = self.client.post(
            "/api/coach/analysis",
            headers=HEADERS,
            json={"fen": FEN, "query": "Explain", "context_note": {"a": 1}},
        )
        assert resp.status_code == 400

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_non_streaming_answer_has_no_raw_marks(self, mock_profile, mock_agent):
        """/position «разобрать ход» showed «[[arrows: e2e4 green]]» in the text."""
        mock_profile.return_value = UserProfile(user_id=USER)
        mock_agent.return_value = _agent("The centre pawn goes first [[arrows: e2e4 green]]. Then the knight.")

        resp = self.client.post("/api/coach/analysis", headers=HEADERS, json={"fen": FEN, "query": "Explain"})
        body = resp.json()
        assert resp.status_code == 200
        assert "[[" not in body["response"] and "]]" not in body["response"]
        assert "The centre pawn goes first" in body["response"]
        arrows = [a for act in body["board_actions"] if act["type"] == "draw_arrows" for a in act["arrows"]]
        assert arrows == [{"from": "e2", "to": "e4", "brush": "green"}]
        session = session_store.get(body["conversation_id"], USER)
        assert "[[" not in session.messages[-1].content
