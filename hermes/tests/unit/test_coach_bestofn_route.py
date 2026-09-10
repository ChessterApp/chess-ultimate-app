"""Turn-path tests for best-of-N on /api/coach/chat (CL Phase 2, Slice 3).

Fully offline: the agent, the engine (evaluate_turn), and the judge LLM are all
mocked. Proves the two invariants that matter at the route level:

  * Flag OFF → byte-identical single-call path (the candidate generator, i.e.
    ``agent.chat``, is called EXACTLY once, with the streaming callback).
  * Flag ON + a FEN-anchored turn → the buffered best-of-N pipeline runs (N
    candidates generated non-streamed), and the engine-and-judge-selected winner
    is streamed back through the same SSE frames.
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import src.config as config
import src.server as server
from src.server import app
from src.sessions import session_store
from src.middleware.rate_limiter import rate_limiter
from src.user_profile import UserProfile


USER_HEADERS = {"X-User-Id": "bon-user"}
FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@pytest.fixture(autouse=True)
def _clear_state():
    session_store._sessions.clear()
    rate_limiter.reset()
    yield
    session_store._sessions.clear()
    rate_limiter.reset()


def _deltas(resp):
    """Concatenate the delta frames of an SSE response into the full reply."""
    parts = []
    done = False
    for line in resp.text.splitlines():
        if not line.startswith("data: "):
            continue
        frame = json.loads(line[len("data: "):])
        if "delta" in frame:
            parts.append(frame["delta"])
        if frame.get("done"):
            done = True
    return "".join(parts), done


def _agent(text, tokens=(100, 30)):
    a = MagicMock()
    a.tools = [{"function": {"name": "check_moves"}}]
    a._api_call_count = 1
    a.max_iterations = 5
    a.session_prompt_tokens = tokens[0]
    a.session_completion_tokens = tokens[1]
    a.chat.return_value = text
    return a


@pytest.mark.unit
class TestFlagOffByteIdentical:
    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server.log_event")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_flag_off_single_agent_call_with_fen(self, mock_profile, mock_agent, _log):
        """Even WITH a FEN, the flag-off path streams once — best-of-N is dormant."""
        assert config.COACH_BESTOFN is False  # default OFF
        mock_profile.return_value = UserProfile(user_id="bon-user")

        agent_instance = _agent("Play e4.")

        def _chat(message, stream_callback=None):
            if stream_callback:
                stream_callback("Play e4.")
            return "Play e4."

        agent_instance.chat.side_effect = _chat
        mock_agent.return_value = agent_instance

        resp = self.client.post(
            "/api/coach/chat", headers=USER_HEADERS,
            json={"message": "what move?", "fen": FEN},
        )
        assert resp.status_code == 200
        text, done = _deltas(resp)
        assert text == "Play e4." and done

        # The candidate generator ran exactly once, with the streaming callback —
        # the single-call, byte-identical contract.
        assert agent_instance.chat.call_count == 1
        assert "stream_callback" in agent_instance.chat.call_args.kwargs


@pytest.mark.unit
class TestFlagOnBestOfN:
    def setup_method(self):
        self.client = TestClient(app)

    @patch("src.server.log_event")
    @patch("src.bestofn.run_judge")
    @patch("src.bestofn.evaluate_turn")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_flag_on_runs_pipeline_and_streams_winner(
        self, mock_profile, mock_agent, mock_eval, mock_judge, _log
    ):
        mock_profile.return_value = UserProfile(user_id="bon-user")

        # Two distinct candidates: base agent (idx 0) + one fresh agent (idx 1).
        agent0 = _agent("candidate A")
        agent1 = _agent("candidate B")
        mock_agent.side_effect = [agent0, agent1]

        # Both candidates pass the engine gate; the judge prefers candidate 1.
        def _fake_eval(fen, text, user, depth):
            score = 0.9 if text == "candidate B" else 0.5
            return {"status": "ok", "correctness_score": score,
                    "illegal_move_rate": 0.0, "claims": [], "notes": []}

        mock_eval.side_effect = _fake_eval
        mock_judge.return_value = {"choice": 1, "reason": "clearer", "model": "cheap"}

        with patch.object(config, "COACH_BESTOFN", True), \
             patch.object(config, "COACH_BESTOFN_N", 2):
            resp = self.client.post(
                "/api/coach/chat", headers=USER_HEADERS,
                json={"message": "explain this", "fen": FEN},
            )

        assert resp.status_code == 200
        text, done = _deltas(resp)
        assert text == "candidate B" and done   # engine+judge winner streamed

        # Two candidates were generated, both BUFFERED (no streaming callback).
        assert agent0.chat.call_count == 1 and agent1.chat.call_count == 1
        assert "stream_callback" not in agent0.chat.call_args.kwargs
        assert "stream_callback" not in agent1.chat.call_args.kwargs
        # The judge was consulted over the survivors.
        assert mock_judge.call_count == 1

    @patch("src.server.log_event")
    @patch("src.bestofn.run_judge")
    @patch("src.bestofn.evaluate_turn")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_flag_on_no_fen_takes_normal_path(
        self, mock_profile, mock_agent, mock_eval, mock_judge, _log
    ):
        """Flag ON but NO FEN → normal single-streamed path, best-of-N dormant."""
        mock_profile.return_value = UserProfile(user_id="bon-user")
        agent_instance = _agent("normal reply")

        def _chat(message, stream_callback=None):
            if stream_callback:
                stream_callback("normal reply")
            return "normal reply"

        agent_instance.chat.side_effect = _chat
        mock_agent.return_value = agent_instance

        with patch.object(config, "COACH_BESTOFN", True):
            resp = self.client.post(
                "/api/coach/chat", headers=USER_HEADERS,
                json={"message": "just chatting"},   # no fen
            )
        assert resp.status_code == 200
        text, _ = _deltas(resp)
        assert text == "normal reply"
        # Single streamed call; engine/judge never touched.
        assert agent_instance.chat.call_count == 1
        mock_eval.assert_not_called()
        mock_judge.assert_not_called()

    @patch("src.server.log_event")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_bestofn_import_failure_falls_back_to_normal_stream(
        self, mock_profile, mock_agent, _log, monkeypatch
    ):
        """Task 2 fail-open: if importing the best-of-N pipeline raises (prod
        incident: missing src.eval/src.optimize), the turn degrades to the normal
        streaming path — one streamed agent.chat call, no SSE error frame."""
        mock_profile.return_value = UserProfile(user_id="bon-user")
        agent_instance = _agent("safe fallback reply")

        def _chat(message, stream_callback=None):
            if stream_callback:
                stream_callback("safe fallback reply")
            return "safe fallback reply"

        agent_instance.chat.side_effect = _chat
        mock_agent.return_value = agent_instance

        # Make `from src import bestofn` raise ImportError inside the route.
        # Both the cached submodule AND the parent-package attribute must be
        # cleared, else the from-import resolves the stale cached attribute.
        import src as src_pkg

        monkeypatch.delattr(src_pkg, "bestofn", raising=False)
        monkeypatch.setitem(sys.modules, "src.bestofn", None)

        with patch.object(config, "COACH_BESTOFN", True), \
             patch.object(config, "COACH_BESTOFN_N", 2):
            resp = self.client.post(
                "/api/coach/chat", headers=USER_HEADERS,
                json={"message": "explain this", "fen": FEN},
            )

        assert resp.status_code == 200
        text, done = _deltas(resp)
        assert text == "safe fallback reply" and done
        # Degraded to the normal single streamed call — no error frame.
        assert agent_instance.chat.call_count == 1
        assert "stream_callback" in agent_instance.chat.call_args.kwargs
        assert "error" not in resp.text
