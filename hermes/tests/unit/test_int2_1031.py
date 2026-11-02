"""Stage-2 integration of plan 31.10 (P2, P4, P5, P6 merged on next-1031): the seams between the packages."""
from __future__ import annotations

import chess
import pytest

from src import board_rules, hypothetical
from src.answer_check import CheckContext, check_sentence, record_shadow
from tests.support.engine_stub import stub_engine  # the timed and the fixed-depth look (K3 02.11)

LUCENA = "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1"


def _fake_engine(monkeypatch, before: float, after: float):
    """The engine: the position before scores *before* with Rc4, the one after the move *after* (White's side)."""
    def fake(fen, movetime_ms, multipv=1, min_depth=None, **kw):
        b = chess.Board(fen)
        if b.turn == chess.WHITE:
            return {"lines": [{"score": before, "pv": "c1c4"}]}
        return {"lines": [{"score": -after, "pv": "d8e7"}]}

    stub_engine(monkeypatch, fake)


# (None: no tablebase answer — undecided while the engine still has White winning, stage 3: _ending_unproven)
@pytest.mark.parametrize("keeping,cut", [(["Rd1+", "Rc4"], False), (["Rc4"], True), (None, False)])
def test_a_move_the_tablebase_says_keeps_the_win_is_no_mistake(monkeypatch, keeping, cut):
    # lucena «Сейчас лучший ход — Rd1+»: the engine's number drops +6.1 → +4.3, yet Rd1+ is the textbook win
    _fake_engine(monkeypatch, 6.1, 4.3)
    tb = None if keeping is None else {"category": "win", "best_san": keeping[0], "keeping": keeping}
    monkeypatch.setattr(board_rules, "tablebase", lambda b: tb)
    board = chess.Board(LUCENA)
    issue = hypothetical.verify_recommendation(board, board.parse_san("Rd1+"), "Rd1+", 300)
    assert bool(issue) is cut, issue


def test_more_than_seven_pieces_never_asks_the_tablebase(monkeypatch):
    monkeypatch.setattr(board_rules, "tablebase", lambda b: pytest.fail("asked"))
    assert hypothetical._tablebase_keeps(chess.Board(), "e4") is False


def test_moves_read_as_a_plan_still_write_a_line():
    # start_scene (P1) reads «Nf3 … ...g6» on the start position as a plan; P2's open_recap must still see a line
    b = chess.Board()
    for san in "e4 c5 Nf3 d6".split():
        b.push_san(san)
    ctx = CheckContext.from_fens([b.fen()], student_color=chess.WHITE)
    ctx.game_moves = "e4 c5 Nf3 d6".split()
    ctx.language = "ru"
    assert check_sentence("Nf3 — и чёрные ответили d6: это классическая сицилианская, с ...g6.", ctx) == []
    assert [san for san, _b, _m in ctx.written_trail][-1] == "g6"


def test_every_shadow_record_has_one_shape():
    ctx = CheckContext.from_fens([chess.STARTING_FEN])
    ctx.sentence_now = "Пример."
    record_shadow(ctx, "a", ["x"])
    record_shadow(ctx, "b", "y", "Другое.")
    record_shadow(ctx, "c", [])
    assert ctx.detector_shadow == [("a", "Пример.", ["x"]), ("b", "Другое.", ["y"])]
