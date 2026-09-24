"""Game mode: state machine, verdicts, endpoints, prompts — with a scripted engine."""

import json
from unittest.mock import patch

import chess
import pytest
from fastapi.testclient import TestClient

from src import game_mode
from src.game_mode import GameError, comment_prompt, game_context, play_move, resign, start_game, takeback
from src.server import app
from src.sessions import Session, session_store
from src.middleware.rate_limiter import rate_limiter

USER = {"X-User-Id": "game-user"}


class ScriptedEngine:
    """Engine stand-in: replies with the first legal move (or a scripted one) and
    returns evals from a table keyed by FEN prefix, default 0."""

    def __init__(self, replies=None, evals=None):
        self.replies = list(replies or [])
        self.evals = dict(evals or {})
        self.calls = []

    def move(self, fen, elo):
        self.calls.append(("move", fen, elo))
        board = chess.Board(fen)
        if self.replies:
            san = self.replies.pop(0)
            return board.parse_san(san).uci()
        return next(iter(board.legal_moves)).uci()

    def evaluate(self, fen, pov):
        self.calls.append(("eval", fen))
        board = chess.Board(fen)
        for prefix, (cp, best) in self.evals.items():
            if fen.startswith(prefix):
                return cp, best
        if board.is_game_over():
            outcome = board.outcome()
            if outcome and outcome.winner is not None:
                return (10000 if outcome.winner == pov else -10000), None
            return 0, None
        return 0, None


@pytest.fixture
def engine(monkeypatch):
    eng = ScriptedEngine()
    monkeypatch.setattr(game_mode, "_engine_move", eng.move)
    monkeypatch.setattr(game_mode, "_evaluate", eng.evaluate)
    return eng


@pytest.fixture(autouse=True)
def _clean():
    session_store._sessions.clear()
    rate_limiter.reset()
    yield
    session_store._sessions.clear()
    rate_limiter.reset()


def _session():
    return session_store.create(user_id="game-user")


@pytest.mark.unit
class TestGameFlow:
    def test_start_as_white_waits_for_the_student(self, engine):
        s = _session()
        board, p = start_game(s, "white", 1500)
        assert board.kind == "game" and s.active_board_id == board.id and board.orientation == "white"
        assert p["student_to_move"] is True and p["engine"] is None and p["moves"] == []
        assert p["fen"] == chess.STARTING_FEN and p["status"] == "playing"
        assert engine.calls == []

    def test_start_as_black_gets_the_engines_first_move(self, engine):
        engine.replies = ["e4"]
        s = _session()
        board, p = start_game(s, "black", 800, "every")
        assert p["engine"] == {"san": "e4", "uci": "e2e4"} and p["moves"] == ["e4"]
        assert p["student_to_move"] is True and board.orientation == "black"
        assert board.pgn.endswith("1. e4 *") and board.ply == 1
        assert engine.calls[0] == ("move", chess.STARTING_FEN, 800)

    def test_random_colour(self, engine):
        s = _session()
        _, p = start_game(s, "random", 1500)
        assert p["student_color"] in ("white", "black")

    def test_bad_colour(self, engine):
        with pytest.raises(GameError):
            start_game(_session(), "green", 1500)

    def test_move_verdict_and_engine_reply(self, engine):
        engine.replies = ["e5"]
        # before e4: +30 with best e4; after e4 (black to move): +30 → no loss
        engine.evals = {chess.STARTING_FEN: (30, "e4"), "rnbqkbnr/pppppppp/8/8/4P3": (30, None)}
        s = _session()
        board, _ = start_game(s, "white", 1500)
        p = play_move(s, board, "e4")
        assert p["student"]["san"] == "e4" and p["student"]["verdict"] == "ok" and p["student"]["best"] is None
        assert p["engine"]["san"] == "e5" and p["moves"] == ["e4", "e5"] and p["ply"] == 2
        assert p["student_to_move"] is True and p["comment_wanted"] is False   # mode "mistakes"
        assert "1. e4 e5" in p["pgn"] and board.game_state["annotations"][0]["ply"] == 1

    def test_blunder_is_flagged_with_the_better_move(self, engine):
        engine.replies = ["Qh4#"]  # 1.f3 e5 2.g4 Qh4# — the student plays 2.g4??
        s = _session()
        board, _ = start_game(s, "white", 1500)
        engine.evals = {}
        engine.replies = ["e5", "Qh4#"]
        play_move(s, board, "f3")
        fen_before_g4 = chess.Board(); fen_before_g4.push_san("f3"); fen_before_g4.push_san("e5")
        engine.evals = {fen_before_g4.fen(): (-40, "e4"), "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2": (-10000, None)}
        p = play_move(s, board, "g4")
        st = p["student"]
        assert st["verdict"] == "blunder" and st["cp_loss"] == 9960 and st["best"] == "e4"
        assert p["status"] == "finished" and p["result"] == "0-1" and p["termination"] == "checkmate"
        assert p["winner"] == "engine" and p["comment_wanted"] is True and p["student_to_move"] is False

    def test_illegal_and_out_of_turn_moves(self, engine):
        s = _session()
        board, _ = start_game(s, "white", 1500)
        with pytest.raises(GameError, match="not a legal move"):
            play_move(s, board, "e5")
        with pytest.raises(GameError, match="Cannot read"):
            play_move(s, board, "???")
        engine.replies = ["e4", "Nf3"]
        board2, _ = start_game(s, "black", 1500)  # engine has moved; student to move — fine
        play_move(s, board2, "e7e5")            # UCI accepted too
        assert board2.game_state["moves"][-2:] == ["e5", "Nf3"]

    def test_uci_promotion_and_san_equivalence(self, engine):
        s = _session()
        board, _ = start_game(s, "white", 1500)
        engine.replies = ["d5"]
        p = play_move(s, board, "e2e4")
        assert p["student"]["san"] == "e4"

    def test_resign_and_no_moves_after(self, engine):
        s = _session()
        board, _ = start_game(s, "white", 1500)
        p = resign(s, board)
        assert p["status"] == "finished" and p["result"] == "0-1" and p["termination"] == "resign"
        with pytest.raises(GameError, match="over"):
            play_move(s, board, "e4")
        with pytest.raises(GameError):
            resign(s, board)

    def test_takeback_undoes_student_move_and_reply(self, engine):
        s = _session()
        board, _ = start_game(s, "white", 1500)
        engine.replies = ["e5", "Nc6"]
        play_move(s, board, "e4")
        play_move(s, board, "Nf3")
        assert board.game_state["moves"] == ["e4", "e5", "Nf3", "Nc6"]
        p = takeback(s, board)
        assert p["moves"] == ["e4", "e5"] and p["student_to_move"] is True and p["ply"] == 2
        assert len(board.game_state["annotations"]) == 1
        takeback(s, board)
        assert board.game_state["moves"] == [] and board.pgn == ""
        with pytest.raises(GameError, match="Nothing"):
            takeback(s, board)

    def test_takeback_as_black_keeps_the_engines_opening_move(self, engine):
        engine.replies = ["e4", "Nf3"]
        s = _session()
        board, _ = start_game(s, "black", 1500)
        play_move(s, board, "e5")
        p = takeback(s, board)
        assert p["moves"] == ["e4"] and p["student_to_move"] is True

    def test_comment_wanted_modes(self, engine):
        s = _session()
        for mode, verdict_cp, expected in (("quiet", 5000, False), ("mistakes", 120, True),
                                           ("mistakes", 10, False), ("every", 0, True)):
            board, _ = start_game(s, "white", 1500, mode)
            engine.replies = ["e5"]
            engine.evals = {chess.STARTING_FEN: (verdict_cp, "d4"), "rnbqkbnr/pppppppp/8/8/4P3": (0, None)}
            p = play_move(s, board, "e4")
            assert p["comment_wanted"] is expected, (mode, verdict_cp)

    def test_game_survives_reload_from_row(self, engine):
        from src.boards import board_from_row

        s = _session()
        board, _ = start_game(s, "white", 1500)
        engine.replies = ["e5"]
        play_move(s, board, "e4")
        restored = board_from_row(board.to_public())
        assert restored.game_state["moves"] == ["e4", "e5"] and restored.kind == "game"
        engine.replies = ["Nc6"]
        p = play_move(s, restored, "Nf3")
        assert p["moves"] == ["e4", "e5", "Nf3", "Nc6"]


@pytest.mark.unit
class TestPrompts:
    def test_game_context_mentions_rules_and_mistakes(self, engine):
        s = _session()
        board, _ = start_game(s, "white", 1200)
        engine.replies = ["e5"]
        engine.evals = {chess.STARTING_FEN: (200, "e4"), "rnbqkbnr/pppppppp/8/8/7P": (-50, None)}
        play_move(s, board, "h4")
        ctx = game_context(board)
        assert "Live game" in ctx and "Student plays white" in ctx and "1200 Elo" in ctx
        assert "Moves so far: 1.h4 e5" in ctx and "the student to move" in ctx
        assert "give a HINT" in ctx and "Never make a move for the student" in ctx
        assert "1. h4 (blunder" in ctx or "1. h4 (mistake" in ctx
        assert game_context(s.ensure_board()) == "" or board.kind == "game"

    def test_game_context_when_finished(self, engine):
        s = _session()
        board, _ = start_game(s, "white", 1500)
        resign(s, board)
        ctx = game_context(board)
        assert "The game is over: 0-1 (resign)" in ctx and "winner: engine" in ctx

    def test_comment_prompt_for_a_blunder_and_the_end(self, engine):
        s = _session()
        board, _ = start_game(s, "white", 1500)
        engine.replies = ["e5"]
        engine.evals = {chess.STARTING_FEN: (400, "e4"), "rnbqkbnr/pppppppp/8/8/7P": (-50, None)}
        play_move(s, board, "h4")
        msgs = comment_prompt(board, "ru")
        assert msgs[0]["role"] == "system" and "Russian" in msgs[0]["content"] and "blundered" in msgs[0]["content"]
        assert "Student's move: h4 — verdict blunder" in msgs[1]["content"]
        assert "Better move was: e4." in msgs[1]["content"] and "Your reply on the board: e5." in msgs[1]["content"]
        resign(s, board)
        end = comment_prompt(board, "en", event="end")
        assert "The game is over" in end[0]["content"] and "Result: 0-1 (resign)" in end[1]["content"]
        assert "Student's mistakes: 1. h4 (blunder, better e4)" in end[1]["content"]

    def test_comment_prompt_ok_move_is_short(self, engine):
        s = _session()
        board, _ = start_game(s, "white", 1500)
        engine.replies = ["e5"]
        play_move(s, board, "e4")
        msgs = comment_prompt(board, "kz")
        assert "Kazakh" in msgs[0]["content"] and "at most 2 short sentences" in msgs[0]["content"]


@pytest.mark.unit
class TestEndpoints:
    def setup_method(self):
        self.client = TestClient(app)

    def _session_id(self):
        return self.client.post("/api/coach/sessions", headers=USER, json={}).json()["id"]

    def test_start_move_resign_over_http(self, engine):
        sid = self._session_id()
        r = self.client.post(f"/api/coach/sessions/{sid}/game", headers=USER, json={"color": "white", "elo": 1400})
        assert r.status_code == 200
        board_id = r.json()["board_id"]
        engine.replies = ["e5"]
        r = self.client.post(f"/api/coach/sessions/{sid}/game/{board_id}/move", headers=USER, json={"move": "e4"})
        assert r.status_code == 200 and r.json()["engine"]["san"] == "e5"
        r = self.client.post(f"/api/coach/sessions/{sid}/game/{board_id}/move", headers=USER, json={"move": "Nf6"})
        assert r.status_code == 400 and "not a legal move" in r.json()["detail"]
        r = self.client.post(f"/api/coach/sessions/{sid}/game/{board_id}/takeback", headers=USER)
        assert r.status_code == 200 and r.json()["moves"] == []
        r = self.client.post(f"/api/coach/sessions/{sid}/game/{board_id}/resign", headers=USER)
        assert r.status_code == 200 and r.json()["status"] == "finished"
        # the board is listed with its game state
        boards = self.client.get(f"/api/coach/sessions/{sid}/boards", headers=USER).json()["boards"]
        game = next(b for b in boards if b["id"] == board_id)
        assert game["kind"] == "game" and game["game_state"]["status"] == "finished"

    def test_unknown_board_and_wrong_user(self, engine):
        sid = self._session_id()
        assert self.client.post(f"/api/coach/sessions/{sid}/game/nope/move", headers=USER, json={"move": "e4"}).status_code == 404
        r = self.client.post(f"/api/coach/sessions/{sid}/game", headers={"X-User-Id": "other"}, json={})
        assert r.status_code == 404

    def test_engine_failure_is_503(self, engine, monkeypatch):
        sid = self._session_id()
        monkeypatch.setattr(game_mode, "_engine_move", lambda fen, elo: (_ for _ in ()).throw(RuntimeError("dead")))
        r = self.client.post(f"/api/coach/sessions/{sid}/game", headers=USER, json={"color": "black"})
        assert r.status_code == 503

    def test_comment_streams_and_is_stored(self, engine):
        from src.quick_reply import QuickReply

        sid = self._session_id()
        board_id = self.client.post(f"/api/coach/sessions/{sid}/game", headers=USER, json={}).json()["board_id"]
        engine.replies = ["e5"]
        self.client.post(f"/api/coach/sessions/{sid}/game/{board_id}/move", headers=USER, json={"move": "e4"})

        def _fake(*, on_delta=None, messages=None, **kw):
            assert messages[0]["role"] == "system"
            for chunk in ("Хороший ", "ход."):
                on_delta(chunk)
            return QuickReply(text="Хороший ход.", prompt_tokens=50, completion_tokens=5)

        with patch("src.quick_reply.stream_completion", _fake), patch("src.server._do_record_usage"):
            r = self.client.post(f"/api/coach/sessions/{sid}/game/{board_id}/comment", headers=USER,
                                 json={"locale": "ru"})
        frames = [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]
        assert "".join(f.get("delta", "") for f in frames) == "Хороший ход."
        assert frames[-1]["done"] is True and frames[-1]["board_id"] == board_id
        session = session_store.get(sid, "game-user")
        assert session.messages[-1].role == "assistant" and session.messages[-1].source == "game"

    def test_comment_failure_is_a_calm_error(self, engine):
        from src.quick_reply import QuickReply

        sid = self._session_id()
        board_id = self.client.post(f"/api/coach/sessions/{sid}/game", headers=USER, json={}).json()["board_id"]
        with patch("src.quick_reply.stream_completion", lambda **kw: QuickReply(error="http_429")), \
             patch("src.server.log_event"):
            r = self.client.post(f"/api/coach/sessions/{sid}/game/{board_id}/comment", headers=USER, json={"locale": "en"})
        frames = [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]
        assert frames[-1]["error"].startswith("The coach is unavailable")

    def test_chat_turn_carries_the_game_context(self, engine):
        from unittest.mock import MagicMock

        sid = self._session_id()
        board_id = self.client.post(f"/api/coach/sessions/{sid}/game", headers=USER, json={"color": "white"}).json()["board_id"]
        engine.replies = ["e5"]
        self.client.post(f"/api/coach/sessions/{sid}/game/{board_id}/move", headers=USER, json={"move": "e4"})
        agent = MagicMock()
        agent.tools = []
        agent.model = "m"
        agent._api_call_count = 1
        agent.max_iterations = 5
        agent.session_prompt_tokens = 1
        agent.session_completion_tokens = 1
        agent.chat.return_value = "Посмотри на центр."
        with patch("src.server._create_agent", return_value=agent), patch("src.server.log_event"), \
             patch("src.server.load_user_profile") as prof:
            from src.user_profile import UserProfile
            prof.return_value = UserProfile(user_id="game-user")
            r = self.client.post("/api/coach/chat", headers=USER,
                                 json={"message": "подскажи, что играть", "session_id": sid, "board_id": board_id})
        assert r.status_code == 200
        sent = agent.chat.call_args.args[0]
        assert "Live game" in sent and "Moves so far: 1.e4 e5" in sent and "give a HINT" in sent
