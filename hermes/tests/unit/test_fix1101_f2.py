"""fix1101 F2 (the scene, src/claim_scene.py): the reviews of 57bb4868 (review-fp, review-miss, 01.11).

  idea_scope   «А почему не X?» — the next sentence speaks of the piece on X's from-square: read from the parts of the
               sentence (where it tells X, a hitter on a square, a denial, a leave verb, the square X went to), not one
               wording; the _LEAVES guard runs (it never did: a '^' pattern matched at a position);
  start_cue    a piece said to stand on a square («король стоит на e2», «на e5 стоит белая пешка», «e5 занято белой
               пешкой») is an «occupied» claim judged in the initial position; on a board a line reached from it, a cue
               that names the initial position is judged there, not on the board now;
  placement    the same reading without a cue, on the board now — its own switch ('placement', off until config lists
               it);
  scene        a line's passing position does not excuse a present-tense claim about the board the line ends on; a move
               the sentence tells later is a reading of a piece named where it is not yet; the answer's scene a line
               was re-anchored on with the side to move flipped is not the «then» board.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import chess
import pytest

from src import claim_scene, config
from src.answer_check import CheckContext
from src.claim_types import Claim, MoveRef, Pos, Ref

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import load_ctx, run_answer  # noqa: E402

ROWS = Path(__file__).resolve().parents[1] / "fixtures" / "detect1031" / "rows"
SCOTCH = "e4 e5 Nf3 Nc6 d4"
QGD = "d4 d5 c4 e6 Nc3 Nf6 Bg5"
RUY = "e4 e5 Nf3 Nc6 Bb5"


@pytest.fixture(autouse=True)
def _relations_on(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    monkeypatch.setattr(config, "STOCKFISH_POOL", False, raising=False)
    monkeypatch.setattr(config, "COACH_PRECOMPUTE", False, raising=False)
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)


def _ctx(moves: str = "", question: str = "") -> CheckContext:
    b = chess.Board()
    for m in moves.split():
        b.push_san(m)
    ctx = CheckContext.from_fens([b.fen()], [moves] if moves else [], question=question)
    ctx.language = "ru"
    return ctx


def _last(sentences, ctx) -> list:
    return run_answer(list(sentences), ctx)[-1][1]


def _row(rid):
    row = json.loads((ROWS / f"{rid}.json").read_text(encoding="utf-8"))
    return row, load_ctx(row["ctx"])


# ── idea_scope ───────────────────────────────────────────────────────────────────────────────────────────────────
IDEA_FALSE = [
    # X told again: what the sentence says after X is about the board after X
    (SCOTCH, "А почему не Nxd4 сразу?", "Если сыграешь 3...Nxd4, то после d5 твой конь c6 окажется под ударом."),
    (SCOTCH, "А почему не Nxd4 сразу?", "При Nxd4 конь c6 попадёт под пешку d5."),
    (SCOTCH, "А почему не Nxd4 сразу?", "После 3...Nxd4 4.d5 конь c6 под боем."),
    # X told in words, the target a bare square after an attack word
    (SCOTCH, "А почему не Nxd4 сразу?", "Взятие конём на d4 плохо из-за d5 с нападением на c6."),
    # «с c6» after a chase verb: the square the piece is driven from
    (SCOTCH, "А почему не Nxd4 сразу?", "Nxd4 сразу плохо: белые ответят d5 и прогонят коня с c6."),
    # a forced move says the piece is there
    (SCOTCH, "А почему не Nxd4 сразу?", "Тогда белые сыграют d5, и коню c6 придётся отступить на e7."),
    # another opening, another piece; the hitter a piece named on its square
    (QGD, "А почему не dxc4 сразу?", "Тогда конь c3 продолжит давить на пешку d5."),
]


@pytest.mark.parametrize("moves,question,sentence", IDEA_FALSE)
def test_idea_scope_reason_about_the_old_square_is_cut(moves, question, sentence):
    got = _last([question, sentence], _ctx(moves))
    assert any("the move the question is about" in i and "is empty" in i for i in got), got


IDEA_TRUE = [
    # review-fp R7: a negated presence, and a leave verb (the _LEAVES guard now runs)
    (SCOTCH, "А почему не Nxd4 сразу?", "Тогда коня c6 там уже нет, и ход d5 ни на кого не нападает."),
    (SCOTCH, "А почему не Nxd4 сразу?", "Тогда конь c6 исчезнет с доски после размена, и d5 будет просто ходом в центр."),
    (SCOTCH, "А почему не Nxd4 сразу?", "Тогда белые разменяют коней, и твой конь c6 исчезнет с доски, а d5 уже не страшен."),
    # the moved piece named by its old square, with the square it went to
    (SCOTCH, "А почему не Nxd4 сразу?", "Тогда конь c6 уже стоит на d4, и после c3 его прогоняют."),
    (SCOTCH, "А почему не Nxd4 сразу?", "Тогда коню c6 придётся уйти на d4, где его разменяют."),
    # «конь с c6»: the piece that came from c6
    (SCOTCH, "А почему не Nxd4 сразу?", "Тогда ход d5 пустой: конь с c6 уже ушёл на d4."),
    # said before X is told: the board now
    (SCOTCH, "А почему не Nxd4 сразу?", "Тогда коню c6 некуда возвращаться: после Nxd4 exd4 белые сразу играют Qxd4."),
    (QGD, "А почему не dxc4 сразу?", "Тогда пешка d5 уходит из центра, и конь c3 получает поле e4."),
    (QGD, "А почему не dxc4 сразу?", "Тогда твоя пешка d5 уже на c4, и белые отыграют её ходом e3."),
    (QGD, "А почему не dxc4 сразу?", "Тогда белые сыграют e4, и пешка d5 им уже не мешает."),
]


@pytest.mark.parametrize("moves,question,sentence", IDEA_TRUE)
def test_idea_scope_true_sentences_are_not_judged(moves, question, sentence):
    got = _last([question, sentence], _ctx(moves))
    assert not any("the move the question is about" in i for i in got), got


def test_leaves_guard_runs_at_the_mention():
    # the old guard: _LEAVES.match(low, pos) with a '^' pattern never matched at pos
    assert claim_scene._LEAVES.search(" исчезнет с доски")
    assert claim_scene._LEAVES.search(" уже разменян")
    assert not claim_scene._LEAVES.search(" окажется под ударом")


def test_idea_scope_switch_off(monkeypatch):
    monkeypatch.setitem(config.DETECTOR_DEFAULTS, "idea_scope", "off")
    got = _last(["А почему не Nxd4 сразу?", "При Nxd4 конь c6 попадёт под пешку d5."], _ctx(SCOTCH))
    assert not any("the move the question is about" in i for i in got)


def test_idea_scope_dev_row():
    row, ctx = _row("can-scotch")
    got = run_answer(row["prefix"] + ["После Nxd4 пешка d5 нападёт на коня c6."], ctx)
    assert any("c6 is empty" in i for i in got[-1][1])


# ── start_cue: placement ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence,truth", [
    ("В исходной позиции король стоит на e2.", "on e2 stands White's pawn, not a king"),
    ("В исходной позиции на e5 стоит белая пешка.", "e5 is empty"),
    ("В начальной позиции чёрный ферзь стоит на e8.", "on e8 stands Black's king, not a queen"),
    ("Перед первым ходом на e5 уже стоит чужая пешка.", "e5 is empty"),
    ("В исходной позиции поле d1 занято королём.", "on d1 stands White's queen, not a king"),
    ("В начальной расстановке поле e5 уже занято.", "e5 is empty"),
])
def test_start_cue_placement_is_judged_in_the_initial_position(sentence, truth):
    got = _last([sentence], _ctx(question="Что значит запись Кр:е5?"))
    assert got == [f"in the initial position: {truth}"]


@pytest.mark.parametrize("sentence", [
    "Сейчас, в самом начале партии, поле e5 пустое, а король стоит на e1 за своими пешками.",
    "В начальной позиции ферзь стоит на d1, а король на e1.",
    "В исходной позиции задачи ферзь стоит на d3.",  # a puzzle's start, not the game's
    "В начале партии конь стоит на f3.",  # the opening phase in general: no cue
    "В начальной позиции на e5 нет пешки.",  # a denial: unjudged
])
def test_start_cue_placement_true_or_unjudged(sentence):
    assert _last([sentence], _ctx()) == []


def test_start_cue_on_a_game_board_means_the_initial_position():
    ctx = _ctx(RUY)
    assert _last(["В исходной позиции белый слон стоит на b5."], ctx) == ["in the initial position: b5 is empty"]
    # a comparison or another part of the sentence is not under the cue
    for s in ("Конь уже стоит на f3, а не на g1, как в начальной позиции.",
              "Сейчас конь стоит на f3, а в исходной позиции конь стоит на g1.",
              "Ферзь по-прежнему стоит на d1, как и в начальной позиции."):
        assert _last([s], _ctx(RUY)) == [], s


def test_start_cue_switch_off_reads_no_placement(monkeypatch):
    monkeypatch.setitem(config.DETECTOR_DEFAULTS, "start_cue", "off")
    assert _last(["В исходной позиции король стоит на e2."], _ctx()) == []


# ── placement on the board now: its own switch ──────────────────────────────────────────────────────────────────
def test_placement_without_a_cue_follows_its_switch(monkeypatch):
    # on by default since the final fix 02.11 (0 false records on the review-fp / review-fp2 true sentences)
    monkeypatch.setitem(config.DETECTOR_DEFAULTS, "placement", "shadow")
    assert _last(["Белый ферзь стоит на e2."], _ctx(RUY)) == []


def test_placement_on(monkeypatch):
    monkeypatch.setitem(config.DETECTOR_DEFAULTS, "placement", "on")
    assert _last(["Белый ферзь стоит на e2."], _ctx(RUY)) == ["on the board now: e2 is empty"]
    assert _last(["На c6 стоит чёрный слон."], _ctx(RUY)) == \
        ["on the board now: on c6 stands Black's knight, not a bishop"]
    for s in ("Белый слон стоит на b5 и давит на коня c6.", "На f3 стоит белый конь.", "Чёрный король находится на e8.",
              "Конь стоит на f3 — идеальное поле.", "Если конь будет стоять на d5, это сильно.",
              "Ферзь обычно стоит на d1 до рокировки.", "Белый ферзь стоит на e2? Нет."):
        assert _last([s], _ctx(RUY)) == [], s


def test_placement_shadow(monkeypatch):
    monkeypatch.setitem(config.DETECTOR_DEFAULTS, "placement", "shadow")
    ctx = _ctx(RUY)
    assert _last(["Белый ферзь стоит на e2."], ctx) == []
    assert any(n == "placement" for n, _t, _l in getattr(ctx, "detector_shadow", []))


# ── the scene's boards ───────────────────────────────────────────────────────────────────────────────────────────
def test_a_passing_position_of_the_line_to_the_board_now_is_no_reading():
    row, ctx = _row("op-show-ck-attack")
    got = run_answer(row["prefix"] + ["Nc3, не давая чёрным сыграть d5."], ctx)
    assert any("Black can still play d5" in i for i in got[-1][1])


def test_end_alts_keeps_lines_that_do_not_end_on_the_board_now():
    ctx = _ctx("e4 c6")
    e4, c6, d4 = MoveRef(san="e4", piece="P", to="e4", number="1.", side=True), MoveRef(san="c6", piece="P", to="c6"), \
        MoveRef(san="d4", piece="P", to="d4")
    ends_now = Pos(alts=(Pos(at="after", moves=(e4,)), Pos(at="after", moves=(e4, c6))))
    assert [len(a.moves) for a in claim_scene._end_alts(ends_now, ctx, {})] == [2]
    # a variation from the board now: its passing positions stay readings
    other = Pos(alts=(Pos(at="after", moves=(d4,)), Pos(at="after", moves=(d4, MoveRef(san="d5", piece="P", to="d5")))))
    assert len(claim_scene._end_alts(other, ctx, {})) == 2


def test_a_move_told_later_is_a_reading_of_a_piece_not_there_yet():
    ctx = _ctx("e4 e5 Nf3 Nc6 Bc4 Nd4")
    got = _last(["А почему не Nxe5?", "Тогда ферзь g5 нападает на коня e5 и на пешку g2: после Qg5 у белых две беды."], ctx)
    assert got == []


def test_a_flipped_scene_is_not_the_end_of_an_unplayable_line():
    after_d5_flipped = chess.Board("r1bqkbnr/pppp1ppp/2n5/3Pp3/4P3/5N2/PPP2PPP/RNBQKB1R b KQkq - 0 3")
    told = (MoveRef(san="Nxd4", piece="N", to="d4", capture=True, number="3...", side=False),
            MoveRef(san="d5", piece="P", to="d5", number="4.", side=True))
    assert not claim_scene._fits_told(after_d5_flipped, told)
    fits = chess.Board("r1bqkbnr/pppp1ppp/8/3Pp3/3n4/5N2/PPP2PPP/RNBQKB1R b KQkq - 0 4")
    assert claim_scene._fits_told(fits, told)
    assert claim_scene._fits_told(after_d5_flipped, ())
    # the next sentence is not judged on the re-anchored board
    got = _last(["После 3...Nxd4 4.d5 всё ясно.", "Тогда конь c6 под ударом пешки d5."], _ctx(SCOTCH))
    assert not any("at the end of the line before" in i for i in got)


def test_placement_claim_shape(monkeypatch):
    monkeypatch.setitem(config.DETECTOR_DEFAULTS, "placement", "off")
    ctx = _ctx()
    state: dict = {}
    claims = claim_scene._placement_claims("В начальной позиции на поле e5 стоит белая пешка.", ctx, state, "start")
    assert claim_scene._placement_claims("На поле e5 стоит белая пешка.", ctx, state, "start") == []  # not under the cue
    assert len(claims) == 1
    c = claims[0]
    assert isinstance(c, Claim) and c.rel == "occupied" and c.kind == "placement"
    assert c.objs == (Ref(sq="e5", piece="P", side=chess.WHITE, text=c.objs[0].text),)
