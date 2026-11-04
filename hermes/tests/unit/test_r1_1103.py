"""fix1103 R1 (verify1102b §6): material_order cut true sentences main leaves alone, in two classes.

(a) approximation   «почти», «примерно», «практически», «приблизительно», «близко к …», «около <amount>», "roughly",
                    "nearly", "almost", "about/close to <amount or equality>" make a material claim approximate: an
                    equality holds within 2 points, a lead is judged by its direction, a difference within 2 points —
                    never as exact («позиция близка к равной по материалу» on a +1 board, fresh-fp-2 m14#2);
(b) a move told     a material outcome of a move the student is told to make («забирай коня и возвращай материал в
                    равновесие», live st1#12) is judged on the board after that move when the words determine its
                    material (a written move, or every capture that fits taking the same), otherwise left unjudged —
                    never on the board before it. With only a dash or a comma between them the claim may be about now
                    or after: it holds on either.
material_order off is main's reading, verbatim.
"""
from __future__ import annotations

import chess
import pytest

from src import answer_check as ac


def _fen(moves: str) -> str:
    b = chess.Board()
    for m in moves.split():
        b.push_san(m)
    return b.fen()


W1 = "r5k1/5ppp/8/8/8/2N1B3/5PPP/6K1 w - - 0 1"  # N+B against R: White +1
W1P = "6k1/5ppp/8/8/8/8/3P1PPP/6K1 w - - 0 1"  # White a pawn up
W2 = "6k1/5ppp/8/8/8/8/2PP1PPP/6K1 w - - 0 1"  # White two pawns up
W5 = "6k1/5ppp/8/8/8/8/R4PPP/6K1 w - - 0 1"  # White a rook up
W9 = "6k1/5ppp/8/8/8/8/Q4PPP/6K1 w - - 0 1"  # White a queen up
B1 = "6k1/4pppp/8/8/8/8/5PPP/6K1 b - - 0 1"  # Black a pawn up
B2 = "6k1/3ppppp/8/8/8/8/5PPP/6K1 w - - 0 1"  # Black two pawns up
ST1_12 = _fen("e4 e5 Nf3 Nc6 Bc4 Be7 O-O d6 d3 Na5 h3 Nxc4")  # Black took the bishop; dxc4 evens it
SCOTCH = _fen("e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nxd4")  # Black took the knight; Qxd4 evens it
QGD = _fen("d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 h6 Bxf6")  # Black to move: gxf6 or Bxf6 evens it
FREE = "r1bqkb1r/pppp1ppp/2n5/4p3/3nP3/2N2N2/PPPP1PPP/R1BQKB1R w KQkq - 0 1"  # equal; Nxd4 wins a knight, Nxe5 a pawn


@pytest.fixture(autouse=True)
def _switches(monkeypatch):
    for k in ("COACH_DETECTORS_OFF", "COACH_DETECTORS_SHADOW"):
        monkeypatch.delenv(k, raising=False)


def _material(fen: str, sentence: str) -> list:
    ctx = ac.CheckContext.from_fens([fen])
    return [i for i in ac.check_sentence(sentence, ctx) if i.startswith("material")]


# ── (a) approximation ────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("fen,sentence", [
    (W1, "Разница всего в одну единицу, так что позиция близка к равной по материалу."),
    (W1, "Позиция близка к равной по материалу."),
    (W1P, "Позиция близка к материальному равенству."),
    (W1, "Материал почти поровну."),
    (W2, "По материалу практически равенство."),
    (W2, "Практически равный материал у сторон."),
    (W1, "Материал приблизительно равный."),
    (B1, "Материала у обеих сторон примерно поровну."),
    (W2, "У белых примерно на пешку больше."),
    (B1, "Чёрные впереди почти на две пешки."),
    (W1, "Разница в материале — около двух пешек."),
    (W2, "Белые опережают по материалу примерно на одну пешку."),
    (W1P, "It is almost equal material."),
    (W1, "Material is close to equal."),
    (W1, "Material is roughly equal."),
])
def test_an_approximate_claim_is_never_read_as_exact(fen, sentence):
    assert _material(fen, sentence) == [], sentence


@pytest.mark.parametrize("fen,sentence", [
    (W9, "Материал почти равный."),
    (W5, "Позиция близка к равной по материалу."),
    (W9, "Material is roughly equal."),
    (W9, "It is almost equal material."),
    (B2, "У белых примерно на пешку больше."),  # the wrong side, however approximate
    (W5, "Материал практически равный."),
    (W1P, "Материал равный."),  # no hedge: exact
    (W2, "У белых на пешку больше."),
])
def test_an_approximate_claim_far_off_or_on_the_wrong_side_is_still_false(fen, sentence):
    assert _material(fen, sentence), sentence


@pytest.mark.parametrize("sentence", [
    "Партия фактически решена — белые впереди на целую ладью.",  # prod st2#9: «фактически» softens the game, not the lead
    "Партия почти решена — у белых на пешку больше.",
    "Ты почти выиграл, у белых на две пешки больше.",
])
def test_a_hedge_of_another_predicate_leaves_the_lead_exact(sentence):
    assert _material(W9, sentence), sentence


@pytest.mark.parametrize("sentence", [
    "Подумай о короле: материал равный.",
    "Think about it: material is equal.",
    "Пешка стоит около короля, а материал равный.",
])
def test_an_ambiguous_word_away_from_the_claim_is_no_hedge(sentence):
    assert _material(W1P, sentence), sentence


# ── (b) a move the student is told to make ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("fen,sentence", [
    (ST1_12, "Так что твой ход фактически бесплатный: забирай коня и возвращай материал в равновесие."),
    (SCOTCH, "Забирай коня ферзём — и материал снова равный."),
    (SCOTCH, "Бери коня на d4, и по материалу снова поровну."),
    (SCOTCH, "Отыграешь фигуру — и снова материал поровну."),
    (SCOTCH, "Отыгрывай фигуру и восстанавливай материальное равенство."),
    (SCOTCH, "Take the knight with the queen and material is level again."),
    (SCOTCH, "Recapture on d4 and the material is equal."),
    (QGD, "Возьми слона пешкой g7 — и материал равный."),
    (QGD, "Забирай слона, и материал снова одинаковый."),
    (QGD, "Верни фигуру, и материал опять равный."),
    (QGD, "Сыграй Bxf6, и материал равный."),
])
def test_the_outcome_of_a_told_move_is_judged_after_it(fen, sentence):
    assert _material(fen, sentence) == [], sentence


@pytest.mark.parametrize("fen,sentence,shown", [
    (FREE, "Забирай коня d4 — и материал равный.", "after N"),
    (FREE, "Take the knight on d4 and material is equal.", "after N"),
    (SCOTCH, "Забирай коня ферзём — и у тебя лишняя фигура.", "after Qxd4"),
    (QGD, "Возьми слона пешкой g7 — и у чёрных на пешку больше.", "after gxf6"),
    (QGD, "Возьми gxf6, и у чёрных лишний конь.", "after gxf6"),
])
def test_a_false_outcome_is_caught_on_the_board_after(fen, sentence, shown):
    issues = _material(fen, sentence)
    assert issues and shown in issues[0], (sentence, issues)


@pytest.mark.parametrize("fen,sentence", [
    (FREE, "Бери, и материал равный."),  # a knight or a pawn: the material after is not told
    (FREE, "Забирай что-нибудь, и материал выровняется."),
    (SCOTCH, "Возвращай материал в равновесие."),  # the result told, not the move
    (FREE, "Выиграй материал, и по материалу снова поровну."),
])
def test_an_outcome_whose_move_is_not_determined_is_left_unjudged(fen, sentence):
    assert _material(fen, sentence) == [], sentence


@pytest.mark.parametrize("fen,sentence,flagged", [
    (SCOTCH, "Материал равный — забирай коня.", True),  # the claim before the move: now
    (ST1_12, "У чёрных лишний слон, так что забирай коня.", False),
    (SCOTCH, "Бери коня — сейчас у чёрных лишняя фигура.", False),  # «сейчас»: now
    (SCOTCH, "Бери коня — сейчас материал равный.", True),
    (SCOTCH, "Бери коня, у чёрных лишняя фигура.", False),  # open: true now
    (FREE, "Бери коня d4, у белых на ладью больше.", True),  # open: false now and after
])
def test_a_claim_about_now_beside_a_told_move(fen, sentence, flagged):
    assert bool(_material(fen, sentence)) == flagged, sentence


def test_a_move_for_the_other_side_is_not_the_students(monkeypatch):
    # the student plays Black and White is to move: «забирай» is the student's next move, after a reply — unjudged
    ctx = ac.CheckContext.from_fens([SCOTCH], student_color=chess.BLACK)
    issues = [i for i in ac.check_sentence("Забирай коня, и материал снова равный.", ctx) if i.startswith("material")]
    assert issues == []


# ── the switch ───────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("fen,sentence", [
    (W1, "Позиция близка к равной по материалу."),
    (ST1_12, "Так что твой ход фактически бесплатный: забирай коня и возвращай материал в равновесие."),
    (W1P, "Практически равный материал у сторон."),
    (FREE, "Забирай коня d4 — и материал равный."),
])
def test_off_is_still_mains_reading(monkeypatch, fen, sentence):
    monkeypatch.setenv("COACH_DETECTORS_OFF", "material_order")
    ctx = ac.CheckContext.from_fens([fen])
    text = sentence.lower().replace("ё", "е")
    assert ac._material_issues(text, sentence, ctx) == ac._material_issues_v1029(text, sentence, ctx)
