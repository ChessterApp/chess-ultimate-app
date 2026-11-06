"""Second review of the student's side (src/student_side.py, 06.11, after 0ed79c39).

- A question with no subject about the move just played («Qxf7 — это мат?», "Is Qxf7 mate?", «После Qxf7 это мат?»)
  lost the 04.11 pin (the student made it, 2026-10-08): the decision has nothing better, so the pin stays.
- A master game on the board is nobody's, whatever the words say, and so is one loaded mid-turn (get_game_pgn); the
  voice check knows it from the session.
- A game started mid-answer decides the colour the game checks read, over the words of the question.
- «я взял на c6» after 4.Bxc6 dxc6 is either side's: a square told alone gives a colour only when every arrival the
  clause fits («слоном», «коня», a capture) is one side's; and in shadow a move other than the pin's never flips it.
- «Я белых поймал?», «Я белым отдал пешку», «Я чёрных не боюсь», «Қаралар үшін қауіп бар ма?» say no side.
"""

import io
import json
import time

import chess
import chess.pgn
import pytest
from fastapi.testclient import TestClient

from src.answer_check import CheckContext, check_sentence
from src.student_side import (StudentSide, applied, check_color, decide, legacy_color, legacy_moves)

W, B = chess.WHITE, chess.BLACK


def _fen(pgn):
    return chess.pgn.read_game(io.StringIO(pgn)).end().board().fen()


MATE_PGN = "1.e4 e5 2.Bc4 Nc6 3.Qh5 Nf6 4.Qxf7#"
MATE = _fen(MATE_PGN)
RUY_X_PGN = "1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Bxc6 dxc6 5.Nxe5"
RUY_X = _fen(RUY_X_PGN)
QG5_PGN = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Nd4 4.Nxe5 Qg5"
QG5 = _fen(QG5_PGN)
RUY_BA4 = "r1bqkbnr/1ppp1ppp/p1n5/4p3/B3P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 1 4"


def _applied(question, fen, pgn, how, master_game=False):
    from src.prompt_builder import question_moves

    named = question_moves(question, fen)
    side = decide(question, fen, pgn=pgn, master_game=master_game)
    return side, applied(side, legacy_color(named, fen), how, pinned_moves=legacy_moves(named))


def _ctx(question, fen, pgn, how):
    _side, used = _applied(question, fen, pgn, how)
    ctx = CheckContext.from_fens([fen], [pgn] if pgn else [], question=question, student_color=check_color(used))
    ctx.student_side_why = used.why()
    ctx.student_side_source = used.source
    return ctx


def _client():
    from src.server import app

    return TestClient(app)


def _agent(script):
    from unittest.mock import MagicMock

    agent = MagicMock()
    agent.tools, agent._api_call_count, agent.max_iterations = [], 1, 5
    agent.model = "deepseek/deepseek-v4.1-flash"
    agent.session_prompt_tokens = agent.session_completion_tokens = agent.session_cache_read_tokens = 0
    seen = {}

    def chat(message, stream_callback=None):
        seen["message"] = message
        text = []
        for i, step in enumerate(script):
            if isinstance(step, tuple):
                tool, args, result = step
                agent.tool_start_callback(f"c{i}", tool, args)
                time.sleep(0.05)
                agent.tool_complete_callback(f"c{i}", tool, args, json.dumps(result))
            else:
                stream_callback(step)
                text.append(step)
            time.sleep(0.05)
        return "".join(text)

    agent.chat.side_effect = chat
    return agent, seen


def _turn(monkeypatch, user, question, fen, script, pgn=None, source=None, how="shadow"):
    """One text turn through /api/coach/chat with a scripted answer (text and tool steps)."""
    from unittest.mock import patch

    from src import config
    from src.sessions import session_store
    from src.user_profile import UserProfile

    for name, value in {"COACH_TWO_STAGE": False, "COACH_ENGINE_NOTE": False, "COACH_OPENING_PRESTEP": False,
                        "COACH_HYPOTHETICAL_NOTE": False, "COACH_ANSWER_FIX": False, "COACH_ANSWER_CHECK": True,
                        "COACH_PUZZLE_PRESTEP": False, "COACH_SITE_PUZZLE_LOOKUP": False,
                        "COACH_RELATION_CHECK": "off"}.items():
        if hasattr(config, name):
            monkeypatch.setattr(config, name, value)
    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", how, raising=False)
    session = session_store.create(user_id=user)
    if pgn or source:
        kwargs = {"kind": "master_game" if source else "study", "fen": fen}
        if pgn:
            kwargs["pgn"] = pgn
        board = session.add_board(**kwargs)
        if source:
            board.source = dict(source)  # loading the PGN forgets a database id: the game tools set it after
    session.board_state = fen
    agent, seen = _agent(script if isinstance(script, list) else [script])
    with patch("src.server._create_agent", return_value=agent), \
            patch("src.server.load_user_profile", return_value=UserProfile(user_id=user)), \
            patch("src.server.log_event"):
        resp = _client().post("/api/coach/chat", headers={"X-User-Id": user},
                              json={"message": question, "session_id": session.id, "fen": fen, "locale": "ru"})
    shown = "".join(json.loads(ln[6:]).get("delta", "") for ln in resp.text.splitlines() if ln.startswith("data: "))
    return shown, seen.get("message", "")


# ── 1. the move just played, asked about with no subject: the 04.11 pin stays ─────────────────────────────────

SUBJECTLESS = ["Qxf7 — это мат?", "Is Qxf7 mate?", "После Qxf7 это мат?", "Ход Qxf7 — мат?", "Qxf7#?"]


@pytest.mark.unit
@pytest.mark.parametrize("question", SUBJECTLESS)
@pytest.mark.parametrize("how", ["shadow", "on"])
def test_subjectless_question_keeps_the_pin(question, how):
    side, used = _applied(question, MATE, MATE_PGN, how)
    assert not side.exact and (used.color, used.source) == (W, "legacy"), (side, used)
    ctx = _ctx(question, MATE, MATE_PGN, how)
    assert check_sentence("Да, это мат — твой ферзь f7 защищён слоном c4.", ctx) == []
    assert check_sentence("Yes, your queen on f7 is protected by your bishop on c4.", ctx) == []
    assert used.note(chess.Board(MATE)) == ""  # the model is not told a side the 04.11 server did not tell


@pytest.mark.unit
@pytest.mark.parametrize("question", ["Qxf7 — это мат?", "Is Qxf7 mate?", "После Qxf7 это мат?"])
@pytest.mark.parametrize("how", ["shadow", "on"])
def test_subjectless_question_through_the_server(monkeypatch, question, how):
    answer = ("Yes, it is mate: your queen on f7 is protected by your bishop on c4." if question.startswith("Is")
              else "Да, это мат — твой ферзь f7 защищён слоном c4.")
    shown, model_saw = _turn(monkeypatch, f"side2-mate-{how}", question, MATE, answer, pgn=MATE_PGN, how=how)
    assert answer in shown, (question, how, shown)
    assert "## The student's side" not in model_saw


@pytest.mark.unit
def test_the_pins_own_move_told_as_someone_elses_still_drops_it():
    # t46 («Белые поставили коня на d5»): the move of the pin told as White's — the student is not the mover
    p46 = "3qk2r/3b1pbp/B2ppp2/P2N4/1Q2PP2/8/1Pr3PP/R3K2R b KQk - 0 16"
    side, used = _applied("Белые поставили коня на d5. Брать?", p46, None, "on")
    assert side.source == "other_mover" and check_color(used) is None, (side, used)
    # shadow is pure logging: the 04.11 pin (Black just moved? no — «already played» Nd5 is White's: White)
    from src.prompt_builder import question_moves

    _side, shadow = _applied("Белые поставили коня на d5. Брать?", p46, None, "shadow")
    assert check_color(shadow) == legacy_color(question_moves("Белые поставили коня на d5. Брать?", p46), p46)


# ── 2. a master game on the board is nobody's ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("question", [
    "Почему они сыграли Ba4, а не Bxc6?",
    "Почему Карлсен сыграл O-O? Я бы сыграл d4.",
    "Как играть за белых в этой партии?",
    "Что делать белыми дальше в этой партии?",
    "Я играю чёрными — как бы я тут защищался?",
])
@pytest.mark.parametrize("how", ["shadow", "on"])
def test_a_master_game_outranks_every_word(question, how):
    side = decide(question, RUY_BA4, master_game=True)
    assert (side.color, side.source) == (None, "master_game")
    # on: the 04.11 pin is dropped too; shadow: the 04.11 pin itself (pure logging, merge review 06.11)
    assert check_color(applied(side, W, how, ("Ba4",))) == (None if how == "on" else W)
    assert side.note(chess.Board(RUY_BA4)) == ""


@pytest.mark.unit
def test_a_master_game_on_the_board_tells_the_model_no_side(monkeypatch):
    pgn = "1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4"
    shown, model_saw = _turn(monkeypatch, "side2-master", "Как играть за белых в этой партии?", RUY_BA4,
                             "Белые обычно рокируются.", pgn=pgn, source={"twic_game_id": 123}, how="on")
    assert "The student plays White" not in model_saw


def _db_game_pgn():
    return ('[White "Carlsen, M."]\n[Black "Caruana, F."]\n[Event "Test"]\n[Date "2019.01.01"]\n[Result "1-0"]\n\n'
            "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 1-0")


@pytest.mark.unit
@pytest.mark.parametrize("source", ["said", "own_move", "their_move", "legacy"])
def test_a_game_loaded_mid_turn_drops_a_side_from_words(monkeypatch, source):
    from src import config
    from src.answer_check_db import note_board_game
    from src.server import _student_side_note

    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", "on", raising=False)
    ctx = CheckContext.from_fens([RUY_BA4], [], question="Покажи партию Карлсена", student_color=W)
    ctx.student_side_why, ctx.student_side_source = "the student said so: «я за белых»", source
    note_board_game(ctx, _db_game_pgn())
    assert ctx.student_color is None and ctx.student_side_why == ""
    note = _student_side_note(ctx)
    assert "neither side is the student" in note and "The student plays" not in note
    # shadow: the colour stays as 04.11 left it
    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", "shadow", raising=False)
    ctx = CheckContext.from_fens([RUY_BA4], [], question="Покажи партию Карлсена", student_color=W)
    ctx.student_side_source = source
    note_board_game(ctx, _db_game_pgn())
    assert ctx.student_color == W


@pytest.mark.unit
def test_a_game_against_the_coach_keeps_its_colour_when_a_master_game_loads(monkeypatch):
    from src import config
    from src.answer_check_db import note_board_game

    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", "shadow", raising=False)
    ctx = CheckContext.from_fens([RUY_BA4], [], question="x", student_color=B)
    ctx.student_side_source = "game"
    note_board_game(ctx, _db_game_pgn())
    assert ctx.student_color == B
    for how in ("off",):  # 04.11 as it was
        monkeypatch.setattr(config, "COACH_STUDENT_SIDE", how, raising=False)
        ctx = CheckContext.from_fens([RUY_BA4], [], question="x", student_color=W)
        ctx.student_side_source = "legacy"
        note_board_game(ctx, _db_game_pgn())
        assert ctx.student_color == W


@pytest.mark.unit
def test_a_game_loaded_by_get_game_pgn_drops_the_said_side(monkeypatch):
    # The path the text turn takes after each tool (src/server → note_tool_result): «Я играю чёрными. Покажи партию
    # Карлсена» applies Black under on; get_game_pgn then puts Carlsen's game on the board — nobody's.
    from src import config
    from src.answer_check_db import note_tool_result
    from src.server import _student_side_note

    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", "on", raising=False)
    question = "Я играю чёрными. Покажи партию Карлсена с Каруаной."
    side = decide(question, chess.STARTING_FEN)
    used = applied(side, None, "on")
    ctx = CheckContext.from_fens([chess.STARTING_FEN], [], question=question, student_color=check_color(used))
    ctx.student_side_why, ctx.student_side_source = used.why(), used.source
    assert ctx.student_color == B
    result = {"pgn": _db_game_pgn(), "headers": {"White": "Carlsen, M.", "Black": "Caruana, F."},
              "board_actions": [{"type": "load_pgn", "pgn": _db_game_pgn()}]}
    note_tool_result(ctx, "get_game_pgn", json.dumps(result), shown=True)
    assert ctx.student_color is None
    assert "neither side is the student" in _student_side_note(ctx)


# ── 3. a game started mid-answer decides the colour ───────────────────────────────────────────────────────────

@pytest.mark.unit
def test_a_game_started_mid_answer_decides_the_colour(monkeypatch):
    # The student said Black; the tool started the game with the student as White (from this position, at random).
    # 1.e4 was the student's, 1...e5 the engine's: «Твой ход был e5» is wrong and must be caught by the game's colour.
    game = {"board_id": "g1", "student_color": "white", "engine_elo": 1200, "status": "playing", "moves": ["e4", "e5"],
            "fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2", "ply": 2,
            "student_to_move": True}
    result = {"ok": True, "board_actions": [{"type": "game", "game": game}]}
    shown, _ = _turn(monkeypatch, "side2-game", "Давай сыграем, я за чёрных", chess.STARTING_FEN,
                     [("start_game", {"color": "random"}, result), "Начали! Твой ход был e5. Хорошее начало."],
                     how="on")
    assert "Твой ход был e5" not in shown, shown


# ── 4. a square told alone: every arrival the clause fits ─────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("question,color", [
    ("Я взял на c6, а потом забрал пешку Nxe5. Правильно?", None),
    ("Я взял на c6. Потом Nxe5 — нормально?", None),
    ("Они взяли на c6. Что теперь?", None),
    ("I took on c6. Was it right?", None),
    ("Я пошёл слоном на c6 и взял коня. Правильно?", W),
    ("Взял коня на c6", W),
    ("Я взял слоном на c6", W),
    ("Я взял пешкой на c6", B),
    ("Я забрал слона на c6", B),
    ("I took the knight on c6", W),
    ("I took with the pawn on c6", B),
    ("Они взяли слоном на c6", B),  # their bishop: the student is Black
])
def test_a_square_in_an_exchange(question, color):
    side = decide(question, RUY_X, pgn=RUY_X_PGN)
    if color is None:
        assert not side.exact, side
    else:
        assert side.exact and side.color == color, side


@pytest.mark.unit
@pytest.mark.parametrize("question", ["Я взял на c6, а потом забрал пешку Nxe5. Правильно?",
                                      "Я взял на c6. Потом Nxe5 — нормально?"])
@pytest.mark.parametrize("how", ["shadow", "on"])
def test_the_exchange_keeps_the_pin_and_the_true_sentences(question, how):
    ctx = _ctx(question, RUY_X, RUY_X_PGN, how)
    assert ctx.student_color == W
    for sentence in ("Твой конь на e5 стоит активно.", "Твоя пешка e4 в центре сильна.", "Your knight on e5 attacks f7."):
        assert check_sentence(sentence, ctx) == [], sentence


@pytest.mark.unit
def test_shadow_is_the_04_11_pin_whatever_the_decision():
    # Merge review 06.11: shadow only logs — the pin of 04.11 (or nothing) reaches the checks, whatever was decided.
    own_c6 = StudentSide(B, "own_move", "я взял на c6", ("@c6",))
    assert check_color(applied(own_c6, W, "shadow", ("Nxe5",))) == W
    assert check_color(applied(own_c6, W, "on", ("Nxe5",))) == B  # on: the decision
    their_f5 = StudentSide(W, "their_move", "они сыграли f5", ("f5",))
    assert check_color(applied(their_f5, B, "shadow", ("f5",))) == B
    assert check_color(applied(their_f5, B, "on", ("f5",))) == W  # on corrects it (t25)
    said = StudentSide(B, "said", "я играю чёрными")
    assert check_color(applied(said, W, "shadow", ("Nxe5",))) == W
    assert check_color(applied(said, None, "shadow")) is None
    assert check_color(applied(said, None, "on")) == B
    agree = StudentSide(W, "own_move", "я сыграл Nf3", ("Nf3",))
    assert check_color(applied(agree, W, "shadow", ("Nxe5",))) == W


@pytest.mark.unit
def test_a_record_without_the_square_tells_nothing():
    # «они взяли на d6»: nothing ever arrived on d6 in the record — not this game's move, no board guess
    assert not decide("Они взяли на d6", RUY_X, pgn=RUY_X_PGN).exact


# ── 5. a colour after «я» as an object ────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("question", [
    "Я белых поймал? Qg5 сильно?",
    "Я белым отдал пешку e5, сыграл Qg5. Правильно?",
    "Я чёрных не боюсь",
    "Я белыми пешками атакую королевский фланг",
    "Я белые поля ослабил?",
    "Қаралар үшін қауіп бар ма?",
    "Ақтар үшін жағдай қалай?",
])
def test_a_colour_as_an_object_is_no_side_said(question):
    assert decide(question, QG5, pgn=QG5_PGN).source != "said", question


@pytest.mark.unit
@pytest.mark.parametrize("question,color", [
    ("Я — чёрные, что делать?", B),
    ("я черные", B),
    ("Я белыми, план?", W),
    ("Я играл чёрными, где ошибся?", B),
    ("Я за чёрных", B),
    ("Ақтар үшін не істеу керек?", W),
    ("Қаралар үшін қалай ойнаймын?", B),
])
def test_a_side_said_after_ya_still_counts(question, color):
    side = decide(question, QG5)
    assert (side.color, side.source) == (color, "said"), (question, side)


@pytest.mark.unit
@pytest.mark.parametrize("question", ["Я белым отдал пешку e5, сыграл Qg5. Правильно?", "Я белых поймал? Qg5 сильно?"])
def test_a_colour_object_keeps_the_pin_in_shadow(question):
    ctx = _ctx(question, QG5, QG5_PGN, "shadow")
    assert ctx.student_color == B
    assert check_sentence("Твой ферзь g5 нападает на g2 и на коня e5.", ctx) == []


# ── 6. the voice check knows the master game from the session ─────────────────────────────────────────────────

def _voice(question, text, fen, pgn, session_id=None):
    from unittest.mock import patch

    async def _no_limit(*a, **k):
        return None

    body = {"text": text, "fen": fen, "pgn": pgn, "question": question, "engine": False}
    if session_id:
        body["session_id"] = session_id
    with patch("src.server.enforce_rate_limit", side_effect=_no_limit), patch("src.server.log_event"):
        return _client().post("/api/coach/voice/check", headers={"X-User-Id": "side2-voice"}, json=body).json()


@pytest.mark.unit
def test_voice_they_about_a_master_game_pins_no_side(monkeypatch):
    from src import config
    from src.sessions import session_store

    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", "on", raising=False)
    pgn = "1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4"
    session = session_store.create(user_id="side2-voice")
    board = session.add_board(kind="master_game", fen=RUY_BA4, pgn=pgn)
    board.source = {"twic_game_id": 7}
    # «они сыграли a6» on a master game: with the opponent's move read (3...a6 was Black's) the student would be White
    # and «твой конь c6» cut as Black's — the master game is nobody's, so the sentence is judged as with no «они».
    sentence = "Твой конь c6 защищает пешку e5."
    on_master = _voice("Почему они сыграли a6?", sentence, RUY_BA4, pgn, session.id)
    no_session = _voice("Почему они сыграли a6?", sentence, RUY_BA4, pgn)  # unknown: the opponent's move decides nothing
    plain = _voice("Почему сыграно a6?", sentence, RUY_BA4, pgn)
    assert plain["issues"] == []
    assert on_master["issues"] == plain["issues"], on_master
    # the same words about a study board of the session: the opponent's move still decides under on
    study = session_store.create(user_id="side2-voice")
    study.add_board(kind="study", fen=RUY_BA4, pgn=pgn)
    assert _voice("Почему они сыграли a6?", sentence, RUY_BA4, pgn, study.id)["issues"]
    assert no_session["issues"] == plain["issues"], no_session


# ── a piece as the subject of a move told as done: a report of a move, not the student's own ──────────────────
# shipped1104/fp t12: «Пешка пошла на g5. Куда отступать конём?» — White's 13.g5; the 04.11 pin made the student White
# and cut «…а защищают её конь c3 и ферзь d3» as the opponent's pieces. Restoring the pin for subject-less questions
# must not bring that back.

P12 = "r2qkb1r/1p3pp1/2bp1n1p/p3p1P1/4P3/P1NQ3P/1PPB1P2/R3KB1R b KQkq - 0 13"
P12_PGN = ("1. e4 c5 2. Nf3 e6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 d6 6. g3 Nc6 7. h3 Bd7 8. g4 h6 9. a3 Nxd4 10. Qxd4 e5 "
           "11. Qd3 Bc6 12. Bd2 a5 13. g5")


@pytest.mark.unit
@pytest.mark.parametrize("question", ["Пешка пошла на g5. Куда отступать конём?",
                                      "The pawn went to g5. Where should my knight go?"])
@pytest.mark.parametrize("how", ["on"])
def test_a_piece_told_as_the_mover_drops_the_pin(question, how):
    side, used = _applied(question, P12, P12_PGN, how)
    assert side.source == "other_mover" and check_color(used) is None, (side, used)
    ctx = _ctx(question, P12, P12_PGN, how)
    assert check_sentence("Слон c6 вместе с конём давят на пешку e4, а защищают её конь c3 и ферзь d3.", ctx) == []


@pytest.mark.unit
@pytest.mark.parametrize("question,color", [
    ("Моя пешка пошла на g5, хорошо?", W),
    ("My pawn went to g5, good?", W),
    ("I pushed the pawn to g5", W),  # an English noun after the verb is its object
    ("Я сыграл g5. Хорошо?", W),
])
def test_the_students_own_piece_or_an_object_still_tells_the_move(question, color):
    side = decide(question, P12, pgn=P12_PGN)
    assert (side.color, side.source) == (color, "own_move"), (question, side)


@pytest.mark.unit
def test_a_piece_with_a_move_to_come_keeps_the_pin():
    # «Ферзь бьёт f7?» proposes a move — it tells no one; a question with the move alone keeps the 04.11 pin
    assert decide("Ферзь бьёт f7 — это мат?", MATE, pgn=MATE_PGN).source == "side_to_move"
