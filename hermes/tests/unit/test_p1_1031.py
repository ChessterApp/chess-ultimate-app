"""P1 Game record (plan 31.10): the game's own score against what the answer says about it.

M1 recap_scope     «Позиция после 1.d4 … 6.exd8=R+: …» — the game's record up to now is the board now, not a line
M2 material_order  «белые впереди на целую ладью»
M3 student_capture «твоя пешка с f6 забрала слона» — the capture must be the student's
M4 block_kind      «закрыться конём — Nxd8» — a block lands between, it neither takes the checker nor moves the king
M6 free_capture    «белые забирают фигуру бесплатно» — nothing may be taken back
M7 gave_up         «Чёрные отдали центральную пешку» — the loss must be in the score
C1a propose_vocab  «Пока же просто развивайся: Qe2, Be3» — the move goes to the engine
C1b plan_place     «План за чёрных прост: конь на f6 …» — the one legal move that does it goes to the engine
H start_scene      a move legal only on the start position sets no scene when the real board is known
F2                 game_mode.ply_words/told_ply name whose piece took whose

Rows: tests/fixtures/detect1031/rows (owner P1). True controls: negatives/P1.json, here also through the engine
stage (tests/conftest.py switches the recommendation check off for the other tests).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import chess
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import load_ctx, run_answer  # noqa: E402

from src import answer_check as ac  # noqa: E402
from src import config, game_mode  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "detect1031"
P1_ROWS = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((FIX / "rows").glob("*.json"))]
P1_ROWS = [r for r in P1_ROWS if r["owner"] == "P1" and r["tier"] == "must"]
CONTROLS = json.loads((FIX / "negatives" / "P1.json").read_text(encoding="utf-8"))["controls"]


def _stockfish() -> bool:
    from src.tools.stockfish import STOCKFISH_PATH

    return bool(shutil.which(STOCKFISH_PATH) or os.path.exists(STOCKFISH_PATH))


@pytest.fixture
def engine_on(monkeypatch):
    if not _stockfish():
        pytest.skip("the engine stage needs a local Stockfish")
    monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
    monkeypatch.setenv("ENGINE_API_URL", "")


def _game(moves: str, student: str = "", fen: str = "", question: str = ""):
    sans = moves.split() if moves else None
    if sans:
        b = chess.Board()
        for m in sans:
            b.push_san(m)
        fen = b.fen()
    color = {"w": chess.WHITE, "b": chess.BLACK}.get(student)
    ctx = ac.CheckContext.from_fens([fen], [" ".join(sans)] if sans else [], question=question, student_color=color)
    if sans and color is not None:
        ctx.game_moves = sans
        first = 0 if color == chess.WHITE else 1
        ctx.game_engine_moves = [m for i, m in enumerate(sans) if i % 2 != first]
    ctx.language = "ru"
    return ctx


def _last(answer, ctx, **kw):
    return run_answer(answer, ctx, **kw)[-1]


ST2 = "d4 e5 dxe5 Nc6 Nf3 Nf6 exf6"
ST2_5 = ST2 + " Be7 fxe7"
ST2_8 = ST2_5 + " d6 exd8=R+"
ST3 = "e4 e5 d4 d6 c3 Be7 Nf3 Nf6 Bc4 exd4 O-O Nxe4"


# ── the rows ─────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("row", P1_ROWS, ids=[r["id"] for r in P1_ROWS])
def test_the_row_is_caught(row, monkeypatch):
    if row["stage"] == "engine":
        if not _stockfish():
            pytest.skip("the engine stage needs a local Stockfish")
        monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
        monkeypatch.setenv("ENGINE_API_URL", "")
    ctx = load_ctx(row["ctx"])
    sentence, issues, stage = run_answer(row["prefix"] + [row["sentence"]], ctx, engine=row["stage"] == "engine",
                                         live_game=row["turn"].get("live_game"))[-1]
    assert issues and stage == row["stage"], f"{row['id']} ({row['mechanism']}): not caught"


def test_the_issue_texts_name_the_true_fact():
    by = {r["id"]: r for r in P1_ROWS}

    def issues(rid):
        r = by[rid]
        return " ".join(run_answer(r["prefix"] + [r["sentence"]], load_ctx(r["ctx"]),
                                   live_game=r["turn"].get("live_game"))[-1][1])
    assert "Black has an extra 2 pawns" in issues("st3#10")
    assert "White has an extra 1 queen, 1 rook, 1 bishop, 1 knight" in issues("st2#9")
    assert "gxf6" in issues("st2#4-eval") and "White wins a knight for a pawn" in issues("st2#4-eval")
    assert "5.fxe7 was White's (the engine's) capture" in issues("st2#5")
    assert "takes the checking rook on d8" in issues("st2#8-block") and "Kxd8, Ke7, Nxd8" in issues("st2#8-block")
    assert "Black (the engine) has lost no pawn" in issues("st1#1")


# ── M1 recap_scope ───────────────────────────────────────────────────────────────────────────────────────────────
def test_a_recap_to_now_is_the_board_now():
    ctx = _game(ST3, "w")
    text = "Позиция после 1.e4 e5 2.d4 d6 3.c3 Be7 4.Nf3 Nf6 5.Bc4 exd4 6.O-O Nxe4: у чёрных на пешку больше."
    at = text.index("у чёрных")
    assert not ac._is_hypothetical(text.lower(), text, at, ctx=ctx)
    assert ac._is_hypothetical(text.lower(), text, at)  # without the game: a line, as before


def test_a_recap_one_ply_early_or_invented_stays_a_line():
    ctx = _game(ST3, "w")
    early = "После 1.e4 e5 2.d4 d6 3.c3 Be7 4.Nf3 Nf6 5.Bc4 exd4 у чёрных лишняя пешка."
    assert ac._is_hypothetical(early.lower(), early, early.index("у чёрных"), ctx=ctx)
    made_up = "После 1.e4 d5 2.exd5 у белых лишняя пешка."
    assert ac._is_hypothetical(made_up.lower(), made_up, made_up.index("у белых"), ctx=ctx)
    cond = "Если бы после 1.e4 e5 2.d4 d6 3.c3 Be7 4.Nf3 Nf6 5.Bc4 exd4 6.O-O Nxe4 ты взял, у белых было бы больше."
    assert ac._is_hypothetical(cond.lower(), cond, cond.index("у белых"), ctx=ctx)


def test_the_material_after_a_recap_is_judged_now():
    _, issues, _ = _last(["Позиция после 1.e4 e5 2.d4 d6 3.c3 Be7 4.Nf3 Nf6 5.Bc4 exd4 6.O-O Nxe4: у чёрных на пешку "
                          "больше."], _game(ST3, "w"))
    assert issues and "Black has an extra 2 pawns" in issues[0]
    _, issues, _ = _last(["Позиция после 1.e4 e5 2.d4 d6 3.c3 Be7 4.Nf3 Nf6 5.Bc4 exd4 6.O-O Nxe4: у чёрных на две "
                          "пешки больше."], _game(ST3, "w"))
    assert issues == []


# ── M2 material_order ────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence,wrong", [
    ("Белые впереди на целую ладью.", True),
    ("Чёрные позади на целую ладью.", True),
    ("Белые впереди на целую фигуру и пешку.", False),
])
def test_material_word_orders(sentence, wrong):
    _, issues, _ = _last([sentence], _game(ST2 + " d6", "b"))
    assert bool(issues) == wrong, issues


# ── M3 student_capture ───────────────────────────────────────────────────────────────────────────────────────────
def test_a_capture_given_to_the_student_must_be_theirs():
    _, issues, _ = _last(["Твоя пешка с f6 забрала слона на e7."], _game(ST2_5, "b"))
    assert issues and "5.fxe7 was White's (the engine's) capture" in issues[0]
    _, issues, _ = _last(["Ты взял ферзя на d1."], _game(ST2_5, "b"))
    assert issues and "never captured a queen on d1" in issues[0]
    _, issues, _ = _last(["Твоя пешка с e5 забрала коня на f6."], _game(ST2, "w"))
    assert issues == []


# ── M4 block_kind ────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_block_that_takes_the_checker_is_not_a_block():
    _, issues, _ = _last(["Ты под шахом: можно закрыться конём — Nxd8."], _game(ST2_8, "b"))
    assert issues and "takes the checking rook on d8" in issues[0]


def test_true_blocks_pass():
    ctx = _game("", fen="rnb1kbnr/pppq2pp/8/4pp1Q/4P3/8/PPPP1PPP/RNB1KBNR b KQkq - 1 4")
    assert _last(["Тебе шах, и лучше всего закрыться ферзём на f7."], ctx)[1] == []
    ctx = _game("", fen="rnbqk1nr/pppp1ppp/8/4p3/1b1PP3/8/PPP2PPP/RNBQKBNR w KQkq - 1 3")
    assert _last(["Тебе шах от слона b4, и проще всего закрыться — c3."], ctx)[1] == []


def test_block_named_with_a_king_move_written():
    ctx = _game("", fen="rnbqk1nr/pppp1ppp/8/4p3/1b1PP3/8/PPP2PPP/RNBQKBNR w KQkq - 1 3")
    _, issues, _ = _last(["Тебе шах, и надо закрыться — Ke2."], ctx)
    assert issues and "Ke2 is a king move" in issues[0] and "c3" in issues[0]


# ── M6 free_capture ──────────────────────────────────────────────────────────────────────────────────────────────
def test_a_capture_told_as_free_must_be_free():
    before = "Nf6 — и белые сразу взяли коня: 4.exf6, пешка с e5 на f6 бьёт твоего коня."
    _, issues, _ = _last([before, "Белые забирают фигуру бесплатно."], _game(ST2, "b"))
    assert issues and "4.exf6 is not free" in issues[0] and "White wins a knight for a pawn" in issues[0]
    _, issues, _ = _last(["Белые забрали пешку e5 бесплатно."], _game("e4 e5 Nf3 Nf6 Nxe5", "b"))
    assert issues == []
    _, issues, _ = _last(["Ты забрал пешку f4 бесплатно: exf4."], _game("e4 e5 f4 exf4", "b"))
    assert issues == []


def test_free_is_not_triggered_by_negation_idiom_or_a_threat():
    ctx = _game(ST2, "b")
    for s in ("Но белые забрали фигуру не бесплатно: пешку f6 можно взять обратно.",
              "Так что даром его не возьмёшь.",
              "Белые просто так ничего не отдают.",
              "Если бы пешку f6 никто не защищал, белые забрали бы ещё и ладью бесплатно."):
        assert _last([s], ctx)[1] == [], s


def test_a_promotion_capture_is_valued_with_the_new_piece():
    # 6.exd8=R+: the new rook on d8 is taken back by Kxd8 or Nxd8 — not free
    _, issues, _ = _last(["Белые забрали ферзя бесплатно: exd8=R+."], _game(ST2_8, "b"))
    assert issues and "rook on d8 can be taken back" in issues[0]


# ── M7 gave_up ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_loss_told_as_done_must_be_in_the_score():
    _, issues, _ = _last(["Чёрные отдали центральную пешку, зато получили полуоткрытую линию c."], _game("e4 c5", "w"))
    assert issues and "has lost no pawn" in issues[0]
    assert _last(["Ты потерял ферзя, и это очень тяжело."], _game(ST2_8, "b"))[1] == []
    assert _last(["Ты отдал пешку f4 ради быстрого развития."], _game("e4 e5 f4 exf4", "w"))[1] == []


def test_another_game_or_a_line_is_not_this_games_loss():
    ctx = _game("e4 c5", "w")
    assert _last(["В партии Морфи белые отдали ферзя ради мата."], ctx)[1] == []
    assert _last(["В гамбите после 1.e4 e5 2.f4 exf4 белые отдали пешку ради центра."], ctx)[1] == []


# ── C1a / C1b proposals ──────────────────────────────────────────────────────────────────────────────────────────
def test_develop_imperative_hands_its_move_to_the_engine():
    ctx = _game("", fen="r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8")
    found = ac.proposed_move("Пока же просто развивайся: Qe2, Be3, и король укроется позже.", ctx)
    assert found and found[2] == "Qe2"
    assert ac.proposed_move("Мат ставит слон по диагонали — Сc6#.", _game("", fen="kb6/p2B4/8/8/8/8/8/K7 w - - 0 1")) is None


def test_a_plan_placing_a_piece_proposes_the_one_move():
    ctx = _game("", fen="rnbqkbnr/pp2pppp/2p5/3pP3/3P4/8/PPP2PPP/RNBQKBNR b KQkq - 0 3")
    found = ac.proposed_move("План за чёрных прост: конь на f6 давит на e4, потом ...c5.", ctx)
    assert found and found[2] == "Nf6"
    assert ac.proposed_move("План за белых прост: конь на f3, слон на d3.", ctx) is None  # not the side to move
    assert ac.proposed_move("План за чёрных: слон на f5 и e6.", _game(
        "", fen="rn1qkbnr/pp2pppp/2p5/3pPb2/3P4/8/PPP2PPP/RNBQKBNR w KQkq - 1 4")) is None  # not Black's move


@pytest.mark.parametrize("control", [c for c in CONTROLS if c.get("stage") == "engine"], ids=lambda c: c["id"])
def test_engine_controls_pass_the_engine(control, engine_on):
    from tests.unit.test_detect1031_rows import _ctx_for

    ctx = _ctx_for(control)
    got = run_answer(list(control.get("before") or []) + [control["sentence"]], ctx, engine=True)
    assert got[-1][1] == [], f"{control['id']}: {got[-1][1]}"


def test_a_plan_move_that_loses_is_cut_by_the_engine(engine_on):
    ctx = _game("", fen="rnbqkbnr/pp2pppp/2p5/3pP3/3P4/8/PPP2PPP/RNBQKBNR b KQkq - 0 3")
    got = run_answer(["План за чёрных прост: конь на f6 давит на e4, потом ...c5 подрывает d4."], ctx, engine=True)
    assert got[-1][2] == "engine" and "Nf6 is a mistake" in got[-1][1][0]


# ── H start_scene ────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_move_legal_only_on_the_start_position_sets_no_scene():
    kid = "r1bq1rk1/ppp1npbp/3p1np1/3Pp3/2P1P3/2N2N2/PP2BPPP/R1BQ1RK1 w - - 1 9"
    ctx = _game("", fen=kid)
    run_answer(["Как только чёрные сыграют ...f5, появится второй удар."], ctx)
    assert ctx.scene is None or ctx.scene.board_fen() != "rnbqkbnr/ppppp1pp/8/5p2/8/8/PPPPPPPP/RNBQKBNR"
    ctx = _game("", fen=kid)
    run_answer(["Ходы были такие: 1.e4c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6."], ctx)  # garbled, still no cut


def test_a_line_from_move_one_still_starts_at_the_start():
    ctx = _game("", fen="rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6")
    assert _last(["Ходы были такие: 1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6."], ctx)[1] == []
    assert ctx.scene is not None and ctx.scene.board_fen() == ctx.current.board_fen()


# ── switches ─────────────────────────────────────────────────────────────────────────────────────────────────────
ST2_4 = ["Nf6 — и белые сразу взяли коня: 4.exf6, пешка с e5 на f6 бьёт твоего коня.",
         "Белые забирают фигуру бесплатно, и теперь у них лишний конь."]


def test_each_detector_rolls_back_alone(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_OFF", "free_capture")
    assert _last(ST2_4, _game(ST2, "b"))[1] == []
    monkeypatch.setenv("COACH_DETECTORS_OFF", "recap_scope")
    assert _last(["Позиция после 1.e4 e5 2.d4 d6 3.c3 Be7 4.Nf3 Nf6 5.Bc4 exd4 6.O-O Nxe4: у чёрных на пешку больше."],
                 _game(ST3, "w"))[1] == []
    monkeypatch.setenv("COACH_DETECTORS_OFF", "gave_up,material_order,block_kind,student_capture")
    assert _last(["Чёрные отдали центральную пешку."], _game("e4 c5", "w"))[1] == []
    assert _last(["Белые впереди на целую ладью."], _game(ST2_8, "b"))[1] == []
    assert _last(["Можно закрыться конём — Nxd8."], _game(ST2_8, "b"))[1] == []
    assert _last(["Твоя пешка с f6 забрала слона на e7."], _game(ST2_5, "b"))[1] == []
    monkeypatch.setenv("COACH_DETECTORS_OFF", "propose_vocab,plan_place")
    ctx = _game("", fen="r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8")
    assert ac.proposed_move("Пока же просто развивайся: Qe2, Be3.", ctx) is None
    ctx = _game("", fen="rnbqkbnr/pp2pppp/2p5/3pP3/3P4/8/PPP2PPP/RNBQKBNR b KQkq - 0 3")
    assert ac.proposed_move("План за чёрных прост: конь на f6 давит на e4.", ctx) is None


def test_shadow_records_and_never_cuts(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "gave_up")
    ctx = _game("e4 c5", "w")
    assert _last(["Чёрные отдали центральную пешку."], ctx)[1] == []
    assert ctx.detector_shadow and ctx.detector_shadow[0][0] == "gave_up"


def test_none_in_the_lesson_tutor_and_shadow_in_move_comments():
    ctx = _game("e4 c5", "w")
    ctx.relation_surface = "lesson"
    assert _last(["Чёрные отдали центральную пешку."], ctx)[1] == [] and not ctx.detector_shadow
    ctx = _game("e4 c5", "w")
    ctx.relation_surface = "game"
    assert _last(["Чёрные отдали центральную пешку."], ctx)[1] == [] and ctx.detector_shadow


# ── F2 owners in the move words ──────────────────────────────────────────────────────────────────────────────────
def test_a_capture_in_words_names_both_owners(monkeypatch):
    state = {"student_color": "black", "moves": ST2_5.split()}
    assert game_mode.told_ply(state, 9) == ("5.fxe7 (White's (the engine's) pawn from f6 to e7, takes Black's "
                                            "(the student's) bishop on e7)")
    assert game_mode.ply_words(state, 8) == "bishop from f8 to e7"  # not a capture: unchanged
    assert game_mode.ply_words({"moves": ST2_5.split()}, 9) == "pawn from f6 to e7, takes the bishop on e7"
    monkeypatch.setattr(config, "COACH_TURN_FACTS", False)
    assert game_mode.ply_words(state, 9) == "pawn from f6 to e7, takes the bishop on e7"
