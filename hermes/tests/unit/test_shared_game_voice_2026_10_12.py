"""2026-10-12: what one coach could do and the other could not.

The game in words (start_game / make_game_move) for the text coach and the voice coach alike; the
board lock, the famous games and «на 8-м ходу» for the voice coach, as the text coach has them.
"""

import json

import chess
import pytest
from tools.registry import registry

from src import config, game_mode, tool_bridge
from src.sessions import session_store
from src.tools import discover_and_register

GAME = ("1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Nc3 Bc5 5. d3 d6 6. Bg5 h6 7. Bh4 g5 8. Bg3 Bg4 "
        "9. h3 Bxf3 10. Qxf3 Nd4 11. Qd1 c6 12. O-O Qe7 13. a3 O-O-O 14. b4 Bb6 15. a4 a5")
POS = "r2q1rk1/pp2bppp/4bn2/3P4/8/2N2N2/PP2BPPP/R2Q1RK1 b - - 0 12"


@pytest.fixture(autouse=True)
def _engine(monkeypatch):
    """No Stockfish in unit tests: the engine answers with its first legal move, every position equal."""
    discover_and_register()
    monkeypatch.setattr(game_mode, "_engine_move", lambda fen, elo: next(iter(chess.Board(fen).legal_moves)).uci())
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))


def _call(name, args, session):
    return json.loads(registry.dispatch(name, args, session_id=session.id))


# ── the game in words ────────────────────────────────────────────────────────

def test_start_game_starts_the_buttons_game_and_says_the_engines_first_move():
    session = session_store.create(user_id="game-words-1")
    out = _call("start_game", {"color": "black", "elo": 1300}, session)
    action = out["board_actions"][0]
    assert action["type"] == "game" and action["game"]["student_color"] == "black"
    assert action["game"]["engine_elo"] == 1200 and action["game"]["comment_mode"] == "quiet"
    assert out["engine_first_move"] and out["to_move"] == "the student's move"
    board = session.get_board(session.active_board_id)
    assert board.kind == "game" and board.game_state["status"] == "playing"
    # one game at a time
    assert "already on" in _call("start_game", {}, session)["error"]


@pytest.mark.parametrize("said,san", [("е4", "e4"), ("e2e4", "e4"), ("пешка е4", "e4"), ("Кf3", "Nf3"), ("Nf3", "Nf3")])
def test_make_game_move_plays_the_students_move_however_written(said, san):
    session = session_store.create(user_id=f"game-words-{said}")
    _call("start_game", {"color": "white"}, session)
    out = _call("make_game_move", {"move": said}, session)
    assert out["ok"] and out["student_move"] == san and out["engine_reply"]
    game = out["board_actions"][0]["game"]
    assert game["moves"][0] == san and len(game["moves"]) == 2 and game["student_to_move"]


def test_an_illegal_move_is_refused_with_the_legal_ones():
    session = session_store.create(user_id="game-words-illegal")
    _call("start_game", {"color": "white"}, session)
    out = _call("make_game_move", {"move": "Qh5"}, session)
    assert "not a legal move" in out["error"] and "e4" in out["legal_moves"]
    assert "No game is on" in _call("make_game_move", {"move": "e4"}, session_store.create(user_id="no-game"))["error"]


def test_the_game_action_passes_the_board_truth_and_the_strict_lock():
    """A live game locks the board strictly; the game's own state still goes out."""
    session = session_store.create(user_id="game-words-lock")
    _call("start_game", {"color": "white"}, session)
    session.lock_board(session.board_state, strict=True)
    try:
        out = _call("make_game_move", {"move": "e4"}, session)
    finally:
        session.lock_board(None)
    assert out["board_actions"][0]["type"] == "game"


def test_the_game_tools_are_always_offered_to_the_text_coach():
    from src.tool_selector import CORE_TOOLS

    assert {"start_game", "make_game_move"} <= CORE_TOOLS


# ── the voice tool calls: the session and the board lock ────────────────────

def _voice(name, args, session, utterance):
    return json.loads(tool_bridge._dispatch_voice(name, args, session, utterance))


def test_a_voice_question_about_the_board_keeps_it():
    session = session_store.create(user_id="voice-lock-1")
    session.board_state = POS
    out = _voice("board_control", {"action_type": "set_fen", "fen": chess.STARTING_FEN}, session, "Как здесь выиграть?")
    assert out == {"shown": False, "board_hint": out["board_hint"]} and "stays on the board" in out["board_hint"]
    assert session.board_lock is None  # released after the call
    out = _voice("board_control", {"action_type": "set_fen", "fen": chess.STARTING_FEN}, session, "Покажи пример связки")
    assert out["board_actions"][0]["fen"] == chess.STARTING_FEN


def test_during_a_voice_game_nothing_replaces_the_position():
    session = session_store.create(user_id="voice-lock-game")
    _call("start_game", {"color": "white"}, session)
    out = _voice("board_control", {"action_type": "load_pgn", "pgn": "1. e4 d5 2. exd5"}, session, "ходи")
    assert out.get("shown") is False and "A game against the student is on" in out["board_hint"]
    out = _voice("make_game_move", {"move": "е4"}, session, "пешка е четыре")
    assert out["ok"] and out["board_actions"][0]["type"] == "game"


# ── the famous games for the voice coach ────────────────────────────────────

def test_famous_game_puts_the_verified_score_up():
    session = session_store.create(user_id="famous-voice")
    out = _call("famous_game", {"text": "Покажи оперную партию Морфи"}, session)
    assert out["found"] and "Morphy" in out["board_actions"][0]["pgn"] and "ALREADY on the board" in out["facts"]
    missing = _call("famous_game", {"text": "как ходит конь"}, session)
    assert missing["found"] is False and "Do not tell or show its moves from memory" in missing["note"]


# ── «на 8-м ходу» by voice ───────────────────────────────────────────────────

def test_the_voice_idea_is_played_at_the_named_move_of_the_game(monkeypatch):
    from fastapi.testclient import TestClient

    from src import server

    monkeypatch.setattr(config, "COACH_HYPOTHETICAL_NOTE", False)
    final = chess.Board()
    for san in GAME.replace(".", ". ").split():
        if not san[0].isdigit():
            final.push_san(san)
    data = TestClient(server.app).post(
        "/api/coach/voice/idea", headers={"X-User-Id": "voice-past"},
        json={"text": "А что было бы, если бы на 8-м ходу я взял слоном на g5 вместо Bg3?",
              "fen": final.fen(), "pgn": GAME},
    ).json()
    assert data["moves"] and data["moves"][0]["san"] == "Bxg5" and data["moves"][0]["legal"]
    assert "played in the game on the board at" in data["note"]


def test_the_text_coachs_tools_see_the_session_through_the_turns_task_id():
    """The framework dispatches with task_id/user_task only: the session comes from the turn binding."""
    from src.tools import turn_session

    session = session_store.create(user_id="turn-binding")
    with turn_session("coach-turn-x", session.id):
        out = json.loads(registry.dispatch("start_game", {"color": "white"}, task_id="coach-turn-x", user_task="давай сыграем"))
    assert out["ok"] and session.get_board(session.active_board_id).kind == "game"
    # outside the turn the task id means nothing
    out = json.loads(registry.dispatch("make_game_move", {"move": "e4"}, task_id="coach-turn-x"))
    assert "No game is on" in out["error"]


def test_chat_in_session_gives_the_agents_tools_the_session():
    """The server's turn: agent.chat → run_conversation(task_id=ours) → the tools see the session."""
    from src.server import _chat_in_session

    session = session_store.create(user_id="chat-in-session")

    class Agent:
        def run_conversation(self, message, stream_callback=None, task_id=None):
            out = json.loads(registry.dispatch("start_game", {"color": "white"}, task_id=task_id, user_task=message))
            return {"final_response": "ok" if out.get("ok") else out.get("error")}

        def chat(self, message, stream_callback=None):
            return self.run_conversation(message, stream_callback=stream_callback)["final_response"]

    assert _chat_in_session(Agent(), "давай сыграем", session.id) == "ok"
    assert session.get_board(session.active_board_id).kind == "game"


# ── the server reads the game request and the bare move itself (src/game_intent.py) ──

@pytest.mark.parametrize("text,color", [
    ("Спорим, я тебя обыграю? Давай сыграем партию, я за белых.", "white"),
    ("Давай сыграем, я чёрными", "black"),
    ("Сыграем партию?", "white"),
    ("давай поиграем", "white"),
    ("Let's play a game", "white"),
    ("Маған қарсы ойнайық", "white"),
])
def test_a_game_asked_for_in_words(text, color):
    from src.game_intent import game_request

    assert game_request(text)["color"] == color


@pytest.mark.parametrize("text", [
    "Как сыграть против сицилианки?", "Что мне сыграть?", "Хочу сыграть Qb6, хорошо?", "Можно сыграть e4?",
    "Спорим, это ничья?", "Давай разберём партию", "Покажи оперную партию Морфи",
])
def test_words_that_do_not_ask_for_a_game(text):
    from src.game_intent import game_request

    assert game_request(text) is None


@pytest.mark.parametrize("text,san", [("е4", "e4"), ("пешка е4", "e4"), ("Кf3", "Nf3"), ("конь f3", "Nf3"),
                                      ("knight f3", "Nf3"), ("а если Кf3?", None), ("можно e4", None), ("e4 хорош?", None)])
def test_a_move_written_on_its_own(text, san):
    from src.game_intent import bare_move

    assert bare_move(text, chess.Board()) == san


def _chat_turn(monkeypatch, session, message, fen, board_id=None):
    from unittest.mock import MagicMock, patch

    from fastapi.testclient import TestClient

    from src import server
    from src.user_profile import UserProfile

    agent = MagicMock()
    agent.tools = []
    agent._api_call_count = 1
    agent.max_iterations = 5
    agent.session_prompt_tokens = agent.session_completion_tokens = 0
    captured = {}

    def _chat(msg, stream_callback=None):
        captured["message"] = msg
        stream_callback("Хорошо.")
        return "Хорошо."

    agent.chat.side_effect = _chat
    for name, value in {"COACH_TWO_STAGE": False, "COACH_ENGINE_NOTE": False, "COACH_ANSWER_CHECK": False,
                        "COACH_HYPOTHETICAL_NOTE": False}.items():
        monkeypatch.setattr(config, name, value)
    with patch("src.server._create_agent", return_value=agent), \
            patch("src.server.load_user_profile", return_value=UserProfile(user_id=session.user_id)), \
            patch("src.server.log_event"):
        resp = TestClient(server.app).post(
            "/api/coach/chat", headers={"X-User-Id": session.user_id},
            json={"message": message, "session_id": session.id, "locale": "ru", "fen": fen, "board_id": board_id},
        )
    assert resp.status_code == 200
    frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
    games = [a["game"] for f in frames for a in (f.get("board_actions") or []) if a.get("type") == "game"]
    return captured.get("message", ""), games


def test_a_text_turn_asking_for_a_game_starts_it_before_the_model_answers(monkeypatch):
    session = session_store.create(user_id="prestep-start")
    told, games = _chat_turn(monkeypatch, session, "Спорим, я тебя обыграю? Давай сыграем, я за чёрных", chess.STARTING_FEN)
    assert games and games[0]["student_color"] == "black" and len(games[0]["moves"]) == 1
    assert "The game has started on the board" in told and "Never play or invent a move" in told


def test_a_move_typed_in_the_game_is_played_and_a_question_is_not(monkeypatch):
    session = session_store.create(user_id="prestep-move")
    _call("start_game", {"color": "white"}, session)
    board = session.get_board(session.active_board_id)
    told, games = _chat_turn(monkeypatch, session, "е4", board.fen, board.id)
    assert games and games[0]["moves"][0] == "e4" and len(games[0]["moves"]) == 2
    assert "The student's move was played on the board" in told
    board = session.get_board(session.active_board_id)
    told, games = _chat_turn(monkeypatch, session, "А если Кf3?", board.fen, board.id)
    assert games == [] and "The student's move was played" not in told


def test_a_question_about_a_move_is_not_played_and_a_played_move_not_twice():
    session = session_store.create(user_id="question-not-move")
    _call("start_game", {"color": "white"}, session)
    out = json.loads(registry.dispatch("make_game_move", {"move": "Nf3"}, session_id=session.id, student_message="А если Кf3?"))
    assert "asked about a move" in out["error"]
    out = json.loads(registry.dispatch("make_game_move", {"move": "Nf3"}, session_id=session.id, student_message="конь f3",
                                       turn_game_step=True))
    assert "already played" in out["error"]
    out = json.loads(registry.dispatch("make_game_move", {"move": "Nf3"}, session_id=session.id, student_message="конь f3"))
    assert out["ok"] and out["student_move"] == "Nf3"


def test_in_a_game_the_coach_names_only_the_engines_moves():
    from src.answer_check import CheckContext, check_sentence

    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    ctx = CheckContext.from_fens([board.fen()])
    ctx.game_engine_moves = ["e5"]
    assert check_sentence("Так что я ответил Кc6 — защитил пешку.", ctx)
    assert check_sentence("Мой ход — d5.", ctx)
    assert check_sentence("Я ответил e5 — симметрично.", ctx) == []
    assert check_sentence("На Кf3 я ответил бы Кc6.", ctx) == []
    ctx.game_engine_moves = None
    assert check_sentence("Так что я ответил Кc6.", ctx) == []


def test_a_question_in_the_game_is_marked_for_the_model(monkeypatch):
    session = session_store.create(user_id="prestep-question")
    _call("start_game", {"color": "white"}, session)
    board = session.get_board(session.active_board_id)
    told, games = _chat_turn(monkeypatch, session, "А если Кf3?", board.fen, board.id)
    assert games == [] and "A question about a move in the game — not a move" in told and "Nf3" in told
