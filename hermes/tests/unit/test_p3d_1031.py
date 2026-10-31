"""P3D Board rules (plan 31.10): the checks along a line judged on geometry (C2a checks_geometry), the result of a
forced retreat (C5 retreat_cover), a move said to prevent the other side's move (C6 prevents) and two more word orders
of the only legal reply to a check (F13 only_move_orders).

Judges are tested with hand-built ``Claim``s (the packages run in parallel); the extractors on their sentences; the three
rows of the package (lucena, castle-ru, op-show-ck-attack) on their replayed contexts; the true controls on their
boards; and each detector's switch (src/config.py detector_mode).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import chess
import pytest

from src import claim_rules as R
from src import config
from src.claim_types import Claim, MoveRef, Pos, Ref

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import load_ctx, run_answer  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "fixtures"
ROWS = FIX / "detect1031" / "rows"

CASTLE = "r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8"  # castle-ru: Bc4 covers f1
KNIGHT = "r1bqkb1r/pppp1ppp/2n3n1/4p3/4P2P/5N2/PPPP1PP1/RNBQKB1R w KQkq - 0 5"  # Ng6 covers f8; h5 chases it
CARO = "rnbqkbnr/pp1ppppp/2p5/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"  # 1.e4 c6
ENGLISH = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2P5/2N2N2/PP1PPPPP/R1BQKB1R w KQkq - 4 4"  # 1.c4 e5 2.Nc3 Nf6 3.Nf3 Nc6
CHECK_FOUR = "4k3/8/8/8/8/8/8/4R1K1 b - - 0 1"  # Black in check, four king moves
CHECK_ONE = "4k3/R7/8/1B6/8/8/8/3RK3 b - - 0 1"  # Black in check, Kf8 the only move


@pytest.fixture(autouse=True)
def _relations_on(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)


def _ctx(fen: str = None, moves: str = None, question: str = ""):
    from src.answer_check import CheckContext

    lines = []
    if moves:
        b = chess.Board()
        for m in moves.split():
            b.push_san(m)
        fen = b.fen()
        lines = [moves]
    ctx = CheckContext.from_fens([fen], lines, question=question)
    ctx.language = "ru"
    return ctx


def _last_issues(sentences, ctx):
    return run_answer(list(sentences), ctx)[-1][1]


# ── C2a checks_geometry ─────────────────────────────────────────────────────────────────────────────────────────
def _geo(king_sq: str, line: str = "file:d", checker=chess.BLACK, king_side=chess.WHITE, piece="R") -> Claim:
    return Claim(rel="checks_along", subj=Ref(piece=piece, side=checker, text="ладья"), objs=(), kind=line, source="rules",
                 move=MoveRef(san="K" + king_sq, piece="K", to=king_sq, side=king_side),
                 to=Ref(sq=king_sq, piece="K", side=king_side, text="king"))


def test_geometry_judges_a_king_off_the_line_false_on_any_board():
    claim = _geo("c7")
    for board in (chess.Board(), chess.Board("1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1"), None):
        v = R.RULE_JUDGES["checks_along"](claim, board or chess.Board(), None)
        assert v.status == "false"
        assert "c7" in v.truth and "d-file" in v.truth and "c-file" in v.truth and "rank 7" in v.truth


def test_geometry_leaves_a_king_on_the_line_to_the_board():
    assert R.judge_checks_geometry(_geo("d6"), chess.Board(), None).status == "undecided"
    assert R.judge_checks_geometry(_geo("c7", line="rank:7"), chess.Board(), None).status == "undecided"
    queen = R.judge_checks_geometry(_geo("c7", piece="Q"), chess.Board(), None)
    assert queen.status == "false" and "diagonal" in queen.truth


@pytest.mark.parametrize("sentence,geometric", [
    ("Затем белый король выходит из-под пешки (Kc7), и когда чёрная ладья начнёт шаховать по вертикали d, наша ладья "
     "перекроет линию.", True),
    # the king told lands on the line: an ordinary claim on its board
    ("Затем белый король идёт на d7 (Kd7), и когда чёрная ладья начнёт шаховать по вертикали d, наша ладья перекроет "
     "линию.", False),
    # whose king walked is not said: not ours to guess
    ("Затем король выходит (Kc7), и когда чёрная ладья начнёт шаховать по вертикали d, наша ладья перекроет линию.", False),
    # the checker's own king walking
    ("Затем чёрный король отходит (Kc7), и когда чёрная ладья начнёт шаховать по вертикали d, белые закроются.", False),
    # the king may walk on after the move told
    ("Затем белый король выходит (Kc7), и чёрная ладья начнёт шаховать по вертикали d, как только король вернётся на d6.",
     False),
])
def test_geometry_extraction(sentence, geometric):
    claims = [c for c in R.extract(sentence, {}) if c.rel == "checks_along"]
    assert claims
    assert any(R._geometric(c) for c in claims) == geometric


# ── C5 retreat_cover ───────────────────────────────────────────────────────────────────────────────────────────
def _retreat(fen_sq: str, covered: str, chase: str, piece="B", to=None) -> Claim:
    return Claim(rel="retreat_cover", subj=Ref(piece=piece, text="слон"), objs=(Ref(sq=covered),), source="rules",
                 kind="chase:" + chase, move=MoveRef(piece=piece, to=to) if to else None)


def test_retreat_cover_false_when_a_safe_retreat_keeps_the_square():
    v = R.judge_retreat_cover(_retreat("c4", "f1", "b3"), chess.Board(CASTLE), None)
    assert v.status == "false"
    assert re.search(r"Ba6.{0,60}(safe|still covers f1)", v.truth) and "after b3" in v.truth  # its antidote


def test_retreat_cover_true_when_every_safe_retreat_gives_the_square_up():
    v = R.judge_retreat_cover(_retreat("g6", "f8", "h5", piece="N"), chess.Board(KNIGHT), None)
    assert v.status == "true"
    v = R.judge_retreat_cover(_retreat("g6", "f8", "h5", piece="N", to="e7"), chess.Board(KNIGHT), None)
    assert v.status == "true"


def test_retreat_cover_named_square_that_still_covers():
    v = R.judge_retreat_cover(_retreat("c4", "f1", "b3", to="a6"), chess.Board(CASTLE), None)
    assert v.status == "false" and "a6 still covers f1" in v.truth


def test_retreat_cover_undecided_off_its_board():
    # no piece of that kind covers the square: «уже не прикрывает» is about another position
    assert R.judge_retreat_cover(_retreat("c4", "h1", "b3"), chess.Board(CASTLE), None).status == "undecided"
    assert R.judge_retreat_cover(_retreat("c4", "f1", "b3"), chess.Board(), None).status == "undecided"


@pytest.mark.parametrize("sentence,n", [
    ("Начни с b3 — b3–c4 — белые сразу нападают на слона, и вот тогда он вынужден уйти туда, откуда f1 уже не прикрывает.", 1),
    ("Белые играют h5, и конь вынужден уйти на e7, откуда f8 уже не прикрывает.", 1),
    # no square: not taken (design FP note)
    ("Ферзь обязан уйти на поле, где сохранит защиту коня.", 0),
    # no piece named in the sentence: the antecedent is not ours to guess
    ("И вот тогда он вынужден уйти туда, откуда f1 уже не прикрывает.", 0),
    # a condition
    ("Если слон вынужден уйти туда, откуда f1 не прикрывает, рокировка станет возможной.", 0),
])
def test_retreat_cover_extraction(sentence, n):
    assert len([c for c in R.extract(sentence, {}) if c.rel == "retreat_cover"]) == n


# ── C6 prevents ────────────────────────────────────────────────────────────────────────────────────────────────
def _prevents(move: str, target: str, piece="P", side=chess.BLACK) -> Claim:
    return Claim(rel="prevents", subj=Ref(side=side, text="черным"), objs=(Ref(sq=target, piece=piece),), source="rules",
                 move=MoveRef(san=move, piece="P", to=move[-2:]), to=Ref(sq=target, piece=piece))


def test_prevents_false_when_the_move_stays_legal_and_safe():
    v = R.judge_prevents(_prevents("d4", "d5"), chess.Board(CARO), None)
    assert v.status == "false"
    assert "d5 is defended by the pawn on c6" in v.truth and v.truth.startswith("after d4 Black can still play d5")


def test_prevents_true_when_the_move_loses_material():
    assert R.judge_prevents(_prevents("e4", "d5"), chess.Board(ENGLISH), None).status == "true"
    assert R.judge_prevents(_prevents("d4", "e5"), chess.Board(CARO), None).status == "true"  # dxe5 wins it


def test_prevents_undecided_off_its_board():
    # the move is not this board's
    assert R.judge_prevents(_prevents("d5", "d5"), chess.Board(CARO), None).status == "undecided"
    # the other side's pawn stands on d5 already: the words are about a board before that
    after_d5 = chess.Board("rnbqkbnr/pp2pppp/2p5/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3")
    assert R.judge_prevents(_prevents("d4", "d5"), after_d5, None).status == "undecided"
    # the side said to be stopped is the mover
    assert R.judge_prevents(_prevents("d4", "d5", side=chess.WHITE), chess.Board(CARO), None).status == "undecided"


@pytest.mark.parametrize("sentence,n", [
    ("На доске сейчас ход твой, за белых: лучший план — d4, занимая центр и не давая чёрным спокойно поставить пешку на d5.", 1),
    ("Лучший план — e4, не давая чёрным спокойно сыграть d5.", 1),
    ("Сыграй d3, не давая коню прыгнуть на e4.", 1),
    # the square before the participle is an object, not the move
    ("Лучший план — d4, атакуя c5 и не давая чёрным спокойно сыграть d5.", 0),
    ("Конь на f6 стоит хорошо, не давая белым сыграть e5.", 0),
    # no move at all
    ("Самый популярный ход готовит d4 и не пускает чёрных первыми занять центр.", 0),
])
def test_prevents_extraction(sentence, n):
    assert len([c for c in R.extract(sentence, {}) if c.rel == "prevents"]) == n


def test_prevents_target_is_not_a_placed_piece():
    st = {}
    R.extract("Лучший план — d4, не давая чёрным спокойно поставить пешку на d5.", st)
    assert ("P", "d5") not in st["rules_placed"]


# ── F13 only_move_orders ───────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", ["Ход Kf8 единственный.", "Есть только один ход: Kf8."])
def test_only_move_orders_probe_pair(sentence):
    """The attack triage's F13 probe: Black in check from Re1 has Kd7, Kd8, Kf7 and Kf8."""
    issues = _last_issues([sentence], _ctx(CHECK_FOUR, question="Чем чёрным уйти от шаха?"))
    assert issues and "Kd7, Kd8 and Kf7" in issues[0]


@pytest.mark.parametrize("sentence", ["Ход Kf8 единственный.", "Есть только один ход: Kf8."])
def test_only_move_orders_true_when_it_is_the_only_move(sentence):
    assert _last_issues([sentence], _ctx(CHECK_ONE)) == []


@pytest.mark.parametrize("sentence", [
    "Единственный ход — Kf8.",  # the only good move: not read (rules_cases only-good-move)
    "Kf8 — единственный ход, который держит ничью.",
    "Есть только один ход, который держит ничью: Kf8.",
    "Ход Kf8! единственный.",
])
def test_only_move_orders_leaves_the_only_good_move_alone(sentence):
    assert not [c for c in R.extract(sentence, {}) if R.detector_of(c) == "only_move_orders"]


def test_only_move_orders_off_a_check_is_undecided():
    claim = Claim(rel="only_move", subj=None, objs=(), source="rules", kind="check_reply",
                  move=MoveRef(san="Nf3", piece="N", to="f3"))
    assert R.RULE_JUDGES["only_move"](claim, chess.Board(), None).status == "undecided"


def test_only_move_orders_the_kings_only_move():
    claim = Claim(rel="only_move", subj=Ref(piece="K"), objs=(), source="rules", kind="check_reply",
                  move=MoveRef(san="Kf8", piece="K", to="f8"))
    v = R.RULE_JUDGES["only_move"](claim, chess.Board(CHECK_FOUR), None)
    assert v.status == "false" and v.truth.startswith("Black's king has other legal replies")


# ── the rows ───────────────────────────────────────────────────────────────────────────────────────────────────
ANTIDOTES = {f["id"] + "/" + f["kind"]: f for f in
             json.loads((FIX / "prevent" / "antidotes.json").read_text(encoding="utf-8"))["findings"]}


@pytest.mark.parametrize("row_id,antidote", [
    ("lucena", "lucena/wrong_attack_or_defence"),
    ("castle-ru", "castle-ru/wrong_attack_or_defence"),
    ("op-show-ck-attack", "op-show-ck/wrong_attack_or_defence"),
])
def test_the_package_rows_are_cut_with_the_truth(row_id, antidote):
    row = json.loads((ROWS / f"{row_id}.json").read_text(encoding="utf-8"))
    got = run_answer(row["prefix"] + [row["sentence"]], load_ctx(row["ctx"]), live_game=row["turn"].get("live_game"))
    issues = got[-1][1]
    assert issues, row_id
    lab = ANTIDOTES[antidote]
    assert any(re.search(p, " ".join(issues)) for p in lab["issue"]), issues  # plan §5.2-e: the issue names the truth
    # and nothing before it in the answer is cut by these detectors
    for sentence, iss, _ in got[:-1]:
        assert not any("still covers" in i or "can still play" in i or "off the d-file" in i for i in iss), sentence


# ── switches ───────────────────────────────────────────────────────────────────────────────────────────────────
def _row(row_id):
    row = json.loads((ROWS / f"{row_id}.json").read_text(encoding="utf-8"))
    return row["prefix"] + [row["sentence"]], load_ctx(row["ctx"]), row["turn"].get("live_game")


@pytest.mark.parametrize("row_id,name", [("lucena", "checks_geometry"), ("castle-ru", "retreat_cover"),
                                         ("op-show-ck-attack", "prevents")])
def test_each_detector_rolls_back_alone(monkeypatch, row_id, name):
    monkeypatch.setenv("COACH_DETECTORS_OFF", name)
    sentences, ctx, live = _row(row_id)
    assert run_answer(sentences, ctx, live_game=live)[-1][1] == []


@pytest.mark.parametrize("row_id,name", [("lucena", "checks_geometry"), ("castle-ru", "retreat_cover"),
                                         ("op-show-ck-attack", "prevents")])
def test_a_shadowed_detector_records_and_never_cuts(monkeypatch, row_id, name):
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", name)
    sentences, ctx, live = _row(row_id)
    assert run_answer(sentences, ctx, live_game=live)[-1][1] == []
    assert any(any(f"[{name}]" in i for i in issues) for _, issues in ctx.relation_shadow)


def test_only_move_orders_switch(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_OFF", "only_move_orders")
    assert _last_issues(["Ход Kf8 единственный."], _ctx(CHECK_FOUR)) == []


def test_relation_check_off_and_the_lesson_tutor(monkeypatch):
    sentences, ctx, live = _row("castle-ru")
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "off")
    assert run_answer(sentences, ctx, live_game=live)[-1][1] == []
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    sentences, ctx, live = _row("op-show-ck-attack")
    ctx.relation_surface = "lesson"
    assert run_answer(sentences, ctx, live_game=live)[-1][1] == []


def test_relation_shadow_records_in_its_own_words(monkeypatch):
    """With the whole relation check in shadow the detectors leave the recording to it (SHADOW == ON)."""
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "shadow")
    sentences, ctx, live = _row("lucena")
    assert run_answer(sentences, ctx, live_game=live)[-1][1] == []
    rec = [i for _, issues in ctx.relation_shadow for i in issues]
    assert any("off the d-file" in i and not i.startswith("[") for i in rec)


def test_detector_of_names_are_the_plans():
    for name in ("checks_geometry", "retreat_cover", "prevents", "only_move_orders"):
        assert name in config.DETECTOR_DEFAULTS and name in config.RELATION_DETECTORS


def test_prevents_with_no_side_named_means_the_other_side():
    claims = [c for c in R.extract("Лучший план — d4, не давая спокойно сыграть d5.", {}) if c.rel == "prevents"]
    assert len(claims) == 1 and claims[0].subj is None
    assert R.judge_prevents(claims[0], chess.Board(CARO), None).status == "false"


def test_only_move_orders_a_reply_mated_at_once_is_no_reply():
    """tests/unit/test_blind_spots.py lesson sweep: after 1.Qa6+ the other legal reply, 1...Ba7+, allows 2.Qxa7#."""
    ctx = _ctx("kb6/1p1B4/1K6/8/p1Q5/8/8/3q4 w - - 0 1")
    assert _last_issues(["Первый ход — **Qa6+!** Ферзь отдаётся с шахом, и у чёрных только один ответ — bxa6."], ctx) == []
