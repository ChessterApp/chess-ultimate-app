"""P3B of plan 31.10 (detect-1031): the scene and the judge.

The scene reads which board a sentence means from its own words (src/claim_scene.py, extract → boards_for/remember):
  start_cue       «в самом начале партии», «в начальной позиции», «на доске сейчас» — the diagram guards step aside;
  idea_scope      «А почему не X?» — the next sentence is about the board after X; a piece named on X's from-square,
                  with a later move that would hit that square, is not there any more;
  bare_pawn_line  «Если чёрные сыграют d5, ты ответишь e5, …» — the conditional claim is judged after that line (shadow);
  loaded_line     «больше не» about a move of a game the turn loaded — the positive relation before it (shadow).
The judge (src/claim_judge.py) decides the new relations — locked (≤ 1 move or reach), cover_cause, pin_exists — and the
presuppositions before_move / exists / no_longer; F5 (an absent piece counted as defended) and F10 («висит» with no
winning capture: undecided). Every mechanism obeys its switch (config.detector_mode): off — nothing; shadow — logged.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import chess
import pytest

from src import claim_grammar, claim_judge, claim_scene, config
from src.answer_check import CheckContext, check_sentence
from src.claim_types import UNDECIDED, BoardSet, Claim, MoveRef, Pos, Ref

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import load_ctx, run_answer  # noqa: E402

ROWS = Path(__file__).resolve().parents[1] / "fixtures" / "detect1031" / "rows"
START = chess.STARTING_FEN


@pytest.fixture(autouse=True)
def _relations_on(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)


def _mode(monkeypatch, name, mode):
    monkeypatch.setitem(config.DETECTOR_DEFAULTS, name, mode)


def _board(moves: str = "", fen: str = START) -> chess.Board:
    b = chess.Board(fen)
    for m in moves.split():
        b.push_san(m)
    return b


def _ctx(moves: str = "", fen: str = START, question: str = "", student=None, game=False) -> CheckContext:
    b = _board(moves, fen)
    lines = [moves] if moves else []
    ctx = CheckContext.from_fens([b.fen()], lines, question=question, student_color=student)
    if game:
        ctx.game_moves = moves.split()
    ctx.language = "ru"
    return ctx


def _run(sentences, ctx):
    return [(s, issues) for s, issues, _stage in run_answer(list(sentences), ctx)]


def _row(rid):
    row = json.loads((ROWS / f"{rid}.json").read_text(encoding="utf-8"))
    return row, load_ctx(row["ctx"])


def _shadowed(ctx, name):
    return [line for n, _text, lines in getattr(ctx, "detector_shadow", []) if n == name for line in lines]


# ── start_cue ────────────────────────────────────────────────────────────────────────────────────────────────────
R_NOTATION = ("Сейчас, в самом начале партии, король на e5 попасть не может — поле слишком далеко и занято своими же "
              "фигурами, так что хода «Кр:e5» тут просто нет.")


def test_start_cue_judges_the_initial_position():
    got = _run([R_NOTATION], _ctx(question="Что значит запись Кр:е5?"))
    assert got[-1][1] == ["in the initial position: e5 is empty"]


def test_without_the_cue_the_diagram_guard_holds():
    # the same claim with no word pointing at the board: a lesson's diagram told in words, not judged
    got = _run(["Король на e5 попасть не может — поле слишком далеко и занято своими же фигурами."], _ctx())
    assert got[-1][1] == []


@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_start_cue_switch(monkeypatch, mode):
    _mode(monkeypatch, "start_cue", mode)
    ctx = _ctx(question="Что значит запись Кр:е5?")
    assert _run([R_NOTATION], ctx)[-1][1] == []
    assert bool(_shadowed(ctx, "start_cue")) == (mode == "shadow")


def test_start_cue_is_off_in_the_lesson_tutor():
    ctx = _ctx()
    ctx.relation_surface = "lesson"
    assert check_sentence(R_NOTATION, ctx) == []


@pytest.mark.parametrize("sentence", [
    "В начальной позиции слон c1 заперт пешками b2 и d2.",  # true there
    "Сейчас, в самом начале партии, слон c1 заперт пешками b2 и d2.",
    # the words point at a board the turn does not have (the lesson's task): the pieces named are not on this one
    "На доске сейчас первая задача урока: ферзь на d3 защищает пешку e4.",
])
def test_start_cue_true_controls(sentence):
    assert _run([sentence], _ctx())[-1][1] == []


# ── idea_scope ───────────────────────────────────────────────────────────────────────────────────────────────────
SCOTCH = "e4 e5 Nf3 Nc6 d4"


def test_idea_scope_the_moved_piece_is_not_on_its_old_square():
    got = _run(["А почему не Nxd4 сразу?", "Подумай, что случится с твоим конём c6 после d5."], _ctx(SCOTCH))
    assert got[-1][1] == ["after 3...Nxd4 (the knight from c6 now stands on d4), the move the question is about: "
                          "c6 is empty"]


def test_idea_scope_the_row():
    row, ctx = _row("can-scotch")
    got = run_answer(row["prefix"] + [row["sentence"]], ctx)
    assert got[-1][1] and "after 3...Nxd4" in got[-1][1][0] and "c6 is empty" in got[-1][1][0]


@pytest.mark.parametrize("sentences", [
    # the old square named for the piece that moved, and nothing said about that square: the moved piece, named the
    # usual way (the pawn from b6 now on a7 — test_relation_integration)
    ["А почему не Nxd4 сразу?", "Тогда белые разменяют коней, и твой конь c6 исчезнет с доски."],
    ["А почему не Nxd4 сразу?", "Тогда твой конь c6 окажется в центре, но его тут же разменяют."],
    # the sentence tells X again: it narrates the move
    ["А почему не Nxd4 сразу?", "После Nxd4 Nxd4 твой конь c6 уже разменян, а d5 ничего не даёт."],
    # «конь с c6»: the piece that came from c6
    ["А почему не Nxd4 сразу?", "Конь с c6 уходит в центр, и после d5 ему ничего не грозит."],
    # the idea lasts one sentence
    ["А почему не Nxd4 сразу?", "Хороший вопрос.", "Подумай, что случится с твоим конём c6 после d5."],
    # no piece named on the from-square (design-detect §2): «после d5» is reachable as exd5
    ["Почему не d5?", "После d5 размен на d5 ведёт к симметричной позиции."],
])
def test_idea_scope_true_controls(sentences):
    moves = "e4 e6 d4" if sentences[0] == "Почему не d5?" else SCOTCH
    assert _run(sentences, _ctx(moves))[-1][1] == []


@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_idea_scope_switch(monkeypatch, mode):
    _mode(monkeypatch, "idea_scope", mode)
    ctx = _ctx(SCOTCH)
    assert _run(["А почему не Nxd4 сразу?", "Подумай, что случится с твоим конём c6 после d5."], ctx)[-1][1] == []
    assert bool(_shadowed(ctx, "idea_scope")) == (mode == "shadow")


def test_the_idea_board_is_the_then_board_of_the_next_sentence_only():
    ctx = _ctx("e4 c6 d4 d5 e5 Bf5")
    state = {}
    claim_scene.remember("Почему не c3 сразу?", [], ctx, state)
    then = Claim(rel="attack", subj=Ref(sq="f5", piece="B"), objs=(Ref(sq="b1"),), pos=Pos(at="then"))
    boards = claim_scene.boards_for(then, ctx, state)
    assert boards is not None and boards.primary.fen().startswith("rn1qkbnr/pp2pppp/2p5/3pPb2/3P4/2P5/PP3PPP/")
    claim_scene.remember("Тогда слон с f5 спокойно отходит.", [], ctx, state)
    claim_scene.remember("Это нормально.", [], ctx, state)
    assert claim_scene.IDEA_KEY not in state and claim_scene.THEN_KEY not in state


# ── bare_pawn_line (shadow by default) ───────────────────────────────────────────────────────────────────────────
def _with_claim(monkeypatch, marker, make):
    """The grammar of this branch (P3A emits «locked» later): add the claim P3A emits for the sentence holding *marker*."""
    orig = claim_grammar.extract

    def ext(text, state, language=None):
        out = list(orig(text, state, language))
        low = claim_grammar.normalize(text).lower()
        i = low.find(marker)
        if i >= 0:
            out.append(make(i))
        return out

    monkeypatch.setattr(claim_grammar, "extract", ext)


def _locked_c8(skip="future"):
    return lambda i: Claim(rel="locked", subj=Ref(sq="c8", piece="B", owner="their", text="слон"), objs=(),
                           pos=Pos(at="skip", tense="future", skip_reason=skip), span=(i, i + 25))


@pytest.mark.parametrize("mode", ["shadow", "on"])
def test_bare_pawn_line_the_row(monkeypatch, mode):
    _mode(monkeypatch, "bare_pawn_line", mode)
    # P3D's «prevents» cuts the sentence before (op-show-ck-attack: «d4 … не давая чёрным поставить пешку на d5»), and
    # a sentence not shown leaves no line for the next one (answer_check.check_sentence): with it on, this row is one
    # the rewrite hides. The line «d4 … d5, e5» is judged here as the sentence before had told it.
    _mode(monkeypatch, "prevents", "off")
    _with_claim(monkeypatch, "слон на c8 останется", _locked_c8())
    row, ctx = _row("op-show-ck-eval")
    got = run_answer(row["prefix"] + [row["sentence"]], ctx)
    want = "after 3.e5: Black's bishop on c8 is not locked in: it can go to h3, g4, f5, e6 and d7 (5 moves)"
    if mode == "on":
        assert got[-1][1] == [want]
    else:
        assert got[-1][1] == [] and _shadowed(ctx, "bare_pawn_line") == [want]


def test_bare_pawn_line_off(monkeypatch):
    _mode(monkeypatch, "bare_pawn_line", "off")
    _mode(monkeypatch, "prevents", "off")
    _with_claim(monkeypatch, "слон на c8 останется", _locked_c8())
    row, ctx = _row("op-show-ck-eval")
    assert run_answer(row["prefix"] + [row["sentence"]], ctx)[-1][1] == []
    assert not _shadowed(ctx, "bare_pawn_line")


def test_bare_pawn_line_french_bishop_is_locked(monkeypatch):
    _mode(monkeypatch, "bare_pawn_line", "on")
    _with_claim(monkeypatch, "слон c8 останется", _locked_c8("conditional"))
    ctx = _ctx("e4 e6 d4 d5")
    assert _run(["Если белые сыграют e5, слон c8 останется запертым."], ctx)[-1][1] == []


@pytest.mark.parametrize("sentence,moves", [
    ("Если белые сыграют e5, конь f6 окажется под ударом.", "e4 Nf6"),  # attacked after 2.e5: true
    ("Если белые сыграют e5, конь f6 будет атакован.", "e4 Nf6"),
    ("Если белые сыграют e5, конь f6 уйдёт.", "e4 Nf6"),
])
def test_bare_pawn_line_true_controls(monkeypatch, sentence, moves):
    _mode(monkeypatch, "bare_pawn_line", "on")
    assert _run([sentence], _ctx(moves))[-1][1] == []


def test_bare_pawn_line_reads_only_a_legal_pawn_move_of_the_side_named(monkeypatch):
    _mode(monkeypatch, "bare_pawn_line", "on")
    ctx = _ctx("e4 Nf6")
    claim = Claim(rel="attacked", subj=None, objs=(Ref(sq="f6", piece="N"),),
                  pos=Pos(at="skip", skip_reason="conditional"), span=(30, 40))
    state = {claim_scene.TEXT_KEY: "Если чёрные сыграют e5, конь f6 под ударом."}  # e5 is no move of Black's now
    assert claim_scene.boards_for(claim, ctx, state) is None


# ── loaded_line + «больше не» (stretch, shadow by default) ───────────────────────────────────────────────────────
@pytest.mark.parametrize("mode", ["shadow", "on"])
def test_loaded_line_opera(monkeypatch, mode):
    _mode(monkeypatch, "loaded_line", mode)
    row, ctx = _row("opera")
    got = run_answer(row["prefix"] + [row["sentence"]], ctx)
    want = "before 16.Qb8+: Black's rook on h8 does not reach d8; what reaches it: White's bishop on g5 and Black's king on e8"
    if mode == "on":
        assert got[-1][1] == [want]
    else:
        assert got[-1][1] == [] and _shadowed(ctx, "loaded_line") == [want]


def test_loaded_line_true_control(monkeypatch):
    # before 16.Qb8+ the knight on d7 does cover f6: «больше не» presupposes a relation that held — true
    _mode(monkeypatch, "loaded_line", "on")
    row, ctx = _row("opera")
    got = run_answer(row["prefix"] + ["Ферзь пожертвован, чтобы конь чёрных больше не защищал поле f6."], ctx)
    assert got[-1][1] == []


# ── the judge: locked ────────────────────────────────────────────────────────────────────────────────────────────
def _locked(sq="c8"):
    return Claim(rel="locked", subj=Ref(sq=sq, piece="B"), objs=())


def test_locked_french_bishop_one_move():
    assert claim_judge.judge_on(_locked(), _board("e4 e6 d4 d5 e5"), None) == (True, "")


def test_locked_caro_advance_bishop_is_free():
    v, truth = claim_judge.judge_on(_locked(), _board("e4 c6 d4 d5 e5"), None)
    assert v is False and "5 moves" in truth and "f5" in truth


def test_locked_switch_off(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_OFF", "locked")
    b = _board("e4 c6 d4 d5 e5")
    assert claim_judge.decide(_locked(), BoardSet(primary=b, where="now"), CheckContext.from_fens([b.fen()])) == UNDECIDED


# ── the judge: cover_cause ───────────────────────────────────────────────────────────────────────────────────────
def test_cover_cause_own_pawn_cannot_be_the_cause_the_row():
    _row_, ctx = _row("st2_4-attack")
    claim = Claim(rel="cover_cause", subj=Ref(sq="g7", piece="P"), objs=(Ref(sq="f6"),), pos=Pos(tense="past"))
    v = claim_judge.decide(claim, BoardSet(primary=ctx.current, where="on the board now"), ctx)
    assert v.status == "false"
    assert "Black's own pawn" in v.truth and "4.exf6" in v.truth and "White's pawn" in v.truth


def test_cover_cause_opposite_sides_is_true():
    ctx = _ctx("e4 Nf6 e5", student=chess.BLACK)
    claim = Claim(rel="cover_cause", subj=Ref(sq="e5", piece="P"), objs=(Ref(sq="f6"),), to=Ref(piece="N", owner="you"))
    assert claim_judge.decide(claim, BoardSet(primary=ctx.current, where="now"), ctx).status == "true"


def test_cover_cause_same_side_by_the_claims_own_ref():
    ctx = _ctx("e4 Nf6 e5 d6", student=chess.BLACK)
    claim = Claim(rel="cover_cause", subj=Ref(sq="g7", piece="P"), objs=(Ref(sq="f6"),), to=Ref(piece="N", owner="you"))
    assert claim_judge.decide(claim, BoardSet(primary=ctx.current, where="now"), ctx).status == "false"


def test_cover_cause_unknown_loss_or_absent_holder_is_undecided():
    ctx = _ctx("e4 Nf6 e5")
    no_loss = Claim(rel="cover_cause", subj=Ref(sq="g7", piece="P"), objs=(Ref(sq="f6"),))
    gone = Claim(rel="cover_cause", subj=Ref(sq="g5", piece="B"), objs=(Ref(sq="f6"),), to=Ref(piece="N", side=False))
    for c in (no_loss, gone):
        assert claim_judge.decide(c, BoardSet(primary=ctx.current, where="now"), ctx) == UNDECIDED


def test_cover_cause_true_control_through_the_sentence():
    # «поле f6 держала пешка e5» after 4.exf6: the holder is gone (it took on f6), nothing to judge
    ctx = _ctx("d4 e5 dxe5 Nc6 Nf3 Nf6 exf6", student=chess.BLACK, game=True)
    assert _run(["Поле f6 держала пешка e5, и твой конь там потерялся."], ctx)[-1][1] == []


# ── the judge: pin_exists, before_move ───────────────────────────────────────────────────────────────────────────
def _pin_exists(**kw):
    return Claim(rel="pin_exists", subj=Ref(piece="B", side=chess.WHITE, text="слон"), objs=(), presup="exists", **kw)


def test_pin_exists_none_on_the_board(monkeypatch):
    _mode(monkeypatch, "pin_noun", "on")
    _row_, ctx = _row("op-ruy")  # 3...a6: the knight c6 is not pinned (d7 between)
    v = claim_judge.decide(_pin_exists(), BoardSet(primary=ctx.current, where="on the board now"), ctx)
    assert v.status == "false" and "pins" in v.truth and "Black's knight on c6" in v.truth


def test_pin_exists_true_on_an_alternative(monkeypatch):
    _mode(monkeypatch, "pin_noun", "on")
    _row_, ctx = _row("op-ruy")
    pinned = _board("e4 e5 Nf3 Nc6 Bb5 d6")
    v = claim_judge.decide(_pin_exists(), BoardSet(primary=ctx.current, where="now", alternatives=(pinned,)), ctx)
    assert v.status == "true"


def test_pin_exists_shadow_by_default():
    _row_, ctx = _row("op-ruy")
    v = claim_judge.decide(_pin_exists(), BoardSet(primary=ctx.current, where="on the board now"), ctx)
    assert v == UNDECIDED and _shadowed(ctx, "pin_noun")


def _escape(sq, san, piece="N"):
    return Claim(rel="pinned", subj=None, objs=(Ref(sq=sq, piece=piece),), presup="before_move",
                 pos=Pos(at="after", moves=(MoveRef(san=san, piece=piece, to=san[-2:]),)))


def test_before_move_no_pin_before_nd2():
    _row_, ctx = _row("plan-caro-adv")
    claim = _escape("b1", "Nd2")
    boards = claim_scene.boards_for(claim, ctx, {})
    v = claim_judge.decide(claim, boards, ctx)
    assert v.status == "false" and v.where == "before 4.Nd2" and "not pinned" in v.truth


def test_before_move_true_when_it_was_pinned():
    ctx = _ctx("e4 e5 Nf3 d6 d4 Bg4")  # the knight f3 is pinned to the queen d1
    claim = _escape("f3", "Nh4")
    assert claim_judge.decide(claim, claim_scene.boards_for(claim, ctx, {}), ctx).status == "true"


# ── F5, F10 ──────────────────────────────────────────────────────────────────────────────────────────────────────
ITALIAN = "e4 e5 Nf3 Nc6 Bc4 Bc5"


def test_f5_an_absent_piece_counted_as_defended_is_an_error():
    got = _run(["Конь f6 защищён трижды."], _ctx(ITALIAN))
    assert got[-1][1] and "there is no knight on f6" in got[-1][1][0]


def test_f10_hanging_with_an_even_exchange_is_undecided():
    claim = Claim(rel="hanging", subj=None, objs=(Ref(sq="e5", piece="P"),))
    assert claim_judge.judge_on(claim, _board(ITALIAN), None) == (None, "")  # Nf3 attacks it once, Nc6 defends once


def test_f10_hanging_when_a_capture_wins():
    b = chess.Board("r1bqkbnr/p1pp1ppp/2n5/1P2p3/4P3/8/1PPP1PPP/RNBQKBNR w KQkq - 0 5")  # b5 pawn hits the knight c6
    claim = Claim(rel="hanging", subj=None, objs=(Ref(sq="c6", piece="N"),))
    assert claim_judge.judge_on(claim, b, None) == (True, "")  # bxc6 wins a knight for a pawn
