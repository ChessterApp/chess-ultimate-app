"""2026-10-26, Alexander's list for the audio mode: the game taken back any number of moves («верни партию на два
хода назад, до того как я сходил конём»), «ты ошибся» undoing the last move, an earlier position shown on the
board while the game goes on («покажи позицию после 10-го хода», «вернись к партии»), and «продолжим отсюда»
cutting the game there (src/game_mode.truncate, src/game_intent.cut_target / view_target, src/tools/game_play)."""

import json

import chess
import pytest
from fastapi.testclient import TestClient

from src import game_mode
from src.game_intent import cut_target, game_command, view_target
from src.sessions import session_store
from src.server import _game_prestep, app
from src.tools.game_play import _handle_game_action, _handle_make_game_move, _handle_start_game, live_game_board


class _Engine:
    def move(self, fen, elo):
        board = chess.Board(fen)
        for san in ("e5", "Nc6", "Nf6", "d6", "d5", "e6"):
            try:
                return board.parse_san(san).uci()
            except ValueError:
                continue
        return next(iter(board.legal_moves)).uci()

    def evaluate(self, fen, pov):
        return 0, None


@pytest.fixture
def engine(monkeypatch):
    eng = _Engine()
    monkeypatch.setattr(game_mode, "_engine_move", eng.move)
    monkeypatch.setattr(game_mode, "_evaluate", eng.evaluate)
    return eng


@pytest.fixture(autouse=True)
def _clean():
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


USER = "controls-user"


def _game_with(moves):
    """A game (student White) with the student's *moves* played, the engine answering each."""
    session = session_store.create(USER)
    assert json.loads(_handle_start_game({"color": "white"}, session_id=session.id, user_id=USER))["ok"]
    for m in moves:
        r = json.loads(_handle_make_game_move({"move": m}, session_id=session.id, user_id=USER))
        assert r["ok"], r
    return session


RECORD = {"moves": ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "d3", "d6"],
          "annotations": [{"ply": 1, "san": "e4"}, {"ply": 3, "san": "Nf3"}, {"ply": 5, "san": "Bc4"}, {"ply": 7, "san": "d3"}]}


# ── the words ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said,command,ply", [
    ("верни ход", "takeback", 6),
    ("Верни партию на 2 хода назад", "takeback", 4),       # the student's last two moves, not «move 2»
    ("верни позицию на два хода назад, до того как я сходил конём", "takeback", 2),
    ("отмени последние три хода", "takeback", 2),
    ("до того как я сходил слоном", "takeback", 4),
    ("верни до 3-го хода", "takeback", 4),
    ("верни всё в начало", "takeback", 0),
    ("undo the last two moves", "takeback", 4),
])
def test_takeback_words_name_where_to_cut(said, command, ply):
    assert game_command(said) == command
    assert cut_target(said, RECORD)["ply"] == ply


@pytest.mark.parametrize("said,command", [
    ("ты ошибся", "mistake"), ("это не мой ход", "mistake"), ("верни как было", "mistake"),
    ("продолжим отсюда", "continue_here"), ("давай играть с этой позиции", "continue_here"),
    ("вернись к партии", "view_live"), ("покажи текущую позицию", "view_live"),
    ("сдаюсь", "resign"), ("давай с начала", "restart"),
    ("как ты думаешь, стоит ли мне предлагать ничью в этой позиции или играть дальше", None),
    ("что думаешь про позицию", None), ("конь f3", None),
])
def test_the_other_commands_and_non_commands(said, command):
    assert game_command(said) == command


@pytest.mark.parametrize("said,ply", [
    ("покажи позицию после 2-го хода", 4),
    ("Покажи позицию после второго хода.", 4),     # the transcription writes the number as a word (Asan's phone, 26.10)
    ("Я говорю, после второго хода.", 4),          # the student correcting which position — a view on its own
    ("нет, до третьего", 4),
    ("покажи позицию после хода номер три", 6),
    ("покажи, как было до моего хода конём", 2),
    ("отмотай на два хода назад посмотреть", 4),
    ("покажи позицию после моего хода слоном", 5),
])
def test_view_words_name_the_position(said, ply):
    assert game_command(said) == "view"
    assert view_target(said, RECORD)["ply"] == ply


# ── the record cut back ───────────────────────────────────────────────────────

def test_truncate_cuts_the_record_and_the_engine_moves_when_it_is_its_turn(engine):
    session = _game_with(["e4", "Nf3", "Bc4"])
    board_rec = live_game_board(session)
    assert len(board_rec.game_state["moves"]) == 6
    view = game_mode.truncate(session, board_rec, 3)          # after 1.e4 e5 2.Nf3: Black (the engine) to move
    assert view["moves"][:3] == ["e4", "e5", "Nf3"] and len(view["moves"]) == 4 and view["engine"]["san"]
    assert view["student_to_move"]
    assert [a["ply"] for a in board_rec.game_state["annotations"]] == [1, 3]
    view = game_mode.truncate(session, board_rec, 0)
    assert view["moves"] == [] and view["student_to_move"] and board_rec.game_state["annotations"] == []


def test_takeback_moves_undoes_the_student_s_last_n_moves(engine):
    session = _game_with(["e4", "Nf3", "Bc4"])
    board_rec = live_game_board(session)
    view = game_mode.takeback_moves(session, board_rec, 2)
    assert view["moves"] == ["e4", "e5"] and view["student_to_move"] and not view["engine"]
    view = game_mode.takeback_moves(session, board_rec, 5)    # more than there are: to the start
    assert view["moves"] == []


def test_a_finished_game_reopens_at_an_earlier_position(engine):
    session = _game_with(["e4"])
    board_rec = live_game_board(session)
    st = board_rec.game_state
    st.update(status="finished", result="0-1", termination="resign", winner="engine")
    view = game_mode.truncate(session, board_rec, 0)
    assert view["status"] == "playing" and view["result"] is None and view["moves"] == []


# ── the steps, by words ─────────────────────────────────────────────────────

def test_takeback_by_words_cuts_to_the_place_named(engine):
    session = _game_with(["e4", "Nf3", "Bc4", "d3"])
    reply = json.loads(_handle_game_action({"said": "верни партию на два хода назад, до того как я сходил слоном"},
                                           session_id=session.id, user_id=USER))
    assert reply["ok"] and reply["action"] == "takeback" and reply["done"]
    assert live_game_board(session).game_state["moves"] == ["e4", "e5", "Nf3", "Nc6"]
    assert "before the student's move Bc4" in reply["note"]
    assert "UNDONE, exactly these moves: 3.Bc4 Nf6 4.d3 d6" in reply["note"]   # the model names these, not guesses (prod, 26.10)


def test_a_mistake_undoes_the_last_move_and_asks_what_was_meant(engine):
    session = _game_with(["e4", "Nf3"])
    reply = json.loads(_handle_game_action({"said": "ты ошибся, это не мой ход"}, session_id=session.id, user_id=USER))
    assert reply["ok"] and reply["action"] == "mistake"
    assert live_game_board(session).game_state["moves"] == ["e4", "e5"]
    assert "ask which move they want" in reply["note"]
    fresh = session_store.create(USER)
    _handle_start_game({"color": "white"}, session_id=fresh.id, user_id=USER)
    reply = json.loads(_handle_game_action({"said": "ты ошибся"}, session_id=fresh.id, user_id=USER))
    assert not reply["ok"] and "no move of theirs is recorded" not in reply["note"] and "Nothing changed" in reply["note"]


def test_viewing_shows_an_earlier_position_without_touching_the_game(engine):
    session = _game_with(["e4", "Nf3", "Bc4"])
    reply = json.loads(_handle_game_action({"said": "покажи позицию после 1-го хода"}, session_id=session.id, user_id=USER))
    assert reply["ok"] and reply["done"] and reply["action"] == "view"
    assert reply["board_actions"] == [{"type": "game_view", "board_id": live_game_board(session).id, "ply": 2,
                                       "fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"}]
    assert len(live_game_board(session).game_state["moves"]) == 6                      # untouched
    assert "The game stands at ply 6" in reply["note"] and "nothing is played" in reply["note"]
    back = json.loads(_handle_game_action({"said": "вернись к партии"}, session_id=session.id, user_id=USER))
    assert back["board_actions"][0] == {"type": "game_view", "board_id": live_game_board(session).id, "ply": None}


def test_continue_here_cuts_the_game_at_the_viewed_ply_and_needs_one(engine):
    session = _game_with(["e4", "Nf3", "Bc4"])
    nothing = json.loads(_handle_game_action({"said": "продолжим отсюда"}, session_id=session.id, user_id=USER))
    assert not nothing["ok"] and "Nothing changed" in nothing["note"] and "current position" in nothing["note"]
    reply = json.loads(_handle_game_action({"said": "продолжим отсюда", "view_ply": 2}, session_id=session.id, user_id=USER))
    assert reply["ok"] and reply["done"]
    assert live_game_board(session).game_state["moves"] == ["e4", "e5"]


def test_a_move_named_while_viewing_the_past_is_not_played(engine):
    session = _game_with(["e4", "Nf3"])
    board_rec = live_game_board(session)
    step = _game_prestep(session, board_rec, "Bc4", view_ply=2)
    assert step and step["view"] is None and "nothing was played" in step["block"].lower()
    assert board_rec.game_state["moves"] == ["e4", "e5", "Nf3", "Nc6"]
    played = _game_prestep(session, board_rec, "Bc4", view_ply=4)                      # the live ply: played
    assert played and played["view"]["student"]["san"] == "Bc4"


def test_the_continue_route_and_the_chat_request_field(engine):
    session = _game_with(["e4", "Nf3"])
    board_rec = live_game_board(session)
    client = TestClient(app)
    resp = client.post(f"/api/coach/sessions/{session.id}/game/{board_rec.id}/continue", headers={"X-User-Id": USER}, json={"ply": 1})
    assert resp.status_code == 200
    view = resp.json()
    assert view["moves"][0] == "e4" and len(view["moves"]) == 2 and view["student_to_move"]
    from src.server import CoachChatRequest

    assert CoachChatRequest(message="x", view_ply=3).view_ply == 3


def test_a_takeback_asked_once_but_arriving_twice_is_done_once(engine):
    """The voice game: the model's own game_action call and the site's for the same «верни ход» (Alexander, 26.10)."""
    session = _game_with(["e4", "Nf3", "Bc4"])
    first = json.loads(_handle_game_action({"said": "Можно ход назад?"}, session_id=session.id, user_id=USER))
    assert first["ok"] and live_game_board(session).game_state["moves"] == ["e4", "e5", "Nf3", "Nc6"]
    second = json.loads(_handle_game_action({"action": "takeback"}, session_id=session.id, user_id=USER))
    assert second["ok"] and live_game_board(session).game_state["moves"] == ["e4", "e5", "Nf3", "Nc6"]   # not undone again
    assert "already done" in second["note"].lower() or "Nothing more was undone" in second["note"]
    # a move played in between: the next takeback is a real one
    _handle_make_game_move({"move": "Bc4"}, session_id=session.id, user_id=USER)
    third = json.loads(_handle_game_action({"said": "верни ход"}, session_id=session.id, user_id=USER))
    assert third["ok"] and live_game_board(session).game_state["moves"] == ["e4", "e5", "Nf3", "Nc6"]


# ── the lines taken back stay in the notation (Alexander, 26.10) ────────────

def test_a_takeback_keeps_the_line_as_a_variation_in_the_record_and_the_pgn(engine):
    session = _game_with(["e4", "Nf3", "Bc4"])
    board_rec = live_game_board(session)
    view = game_mode.takeback_moves(session, board_rec, 2)
    assert view["moves"] == ["e4", "e5"]
    assert view["variations"] == [{"at_ply": 2, "moves": ["Nf3", "Nc6", "Bc4", "Nf6"]}]
    assert "(" not in view["pgn"].split("\n\n")[-1]            # at the end of the main line a PGN variation would be the main line
    ctx = game_mode.game_context(board_rec)
    assert "Lines taken back" in ctx and "after 1.e4 e5: 2.Nf3 Nc6 3.Bc4 Nf6" in ctx
    # played on differently: the new line is the main line, the old one stays — now a proper PGN variation
    r = json.loads(_handle_make_game_move({"move": "d4"}, session_id=session.id, user_id=USER))
    assert r["ok"] and live_game_board(session).game_state["moves"][:3] == ["e4", "e5", "d4"]
    assert live_game_board(session).game_state["variations"][0]["moves"] == ["Nf3", "Nc6", "Bc4", "Nf6"]
    pgn = r["board_actions"][0]["game"]["pgn"].replace("\n", " ")
    assert "2. d4" in pgn and "( 2. Nf3 Nc6 3. Bc4 Nf6 )" in pgn


def test_the_button_takeback_keeps_the_line_too_and_a_longer_line_swallows_a_shorter(engine):
    session = _game_with(["e4", "Nf3"])
    board_rec = live_game_board(session)
    game_mode.takeback(session, board_rec)                       # the game's button: Nf3 + the reply go
    assert board_rec.game_state["variations"] == [{"at_ply": 2, "moves": ["Nf3", "Nc6"], "at": board_rec.game_state["variations"][0]["at"]}]
    _handle_make_game_move({"move": "Nf3"}, session_id=session.id, user_id=USER)   # the same move again
    _handle_make_game_move({"move": "Bc4"}, session_id=session.id, user_id=USER)
    game_mode.takeback_moves(session, board_rec, 2)                # back to after 1...e5: the longer line replaces the short one
    vs = board_rec.game_state["variations"]
    assert [v["moves"] for v in vs] == [["Nf3", "Nc6", "Bc4", "Nf6"]]


def test_the_voice_tool_path_keeps_the_game_view_action(engine):
    """The Live model's own game_action call goes through the tool bridge, which dropped game_view as an unknown type
    (prod, 26.10: «покажи позицию после первого хода» answered ok with no board action)."""
    session = _game_with(["e4", "Nf3"])
    client = TestClient(app)
    resp = client.post("/api/coach/tool/game_action", headers={"X-User-Id": USER},
                       json={"args": {"said": "покажи позицию после первого хода"}, "session_id": session.id, "utterance": "покажи позицию после первого хода"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"]["ok"] and data["board_actions"] and data["board_actions"][0]["type"] == "game_view"
    assert data["board_actions"][0]["ply"] == 2
    assert live_game_board(session).game_state["moves"] == ["e4", "e5", "Nf3", "Nc6"]   # the game itself untouched
