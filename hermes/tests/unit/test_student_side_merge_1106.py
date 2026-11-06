"""Merge review of the student's side (src/student_side.py, 06.11, after 9c83ae61).

- COACH_STUDENT_SIDE=shadow is pure logging: the model's prompt, the answer check's colour, the rewrite's side note and
  the voice check are exactly what prod 04.11 gave (``off``) — the decision only reaches them under ``on``.
- The dropped-«я» reading («Сыграл Qb6. Это мат?») is taken only when the clause is the verb and the move and nothing
  that could be the verb's subject: «Пошёл слон на b4», «Взяла пешка на c4», «Пошёл конь на d5», «Сыграл Карлсен Bb4»,
  «Ответил Bb4 мой соперник», «Пошёл на b4 слон» decide nothing (no decision beats a wrong one).
- A bare square in a clause told as a capture is where the capture landed, not a pawn push: «я съел пешку e5 конём»
  after 4.Nxe5 is White's move, not 1...e5; «соперник забрал пешку c4» after 2...dxc4 is Black's.
- A move in the subjunctive was not made: «Я бы тоже сыграл d4», «Если бы я сыграл d4», "I would have played d4".
"""

import io
import json
import time

import chess
import chess.pgn
import pytest
from fastapi.testclient import TestClient

from src.prompt_builder import question_moves
from src.student_side import applied, check_color, decide, legacy_color, legacy_moves

W, B = chess.WHITE, chess.BLACK


def _fen(pgn):
    return chess.pgn.read_game(io.StringIO(pgn)).end().board().fen()


def _client():
    from src.server import app

    return TestClient(app)


def _turn(monkeypatch, user, question, pgn, answer, how):
    """One text turn through /api/coach/chat with a scripted answer: (what was shown, what the model got)."""
    from unittest.mock import MagicMock, patch

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
    fen = _fen(pgn)
    session = session_store.create(user_id=user)
    session.add_board(kind="study", fen=fen, pgn=pgn)
    session.board_state = fen
    agent = MagicMock()
    agent.tools, agent._api_call_count, agent.max_iterations = [], 1, 5
    agent.model = "deepseek/deepseek-v4.1-flash"
    agent.session_prompt_tokens = agent.session_completion_tokens = agent.session_cache_read_tokens = 0
    seen = {}

    def chat(message, stream_callback=None):
        seen["message"] = message
        stream_callback(answer)
        time.sleep(0.05)
        return answer

    agent.chat.side_effect = chat
    with patch("src.server._create_agent", return_value=agent), \
            patch("src.server.load_user_profile", return_value=UserProfile(user_id=user)), \
            patch("src.server.log_event"):
        resp = _client().post("/api/coach/chat", headers={"X-User-Id": user},
                              json={"message": question, "session_id": session.id, "fen": fen, "locale": "ru"})
    shown = "".join(json.loads(ln[6:]).get("delta", "") for ln in resp.text.splitlines() if ln.startswith("data: "))
    return shown, seen.get("message", "")


T25_PGN = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6 5.d4 exd4 6.cxd4 Bb4+ 7.Bd2 Bxd2+ 8.Nbxd2 d5"
ITAL = "1.e4 e5 2.Nf3 Nc6"
PETROV_NF3 = "1.e4 e5 2.Nf3"
MATE_G7 = '[SetUp "1"]\n[FEN "5rk1/5p1p/5PpQ/8/8/8/8/6K1 w - - 0 1"]\n\n1. Qg7#'
NIMZO = "1.d4 Nf6 2.c4 e6 3.Nc3 Bb4"
ITAL_BB4 = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6 5.d4 exd4 6.cxd4 Bb4+"
QGA = "1.d4 d5 2.c4 dxc4"
ND5 = "1.e4 e5 2.Nc3 Nf6 3.Nd5"
SIC_NB4 = "1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 6.Bg5 e6 7.f4 Qb6 8.Nb3 Nc6 9.Qd2 Nb4"
NXE5 = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Nd4 4.Nxe5"
SCANDI = "1.e4 d5 2.exd5"
SICIL_D4 = "1.e4 c5 2.Nf3 d6 3.d4"


# ── 1. shadow is pure logging ─────────────────────────────────────────────────────────────────────────────────

SHADOW_CASES = [
    # (question, pgn, answer) — the opponent's move told, a side said, a subject-less mate question, nothing told
    ("Соперник ответил Nc6. Что дальше?", ITAL, "Твой конь c6 защищает пешку e5. Твой конь f3 нападает на e5."),
    ("Они сыграли Nf3. Как защитить пешку e5?", PETROV_NF3, "Твоя пешка e5 под ударом коня f3."),
    ("Я играю чёрными. Что сделают белые?", ITAL, "Твой конь c6 защищает пешку e5."),
    ("Qg7 — это мат?", MATE_G7, "Да, это мат — твой ферзь g7 защищён пешкой f6."),
    ("После Qg7 это мат?", MATE_G7, "Да, это мат — твой ферзь g7 защищён пешкой f6."),
    ("Белые сыграли Nf3. Как защитить мою пешку e5?", PETROV_NF3, "Твоя пешка e5 под ударом коня f3."),
    ("Пошёл слон на b4. Что делать?", NIMZO, "Твой слон b4 связал коня c3."),
    ("Что здесь играть?", ITAL, "Твой конь f3 нападает на пешку e5."),
]


@pytest.mark.unit
@pytest.mark.parametrize("question,pgn,answer", SHADOW_CASES, ids=[c[0] for c in SHADOW_CASES])
def test_shadow_gives_the_model_and_the_check_exactly_what_off_gives(monkeypatch, question, pgn, answer):
    shown_off, prompt_off = _turn(monkeypatch, "merge-off", question, pgn, answer, "off")
    shown_shadow, prompt_shadow = _turn(monkeypatch, "merge-shadow", question, pgn, answer, "shadow")
    assert "## The student's side" not in prompt_shadow
    assert prompt_shadow == prompt_off
    assert shown_shadow == shown_off


@pytest.mark.unit
@pytest.mark.parametrize("question", ["Qg7 — это мат?", "После Qg7 это мат?", "Ход Qg7 — мат?", "Qg7 мат?"])
@pytest.mark.parametrize("how", ["shadow", "on"])
def test_the_mate_question_keeps_the_pin(monkeypatch, question, how):
    # The 04.11 pin (the student made the move just played, 2026-10-08): «твой ферзь g7» is White's queen.
    for answer in ("Да, это мат — твой ферзь g7 защищён пешкой f6.", "Твой ферзь g7 стоит под защитой пешки f6."):
        shown, _ = _turn(monkeypatch, f"merge-qg7-{how}", question, MATE_G7, answer, how)
        assert answer in shown, (question, how, shown)


@pytest.mark.unit
def test_shadow_check_colour_is_the_04_11_pin():
    for question, pgn in [("Соперник ответил Nc6. Что дальше?", ITAL), ("Я играю чёрными.", ITAL),
                          ("Qg7 — это мат?", MATE_G7), ("Они сыграли d5. Брать?", T25_PGN),
                          ("Сыграл Карлсен Bb4. Почему?", NIMZO)]:
        fen = _fen(pgn)
        named = question_moves(question, fen)
        legacy = legacy_color(named, fen)
        side = decide(question, fen, pgn=pgn)
        used = applied(side, legacy, "shadow", pinned_moves=legacy_moves(named))
        assert check_color(used) == legacy, (question, side, used)
        assert used.note(chess.Board(fen)) == ""


@pytest.mark.unit
def test_shadow_rewrite_note_is_the_04_11_one(monkeypatch):
    from src import config
    from src.answer_check import CheckContext
    from src.server import _student_side_note

    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", "shadow", raising=False)
    ctx = CheckContext.from_fens([_fen(MATE_G7)], [], question="Qg7 — это мат?", student_color=W)
    assert "(the side to move on the board)" in _student_side_note(ctx)


@pytest.mark.unit
def test_shadow_voice_check_pins_no_side(monkeypatch):
    from unittest.mock import patch

    from src import config

    async def _no_limit(*a, **k):
        return None

    sentence = "Твой конь c6 защищает пешку e5."
    fen = _fen(ITAL)
    out = {}
    for how in ("off", "shadow", "on"):
        monkeypatch.setattr(config, "COACH_STUDENT_SIDE", how, raising=False)
        body = {"text": sentence, "fen": fen, "pgn": ITAL, "question": "Я играю белыми. Соперник сыграл Nc6.",
                "engine": False}
        with patch("src.server.enforce_rate_limit", side_effect=_no_limit), patch("src.server.log_event"):
            out[how] = _client().post("/api/coach/voice/check", headers={"X-User-Id": "merge-voice"},
                                      json=body).json()["issues"]
    assert out["shadow"] == out["off"]
    assert out["on"]  # on: the student said White, «твой конь c6» is Black's


# ── 2. the dropped «я» only where nothing else can be the subject ─────────────────────────────────────────────

NOT_FIRST = [
    (NIMZO, "Пошёл слон на b4. Что делать?"),
    (ITAL_BB4, "Пошёл слон на b4. Что делать?"),
    (QGA, "Взяла пешка на c4. Как отыграть?"),
    (ND5, "Пошёл конь на d5. Это опасно?"),
    (NIMZO, "Сыграл Карлсен Bb4. Почему?"),
    (ITAL_BB4, "Сыграл Карлсен Bb4. Почему?"),
    (NIMZO, "Сыграл гроссмейстер Bb4, почему?"),
    (NIMZO, "Ответил Bb4 мой соперник."),
    (NIMZO, "Пошёл на b4 слон. Что делать?"),
    (SIC_NB4, "Пошёл на b4 слон."),
    (SIC_NB4, "Пошёл конь на b4. Опасно?"),
]


@pytest.mark.unit
@pytest.mark.parametrize("pgn,question", NOT_FIRST)
def test_a_subject_after_the_verb_is_not_the_dropped_ya(pgn, question):
    side = decide(question, _fen(pgn), pgn=pgn)
    assert side.source != "own_move", side


@pytest.mark.unit
@pytest.mark.parametrize("pgn,question,color", [
    (NIMZO, "Сыграл Bb4. Нормально?", B),
    (NIMZO, "Сыграл Bb4+, нормально?", B),
    (NIMZO, "Пошёл слоном на b4. Нормально?", B),
    (PETROV_NF3, "Сходил конём на f3, нормально?", W),
    (NIMZO, "Сыграл Bb4 — это мат?", B),
])
def test_the_dropped_ya_still_counts(pgn, question, color):
    side = decide(question, _fen(pgn), pgn=pgn)
    assert (side.source, side.color) == ("own_move", color), side


# ── 3. a square in a capture is where it landed ───────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("pgn,question,source,color", [
    (NXE5, "Я съел пешку e5 конём. Нормально?", "own_move", W),
    (NXE5, "Я взял конём пешку e5, правильно?", "own_move", W),
    (NXE5, "Забрал конём пешку e5 — не ошибка?", "own_move", W),
    (NXE5, "I took the e5 pawn with my knight. Was it right?", "own_move", W),
    (NXE5, "Мен e5 пешкасын алдым. Дұрыс па?", "own_move", W),
    (QGA, "Соперник забрал пешку c4. Как отыграть?", "their_move", W),
    (SCANDI, "Соперник съел мою пешку d5. Брать ферзём?", "their_move", B),
    (SCANDI, "They took my d5 pawn. Recapture with the queen?", "their_move", B),
    ("1.e4 e5 2.Nf3 Nc6 3.d4 exd4", "Я взял пешку d4 пешкой. Правильно?", "own_move", B),
])
def test_a_square_taken_on_is_not_a_pawn_push(pgn, question, source, color):
    side = decide(question, _fen(pgn), pgn=pgn)
    assert (side.source, side.color) == (source, color), side


@pytest.mark.unit
def test_a_square_taken_on_twice_tells_nothing():
    pgn = "1.e4 e5 2.Nf3 Nc6 3.d4 exd4 4.Nxd4"  # both sides took on d4
    assert not decide("Я взял пешку d4. Нормально?", _fen(pgn), pgn=pgn).exact


# ── 4. a move in the subjunctive was not made ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("question", ["Я бы тоже сыграл d4. А что мне теперь?", "Если бы я сыграл d4, было бы лучше?",
                                      "I would have played d4 too. What now?", "I should have played d4, right?",
                                      "Я б сыграл d4 тоже."])
def test_a_subjunctive_move_tells_no_side(question):
    assert decide(question, _fen(SICIL_D4), pgn=SICIL_D4).source not in ("own_move", "their_move")


@pytest.mark.unit
def test_a_move_to_come_still_tells_the_side():
    side = decide("Если я возьму на d4, что дальше?", _fen(SICIL_D4), pgn=SICIL_D4)
    assert side.color in (B, None)  # never White: only Black can take on d4


# ── the first merge attempt's phrasings (3c09b90e), on the boards it used ─────────────────────────────────────

def _board(sans):
    board = chess.Board()
    for san in sans:
        board.push_san(san)
    return board


KQ_MATE = "6k1/6Q1/6K1/8/8/8/8/8 b - - 0 1"  # 1.Qg7# just played
P46 = "3qk2r/3b1pbp/B2ppp2/P2N4/1Q2PP2/8/1Pr3PP/R3K2R b KQk - 0 16"
_FR = _board("e4 e6 d4 d5 Nc3 Bb4".split())
FRENCH, FRENCH_PGN = _FR.fen(), chess.Board().variation_san(_FR.move_stack)
_QG = _board("d4 d5 c4 dxc4".split())
QGA_FEN, QGA_PGN = _QG.fen(), chess.Board().variation_san(_QG.move_stack)


@pytest.mark.unit
@pytest.mark.parametrize("question,fen,pgn", [
    ("Пошёл слон на b4 — что делать?", FRENCH, FRENCH_PGN),
    ("Взяла пешка на c4, отыгрывать?", QGA_FEN, QGA_PGN),
    ("Сыграл Карлсен Bb4 в этой партии?", FRENCH, FRENCH_PGN),
    ("Пошёл конь на d5, брать?", P46, None),
    ("Как я могу наказать Bb4?", FRENCH, FRENCH_PGN),
])
def test_first_attempt_subjects_decide_nothing(question, fen, pgn):
    side = decide(question, fen, pgn=pgn)
    assert not side.exact, (question, side)


@pytest.mark.unit
@pytest.mark.parametrize("question,fen,pgn,color", [
    ("Поставил ферзя на g7, мат?", KQ_MATE, None, W),
    ("Взял на c4. Удержу ли пешку?", QGA_FEN, QGA_PGN, B),
])
def test_first_attempt_dropped_ya_still_reads(question, fen, pgn, color):
    side = decide(question, fen, pgn=pgn)
    assert (side.color, side.source) == (color, "own_move"), (question, side)
