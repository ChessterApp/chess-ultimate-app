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
