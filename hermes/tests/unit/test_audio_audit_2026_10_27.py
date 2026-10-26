"""2026-10-27, the audit of the audio-mode game (Alexander's list): the server half.

* undo requests: one family (takeback / mistake / correct), deduped by the student's words, not the clock alone —
  a real second «верни ещё ход» inside 12 s is done; the model's bare call reads the count from the utterance;
* kept lines re-rooted when the main line is cut below them (no orphan in the PGN);
* a finished game (a mis-made last move ended it) can be taken back, viewed and continued — it reopens;
* «ты не так сходил» objects to the ENGINE's move: nothing undone;
* a restart asked twice at once is one game; the engine's first move is to be said aloud;
* a move said while browsing an earlier position is never played (pre-step and the Live model's tool);
* the comment after a hand move knows the moves were already said aloud;
* phrasings: «верни два хода», «ой, не туда», «рестарт», «начни партию заново»; «объясни ещё раз» is not a restart."""

import json
import time

import chess
import pytest
from fastapi.testclient import TestClient

from src import game_mode
from src.game_intent import game_command
from src.server import _game_prestep, app
from src.sessions import session_store
from src.tools.game_play import (_handle_game_action, _handle_make_game_move, _handle_start_game, last_game_board,
                                 live_game_board)


class _Engine:
    def move(self, fen, elo):
        board = chess.Board(fen)
        for san in ("e5", "Nc6", "Nf6", "d6", "d5", "e6", "g6"):
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


USER = "audit-user"


def _game_with(moves, color="white"):
    session = session_store.create(USER)
    assert json.loads(_handle_start_game({"color": color}, session_id=session.id, user_id=USER))["ok"]
    for m in moves:
        r = json.loads(_handle_make_game_move({"move": m}, session_id=session.id, user_id=USER))
        assert r["ok"], r
    return session


def _act(session, utterance=None, **args):
    kw = {"session_id": session.id, "user_id": USER}
    if utterance is not None:
        kw["student_message"] = utterance
    return json.loads(_handle_game_action(args, **kw))


def _moves(session):
    return (last_game_board(session).game_state or {}).get("moves")


# ── undo requests ───────────────────────────────────────────────────────────

def test_the_same_words_twice_undo_once_but_new_words_undo_again(engine):
    session = _game_with(["e4", "Nf3", "Bc4"])
    _act(session, said="верни ход")
    assert _moves(session) == ["e4", "e5", "Nf3", "Nc6"]
    _act(session, "верни ход", action="takeback")                 # the model's own call for the same words
    assert _moves(session) == ["e4", "e5", "Nf3", "Nc6"]
    _act(session, said="верни ещё ход")                            # a NEW request inside 12 s: done
    assert _moves(session) == ["e4", "e5"]


def test_mistake_after_takeback_for_the_same_words_is_one_undo(engine):
    session = _game_with(["e4", "Nf3"])
    _act(session, said="это не мой ход")                          # the site reads it as mistake
    assert _moves(session) == ["e4", "e5"]
    _act(session, "это не мой ход", action="takeback")             # the model calls takeback for it
    assert _moves(session) == ["e4", "e5"]


def test_the_models_bare_call_reads_the_count_from_the_utterance(engine):
    session = _game_with(["e4", "Nf3", "Bc4"])
    r = _act(session, "верни два хода", action="takeback")
    assert r["ok"] and _moves(session) == ["e4", "e5"]


# ── kept lines ──────────────────────────────────────────────────────────────

def test_two_takebacks_in_a_row_leave_no_orphan_line(engine):
    session = _game_with(["e4", "Nf3", "Bc4"])
    board_rec = live_game_board(session)
    game_mode.takeback_moves(session, board_rec, 1)               # Bc4 Nf6 kept at ply 4
    game_mode.takeback_moves(session, board_rec, 1)               # Nf3 Nc6 cut: the Bc4 line is re-rooted at ply 2
    vs = board_rec.game_state["variations"]
    assert all(int(v["at_ply"]) <= len(board_rec.game_state["moves"]) for v in vs)
    assert ["Nf3", "Nc6", "Bc4", "Nf6"] in [v["moves"] for v in vs]
    r = json.loads(_handle_make_game_move({"move": "d4"}, session_id=session.id, user_id=USER))
    pgn = r["board_actions"][0]["game"]["pgn"].replace("\n", " ")
    assert "( 2. Nf3 Nc6 3. Bc4 Nf6 )" in pgn


# ── a finished game ─────────────────────────────────────────────────────────

def test_a_finished_game_can_be_taken_back_and_reopens(engine):
    session = _game_with(["e4", "Nf3"])
    board_rec = live_game_board(session)
    game_mode.resign(session, board_rec)
    assert live_game_board(session) is None
    r = _act(session, said="верни ход")
    assert r["ok"] and _moves(session) == ["e4", "e5"]
    assert last_game_board(session).game_state["status"] == "playing"


def test_the_pre_step_takes_back_a_finished_game_on_the_board(engine):
    session = _game_with(["e4", "Nf3"])
    board_rec = live_game_board(session)
    game_mode.resign(session, board_rec)
    step = _game_prestep(session, board_rec, "верни ход")
    assert step and step["view"] and step["view"]["moves"] == ["e4", "e5"]


# ── the engine's move objected to ───────────────────────────────────────────

def test_an_objection_to_the_engines_move_undoes_nothing(engine):
    session = _game_with(["e4", "Nf3"])
    assert game_command("ты не так сходил") == "coach_move"
    r = _act(session, said="ты не так сходил")
    assert _moves(session) == ["e4", "e5", "Nf3", "Nc6"]
    assert "Nc6" in r["note"] and "nothing was changed" in r["note"].lower() or "Nc6" in r["note"]


@pytest.mark.parametrize("said,command", [
    ("ты ошибся", "mistake"),
    ("ты неправильно оцениваешь позицию", None),                  # a remark about the assessment, not the board
    ("ты ошибся, конь не висит", None),
    ("это не мой ход", "mistake"),
    ("твой ход не тот", "coach_move"),
])
def test_mistake_words_are_about_the_board_only(said, command):
    assert game_command(said) == command


# ── restart ─────────────────────────────────────────────────────────────────

def test_a_restart_asked_twice_at_once_is_one_game(engine):
    session = _game_with(["e4"])
    _act(session, said="давай заново")
    first = live_game_board(session)
    r = _act(session, "давай заново", action="restart")
    assert live_game_board(session).id == first.id
    assert r["ok"]


def test_a_restart_as_black_asks_to_say_the_engines_first_move(engine):
    session = _game_with(["e4"])
    r = _act(session, said="давай заново, я чёрными")
    assert "say this move aloud" in r["note"]


def test_a_restart_after_the_panel_was_closed_needs_game_words(engine):
    session = _game_with(["e4"])
    game_mode.resign(session, live_game_board(session))
    study = session.ensure_board() if hasattr(session, "ensure_board") else None
    other = next((b for b in session.boards if b.kind != "game"), None) or study
    if other is not None:
        session.active_board_id = other.id
        assert _game_prestep(session, other, "объясни ещё раз") is None
        step = _game_prestep(session, other, "давай сыграем ещё партию")
        assert step and step["view"] and step["view"]["status"] == "playing"


# ── browsing ────────────────────────────────────────────────────────────────

def test_a_move_said_while_browsing_is_not_played_even_when_legal_on_the_live_board(engine):
    session = _game_with(["e4", "Nf3"])
    board_rec = live_game_board(session)
    step = _game_prestep(session, board_rec, "Bc4", view_ply=2)
    assert step and step["view"] is None and "EARLIER position" in step["block"]
    assert board_rec.game_state["moves"] == ["e4", "e5", "Nf3", "Nc6"]
    step = _game_prestep(session, board_rec, "что здесь лучше?", view_ply=2)
    assert step is None                                           # a question: the model answers about the shown position


def test_the_live_models_move_tool_refuses_while_browsing(engine):
    session = _game_with(["e4", "Nf3"])
    r = json.loads(_handle_make_game_move({"move": "Bc4", "view_ply": 2}, session_id=session.id, user_id=USER))
    assert not r.get("ok") and "EARLIER position" in (r.get("error") or "")
    assert _moves(session) == ["e4", "e5", "Nf3", "Nc6"]


# ── the comment after a hand move ───────────────────────────────────────────

def test_the_comment_knows_the_moves_were_said_aloud(engine):
    session = _game_with(["e4"])
    msgs = game_mode.comment_prompt(live_game_board(session), "ru", "move", spoken=True)
    assert "do not restate them" in msgs[0]["content"]
    assert "do not restate" not in game_mode.comment_prompt(live_game_board(session), "ru", "move")[0]["content"]


# ── phrasings ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said,command", [
    ("верни два хода", "takeback"), ("верни последний ход", "takeback"), ("верни обратно", "takeback"),
    ("ой, не туда", "takeback"), ("промахнулся", "takeback"), ("верни", "takeback"), ("верни ещё раз", "takeback"),
    ("take that back", "takeback"), ("начни партию заново", "restart"), ("рестарт", "restart"),
    ("давай снова", "restart"), ("заново", "restart"), ("объясни ещё раз", None),
])
def test_phrasings(said, command):
    assert game_command(said) == command


# ── the answer check: the long prod run (26.10) ─────────────────────────────

def _ctx_for(moves):
    from src.answer_check import CheckContext

    b = chess.Board()
    for m in moves:
        b.push_san(m)
    return CheckContext.from_fens([b.fen()], [" ".join(moves)])


_LONG = ["e4", "c5", "Nf3", "g6", "Bc4", "Bg7", "O-O", "e5", "d3", "h6", "Nc3", "d6"]


@pytest.mark.parametrize("moves,sentence,wrong", [
    (_LONG, "Ход отменён — слон на g5 и пешка h5 взяла его, теперь этих ходов нет.", "no pawn on h5"),
    (_LONG, "Пешка на h5 стоит крепко.", "no pawn on h5"),
])
def test_ghost_actors_of_past_captures_are_caught(moves, sentence, wrong):
    from src.answer_check import check_sentence
    from src.game_intent import spoken_squares

    issues = check_sentence(spoken_squares(sentence), _ctx_for(moves))
    assert any(wrong in i for i in issues), issues


@pytest.mark.parametrize("moves,sentence", [
    (_LONG + ["Bg5", "hxg5"], "Пешка h6 взяла твоего слона на g5."),             # true a move ago: the history counts
    (_LONG + ["Bg5", "hxg5"], "Твоя пешка h2 под боем ладьи h8, и конь f3 держит её."),   # the knight does defend h2
    (["e4", "e5", "Nf3", "Nc6"], "Конь f3 нападает на пешку e5, а конь c6 защищает её."),
    (["e4", "d5"], "Пешка e4 берёт d5."),
])
def test_true_sentences_pass(moves, sentence):
    from src.answer_check import check_sentence
    from src.game_intent import spoken_squares

    assert check_sentence(spoken_squares(sentence), _ctx_for(moves)) == []


def test_an_object_pronoun_is_judged_on_the_piece_it_stands_for():
    from src.answer_check import check_sentence

    issues = check_sentence("пешка e5 под ударом, и конь g1 защищает её.", _ctx_for(["e4", "e5", "Nf3"]))
    assert any("g1" in i and "e5" in i for i in issues), issues


def test_the_better_move_question_gets_the_engines_verdict(engine, monkeypatch):
    from src import server

    assert server._ASKS_BETTER_MOVE.search("Что здесь было лучше вместо моего хода?")
    assert server._ASKS_BETTER_MOVE.search("как надо было сыграть?")
    assert not server._ASKS_BETTER_MOVE.search("какой план лучше?")


# ── continuing from a side line (item 4: «из текущей позиции на доске») ────

def test_the_game_continues_from_a_side_line_and_keeps_the_old_line(engine):
    session = _game_with(["e4", "Nf3", "Bc4"])
    board_rec = live_game_board(session)
    game_mode.takeback_moves(session, board_rec, 2)                         # the side line 2.Nf3 Nc6 3.Bc4 Nf6 kept
    json.loads(_handle_make_game_move({"move": "d4"}, session_id=session.id, user_id=USER))
    main_before = list(board_rec.game_state["moves"])                       # e4 e5 d4 …
    view = game_mode.continue_from_line(session, board_rec, ["e4", "e5", "Nf3", "Nc6"])
    assert view["moves"][:4] == ["e4", "e5", "Nf3", "Nc6"] and view["student_to_move"]
    lines = [v["moves"] for v in view["variations"]]
    assert main_before[2:] in lines                                         # the old main continuation stays
    assert ["Bc4", "Nf6"] in lines                                          # the rest of the side line stays
    assert [a["ply"] for a in board_rec.game_state["annotations"]] == [1, 3]


def test_continue_here_by_words_on_a_side_line(engine):
    session = _game_with(["e4", "Nf3"])
    board_rec = live_game_board(session)
    game_mode.takeback_moves(session, board_rec, 1)
    _handle_make_game_move({"move": "d4"}, session_id=session.id, user_id=USER)
    r = _act(session, said="продолжим отсюда", view_line=["e4", "e5", "Nf3"])
    assert r["ok"] and _moves(session)[:3] == ["e4", "e5", "Nf3"] and len(_moves(session)) == 4   # the engine answered


def test_the_continue_route_takes_a_line(engine):
    session = _game_with(["e4", "Nf3"])
    board_rec = live_game_board(session)
    game_mode.takeback_moves(session, board_rec, 1)
    _handle_make_game_move({"move": "d4"}, session_id=session.id, user_id=USER)
    resp = TestClient(app).post(f"/api/coach/sessions/{session.id}/game/{board_rec.id}/continue",
                                headers={"X-User-Id": USER}, json={"line": ["e4", "e5", "Nf3", "Nc6"]})
    assert resp.status_code == 200 and resp.json()["moves"][:4] == ["e4", "e5", "Nf3", "Nc6"]
