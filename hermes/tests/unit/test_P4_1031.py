"""P4 engine claims (plan 31.10): «решает ферзь» judged by the piece's own best move (piece_decides), and the swing
of a trade the sentence names (trade_swing_named, off until Асан agrees).

The detection is tested without the engine on hand-built contexts; the verdicts with the local Stockfish, with the
engine stage switched on (tests/conftest.py switches it off for every test).
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

from src import line_verdict as lv  # noqa: E402
from src.answer_check import CheckContext, _to_san  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "detect1031"
MATE2_NO = "r1bq1b1r/ppp3pp/2n1k3/3np3/2B5/5Q2/PPPP1PPP/RNB1K2R w KQ - 2 8"
SCHOLAR = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
B3 = "r1bqk2r/1pppbppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQ1RK1 w kq - 4 6"
B3_SENTENCE = "В лучшем случае белые отдают слона за пешку — это почти на четыре пешки хуже, чем было."


def _stockfish() -> bool:
    from src.tools.stockfish import STOCKFISH_PATH

    return bool(shutil.which(STOCKFISH_PATH) or os.path.exists(STOCKFISH_PATH))


needs_engine = pytest.mark.skipif(not _stockfish(), reason="the engine stage needs a local Stockfish")


@pytest.fixture
def engine_stage(monkeypatch):
    from src import config

    monkeypatch.setenv("ENGINE_API_URL", "")
    monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
    monkeypatch.setattr(config, "COACH_LINE_VERDICT", True)


def _ctx(fen: str, question: str = "", student=None, language: str = "ru") -> CheckContext:
    ctx = CheckContext.from_fens([fen], question=question, student_color=student)
    ctx.language = language
    return ctx


def _piece_claims(sentence: str, ctx) -> list:
    return [c for c in lv.line_claims(sentence, ctx) if c["kind"] == "piece_decides"]


# ── detection (no engine) ───────────────────────────────────────────────────────────────────────────────────────


def test_mate2_no_sentence_makes_a_queen_claim_for_the_side_to_move():
    row = json.loads((FIX / "rows" / "mate2-no.json").read_text(encoding="utf-8"))
    claims = _piece_claims(row["sentence"], load_ctx(row["ctx"]))
    assert len(claims) == 1
    c = claims[0]
    assert c["piece"] == chess.QUEEN and c["side"] == chess.WHITE and c["squares"] == (chess.F3,)
    assert c["board"].fen() == MATE2_NO and c["mode"] == "on"


@pytest.mark.parametrize("sentence,piece", [
    ("Здесь решает конь.", chess.KNIGHT),
    ("Всё решает белый ферзь на f3.", chess.QUEEN),
    ("Ферзь f3 решает исход партии.", chess.QUEEN),
    ("Белые решают ферзём.", chess.QUEEN),
    ("The black king is stuck in the centre, and the queen decides.", chess.QUEEN),
    ("У белых решает слон.", chess.BISHOP),
])
def test_the_class_of_forms_is_detected(sentence, piece):
    claims = _piece_claims(sentence, _ctx(MATE2_NO))
    assert [c["piece"] for c in claims] == [piece], sentence


@pytest.mark.parametrize("sentence", [
    "Ферзь тут один ничего не решает.",                         # denied
    "Решает не ферзь, а развитие.",                              # denied
    "Если ферзь прорвётся на королевский фланг, он решает.",     # conditional
    "Когда ферзь войдёт в игру, решает ферзь.",                  # conditional
    "В таких позициях обычно решает конь.",                      # general
    "В эндшпиле часто решает ладья.",                            # general
    "Решает ли тут ферзь?",                                      # a question
    "Ты думаешь, что решает ферзь, но это не так.",              # the student's belief
    "У чёрных в защите решает ферзь.",                           # the side not to move
    "Король белых в опасности, и решает ферзь.",                 # the side to move named as the victim
    "Лишний конь решает партию.",                                # material, not a move
    "Слон c4 и ферзь решают.",                                   # two pieces
    "Решает ферзь вместе с ладьёй.",                             # two pieces
    "Решает ферзь: Qxf7#.",                                      # a written line: _verify_line's
    "Ферзь на d1 решает.",                                       # no queen there
    "Потом решает ферзь.",                                       # later
    "Хочешь, покажу пример, где решает ферзь.",                  # an example offered
    "В партии Морфи решает ферзь.",                              # another game
    "Пешка решает.",                                             # a pawn: never the subject
    "Ферзь может решить партию.",                                # a possibility, not «решает»
])
def test_not_a_claim_about_a_move_now(sentence):
    assert _piece_claims(sentence, _ctx(MATE2_NO)) == [], sentence


def test_no_claim_after_a_line_in_the_sentence_before():
    ctx = _ctx(MATE2_NO)
    lv.line_claims("Берёшь коня: Qxd5+ Qxd5.", ctx)
    assert ctx._line_end is not None
    assert _piece_claims("И решает ферзь.", ctx) == []


def test_no_claim_when_the_question_names_a_move():
    ctx = _ctx(MATE2_NO, question="А если Qxd5+?")
    ctx.quoted = {"Qxd5+"}
    assert _piece_claims("Тут решает ферзь.", ctx) == []


def test_no_claim_when_the_turn_shows_another_position():
    ctx = _ctx(MATE2_NO)
    ctx.add(SCHOLAR)  # a second state given to the turn: which board «решает ферзь» means is not known
    assert _piece_claims("Тут решает ферзь.", ctx) == []


def test_no_claim_for_the_opponent_piece_in_a_game():
    # The student plays Black and it is White's move: «твой ферзь решает» is the student's queen, not to move.
    ctx = _ctx(MATE2_NO, student=chess.BLACK)
    assert _piece_claims("Тут решает твой ферзь.", ctx) == []
    ctx = _ctx(MATE2_NO, student=chess.WHITE)
    assert [c["side"] for c in _piece_claims("Тут решает твой ферзь.", ctx)] == [chess.WHITE]


def test_switches(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_OFF", "piece_decides")
    assert _piece_claims("Здесь решает ферзь.", _ctx(MATE2_NO)) == []
    monkeypatch.delenv("COACH_DETECTORS_OFF")
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "piece_decides")
    assert [c["mode"] for c in _piece_claims("Здесь решает ферзь.", _ctx(MATE2_NO))] == ["shadow"]
    monkeypatch.delenv("COACH_DETECTORS_SHADOW")
    ctx = _ctx(MATE2_NO)
    ctx.relation_surface = "lesson"  # the /learn tutor gets no detector
    assert _piece_claims("Здесь решает ферзь.", ctx) == []
    ctx = _ctx(MATE2_NO)
    ctx.relation_surface = "game"  # a game move comment: the engine claims judge it as a chat answer (fix 01.11)
    assert [c["mode"] for c in _piece_claims("Здесь решает ферзь.", ctx)] == ["on"]


@pytest.mark.parametrize("words,value", [
    ("слона", 3), ("пешку", 1), ("пешку и слона", 4), ("две пешки", 2), ("ферзя", 9), ("качество", 2),
    ("ладью и коня", 8), ("a bishop", 3), ("two pawns", 2), ("фигуру", 3),
])
def test_trade_units(words, value):
    assert lv._units(words) == value


def test_named_trade_is_kept_only_with_the_flag(monkeypatch):
    def swing(flag):
        if flag is None:
            monkeypatch.delenv("COACH_TRADE_SWING_NAMED", raising=False)
        else:
            monkeypatch.setenv("COACH_TRADE_SWING_NAMED", flag)
        ctx = _ctx(B3, question="А если b3?")
        ctx.quoted = {"b3"}
        return [c for c in lv.line_claims(B3_SENTENCE, ctx) if c["kind"] == "swing"]

    off = swing(None)
    assert len(off) == 1 and "named" not in off[0]
    on = swing("1")
    assert len(on) == 1 and on[0]["named"] == 2 and on[0]["named_mode"] == "on"
    assert "слона за пешку" in on[0]["named_words"]


# ── verdicts (the engine) ───────────────────────────────────────────────────────────────────────────────────────


@needs_engine
def test_mate2_no_row_is_caught_with_both_moves_named(engine_stage):
    row = json.loads((FIX / "rows" / "mate2-no.json").read_text(encoding="utf-8"))
    got = run_answer(row["prefix"] + [row["sentence"]], load_ctx(row["ctx"]), engine=True, live_game=False)
    sentence, issues, stage = got[-1]
    assert stage == "engine" and len(issues) == 1
    assert "Qg3" in issues[0] and "Nc3" in issues[0]  # the antidote (tests/fixtures/prevent/antidotes.json)
    assert "no move decides" in issues[0]


@needs_engine
@pytest.mark.parametrize("sentence", ["Здесь решает конь.", "Белые решают ферзём.",
                                      "The black king is stuck in the centre, and the queen decides."])
def test_the_class_is_judged_false_on_the_mate2_no_board(engine_stage, sentence):
    language = "en" if sentence.isascii() else "ru"
    got = run_answer([sentence], _ctx(MATE2_NO, language=language), engine=True, live_game=False)
    assert got[-1][2] == "engine", got


@needs_engine
def test_a_live_game_names_no_move(engine_stage):
    ctx = _ctx(MATE2_NO)
    claims = _piece_claims("Здесь решает ферзь.", ctx)
    why = lv.verify_claims(claims, 300, reveal=False)
    assert why and "queen" in why
    assert not any(san in why for san in ("Qg3", "Nc3", "Qxd5"))


@needs_engine
def test_shadow_judges_but_never_cuts(engine_stage, monkeypatch, caplog):
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "piece_decides")
    from src.answer_check import shadow_into

    ctx = _ctx(MATE2_NO)
    claims = _piece_claims("Здесь решает ферзь.", ctx)
    with shadow_into(ctx, "Здесь решает ферзь."):  # fix1101 F8: the record lands on the turn's check
        assert lv.verify_claims(claims, 300, True) is None
    assert any(name == "piece_decides" for name, _t, _i in (ctx.detector_shadow or []))


@needs_engine
@pytest.mark.parametrize("fen,sentence", [
    (SCHOLAR, "Здесь всё решает ферзь."),                                   # Qxf7#
    ("2Q2qk1/1p4pp/p7/5P1B/2pP1r2/3b2K1/PP5P/8 w - - 0 1",
     "Король чёрных раскрыт, и решает ферзь."),                              # 1.Bf7+ Kxf7 2.Qe6#: in the engine's line
    ("4Rnk1/1q3pp1/p1r2Q2/1p5p/6B1/PP5P/3B1PP1/6K1 w - - 0 1",
     "Чёрный король заперт, и решает ферзь."),                               # 1.Rxf8+ … Qh8#
    (SCHOLAR, "Here the queen decides."),
])
def test_a_true_claim_is_judged_and_holds(engine_stage, fen, sentence):
    ctx = _ctx(fen, language="en" if sentence.isascii() else "ru")
    claims = _piece_claims(sentence, ctx)
    assert len(claims) == 1, "the control must reach the judge, not be skipped"
    assert lv.verify_claims(claims, 300, True) is None


@needs_engine
def test_pawn_b3_bare_with_the_flag(engine_stage, monkeypatch):
    row = json.loads((FIX / "rows" / "pawn-b3-bare.json").read_text(encoding="utf-8"))

    def run():
        got = run_answer(row["prefix"] + [row["sentence"]], load_ctx(row["ctx"]), engine=True, live_game=False)
        return got[-1]

    monkeypatch.delenv("COACH_TRADE_SWING_NAMED", raising=False)
    assert run()[1] == []  # off: as on main (Асан decides)
    monkeypatch.setenv("COACH_TRADE_SWING_NAMED", "1")
    sentence, issues, stage = run()
    assert stage == "engine" and "2 pawns" in issues[0]
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "trade_swing_named")
    assert run()[1] == []  # shadow: logged, never cut


@needs_engine
def test_named_trade_with_its_own_count_passes(engine_stage, monkeypatch):
    monkeypatch.setenv("COACH_TRADE_SWING_NAMED", "1")
    ctx = _ctx(B3, question="А если b3?")
    ctx.quoted = {"b3"}
    for sentence in ("В лучшем случае белые отдают слона за пешку — это на две пешки хуже, чем было.",
                     "Белые отдают слона за пешку — это примерно на 6.5 пешки хуже, чем было."):
        claims = [c for c in lv.line_claims(sentence, ctx) if c["kind"] == "swing"]
        assert claims and claims[0]["named"] == 2, sentence
        assert lv.verify_claims(claims, 300, True) is None, sentence


@needs_engine
@pytest.mark.parametrize("control", json.loads((FIX / "negatives" / "P4.json").read_text(encoding="utf-8"))["controls"],
                         ids=lambda c: c["id"])
def test_p4_controls_with_the_engine_stage_on(engine_stage, control):
    """tests/unit/test_detect1031_rows.py runs these with the engine stage off (tests/conftest.py); here it is on."""
    moves = control["moves"].split() if control.get("moves") else None
    fen = control.get("fen")
    if moves:
        b = chess.Board()
        for m in moves:
            b.push_san(m)
        fen = b.fen()
    ctx = _ctx(fen, question=control.get("question") or "")
    got = run_answer([control["sentence"]], ctx, engine=True, live_game=False)
    assert got[-1][1] == [], f"{control['id']}: {got[-1][1]}"
