"""fix1101 F1: the relation grammar and judge after the reviews of next-1031 (57bb4868).

  pin_escape   the move M the sentence tells for a pin's end — whoever makes it — binds the board: the pin held right
               before M (the board's last move when it is M; a legal move of the side to move when it is not; the
               piece named by its square must be M's side's), and an affirmative report of another piece's move
               («Bd2 развязывает коня c3») is also judged after M: the pin that held is gone. «снять связку», a
               proposal and the past are pin_escape's switch, not pin_noun's.
  locked       a blocker or cause anywhere in the clause, or a hedge, leaves the strict «no way out» unjudged; the
               subject is read on either side of the cue, in the dative before «некуда», unsquared when unique.
  cover_cause  the loss and the hold are read apart (either order, a causal link, no contrast); a lost piece named by
               its kind alone is bound to the game's capture on the square.
  lines        a later capture on a pawn's square no longer drops the pawn move; two SAN moves alike are two moves.

Each mechanism is tested with true sentences that must stay clean and false ones that must be cut, on boards other
than the reviewers' rows where possible.
"""
from __future__ import annotations

import sys
from pathlib import Path

import chess
import pytest

from src import claim_grammar as cg
from src import claim_judge as J
from src.claim_types import Claim, MoveRef, Ref

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import run_answer  # noqa: E402

NIMZO = "d4 Nf6 c4 e6 Nc3 Bb4"
RUY = "e4 e5 Nf3 Nc6 Bb5 d6 d4"
RUY_BD7 = "e4 e5 Nf3 Nc6 Bb5 d6 d4 Bd7"
QGD = "d4 d5 c4 e6 Nc3 Nf6 Bg5"
ELEPHANT = "d4 d5 c4 e6 Nc3 Nf6 Bg5 Nbd7 cxd5 exd5 Nxd5"
LEGAL = "e4 e5 Nf3 d6 Bc4 Bg4 Nc3 g6"
CARO = "e4 c6 d4 d5 e5 Bf5"
FRENCH = "e4 e6 d4 d5 e5"
KID = "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5 O-O Nc6 d5 Ne7"
SCOTCH = "e4 e5 Nf3 Nc6 d4"
FIELD_F6 = "e4 Nc6 Nf3 e5 d4 exd4 e5 Nf6 exf6"  # Black's knight f6 taken by the pawn from e5


def _ctx(moves: str, student=None, game: bool = False):
    from src.answer_check import CheckContext

    mv = moves.split()
    b = chess.Board()
    for m in mv:
        b.push_san(m)
    ctx = CheckContext.from_fens([b.fen()], [" ".join(mv)] if mv else [], question="", student_color=student)
    if game or student is not None:
        ctx.game_moves = mv
        first = 0 if student == chess.WHITE else 1
        ctx.game_engine_moves = [m for i, m in enumerate(mv) if i % 2 != first]
    ctx.language = "ru"
    return ctx


def _issues(moves: str, sentence: str, **kw) -> list:
    return run_answer([sentence], _ctx(moves, **kw))[-1][1]


def _kinds(text: str, kind: str) -> list:
    return [c for c in cg.extract(text, {}) if c.kind == kind]


# ── pin_escape: the board of the told move ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("moves,sentence", [
    (NIMZO, "Bd2 развязывает коня c3."),
    (NIMZO, "4.Bd2 развязывает коня c3."),
    (NIMZO, "После Bd2 конь c3 выходит из-под связки."),
    (NIMZO, "Ход Bd2 выводит коня c3 из-под связки."),
    (NIMZO, "Bd2 — и конь c3 выходит из-под связки."),
    (NIMZO, "После Bd2 связка коня c3 исчезает."),
    (NIMZO, "Сыграй Bd2: конь c3 уходит из-под связки."),
    (NIMZO, "Qd2 тоже развязывает коня c3, но слон лучше."),  # a new relative pin to the queen is not the old one
    (NIMZO, "Играй Bd2, чтобы развязать коня c3."),
    (NIMZO, "Связку можно снять ходом Bd2."),
    (NIMZO, "Ход Qc2 не развязывает коня c3, но защищает его."),
    (QGD, "4...Be7 развязывает коня f6."),
    (QGD, "Be7 — и связка с коня f6 снята."),
    (QGD, "После Be7 конь f6 больше не под связкой."),
    (RUY, "Bd7 развязывает коня c6."),
    (RUY_BD7, "4...Bd7 — и конь c6 выходит из-под связки."),
    (RUY_BD7, "Ход Bd7 развязал коня c6."),
    (RUY_BD7, "Ход 4...Bd7 снял связку с коня c6."),
    (LEGAL, "Nxe5! — конь f3 уходит из-под связки, жертвуя ферзя."),
    (LEGAL, "h3 не снимает связку с коня f3."),
    (LEGAL, "Чтобы снять связку, сыграй h3."),
    (ELEPHANT, "Nxd5! — конь f6 уходит из-под связки, потому что на 7.Bxd8 следует Bb4+."),
    (ELEPHANT, "Бери конём: Nxd5, конь f6 выходит из-под связки с выигрышем фигуры."),
])
def test_true_unpinning_stays_clean(moves, sentence):
    assert _issues(moves, sentence) == []


def test_true_unpinning_in_a_game_stays_clean():
    assert _issues(RUY_BD7, "Ты сыграл 4...Bd7, и конь c6 вышел из-под связки.", student=chess.BLACK) == []
    assert _issues(RUY_BD7, "4...Bd7 — отличный ход: ты развязал коня c6.", student=chess.BLACK) == []


@pytest.mark.parametrize("moves,sentence,where", [
    (NIMZO, "h3 развязывает коня c3.", "after 4.h3"),
    (NIMZO, "Ход e3 снимает связку с коня c3.", "after 4.e3"),
    (NIMZO, "Сыграй g3: конь c3 уходит из-под связки.", "after 4.g3"),
    (NIMZO, "После e3 связка коня c3 исчезает.", "after 4.e3"),
    (NIMZO, "Белые сыграли h3 и вывели коня c3 из-под связки.", "after 4.h3"),
    (NIMZO, "После Nf3 конь c3 выходит из-под связки.", "after 4.Nf3"),
    (QGD, "Nbd7 развязывает коня f6.", "after 4...Nbd7"),
    (QGD, "h6 снимает связку с коня f6.", "after 4...h6"),
    (RUY, "a6 снимает связку с коня c6.", "after 4...a6"),
    (LEGAL, "Ход d3 развязывает коня f3.", "after 5.d3"),
])
def test_a_move_that_leaves_the_pin_is_cut_after_it(moves, sentence, where):
    got = _issues(moves, sentence)
    assert len(got) == 1 and got[0].startswith(where) and "still pinned" in got[0], got


@pytest.mark.parametrize("moves,sentence,where", [
    (CARO, "Nd2 развязывает коня b1.", "before 4.Nd2"),
    (CARO, "Ход Nd2 выводит коня b1 из-под связки.", "before 4.Nd2"),
    (CARO, "Конь b1 уходит из-под связки ходом Nd2.", "before 4.Nd2"),
    (CARO, "Ход Nd2 снимает связку с коня b1.", "before 4.Nd2"),
    (CARO, "Nd2, и конь избавляется от связки.", "before 4.Nd2"),
    (CARO, "Nd2 — конь прыгает из-под связки.", "before 4.Nd2"),
    (CARO, "Nd2 — теперь конь не под связкой.", "before 4.Nd2"),
])
def test_no_pin_before_the_move_is_cut_before_it(moves, sentence, where):
    got = _issues(moves, sentence)
    assert got and got[0].startswith(where) and "not pinned" in got[0], got


def test_proposals_and_remove_are_judged_under_pin_escape_not_pin_noun():
    # CARO: no pin on the board — the proposal is cut with pin_escape on, though pin_noun ships in shadow
    assert _issues(CARO, "Белым надо развязать коня b1.")
    assert _issues(CARO, "Главное — убрать коня b1 из-под связки слона f5.")
    c = _kinds("Белым нужно снять связку с коня b1.", "pin_escape")[0]
    assert c.rel == "pin_exists" and J._detectors(c, None) == ["pin_escape"]


def test_the_told_move_binds_to_the_side_and_square_the_words_name():
    # «Nxd5» said to Black after 6.Nxd5: Black's Nf6xd5 now, not White's last move — the knight named is f6's
    c = _kinds("Nxd5! — конь f6 уходит из-под связки.", "pin_escape")[0]
    assert c.objs[0].sq == "f6" and c.presup == "before_move" and c.move.san == "Nxd5"
    ctx = _ctx(ELEPHANT)
    b = ctx.current
    frames = J._escape_frames(c, b, ctx)
    assert len(frames) == 1 and frames[0][0] is b and chess.square_name(frames[0][2].from_square) == "f6"


def test_an_opponents_move_or_a_moment_is_not_the_unpinning_move():
    # «после 3...Bb4 надо развязать коня c3»: Bb4 is the moment, the pin is on the board after it
    c = _kinds("После 3...Bb4 надо развязать коня c3.", "pin_escape")[0]
    assert c.presup == "exists" and c.move is None
    # the pinner's side cannot unpin White's knight: no reading binds, the claim stays undecided
    claim = Claim("pinned", None, (Ref(sq="c3", piece="N"),), move=MoveRef(san="Ba5", piece="B", to="a5"),
                  presup="before_move", kind="pin_escape", escape=True)
    ctx = _ctx(NIMZO)
    assert J._escape_frames(claim, ctx.current, ctx) == []


def test_negation_question_future_and_purpose_keep_only_the_presupposition():
    for text in ("h3 не развязывает коня c3.", "Bd2 развязывает коня c3?", "Сыграй a3, чтобы развязать коня c3.",
                 "После a3 конь c3 выйдет из-под связки."):
        got = _kinds(text, "pin_escape")
        assert got and not any(c.escape for c in got), text
    assert _kinds("Bd2 развязывает коня c3.", "pin_escape")[0].escape


def test_unpinning_claims_carry_the_escape_flag_through_dicts():
    c = _kinds("Bd2 развязывает коня c3.", "pin_escape")[0]
    assert Claim.from_dict(c.to_dict()).escape is True
    assert "escape" not in Claim("pinned", None, ()).to_dict()


# ── locked ───────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("moves,sentence", [
    (KID, "Слон g7 пока заперт цепью d6–e5."),
    (KID, "Слон g7 пока заперт пешечной цепью."),
    (KID, "Чёрный слон g7 — «плохой»: он заперт центром."),
    (KID, "Слон g7 упирается в собственную пешку e5 и сейчас заперт."),
    (KID, "Слон g7 фактически заперт."),
    (FRENCH, "Слон c8 почти заперт."),
    (FRENCH, "Слон c8 заперт."),
    (FRENCH, "Чёрный слон c8 заперт своими пешками."),
    ("", "Ладья a1 заперта."),
])
def test_locked_true_or_hedged_stays_clean(moves, sentence):
    assert _issues(moves, sentence) == []


@pytest.mark.parametrize("moves,sentence", [
    (FRENCH, "Чёрный ферзь без ходов."),
    (FRENCH, "У белых ферзь заперт на d1."),
    (FRENCH, "У белых заперт ферзь d1."),
    (FRENCH, "Ферзю d1 некуда ходить."),
    (FRENCH, "Слон f1 замурован."),
    (FRENCH, "Твой слон f1 сидит взаперти."),
    (FRENCH, "Твой ферзь d1 оказался заперт."),
    (KID, "Конь e7 заперт."),
])
def test_locked_false_in_any_word_order_is_cut(moves, sentence):
    assert _issues(moves, sentence), sentence


def test_locked_after_a_numbered_line_in_the_future():
    assert _issues("e4 c6", "На 2.d4 d5 3.e5 чёрный слон c8 окажется заперт.")  # Caro-Kann: the bishop is free
    assert _issues("e4 e6", "На 2.d4 d5 3.e5 чёрный слон c8 окажется заперт.") == []  # French: it is locked


# ── cover_cause ──────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Поле f6 контролировала пешка g7, поэтому конь там и погиб.",
    "Конь пропал на f6, потому что это поле держала пешка g7.",
    "Пешка g7 контролировала f6, и конь был потерян.",
    "Конь пропал: f6 держит пешка g7.",
    "На f6 конь погиб из-за пешки g7.",
    "Из-за того, что пешка g7 бьёт f6, твой конь потерялся.",
    "Это была ошибка: поле f6 держала пешка g7, и коня там съели.",
    "Конь потерялся, потому что пешка g7 смотрела на f6.",
])
def test_cover_cause_in_any_order_is_cut(sentence):
    got = _issues(FIELD_F6, sentence, student=chess.BLACK)
    assert any("g7 is Black's own" in i and "exf6" in i for i in got), got


@pytest.mark.parametrize("sentence", [
    "Пешка g7 держала f6, но конь всё равно погиб.",  # a contrast: the hold is no cause
    "Конь потерялся, хотя пешка g7 держала f6.",
    "Пешка g7 держит f6, поэтому твой слон погиб.",  # no bishop was lost on f6: unbound
    "Поле f6 держала пешка g7, и твой конь там не потерялся бы.",
])
def test_cover_cause_stays_unjudged_without_a_bound_cause(sentence):
    assert not any("own" in i for i in _issues(FIELD_F6, sentence, student=chess.BLACK))


def test_cover_cause_true_cause_stays_clean():
    # the pawn that took on f6 came from e5: it is no longer there, the claim cannot be judged false
    assert _issues(FIELD_F6, "Поле f6 било пешкой e5, и конь там потерялся.", student=chess.BLACK) == []


# ── lines: a recapture on a pawn's square, two moves alike ───────────────────────────────────────────────────────
def test_a_capture_on_a_pawns_square_keeps_the_pawn_move():
    text = "Позиция после 1.e4 e5 2.d4 d6 3.c3 Be7 4.Nf3 Nf6 5.Bc4 exd4 6.O-O Nxe4: пешка d4 защищена ферзём d8."
    sans = [m.san for m in cg.written_moves(text)]
    assert sans[:4] == ["e4", "e5", "d4", "d6"] and "exd4" in sans
    assert _issues("", text)  # the board after the line: the queen d8 does not defend d4 (d6 is in the way)


def test_a_long_move_still_restates_its_pawn_move():
    assert [(m.frm, m.to) for m in cg.written_moves("Сыграй e2-e4 (e4).")] == [("e2", "e4")]


def test_two_san_moves_alike_are_two_moves():
    assert [m.san for m in cg.written_moves("Тогда после Nxd4 Nxd4 exd4 Qxd4 ферзь в центре.")] == \
        ["Nxd4", "Nxd4", "exd4", "Qxd4"]
    assert len(cg.written_moves("Nc6: конь с b8 встал на c6.")) == 1


def test_an_untold_move_leaves_the_end_of_a_pin_unjudged():
    # the move that ended the pin is not in the sentence: the board now is after it — never judged there
    after_bd2 = NIMZO + " Bd2"
    assert _issues(after_bd2, "Это снимает связку с коня c3.") == []
    assert _issues(after_bd2, "Конь c3 вышел из-под связки.") == []
    assert _issues(after_bd2, "Белые развязали коня c3.") == []
    c = _kinds("Конь ушёл из-под связки.", "pin_escape")[0]
    assert J.decide(c, J.BoardSet(primary=chess.Board(), where=""), None).status == "undecided"
