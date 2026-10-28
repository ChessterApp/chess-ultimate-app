"""Prod Live run 28.10 (after Hermes 28.10-2): «Давай сыграем, я чёрными» — the model's start_game opened the game
with 1.e4, the site's call for the same words a second later (voice/intent read them as «new game», because a game
was now on) resigned that game and started another one, which opened 1.Nf3. The coach announced «Мой первый ход —
пешка на е4»; the check let it through. Every voice start also left a resigned game in the student's history.

Now any start counts for the «same request» guard (the model's call recorded no words, a first game no
``started_by`` at all), the student's own words decide the colour of the model's call, the engine's first move is
given in words, and «мой первый ход — X» / «начну с X» are checked against the game."""

import json
import re

import chess
import pytest

from src import game_mode
from src.answer_check import CheckContext, check_sentence
from src.game_intent import spoken_squares
from src.sessions import session_store
from src.tools.game_play import _handle_game_action, _handle_start_game


@pytest.fixture(autouse=True)
def engine(monkeypatch):
    replies = iter(["Nf3", "e4", "d4", "c4"] * 10)  # each new game of the engine opens differently

    def move(fen, elo):
        board = chess.Board(fen)
        if board.fullmove_number == 1 and board.turn == chess.WHITE:
            return board.parse_san(next(replies)).uci()
        for san in ("d5", "e5", "Nf6", "Nc6"):
            try:
                return board.parse_san(san).uci()
            except ValueError:
                continue
        return next(iter(board.legal_moves)).uci()

    monkeypatch.setattr(game_mode, "_engine_move", move)
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


WORDS = "Давай сыграем, я чёрными."


def _games(session):
    return [b for b in session.boards if b.kind == "game"]


def _model_start(session, args, words=WORDS):
    return json.loads(_handle_start_game(args, session_id=session.id, user_id="u", utterance=words))


def _site_action(session, words=WORDS):
    return json.loads(_handle_game_action({"said": words}, session_id=session.id, user_id="u", utterance=words))


@pytest.mark.unit
def test_model_start_then_the_sites_restart_for_the_same_words_is_one_game():
    session = session_store.create("u")
    first = _model_start(session, {"color": "black"})
    second = _site_action(session)
    assert first["ok"] and second["ok"]
    games = _games(session)
    assert len(games) == 1, "the site's call for the same words must not start a second game"
    assert games[0].game_state["status"] == "playing"
    assert games[0].game_state["moves"][:1] == [first["engine_first_move"]]
    assert "already" in second["note"].lower()


@pytest.mark.unit
def test_a_restart_over_an_old_game_then_the_sites_call_is_one_new_game():
    session = session_store.create("u")
    old = _model_start(session, {"color": "white"}, words="давай сыграем")
    game_mode.play_move(session, _games(session)[0], "e4")
    first = _model_start(session, {"color": "black"})  # a restart: the old game had a move
    assert first.get("restarted")
    second = _site_action(session)
    games = _games(session)
    assert len(games) == 2, "one old (resigned) game and ONE new game"
    assert [g.game_state["status"] for g in games] == ["finished", "playing"]
    assert games[1].game_state["moves"][:1] == [first["engine_first_move"]]
    assert second["ok"] and old["ok"]


@pytest.mark.unit
def test_the_students_words_decide_the_colour_of_the_models_call():
    session = session_store.create("u")
    out = _model_start(session, {"color": "black"}, words="Давай сыграем, я белыми.")
    assert out["student_color"] == "white"
    again = _site_action(session, words="Давай сыграем, я белыми.")
    assert again["ok"] and len(_games(session)) == 1


@pytest.mark.unit
def test_a_different_colour_a_moment_later_is_a_real_new_game():
    session = session_store.create("u")
    _model_start(session, {"color": "white"}, words="Давай сыграем, я белыми.")
    out = _site_action(session, words="Нет, давай заново, я чёрными.")
    games = _games(session)
    assert out["ok"] and len(games) == 2 and games[-1].game_state["student_color"] == "black"


@pytest.mark.unit
def test_the_engines_first_move_comes_in_words():
    session = session_store.create("u")
    out = _model_start(session, {"color": "black"})
    assert out["engine_first_move"] == "Nf3"
    assert out["engine_first_move_words"] == "knight from g1 to f3"
    assert "knight from g1 to f3" in out["note"]
    same = _site_action(session)
    assert "knight from g1 to f3" in same["note"]


def _check(text, engine_moves, fen):
    ctx = CheckContext.from_fens([fen])
    ctx.game_engine_moves = engine_moves
    ctx.student_color = chess.BLACK
    return [i for i in check_sentence(spoken_squares(text), ctx) if "engine plays your moves" in i]


AFTER_NF3 = "rnbqkbnr/pppppppp/8/8/8/5N2/PPPPPPPP/RNBQKB1R b KQkq - 1 1"


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "Мой первый ход — пешка на е4.",
    "Я начинаю с хода е4.",
    "Начну с е4.",
    "Я открываю партию ходом е4.",
    "Ты чёрными, движок начал с e4 — твой ход.",
    "My first move is e4.",
])
def test_a_first_move_the_engine_did_not_play_is_read_back(text):
    assert _check(text, ["Nf3"], AFTER_NF3)


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "Мой первый ход — конь на эф три.",
    "Начну с того, что конь f3 хорош.",
    "Начну с главного: у тебя крепкая позиция.",
    "А теперь вспомни пример, где белые начали с e4.",
    "Твой первый ход — е5?",
])
def test_true_or_unrelated_first_move_words_pass(text):
    assert not _check(text, ["Nf3"], AFTER_NF3)


# ── the text coach: moves numbered and in words (prod text game 28.10: «4.e4» for 3.e4, «dxc6 берёт твою пешку»
# when it took the knight, «мой последний ход — слон на c4» for the student's Bc4) ─────────────────────────────


@pytest.mark.unit
def test_the_text_coach_gets_both_moves_numbered_and_in_words():
    from src.server import _game_prestep

    session = session_store.create("u")
    board, view = game_mode.start_game(session, "black", 1200, "quiet")  # the engine opens 1.Nf3
    step = _game_prestep(session, session.get_board(view["board_id"]), "e5")
    assert "1...e5 (pawn from e7 to e5)" in step["block"]
    assert re.search(r"the engine answered 2\.\S+ \((?:pawn|knight|bishop|rook|queen|king) from [a-h][1-8] to [a-h][1-8]",
                     step["block"])
    assert "name exactly that piece" in step["block"]


@pytest.mark.unit
def test_a_capture_reply_names_the_piece_taken():
    session = session_store.create("u")
    board, _ = game_mode.start_game(session, "white", 1200, "quiet")
    state = board.game_state
    state["moves"] = ["e4", "Nc6", "d4", "Nf6", "d5", "e6", "dxc6"]
    assert game_mode.told_ply(state, 7) == "4.dxc6 (pawn from d5 to c6, takes the knight on c6)"
    assert game_mode.told_ply(state, 2) == "1...Nc6 (knight from b8 to c6)"
    assert game_mode.told_ply(state, 8) is None


@pytest.mark.unit
@pytest.mark.parametrize("text", ["Мой последний ход — слон на c4.", "My last move was Bc4."])
def test_the_students_move_called_the_coachs_last_move_is_read_back(text):
    fen = "r1bqkbnr/ppp2ppp/2np4/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4"
    ctx = CheckContext.from_fens([fen])
    ctx.game_engine_moves = ["e5", "Nc6", "d6"]
    assert [i for i in check_sentence(spoken_squares(text), ctx) if "engine plays your moves" in i]
    ctx2 = CheckContext.from_fens([fen])
    ctx2.game_engine_moves = ["e5", "Nc6", "d6"]
    assert not check_sentence(spoken_squares("Мой последний ход был d6."), ctx2)


# ── numbered claims (stand text game 28.10: «Мой последний ход был 2...Nc6» — the student's move — passed because the
# claim was read up to the first dot) ─────────────────────────────────────────────────────────────────────────────

AFTER_D4 = "r1bqkbnr/pppp1ppp/2n5/4p3/3P4/2N1P3/PPP2PPP/R1BQKBNR b KQkq - 0 3"  # 1.e3 e5 2.Nc3 Nc6 3.d4


def _claims(text, engine=("e3", "Nc3", "d4")):
    ctx = CheckContext.from_fens([AFTER_D4])
    ctx.game_engine_moves = list(engine)
    ctx.student_color = chess.BLACK
    return check_sentence(spoken_squares(text), ctx)


@pytest.mark.unit
def test_a_numbered_move_of_the_student_called_the_coachs_is_read_back():
    assert any("did not play Nc6" in i for i in _claims("Мой последний ход был 2...Nc6 — конь вышел на c6."))


@pytest.mark.unit
def test_the_number_of_the_coachs_own_move_must_be_the_records():
    assert any("was 3.d4, not 4.d4" in i for i in _claims("Мой ответ: 4.d4 — пешка в центр."))
    assert not _claims("Мой ответ: 3.d4 — пешка в центр.")
    assert not _claims("Я ответил 2.Nc3.")


# ── attacks told in the past, on the turn's own written move (stand text game 28.10: «7.Bb5, слон вышел на b5 и напал
# на твою пешку c6» — c6 held White's own pawn; «2.Nc3, конь вышел на c3 и напал на твою пешку e5») ──────────────

GAME = "e3 e5 Nc3 Nc6 d4 Nf6 a3 Be7 d5 O-O dxc6 d6 Bb5".split()


def _game_ctx(moves):
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    ctx = CheckContext.from_fens([board.fen()])
    ctx.game_moves = list(moves)
    ctx.game_engine_moves = list(moves[::2])
    ctx.student_color = chess.BLACK
    return ctx


@pytest.mark.unit
def test_an_attack_on_a_piece_of_ones_own_side_is_read_back():
    issues = check_sentence("Белые ответили 7.Bb5, слон вышел на b5 и напал на твою пешку c6.", _game_ctx(GAME))
    assert any("its own side's piece stands there" in i for i in issues)


@pytest.mark.unit
def test_a_piece_that_went_somewhere_and_attacks_what_it_cannot_is_read_back():
    issues = check_sentence("Соперник ответил 2.Nc3, конь вышел на c3 и напал на твою пешку e5.", _game_ctx(GAME[:3]))
    assert any("does not attack e5" in i for i in issues)


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "А если 8.Ba4, слон нападёт на пешку c6.",       # a line to imagine stays unchecked on the board
    "Слон b5 держит пешку c6.",                        # holding one's own pawn is fine
    "Пешка h6 бьёт твоего слона g5.",                  # names a bishop where a pawn stands: another position
])
def test_true_or_other_position_attack_words_pass(text):
    moves = GAME if "b5" in text or "c6" in text else "d4 d5 Nf3 Nf6 Bg5 h6 Bh4 g5".split()
    issues = check_sentence(text, _game_ctx(moves))
    assert not any("its own side's piece" in i or "does not attack" in i for i in issues)
