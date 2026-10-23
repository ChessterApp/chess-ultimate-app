"""2026-10-23, Alexander's phone, the voice game: «1.e4 — невозможный ход» on the very first move. The voice
model and the site both played the student's «E4» at the same moment; with no lock on the game both read the
start position and both appended «e4» — and every call after that failed replaying the record:
«Tool execution failed: IllegalMoveError: illegal san: 'e4' in …/4P3/… b KQkq - 0 1».

Now one call at a time changes a game (src/game_mode.board_lock), a second call for the move just played
gets the first one's result again (``already_played``), a broken record is read as far as it goes and cut
(``_repair``), and a second start of a game just started is the same game (``already_started``)."""

import json
import threading
import time

import chess
import pytest

from src import game_mode
from src.game_mode import play_move, start_game
from src.sessions import session_store
from src.tools.game_play import _handle_make_game_move, _handle_start_game


class _Engine:
    """A stand-in for Stockfish: a fixed reply, a fixed evaluation, and a pause that lets two calls overlap."""

    def __init__(self, delay=0.0):
        self.delay = delay
        self.calls = 0

    def move(self, fen, elo):
        self.calls += 1
        time.sleep(self.delay)
        board = chess.Board(fen)
        for san in ("d5", "e5", "Nf6", "Nc6"):
            try:
                return board.parse_san(san).uci()
            except ValueError:
                continue
        return next(iter(board.legal_moves)).uci()

    def evaluate(self, fen, pov):
        time.sleep(self.delay)
        return 0, None


@pytest.fixture
def engine(monkeypatch):
    eng = _Engine(delay=0.05)
    monkeypatch.setattr(game_mode, "_engine_move", eng.move)
    monkeypatch.setattr(game_mode, "_evaluate", eng.evaluate)
    return eng


@pytest.fixture(autouse=True)
def _clean():
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


def _session():
    return session_store.create("race-user")


def test_two_calls_for_one_move_at_once_play_it_once(engine):
    session = _session()
    board_rec, _ = start_game(session, "white", 1200, "quiet")
    results = {}

    def _go(tag):
        try:
            results[tag] = play_move(session, board_rec, "e4")
        except Exception as exc:  # noqa: BLE001
            results[tag] = exc

    threads = [threading.Thread(target=_go, args=(t,)) for t in ("site", "model")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(isinstance(r, dict) for r in results.values()), results
    assert board_rec.game_state["moves"] == ["e4", "d5"]          # one e4, one reply — not «e4 e4»
    assert sum(1 for r in results.values() if r.get("already_played")) == 1
    assert all(r["student"]["san"] == "e4" and r["engine"]["san"] == "d5" for r in results.values())
    assert chess.Board(board_rec.fen).fullmove_number == 2


def test_the_move_just_played_asked_again_later_is_not_a_second_move(engine):
    session = _session()
    board_rec, _ = start_game(session, "white", 1200, "quiet")
    first = play_move(session, board_rec, "e4")
    again = play_move(session, board_rec, "e4")
    assert not first.get("already_played") and again["already_played"]
    assert again["engine"]["san"] == "d5" and board_rec.game_state["moves"] == ["e4", "d5"]
    with pytest.raises(game_mode.GameError):
        play_move(session, board_rec, "e3")   # a move not legal now and not the one just played: refused as before


def test_a_broken_record_is_read_as_far_as_it_goes_and_cut(engine):
    session = _session()
    board_rec, _ = start_game(session, "white", 1200, "quiet")
    state = board_rec.game_state
    state["moves"] = ["e4", "e4", "d5", "d5"]      # what two parallel calls left on production
    state["annotations"] = [{"ply": 1, "san": "e4", "verdict": "ok", "cp_loss": 0, "eval_after": 0, "best": None},
                            {"ply": 2, "san": "e4", "verdict": "ok", "cp_loss": 0, "eval_after": 0, "best": None}]
    board = game_mode._replay(state["moves"])
    assert len(board.move_stack) == 1               # no exception: read up to the first e4
    view = play_move(session, board_rec, "e4")       # the student's second «e4»: the move already played
    assert view["already_played"] and state["moves"] == ["e4", "d5"] and [a["ply"] for a in state["annotations"]] == [1]
    view = play_move(session, board_rec, "Nf3")      # and the game goes on
    assert state["moves"][:3] == ["e4", "d5", "Nf3"] and view["student"]["san"] == "Nf3"


def test_the_tool_answers_the_second_call_with_the_first_result_not_a_refusal(engine):
    session = _session()
    board_rec, _ = start_game(session, "white", 1200, "quiet")
    first = json.loads(_handle_make_game_move({"move": "e4"}, session_id=session.id, user_id="race-user"))
    assert first["ok"] and first["engine_reply"] == "d5"
    second = json.loads(_handle_make_game_move({"move": "e4"}, session_id=session.id, user_id="race-user"))
    assert second["ok"] and second["already_played"] and second["engine_reply"] == "d5"
    assert "already played" in second["note"] and "error" not in second
    said = json.loads(_handle_make_game_move({"said": "е4"}, session_id=session.id, user_id="race-user"))  # Cyrillic е
    assert said["ok"] and said["already_played"]
    other = json.loads(_handle_make_game_move({"move": "e3"}, session_id=session.id, user_id="race-user"))
    assert "error" in other and "not a legal move" in other["error"]


def test_a_broken_record_does_not_break_the_tool(engine):
    session = _session()
    board_rec, _ = start_game(session, "white", 1200, "quiet")
    board_rec.game_state["moves"] = ["e4", "e4"]
    board_rec.game_state["annotations"] = [{"ply": 1, "san": "e4", "verdict": "ok", "cp_loss": 0, "eval_after": 0, "best": None}]
    out = json.loads(_handle_make_game_move({"move": "e4"}, session_id=session.id, user_id="race-user"))
    assert out["ok"] and out["already_played"] and "Tool execution failed" not in json.dumps(out)
    assert board_rec.game_state["moves"] == ["e4", "d5"]


def test_a_second_start_right_after_the_first_is_the_same_game(engine):
    session = _session()
    first = json.loads(_handle_start_game({"color": "white"}, session_id=session.id, user_id="race-user"))
    second = json.loads(_handle_start_game({"said": "давай сыграем"}, session_id=session.id, user_id="race-user"))
    assert first["ok"] and second["ok"] and second["already_started"] and not second.get("restarted")
    assert len([b for b in session.boards if b.kind == "game"]) == 1
    # a game with moves in it is restarted as before
    board_rec = next(b for b in session.boards if b.kind == "game")
    play_move(session, board_rec, "e4")
    third = json.loads(_handle_start_game({"said": "давай сыграем ещё раз"}, session_id=session.id, user_id="race-user"))
    assert third["ok"] and third.get("restarted")
