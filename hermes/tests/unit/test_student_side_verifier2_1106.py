"""Second verifier of the student's side (src/student_side.py, 06.11, after c1f60dc0) — wrong exact decisions ``on``
made where prod 04.11 had none. No decision is better than a wrong one: the 04.11 pin then applies.

- A side the student only seems to state: the colour as an object ("I have White on the ropes", "I have Black in
  zugzwang"), a question about which side («Мне играть белыми или чёрными?», «Я играю белыми? Или чёрными?», "Should I
  play as White or Black?"), a preference («Я сам за белых не люблю играть») or another game («в прошлой партии», «в
  следующем турнире»).
- «они»/"they" right after the student's own pieces («Мои кони отличные, они пошли на g5 и f7»).
- "I wouldn't have played f5": the contraction is the subjunctive too.
- «Я ответил на Nc3 ходом a6»: the move answered is not the subject's.
Stated sides that still decide: "I have White.", "I have the white pieces", «У меня белые, а у него чёрные», «Я играю
чёрными, а белые сыграли f5», "What should I play as Black?". Shadow stays the 04.11 pin for all of them.
"""

import io

import chess
import chess.pgn
import pytest

from src.answer_check import CheckContext, check_sentence
from src.prompt_builder import question_moves
from src.student_side import applied, check_color, decide, legacy_color, legacy_moves

W, B = chess.WHITE, chess.BLACK

FEG = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5 5.exd5 Nxd5 6.Nxf7"   # Black to move, White just sacrificed
NIMZO = "1.d4 Nf6 2.c4 e6 3.Nc3 Bb4"                              # White to move, Black just played Bb4
KID = "1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.Be2 e5 7.O-O Nc6 8.d5 Ne7 9.Ne1 Nd7 10.f3 f5"  # White to move
QGD = "1.d4 d5 2.c4 e6 3.Nc3"                                     # Black to move


def _fen(pgn):
    return chess.pgn.read_game(io.StringIO(pgn)).end().board().fen()


def _used(q, pgn, how):
    f = _fen(pgn)
    named = question_moves(q, f)
    side = decide(q, f, pgn=pgn)
    return side, applied(side, legacy_color(named, f), how, pinned_moves=legacy_moves(named)), legacy_color(named, f)


def _cuts(q, pgn, how, sentences):
    _side, used, _leg = _used(q, pgn, how)
    ctx = CheckContext.from_fens([_fen(pgn)], [pgn], question=q, student_color=check_color(used))
    return {s: check_sentence(s, ctx) for s in sentences if check_sentence(s, ctx)}


SAID_OVERREACH = [
    "I have White on the ropes after Bb4?",
    "I have Black in zugzwang?",
    "Should I play as White or Black in this line?",
    "Мне играть белыми или чёрными?",
    "Чем играть за белых и чёрных в этом дебюте?",
    "Я играю белыми? Или чёрными?",
    "Я сам за белых не люблю играть",
    "Я играл за белых в прошлой партии, а сейчас за чёрных. Bb4 хорошо?",
    "Я играю чёрными в следующем турнире, а сейчас белыми",
    "Я обычно играю белыми, Bb4 сильно?",
    "I usually play White. Is Bb4 good?",
]


@pytest.mark.unit
@pytest.mark.parametrize("q", SAID_OVERREACH)
def test_no_side_said_where_none_is_stated_for_this_game(q):
    side = decide(q, _fen(NIMZO), pgn=NIMZO)
    assert side.source != "said", side
    assert not side.exact or side.color == B, side  # never White on the board where the student is Black


@pytest.mark.unit
@pytest.mark.parametrize("q", ["I have White on the ropes after Bb4?",
                               "Я играл за белых в прошлой партии, а сейчас за чёрных. Bb4 хорошо?",
                               "Я сам за белых не люблю играть. Bb4 хорошо?"])
@pytest.mark.parametrize("how", ["shadow", "on"])
def test_true_sentences_for_the_black_student_stay(q, how):
    sentences = ["Your bishop on b4 pins the knight on c3.", "Да, твой слон b4 связывает коня c3.",
                 "Твой конь f6 контролирует e4."]
    assert _cuts(q, NIMZO, how, sentences) == {}


STATED = [
    ("I have White.", W), ("I have the white pieces", W), ("I have Black here, what now?", B),
    ("У меня белые, а у него чёрные. Что делать?", W), ("Я играю чёрными, а белые сыграли f5.", B),
    ("What should I play as Black?", B), ("Я играю белыми. Что дальше?", W), ("Что делать чёрными?", B),
    ("Я за чёрных, соперник сыграл Nc3.", B),
]


@pytest.mark.unit
@pytest.mark.parametrize("q,color", STATED)
def test_a_stated_side_still_decides(q, color):
    side = decide(q, _fen(QGD), pgn=QGD)
    assert (side.color, side.exact) == (color, True), side


@pytest.mark.unit
@pytest.mark.parametrize("q", ["Мои кони отличные, они пошли на g5 и f7. Жертва верная?",
                               "My knights are strong, they went to g5 and f7. Is the sac sound?",
                               "Мои кони отличные. Они пошли на g5 и f7."])
def test_they_after_the_students_own_pieces_is_no_opponent(q):
    side, used, _ = _used(q, FEG, "on")
    assert side.source != "their_move", side
    assert check_color(used) in (W, None), used


@pytest.mark.unit
def test_they_alone_is_still_the_opponent():
    side = decide("Они сыграли Nxf7. Брать королём?", _fen(FEG), pgn=FEG)
    assert (side.color, side.source) == (B, "their_move")


@pytest.mark.unit
@pytest.mark.parametrize("q", ["I wouldn't have played f5", "I shouldn't have played f5"])
def test_a_contracted_subjunctive_tells_no_mover(q):
    side = decide(q, _fen(KID), pgn=KID)
    assert side.source != "own_move", side
    assert _cuts(q, KID, "on", ["Your knight on e1 can go to d3.", "Your pawn on d5 is strong."]) == {}


@pytest.mark.unit
@pytest.mark.parametrize("q", ["Я ответил на Nc3 ходом a6, нормально?", "I replied to Nc3 with a6 — fine?"])
def test_the_move_answered_is_not_the_subjects(q):
    side = decide(q, _fen(QGD), pgn=QGD)
    assert side.source != "conflict", side
    assert not any(m.lstrip("@") == "Nc3" for m in side.moves), side


@pytest.mark.unit
@pytest.mark.parametrize("q", ["Соперник пожертвовал коня на f7. Брать королём?", "Соперница сыграла Nxf7. Брать?",
                               "The opponent sacrificed a knight with Nxf7. Do I take?"])
def test_more_ways_to_tell_the_opponents_move(q):
    side = decide(q, _fen(FEG), pgn=FEG)
    assert (side.color, side.exact) == (B, True), side
    assert _cuts(q, FEG, "on", ["Твой король e8 может взять коня f7."]) == {}


ALL_Q = [(NIMZO, q) for q in SAID_OVERREACH] + [(QGD, q) for q, _c in STATED] + [
    (FEG, "Мои кони отличные, они пошли на g5 и f7."), (KID, "I wouldn't have played f5"),
    (QGD, "Я ответил на Nc3 ходом a6, нормально?"), (FEG, "Соперник пожертвовал коня на f7."),
    (NIMZO, "Пошёл слон на b4. Что делать?"), (NIMZO, "Сыграл Карлсен Bb4. Почему?"),
]


@pytest.mark.unit
@pytest.mark.parametrize("pgn,q", ALL_Q, ids=[q[:40] for _p, q in ALL_Q])
def test_shadow_is_the_0411_pin(pgn, q):
    _side, used, leg = _used(q, pgn, "shadow")
    assert check_color(used) == leg
    assert used.note(chess.Board(_fen(pgn))) == ""
