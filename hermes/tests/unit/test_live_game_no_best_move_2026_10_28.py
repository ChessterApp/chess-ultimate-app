"""2026-10-28, Alexander's phone (27.10): in a voice game the coach said «Мой ответ — конь на f6» while the engine
played a6, and «я забираю его слоном» while it took with the pawn. The voice coach got the full engine line — with
the best move — for positions of the game other than its live one: the student's hand move before the engine's
reply, and a request the game had overtaken. Now no position of the game gets a best move."""

import chess
import pytest

from src import game_mode, server
from src.game_mode import belongs_to_game
from src.sessions import session_store
from src.tools.game_play import live_game_board
from tests.unit.test_audio_audit_2026_10_27 import USER, _game_with, engine  # noqa: F401 — the fixture


@pytest.fixture(autouse=True)
def _clean():
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


def _fen(moves):
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    return board.fen()


def test_the_games_own_positions_are_known(engine):
    session = _game_with(["e4", "Nf3"])               # 1.e4 e5 2.Nf3 Nc6
    state = live_game_board(session).game_state
    assert state["moves"] == ["e4", "e5", "Nf3", "Nc6"]
    assert belongs_to_game(state, chess.STARTING_FEN)
    assert belongs_to_game(state, _fen(["e4", "e5"]))                       # a past ply
    assert belongs_to_game(state, _fen(["e4", "e5", "Nf3", "Nc6", "Bc4"]))  # the hand move, reply on its way
    assert not belongs_to_game(state, _fen(["d4", "d5"]))                   # another position
    assert not belongs_to_game(state, "not a fen")


def test_a_kept_side_line_is_the_games_too(engine):
    session = _game_with(["e4", "Nf3"])
    board_rec = live_game_board(session)
    game_mode.takeback_moves(session, board_rec, 1)                        # 2.Nf3 Nc6 kept as a line
    assert belongs_to_game(board_rec.game_state, _fen(["e4", "e5", "Nf3", "Nc6"]))


def test_no_engine_line_for_the_hand_move_before_the_reply(engine, monkeypatch):
    called = []
    monkeypatch.setattr(server, "engine_note", lambda fen, **kw: called.append(fen) or {"fen": fen, "note": "[Engine] Best: Nf6"})
    session = _game_with(["e4", "Nf3"])
    note = server._voice_board_note(_fen(["e4", "e5", "Nf3", "Nc6", "Bc4"]), session.id, USER)
    assert note == {"fen": _fen(["e4", "e5", "Nf3", "Nc6", "Bc4"]), "note": None, "kind": "game"}
    assert called == []


def test_no_engine_line_for_a_position_the_game_has_left(engine, monkeypatch):
    monkeypatch.setattr(server, "engine_note", lambda fen, **kw: {"fen": fen, "note": "[Engine] Best: d4"})
    session = _game_with(["e4", "Nf3"])
    note = server._voice_board_note(_fen(["e4", "e5"]), session.id, USER)
    assert note["kind"] == "game" and note["note"] is None


def test_another_board_still_gets_the_engine_line(engine, monkeypatch):
    monkeypatch.setattr(server, "engine_note", lambda fen, **kw: {"fen": fen, "note": "[Engine] Best: c4"})
    session = _game_with(["e4"])
    note = server._voice_board_note(_fen(["d4", "d5"]), session.id, USER)
    assert note["note"].endswith("[Engine] Best: c4")


def test_another_board_shown_during_the_game_keeps_its_engine_line(engine, monkeypatch):
    """A master game opened in a tab while the game is on: its opening positions are not the game's (review 28.10)."""
    monkeypatch.setattr(server, "engine_note", lambda fen, **kw: {"fen": fen, "note": "[Engine] Best: e4"})
    session = _game_with(["e4"])
    session.add_board(kind="master_game", activate=True)
    note = server._voice_board_note(chess.STARTING_FEN, session.id, USER)
    assert note["note"].endswith("[Engine] Best: e4")


def test_a_broken_kept_line_is_skipped_not_raised(engine):
    session = _game_with(["e4", "Nf3"])
    state = dict(live_game_board(session).game_state)
    state["variations"] = [{"at_ply": None, "moves": ["e5"]}, "junk", {"at_ply": 2, "moves": ["Zz9"]}]
    assert belongs_to_game(state, _fen(["e4", "e5"]))
    assert not belongs_to_game(state, _fen(["d4", "d5"]))


def test_analyze_position_in_a_game_gives_no_line_for_the_coach(engine, monkeypatch):
    import json

    from src.tools import stockfish

    def fake(fen, depth, multipv):
        return {"evaluation": 0.2, "best_move": "g8f6", "lines": [{"pv": "g8f6 b1c3 f8e7", "score": 0.2, "depth": 12}]}

    monkeypatch.setattr(stockfish, "analyze_cached", fake)
    session = _game_with(["e4", "Nf3"])                                  # live: 1.e4 e5 2.Nf3 Nc6, White to move
    ahead = json.loads(stockfish._handle_analyze_position({"fen": _fen(["e4", "e5", "Nf3", "Nc6", "Bc4"])},
                                                          session_id=session.id))
    assert "best_move" not in ahead and all("pv" not in ln for ln in ahead["lines"]) and ahead["game_note"]
    live = json.loads(stockfish._handle_analyze_position({"fen": _fen(["e4", "e5", "Nf3", "Nc6"])}, session_id=session.id))
    assert [ln["pv"] for ln in live["lines"]] == ["g8f6"]               # the student's candidate only, no reply
    other = json.loads(stockfish._handle_analyze_position({"fen": _fen(["d4", "d5"])}, session_id=session.id))
    assert other["lines"][0]["pv"] == "g8f6 b1c3 f8e7" and "game_note" not in other
    plain = json.loads(stockfish._handle_analyze_position({"fen": _fen(["e4", "e5", "Nf3", "Nc6", "Bc4"])}))
    assert plain["best_move"] == "g8f6"                                  # no session: as before


@pytest.mark.parametrize("played,sentence,wrong", [
    (["e5", "d6", "a6"], "Мой ответ — конь на f6.", True),           # screenshot 1
    (["e5", "d6", "fxe6"], "Хорошо, я забираю его слоном.", True),   # screenshot 2
    (["e5", "d6", "fxe6"], "Я забираю его пешкой.", False),
    (["e5", "Nf6"], "Отвечу конем f6.", False),
    (["e5", "Nf6"], "Мой ответ — конь на f6.", False),
    (["e5", "Nc6", "a6"], "Мой ход — конь c6.", True),               # an earlier move is not «my reply» now
    (["e5", "Nc6"], "Я сыграл e5 на первом ходу.", False),
])
def test_the_coach_names_only_the_engines_last_move(played, sentence, wrong):
    from src.answer_check import CheckContext, _coach_move_issues

    ctx = CheckContext.from_fens()
    ctx.game_engine_moves = played
    assert bool(_coach_move_issues(sentence, ctx)) is wrong


def test_the_idea_note_in_a_game_says_the_reply_is_not_the_engines_move():
    from src.prompt_builder import voice_idea_note

    note = voice_idea_note([{"san": "Be6", "verdict": "ok"}], {"note": "- Be6. The opponent's best reply: Bxe6."},
                           live_game=True)
    assert "not the move the engine will play" in note


@pytest.mark.parametrize("sentence", [
    "Если ты возьмешь на c6, я заберу пешкой d7.",
    "Если я заберу слоном, то потеряю темп.",
    "Отвечу на вопрос: конь на c6 защищает пешку e5.",
    "Ладно, ставлю тебе плюс за ход Bb5.",
    "I played e5 to fight for the centre.",
    "My reply was Nc6, defending e5.",
    "I answered Nc6, defending the pawn.",
])
def test_lines_recaps_and_everyday_words_are_not_moves_claimed(sentence):
    """Review 28.10: a conditional line, a recap of earlier moves, «отвечу на вопрос» are not «my move now»."""
    from src.answer_check import CheckContext, _coach_move_issues

    ctx = CheckContext.from_fens()
    ctx.game_engine_moves = ["e5", "Nc6", "a6"]
    assert _coach_move_issues(sentence, ctx) == []


def test_compare_variations_in_a_game_gives_no_line_for_the_coach(engine, monkeypatch):
    import json

    from src.tools import compare_variations as cv

    monkeypatch.setattr(cv, "compare_variations", lambda fen, num_lines, depth: {
        "fen": fen, "depth": depth, "variations": [{"moves": "g8f6 b1c3", "score": 0.2}, {"moves": "a7a6 d2d4", "score": 0.3}]})
    session = _game_with(["e4", "Nf3"])
    ahead = json.loads(cv._handle_compare_variations({"fen": _fen(["e4", "e5", "Nf3", "Nc6", "Bc4"])}, session_id=session.id))
    assert all("moves" not in v for v in ahead["variations"]) and ahead["game_note"]
    live = json.loads(cv._handle_compare_variations({"fen": _fen(["e4", "e5", "Nf3", "Nc6"])}, session_id=session.id))
    assert [v["moves"] for v in live["variations"]] == ["g8f6", "a7a6"]


def test_a_master_game_tab_keeps_its_full_analysis(engine, monkeypatch):
    import json

    from src.tools import stockfish

    monkeypatch.setattr(stockfish, "analyze_cached", lambda fen, depth, multipv: {
        "evaluation": 0.2, "best_move": "g8f6", "lines": [{"pv": "g8f6 b1c3", "score": 0.2, "depth": 12}]})
    session = _game_with(["e4", "Nf3"])
    session.add_board(kind="master_game", activate=True)
    out = json.loads(stockfish._handle_analyze_position({"fen": _fen(["e4", "e5", "Nf3", "Nc6", "Bc4"])}, session_id=session.id))
    assert out["lines"][0]["pv"] == "g8f6 b1c3" and "game_note" not in out


def test_the_coach_board_tab_still_counts_as_the_game(engine, monkeypatch):
    """The coach page's «coach board» tab sets the study board active while the game is on it (review 28.10)."""
    monkeypatch.setattr(server, "engine_note", lambda fen, **kw: {"fen": fen, "note": "[Engine] Best: Nf6"})
    session = _game_with(["e4", "Nf3"])
    study = session.add_board(kind="study", activate=True)
    assert session.active_board_id == study.id
    note = server._voice_board_note(_fen(["e4", "e5", "Nf3", "Nc6", "Bc4"]), session.id, USER)
    assert note == {"fen": _fen(["e4", "e5", "Nf3", "Nc6", "Bc4"]), "note": None, "kind": "game"}


# The battery of review round 3 (28.10): claims of the move just made, lines, recaps and everyday words.
_A = ['e5','Nc6','a6'] 
_B = ['d5','Nf6','fxe6'] 
_C = ['e5','d6','a6']
_FLAG = [(_C,'Мой ответ — конь на f6.'),(_B,'Хорошо, я забираю его слоном.'),(_A,'Хорошо, теперь, когда ты сыграл Bb5, мой ответ — Кf6.'),
(_A,'Теперь, когда ты сыграл Bb5, я отвечаю конём на f6.'),(_A,'Когда ты пошёл слоном, я ответил конём f6.'),(_A,'When you played Bb5, I replied Nf6.'),
(_B,'Беру ферзём на e6.'),(_B,'Беру слоном на e6.'),(_B,'Забираю слоном на e6.'),(_B,'Я забираю на e6 слоном.'),(_B,'Я беру конём на e6.'),
(_A,'Мой ход — конь c6.'),(_A,'Я пойду конём на f6.'),(_A,'I play Nf6.'),(_A,'My reply: Nf6.')]
_PASS = [(_C,'Мой ответ — пешка a6.'),(_B,'Я забираю пешкой.'),(_B,'Беру пешкой на e6.'),(_B,'Забираю на e6 пешкой f7.'),(['e5','Nf6'],'Отвечу конём f6.'),
(_A,'Если ты возьмёшь на c6, я заберу пешкой d7.'),(_A,'Если я заберу слоном, то потеряю темп.'),(_A,'Отвечу на вопрос: конь на c6 защищает пешку e5.'),
(_A,'Ладно, ставлю тебе плюс за ход Bb5.'),(_A,'I played e5 to fight for the centre.'),(_A,'My reply was Nc6, defending e5.'),(_A,'I answered Nc6, defending the pawn.'),
(_A,'Я беру паузу, подумай о Ba4.'),(_A,'Я ставлю тебе задачу: найди Bxc6.'),(_A,'Я бью тревогу: пешка e4 висит.'),(_A,'Я отвечаю за то, чтобы ты понял идею e5.'),
(_A,'I answer your question: Nc6 defends e5.'),(_A,'I answer that: Nc6 defends e5.'),(_A,'На e4 я отвечаю e5 — это открытая игра.'),(_A,'В ответ на e4 я играю e5, как в этой партии.'),
(_A,'Мой ход Кc6 защищал пешку.'),(_A,'Ты берёшь на c6 — я забираю пешкой d7.'),(_A,'На Ba4 я отвечу b5.'),(_A,'После Ba4 я отвечу b5.'),(_A,'Мой ответ — пешка a6.'),
(_A,'Я сыграл пешкой a6, чтобы прогнать слона.'),(_A,'Хожу пешкой на a6.'),(_A,'Отвечаю a6.'),(_A,'Я отвечаю пешкой a6.'),(['e5','Nf6','Nxe4'],'Забираю конём на e4.'),(['e5','Nf6','Nxe4'],'Я забираю пешку конём.')]


@pytest.mark.parametrize("played,sentence", _FLAG)
def test_a_claim_of_a_move_the_engine_did_not_make_is_caught(played, sentence):
    from src.answer_check import CheckContext, _coach_move_issues

    ctx = CheckContext.from_fens()
    ctx.game_engine_moves = played
    assert _coach_move_issues(sentence.replace("ё", "е"), ctx)


@pytest.mark.parametrize("played,sentence", _PASS)
def test_a_true_claim_a_line_or_a_recap_passes(played, sentence):
    from src.answer_check import CheckContext, _coach_move_issues

    ctx = CheckContext.from_fens()
    ctx.game_engine_moves = played
    assert _coach_move_issues(sentence.replace("ё", "е"), ctx) == []
