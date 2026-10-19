"""2026-10-20: the hidden board for theory questions (src/question_position.py).

The position a theory question is about — an opening line's end, a famous game, a textbook endgame
named by its material, a topic's example — is built and analysed on a board the student does not see;
their own position stays in front of them unless the board is nobody's or they ask («покажи»). The
lesson chat on /learn shows the lesson's diagram beside the answer (`diagram` frame).
"""

import json
from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src import config
from src.board_lock import _board_lock_level, board_lock_with_owner
from src.boards import new_board
from src.famous_games import famous_game
from src.intent import read_intent
from src.position_facts import static_facts
from src.question_position import (
    ENDGAMES, board_material, endgame_block, endgame_theory, material_in, show_on_board, student_owns, wants_shown,
)
from src.server import app, session_store
from src.user_profile import UserProfile

OWN = "r2q1rk1/pp2bppp/4bn2/3P4/8/2N2N2/PP2BPPP/R2Q1RK1 b - - 0 12"   # the student's own position
R_V_P = "8/8/8/8/3k4/3p4/8/R3K3 w - - 0 1"                             # a rook against a pawn, on the board


# ── the textbook endgames ───────────────────────────────────────────────────

@pytest.mark.parametrize("key", sorted(ENDGAMES))
def test_every_textbook_position_is_legal_and_quiet(key):
    entry = ENDGAMES[key]
    board = chess.Board(entry["fen"])
    assert board.is_valid() and not board.is_check() and (not board.is_game_over() or key in ("B|", "N|"))  # a lone minor piece: drawn at once
    assert not [f for f in static_facts(board) if "not defended" in f or "cheaper" in f], key
    assert entry["result"] in ("win", "draw", "depends") and len(entry["method"]) > 40
    strong, weak = key.split("|")
    assert board_material(entry["fen"]) == (strong, weak)


@pytest.mark.parametrize("text,sides", [
    ("ферзь против ладьи — это выигрыш?", ("Q", "R")),
    ("ладья против ферзя", ("Q", "R")),                       # the stronger side first, whatever the order
    ("как поставить мат ладьёй", ("R", "")),
    ("мат двумя слонами", ("BB", "")),
    ("конём и слоном можно заматовать?", ("BN", "")),
    ("ладья и слон против ладьи", ("RB", "R")),
    ("король и пешка против короля", ("P", "")),
    ("два коня против короля", ("NN", "")),
    ("queen vs rook", ("Q", "R")),
    ("how do I mate with two bishops", ("BB", "")),
    ("слон против коня кто сильнее", ("B", "N")),
    ("мат конём", None),                                      # a tactic (the site's set), not an endgame
    ("мат слоном в два хода", None),
    ("что такое вилка", None),
    ("расскажи про ладейный эндшпиль", None),
    ("мат в два хода", None),
    ("как ходит конь", None),
])
def test_the_material_the_words_name(text, sides):
    assert material_in(text) == sides


def test_the_theory_for_the_material():
    th = endgame_theory("ферзь против ладьи — выигрыш?")
    assert th["key"] == "Q|R" and th["result"] == "win" and th["title"] == "Ферзь против ладьи"
    assert endgame_theory("мат конём и слоном")["title"] == "Слон и конь против короля"
    assert endgame_theory("король и пешка против короля")["title"] == "Король и пешка против короля"
    assert endgame_theory("ладья и слон против ладьи")["title"] == "Ладья и слон против ладьи"
    assert endgame_theory("ферзь и две ладьи против короля") is None   # not in the table
    block = endgame_block(th, "[Engine] … Best: Qf4+", shown=False)
    assert "HIDDEN board" in block and "a WIN for the stronger side" in block and "Qf4+" in block
    assert "ALREADY put it" in endgame_block(th, None, shown=True)


# ── whose board it is ───────────────────────────────────────────────────────

def test_the_students_own_position_and_the_coachs():
    board = new_board("s", fen=chess.STARTING_FEN)
    assert not student_owns(board) and show_on_board("что такое вилка", board)
    board.set_fen(OWN)
    assert student_owns(board) and not show_on_board("что такое вилка", board)
    assert show_on_board("покажи пример вилки", board) and wants_shown("поставь на доску") and not wants_shown("объясни")
    board.mark_coach("set_fen")
    assert not student_owns(board) and show_on_board("что такое вилка", board)
    board.set_fen(R_V_P)  # the student sets a fresh position: theirs again
    assert student_owns(board)


def test_the_lock_keeps_the_students_own_position_unless_they_ask():
    assert _board_lock_level("что такое вилка", True, False, OWN, owned=True) == (OWN, False, "owned")
    assert _board_lock_level("покажи пример вилки", True, False, OWN, owned=True) == (None, False, "")
    assert _board_lock_level("дай задачу на вилку", True, False, OWN, owned=True)[0] is None  # a puzzle still goes up
    assert _board_lock_level("что такое вилка", True, False, OWN, owned=False) == (None, False, "")
    assert _board_lock_level("какой здесь лучший ход", True, False, OWN, owned=True)[2] == "asked"
    assert _board_lock_level("что такое вилка", True, False, chess.STARTING_FEN, owned=True)[0] is None


def test_the_lock_reads_the_owner_from_the_session():
    session = session_store.create(user_id="u-hidden", session_id="hidden-lock")
    session.set_board_state(OWN)
    assert board_lock_with_owner("что такое вилка", True, False, session) == (OWN, False, "owned")
    session.apply_board_actions([{"type": "set_fen", "fen": R_V_P}])
    assert board_lock_with_owner("что такое вилка", True, False, session)[0] is None  # the coach's position


# ── the tools: get_topic, lookup_opening, the famous game, the intent ───────

def test_get_topic_teaches_a_textbook_endgame_with_its_position_and_the_engines_look():
    from src.tools import knowledge_topics as kt

    out = kt.get_topic("ферзь против ладьи", with_lessons=False)
    assert out["source"] == "endgame_theory" and out["result"] == "win" and out["title"] == "Ферзь против ладьи"
    assert out["board_actions"] == [{"type": "set_fen", "fen": ENDGAMES["Q|R"]["fen"]}]
    assert out["example"]["engine"].startswith("[Engine]") and "ALREADY" in out["board_hint"]
    hidden = kt.get_topic("ферзь против ладьи", with_lessons=False, show=False)
    assert "board_actions" not in hidden and "HIDDEN" in hidden["board_hint"]
    # The base's own topic keeps the lead for the elementary mates, with the theory attached.
    out = kt.get_topic("как поставить мат ладьёй", with_lessons=False)
    assert out["slug"] == "basic-checkmates" and out["endgame_theory"]["result"] == "win"
    # A base example is looked at on the hidden board too: facts and the engine's line.
    out = kt.get_topic("связка", with_lessons=False)
    assert out["slug"] == "pin" and out["example"]["engine"].startswith("[Engine]") and isinstance(out["example"]["facts"], list)


def test_the_topic_handler_keeps_the_students_board_and_still_brings_the_example():
    from src.sessions import BOARD_KEPT_NOTE, HIDDEN_BOARD_NOTE
    from src.tools.knowledge_topics import _handle_get_topic

    session = session_store.create(user_id="u-hidden", session_id="hidden-topic")
    session.set_board_state(OWN)
    session.lock_board(OWN, strict=False, reason="owned")
    out = json.loads(_handle_get_topic({"topic": "вилка"}, session_id=session.id))
    assert "board_actions" not in out and out["board_hint"] == HIDDEN_BOARD_NOTE
    assert out["example"]["fen"] and out["example"]["engine"].startswith("[Engine]")
    session.lock_board(OWN, strict=False, reason="asked")
    out = json.loads(_handle_get_topic({"topic": "вилка"}, session_id=session.id))
    assert "board_actions" not in out and out["board_hint"] == BOARD_KEPT_NOTE and "example" not in out
    session.lock_board(None)


def test_lookup_opening_keeps_the_students_board_and_analyses_the_line_hidden():
    from src.tools.opening_lookup import _handle_lookup_opening

    session = session_store.create(user_id="u-hidden", session_id="hidden-opening")
    session.set_board_state(OWN)
    out = json.loads(_handle_lookup_opening({"question": "расскажи про жареную печень"}, session_id=session.id,
                                            student_message="расскажи про жареную печень"))
    assert out["found"] and out["hidden"] and not out["loaded"] and "board_actions" not in out
    assert out["hidden_board"]["engine"].startswith("[Engine]") and "HIDDEN board" in out["note"]
    out = json.loads(_handle_lookup_opening({"question": "покажи жареную печень"}, session_id=session.id,
                                            student_message="покажи жареную печень"))
    assert out["loaded"] and out["board_actions"][0]["type"] == "load_pgn"


def test_the_famous_game_is_told_not_loaded_on_the_students_board():
    hidden = famous_game("расскажи про оперную партию Морфи", hidden=True)
    assert hidden["hidden"] and "NOT on the student's board" in hidden["block"] and "покажи" in hidden["block"]
    assert not famous_game("покажи оперную партию")["hidden"]


def test_the_voice_intent_sends_a_material_question_to_the_topic():
    assert read_intent("ферзь против ладьи — это выигрыш?", fen=OWN) == {"kind": "concept", "topic": "ферзь против ладьи — это выигрыш?"}
    assert read_intent("как поставить мат двумя слонами", fen=OWN)["kind"] == "concept"
    assert read_intent("привет", fen=OWN)["kind"] == "none"


def test_the_voice_tool_call_runs_under_the_owner_lock():
    from src.tool_bridge import _dispatch_voice

    session = session_store.create(user_id="u-hidden", session_id="hidden-voice")
    session.set_board_state(OWN)
    out = json.loads(_dispatch_voice("get_topic", {"topic": "вилка"}, session, "что такое вилка"))
    assert "board_actions" not in out and "hidden board" in out["board_hint"] and out["example"]["fen"]
    assert session.board_lock is None  # released after the call
    out = json.loads(_dispatch_voice("get_topic", {"topic": "вилка"}, session, "покажи пример вилки"))
    assert out["board_actions"][0]["type"] == "set_fen"


# ── the text turn ───────────────────────────────────────────────────────────

@pytest.mark.unit
class TestTurn:
    @pytest.fixture(autouse=True)
    def _engine_in_time(self, monkeypatch):
        # The engine line is on (the root conftest turns it off), a short search with a long wait: the turn's
        # engine line must be in the message, whatever the machine.
        monkeypatch.setattr(config, "COACH_ENGINE_NOTE", True)
        monkeypatch.setattr(config, "COACH_ENGINE_NOTE_MOVETIME_MS", 300)
        monkeypatch.setattr(config, "COACH_ENGINE_NOTE_WAIT_MS", 10000)

    def setup_method(self):
        self.client = TestClient(app)
        self.user = {"X-User-Id": "hidden-turn-user"}
        self.sid = self.client.post("/api/coach/sessions", headers=self.user).json()["id"]

    def _turn(self, mock_agent, mock_profile, message: str, fen: str):
        mock_profile.return_value = UserProfile(user_id="hidden-turn-user")
        agent = MagicMock()
        seen = {}

        def _chat(msg, stream_callback=None):
            seen["message"] = msg
            if stream_callback:
                stream_callback("Понятно.")
            return "Понятно."

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent
        resp = self.client.post("/api/coach/chat", headers=self.user, json={"message": message, "session_id": self.sid, "fen": fen})
        assert resp.status_code == 200
        frames = [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]
        actions = [a for f in frames for a in f.get("board_actions", [])]
        return seen["message"], actions

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_an_endgame_by_material_goes_on_a_default_board_and_stays_hidden_on_the_students(self, mock_profile, mock_agent):
        message, actions = self._turn(mock_agent, mock_profile, "ферзь против ладьи — это выигрыш?", chess.STARTING_FEN)
        assert actions[0] == {"type": "set_fen", "fen": ENDGAMES["Q|R"]["fen"], "board_id": session_store.get(self.sid).active_board_id}
        assert "Ферзь против ладьи" in message and "ALREADY put it on the student's board" in message
        assert "Engine and tablebase on that position: [Engine]" in message
        session = session_store.get(self.sid, "hidden-turn-user")
        assert session.board_state == ENDGAMES["Q|R"]["fen"]

        message, actions = self._turn(mock_agent, mock_profile, "а ладья против слона?", OWN)
        assert not actions and "Ладья против слона" in message and "on a HIDDEN board" in message
        assert session_store.get(self.sid, "hidden-turn-user").board_state == OWN

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_the_students_own_ending_of_that_material_is_answered_from_their_board(self, mock_profile, mock_agent):
        message, actions = self._turn(mock_agent, mock_profile, "ладья против пешки — это выигрыш?", R_V_P)
        assert not actions and "Ладья против пешки" not in message
        assert "## Engine analysis of the board" in message

    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_a_famous_game_is_told_from_a_hidden_board_on_the_students_position(self, mock_profile, mock_agent):
        message, actions = self._turn(mock_agent, mock_profile, "расскажи про оперную партию Морфи", OWN)
        assert not actions and "NOT on the student's board" in message
        assert "## Engine analysis on a hidden board — the final position of" in message
        assert session_store.get(self.sid, "hidden-turn-user").board_state == OWN


# ── the lesson chat: the diagram beside the answer ──────────────────────────

@pytest.mark.unit
class TestLessonDiagram:
    PIN_FEN = "8/2k5/8/8/2b5/8/2Q4K/8 w - - 0 1"

    def setup_method(self):
        self.client = TestClient(app)

    def _events(self, mock_stream, message: str):
        mock_stream.return_value = iter(["Связка — это нападение."])
        resp = self.client.post("/api/lesson/chat", headers={"X-User-Id": "lesson-user"}, json={
            "message": message, "lesson_title": "Связка", "lesson_content": "", "course_slug": "chess-basics",
            "lesson_id": "no-such-id", "locale": "ru",
        })
        return [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")], mock_stream.call_args.args[1]

    @patch("src.server._lesson_chat_stream")
    def test_a_theory_question_brings_the_lessons_diagram(self, mock_stream):
        events, prompt = self._events(mock_stream, "что такое связка?")
        assert events[0]["diagram"]["fen"] == self.PIN_FEN and events[0]["diagram"]["n"] == 1 and events[0]["diagram"]["of"] == 2
        assert "Связка" in events[0]["diagram"]["caption"]
        assert f"Diagram 1 of 2 ({self.PIN_FEN}) is SHOWN to the student" in prompt
        assert "".join(e.get("delta", "") for e in events) == "Связка — это нападение."

    @patch("src.server._lesson_chat_stream")
    def test_the_second_diagram_by_its_number_and_none_for_the_puzzle(self, mock_stream):
        events, _ = self._events(mock_stream, "покажи вторую диаграмму")
        assert events[0]["diagram"]["n"] == 2
        events, prompt = self._events(mock_stream, "какой здесь первый ход?")
        assert not any("diagram" in e for e in events) and "is SHOWN" not in prompt
