"""Stage-3 integration of plan 31.10 (P8 prevention and P7 speed merged on next-1031): the seams between them."""
from __future__ import annotations

import os

from src import config
from src.answer_check import CheckContext, record_shadow, shadow_event_payload


def test_opening_ideas_are_one_set_from_both_files():
    """ideas.yaml (P8) names the idea first; an opening only lines.yaml (P2) has still gets its `idea`."""
    from src.answer_check_openings import opening_lines
    from src.prompt_builder import _ideas_cache, opening_ideas

    _ideas_cache.clear()
    ideas = opening_ideas()
    lines = {o["book"]: o.get("idea") for o in opening_lines()["openings"] if o.get("idea")}
    assert lines, "lines.yaml has no ideas"
    for book, idea in lines.items():
        assert book in ideas, book
    # where both name the opening, ideas.yaml's line wins (the Slav's «not with ...e6 as in the QGD», name-slav)
    assert "not with ...e6" in ideas["Slav Defense"]
    assert ideas["Queen's Gambit"] == " ".join(lines["Queen's Gambit"].split())


def test_shadow_records_become_one_event_payload():
    ctx = CheckContext.from_fens([None], [])
    assert shadow_event_payload(ctx) is None
    ctx.sentence_now = "Держи связку  слоном."
    record_shadow(ctx, "pin_noun", ["no pin on the board"])
    record_shadow(ctx, "loaded_line", "x" * 500, text="Ферзь пожертвован.")
    got = shadow_event_payload(ctx)
    assert got["total"] == 2
    assert got["records"][0] == {"detector": "pin_noun", "sentence": "Держи связку слоном.",
                                 "issues": ["no pin on the board"]}
    assert got["records"][1]["detector"] == "loaded_line" and len(got["records"][1]["issues"][0]) == 300


def test_pool_hash_defaults_to_stockfishs_own():
    """16 MB: the lines a process per search gave on main, and the depth-17 confirm inside its 1 s budget."""
    if "STOCKFISH_HASH_MB" not in os.environ:
        assert config.STOCKFISH_HASH_MB == 16


LUCENA = "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1"


def _fake_engine(monkeypatch, before: float, after: float):
    import chess

    from src import hypothetical

    def fake(fen, movetime_ms, multipv=1, min_depth=None, **kw):
        if chess.Board(fen).turn == chess.WHITE:
            return {"lines": [{"score": before, "pv": "c1c4"}]}
        return {"lines": [{"score": -after, "pv": "d8e7"}]}

    monkeypatch.setattr(hypothetical, "analyze_timed", fake)


import pytest  # noqa: E402


@pytest.mark.parametrize("before,after,tb,cut", [
    (6.5, 4.4, None, False),                                                       # no tablebase: still winning
    (6.5, 1.0, None, True),                                                        # the engine sees the win go
    (6.5, 4.4, {"category": "win", "best_san": "Rc4", "keeping": ["Rc4"]}, True),  # the tablebase decides
    (6.5, 4.4, {"category": "win", "best_san": "Rc4", "keeping": ["Rc4", "Rd1+"]}, False),
])
def test_an_ending_without_a_tablebase_answer_is_undecided_while_the_win_stays(monkeypatch, before, after, tb, cut):
    import chess

    from src import board_rules, hypothetical

    _fake_engine(monkeypatch, before, after)
    monkeypatch.setattr(board_rules, "tablebase", lambda b: tb)
    board = chess.Board(LUCENA)
    issue = hypothetical.verify_recommendation(board, board.parse_san("Rd1+"), "Rd1+", 300)
    assert bool(issue) is cut, issue


def test_more_than_seven_pieces_keep_the_engine_verdict(monkeypatch):
    import chess

    from src import board_rules, hypothetical

    _fake_engine(monkeypatch, 6.5, 4.4)
    monkeypatch.setattr(board_rules, "tablebase", lambda b: None)
    board = chess.Board("1K1k4/1P6/8/8/8/2p5/rpp5/2R5 w - - 0 1")
    assert hypothetical._ending_unproven(board, 6.5, 4.4) is False
