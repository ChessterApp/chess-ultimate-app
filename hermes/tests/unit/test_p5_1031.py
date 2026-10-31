"""P5 of plan 31.10 (endgames): the race said in words of distance, where a mate can stand, the king's direction.

  race_distance  — «Твой король на e5 слишком далеко» on a tablebase draw (prod 29.10, square: Kd5 and Kd6 draw);
  mate_squares   — «Мат случается только если чёрный король сам забредёт в угол» with K+N+N (prod 29.10,
                   two-knights: mate is possible on the edge, e.g. on d8), judged by src/data/mate_squares.json;
  king_direction — «не гонись по диагонали: вставай на одну вертикаль с пешкой» (shadow: logged, never cut).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import chess
import pytest

from src import board_rules, config
from src import endgame_claims as ec
from src.answer_check import CheckContext, check_sentence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import load_ctx, run_answer  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "detect1031"
SQUARE = "8/8/8/P3k3/8/8/8/7K b - - 0 1"  # tablebase: draw, only 1...Kd5 and 1...Kd6 hold
SQUARE_LOST = "8/8/8/P4k2/8/8/8/7K b - - 0 1"  # tablebase: White wins
FAR_LOST = "8/8/8/P7/7K/8/8/6k1 b - - 0 1"  # Kg1 is outside the a5 pawn's square: White wins
KNNK = "8/8/8/8/8/2k5/8/K1N1N3 w - - 0 1"
KRK = "8/8/8/4k3/8/8/8/R3K3 w - - 0 1"
KQK = "k7/8/1Q6/8/8/8/8/2K5 b - - 0 1"
KBNK = "8/8/8/4k3/8/8/8/2BNK3 w - - 0 1"
RACE_Q = "Я чёрными, мой ход. Догонит ли мой король пешку?"


@pytest.fixture(autouse=True)
def _switches(monkeypatch):
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)
    saved = dict(board_rules._tb_cache)
    yield
    board_rules._tb_cache.clear()
    board_rules._tb_cache.update(saved)


def _ctx(fen: str, question: str = "", tablebase: str | None = None) -> CheckContext:
    ctx = CheckContext.from_fens([fen], [], question=question)
    ctx.language = "ru"
    if tablebase:
        ctx.tablebase = tablebase
        ctx.engine_eval = 0.0 if tablebase == "draw" else (20.0 if tablebase.startswith("White") else -20.0)
    return ctx


def _issues(sentence: str, ctx) -> list:
    return list(check_sentence(sentence, ctx) or [])


def _seed_tablebase(fen: str, category: str, keeping: list, best: str | None = None) -> None:
    """The tablebase's answer as the turn's facts would have fetched it (no network in a test)."""
    b = chess.Board(fen)
    board_rules._tb_cache[b.epd()] = {"category": category, "dtz": 0, "dtm": 0, "best_san": best or keeping[0],
                                      "best_category": category, "keeping": list(keeping)}


# ── the rows ─────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("rid,needle", [("square-made_up", "draw"), ("two-knights", "edge")])
def test_the_rows_are_caught(rid, needle):
    row = json.loads((FIX / "rows" / f"{rid}.json").read_text(encoding="utf-8"))
    got = run_answer(row["prefix"] + [row["sentence"]], load_ctx(row["ctx"]))
    issues = got[-1][1]
    assert issues and needle in issues[0], issues


def test_two_knights_issue_names_the_true_squares():
    row = json.loads((FIX / "rows" / "two-knights.json").read_text(encoding="utf-8"))
    issues = run_answer(row["prefix"] + [row["sentence"]], load_ctx(row["ctx"]))[-1][1]
    text = issues[0]
    for sq in ("d8", "e1", "a4"):
        assert sq in text
    assert "not only in the corner" in text and "never be forced" in text
    fen = text.split(": ")[-1].split(" (")[0]
    assert chess.Board(fen).is_checkmate()


# ── race_distance ────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Твой король на e5 слишком далеко: пешка a5 идёт вперёд с темпом.",
    "Чёрный король слишком далеко от пешки.",
    "Твой король опаздывает к пешке.",
    "Король вне квадрата пешки a5.",
    "Твой король не дотянется до пешки.",
    "Твой король слишком далеко, пешку уже не остановить.",
])
def test_distance_words_on_a_drawn_race_are_cut(sentence):
    issues = _issues(sentence, _ctx(SQUARE, RACE_Q, "draw"))
    assert issues and "draw" in issues[0], issues


def test_the_issue_names_the_moves_that_hold_the_draw():
    _seed_tablebase(SQUARE, "draw", ["Kd5", "Kd6"])
    issues = _issues("Твой король на e5 слишком далеко.", _ctx(SQUARE, RACE_Q, "draw"))
    assert issues and "Kd5, Kd6" in issues[0] and "every other move loses" in issues[0], issues


@pytest.mark.parametrize("fen,tb,sentence", [
    (SQUARE, "draw", "Кd5! Король не слишком далеко — он успевает в квадрат."),
    (SQUARE, "draw", "Король не слишком далеко от пешки."),
    (SQUARE, "draw", "Пешка слишком далеко."),  # no king word: not the race (judge [J])
    (SQUARE, "draw", "Белый король слишком далеко, чтобы помочь пешке."),  # the pawn's own king
    (SQUARE, "draw", "Белый король слишком далеко от своей пешки."),
    (SQUARE, "draw", "Если король пойдёт на e4, он окажется слишком далеко от пешки."),
    (SQUARE, "draw", "Как правило, король, который стоит вне квадрата, пешку не догоняет."),
    (FAR_LOST, "White wins", "Король слишком далеко от пешки и не догонит её."),
    (SQUARE_LOST, "White wins", "Твой король на f5 слишком далеко от пешки, она проходит."),
])
def test_true_distance_sentences_pass(fen, tb, sentence):
    assert _issues(sentence, _ctx(fen, RACE_Q, tb)) == []


def test_race_distance_switch(monkeypatch):
    s = "Твой король на e5 слишком далеко."
    monkeypatch.setenv("COACH_DETECTORS_OFF", "race_distance")
    assert _issues(s, _ctx(SQUARE, RACE_Q, "draw")) == []
    monkeypatch.delenv("COACH_DETECTORS_OFF")
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "race_distance")
    ctx = _ctx(SQUARE, RACE_Q, "draw")
    assert _issues(s, ctx) == []
    assert [n for n, *_ in ctx.detector_shadow] == ["race_distance"]
    monkeypatch.delenv("COACH_DETECTORS_SHADOW")
    ctx = _ctx(SQUARE, RACE_Q, "draw")
    ctx.relation_surface = "lesson"  # the /learn tutor gets no new detector
    assert ec.outcome_issues("твой король на e5 слишком далеко.", ctx) == []


def test_old_race_claims_do_not_depend_on_the_switch(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_OFF", "race_distance,mate_squares,king_direction")
    assert _issues("Нет, не догонит.", _ctx(SQUARE, RACE_Q, "draw"))


# ── mate_squares ─────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("fen,sentence,needle", [
    (KNNK, "Мат случается только если чёрный король сам забредёт в угол, и ты поймаешь момент — но заставить его "
           "туда пойти нельзя.", "KNNK"),
    (KNNK, "Мат получается только если чёрный король сам зайдёт в угол.", "KNNK"),
    (KNNK, "Мат тут возможен только если чёрный король сам зайдёт в угол под удар — то есть по ошибке.", "KNNK"),
    (KNNK, "Мат получается только если защищающийся сам зайдёт в угол и подставится под удар.", "KNNK"),
    ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
     "Двумя конями мат бывает только в углу доски.", "KNNK"),  # named in the sentence: the board does not matter
    (KRK, "Ладьёй мат бывает только в углу.", "KRK"),
    (KQK, "Ферзём мат ставится только в углу.", "forced"),  # solved: the queen forces it on the edge as well
])
def test_wrong_mate_places_are_cut(fen, sentence, needle):
    issues = _issues(sentence, _ctx(fen))
    assert issues and needle in issues[0] and ("edge" in issues[0]), issues


@pytest.mark.parametrize("fen,sentence", [
    (KNNK, "Нет — двумя конями мат здесь не форсируется."),
    ("8/8/8/4k3/8/8/8/1NN1K3 w - - 0 1", "Двумя конями мат не форсируется."),
    (KRK, "Ладьёй мат ставится только на краю доски."),
    (KQK, "Запомни на будущее: ферзь в одиночку матует только прижатого к краю короля, и решает не шах, а «отнять "
          "клетки, но оставить одну и подойти своим королём»."),
    (KBNK, "Важно: мат в таких позициях ставится только у самого края доски, в углу."),
    (KBNK, "Мат слоном и конём ставится только в углу."),  # forced, not solved for four pieces: not judged
    (KNNK, "Мат возможен не только в углу, но и на краю."),
    (KNNK, "Двумя конями мат возможен только на краю доски."),
    (KNNK, "Мат случается только в углу?"),
    (KNNK, "Мат в два хода здесь возможен только если король пойдёт в угол."),  # one position, not the ending
    (KNNK, "После Nd3 мат возможен только в углу."),
    ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "Мат бывает только в углу."),  # no ending
    (KRK, "Ладьёй и ферзём мат бывает только в углу."),  # two endings named: not judged
    (KNNK, "Кажется, что мат случается только в углу, но это не так."),
])
def test_true_or_unjudged_mate_places_pass(fen, sentence):
    assert _issues(sentence, _ctx(fen)) == []


def test_mate_squares_switch(monkeypatch):
    s = "Мат случается только если чёрный король сам забредёт в угол."
    monkeypatch.setenv("COACH_DETECTORS_OFF", "mate_squares")
    assert _issues(s, _ctx(KNNK)) == []
    monkeypatch.setenv("COACH_DETECTORS_OFF", "")
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "mate_squares")
    ctx = _ctx(KNNK)
    assert _issues(s, ctx) == []
    assert [n for n, *_ in ctx.detector_shadow] == ["mate_squares"]


def test_the_mate_table_is_sound():
    data = json.loads((Path(ec.__file__).parent / "data" / "mate_squares.json").read_text(encoding="utf-8"))
    edge = set(data["regions"]["edge"])
    assert set(data["endings"]) == {"KQK", "KRK", "KBBK", "KBNK", "KNNK"}
    for name, entry in data["endings"].items():
        assert set(entry["possible"]) <= edge, name  # none of the five mates a king off the edge
        assert set(entry["example"]) == set(entry["possible"])
        for sq, fen in entry["example"].items():
            b = chess.Board(fen)
            assert b.is_checkmate() and b.king(b.turn) == chess.parse_square(sq), (name, sq)
            assert ec._board_ending(b) == name
    knnk = set(data["endings"]["KNNK"]["possible"])
    assert {"d8", "e8", "d1", "e1", "a4", "h5", "a8"} <= knnk and "b8" not in knnk
    assert data["endings"]["KNNK"]["forced_outside"]["never_forced"] is True
    assert data["endings"]["KRK"]["forced_outside"]["corner"] is True
    assert data["endings"]["KBNK"]["forced_outside"]["corner"] is None


def test_board_ending():
    assert ec._board_ending(chess.Board(KNNK)) == "KNNK"
    assert ec._board_ending(chess.Board("8/8/8/4k3/8/8/8/1B1BK3 w - - 0 1")) is None  # both bishops on one colour
    assert ec._board_ending(chess.Board("8/8/8/4k3/8/8/8/2BBK3 w - - 0 1")) == "KBBK"
    assert ec._board_ending(chess.Board(SQUARE)) is None


# ── king_direction (shadow) ──────────────────────────────────────────────────────────────────────────────────────
ROW_EVAL = "Поэтому не гонись за ней по диагонали: вставай на одну вертикаль с пешкой и двигайся прямо к ней."


def test_king_direction_is_shadow_by_default():
    assert config.detector_mode("king_direction") == "shadow"
    _seed_tablebase(SQUARE, "draw", ["Kd5", "Kd6"])
    ctx = _ctx(SQUARE, RACE_Q, "draw")
    assert _issues(ROW_EVAL, ctx) == []
    logged = [(n, iss) for n, _t, iss in getattr(ctx, "detector_shadow", [])]
    assert logged and logged[0][0] == "king_direction" and "pawn's file" in logged[0][1][0]
    assert "Kd5, Kd6" in logged[0][1][0]


@pytest.fixture
def direction_on(monkeypatch):
    monkeypatch.setitem(config.DETECTOR_DEFAULTS, "king_direction", "on")


def test_king_direction_judge(direction_on):
    _seed_tablebase(SQUARE, "draw", ["Kd5", "Kd6"])
    ctx = _ctx(SQUARE, RACE_Q, "draw")
    assert ec.king_direction_issues(ROW_EVAL.lower(), ctx)
    # forbidding the diagonal is not wrong while Kd5 holds; advising the straight way to the pawn is right
    for s in ("Не гонись за пешкой по диагонали.", "Иди прямо к пешке: Kd5.", "Двигайся к пешке по диагонали."):
        assert ec.king_direction_issues(s.lower().replace("ё", "е"), _ctx(SQUARE, RACE_Q, "draw")) == [], s
    # every keeping move diagonal: forbidding the diagonal is wrong
    _seed_tablebase(SQUARE, "draw", ["Kd6"])
    got = ec.king_direction_issues("не иди по диагонали.", _ctx(SQUARE, RACE_Q, "draw"))
    assert got and "forbids" in got[0] and "Kd6" in got[0]


def test_king_direction_needs_the_tablebase_answer(direction_on):
    ctx = _ctx(SQUARE, RACE_Q, "draw")  # nothing fetched: undecided
    assert ec.king_direction_issues(ROW_EVAL.lower(), ctx) == []
    _seed_tablebase(SQUARE, "draw", ["Kd5", "Kd6"])
    assert ec.king_direction_issues("белый король идет по диагонали.", _ctx(SQUARE, RACE_Q, "draw")) == []
    assert ec.king_direction_issues("если пойдешь по диагонали, проиграешь.", _ctx(SQUARE, RACE_Q, "draw")) == []
