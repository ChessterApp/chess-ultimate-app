"""Verified facts for the engine line (2026-09-29): threats, hanging and pinned pieces."""

from unittest.mock import patch

import chess
import pytest

from src.position_facts import describe_move, dynamic_facts, static_facts

# The production screenshot: the voice coach claimed the queen e7 attacked e4 and
# that Nxb5 attacked the knight f6, and missed the threat Nxc7+.
SCREENSHOT = "rnb1kb1r/p1ppqppp/5n2/1p2p3/4P3/2NP4/PPP1BPPP/R1BQK1NR w KQkq - 0 6"


def _engine(best_by_fen: dict):
    """A fake analyse(): the given first move and score for known positions."""
    def analyse(fen):
        key = " ".join(fen.split()[:4])
        for known, (uci, score, mate) in best_by_fen.items():
            if " ".join(known.split()[:4]) == key:
                line = {"pv": uci, "score": score, "depth": 12}
                if mate is not None:
                    line["mate_in"] = mate
                return {"lines": [line]}
        return {"lines": []}
    return analyse


@pytest.mark.unit
def test_static_facts_name_the_real_attackers_only():
    facts = static_facts(chess.Board(SCREENSHOT))
    assert "the black pawn b5 is attacked by the white knight c3 and not defended" in facts
    e4 = next(f for f in facts if f.startswith("the white pawn e4"))
    assert "the black knight f6" in e4 and "queen" not in e4
    assert "defended by the white pawn d3 and the white knight c3" in e4


@pytest.mark.unit
def test_the_threat_of_the_best_move_is_the_fork():
    board = chess.Board(SCREENSHOT)
    after = board.copy()
    after.push_san("Nxb5")
    passed = after.copy()
    passed.push(chess.Move.null())
    analyse = _engine({passed.fen(): ("b5c7", 7.5, None)})
    facts = dynamic_facts(board, "c3b5", 1.8, analyse)
    threat = next(f for f in facts if f.startswith("after Nxb5"))
    assert "Nxc7+" in threat
    assert "a fork of the black rook a8 and the black king e8" in threat


@pytest.mark.unit
def test_being_mated_is_not_a_threat():
    # K+R v K: the defending side "threatens" nothing — every line is mate against it.
    board = chess.Board("8/8/8/4k3/8/8/8/4K2R w - - 0 1")
    passed = board.copy()
    passed.push(chess.Move.null())
    analyse = _engine({passed.fen(): ("e5e4", -10000.0, -14)})
    assert not any("Black threatens" in f for f in dynamic_facts(board, "h1h5", 10000.0, analyse))


@pytest.mark.unit
def test_a_small_gain_is_not_a_threat_but_a_free_piece_is():
    board = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
    passed = board.copy()
    passed.push(chess.Move.null())
    # Black's knight takes the undefended queen: reported even with a tiny score gain.
    facts = dynamic_facts(board, "h5f7", 10000.0, _engine({passed.fen(): ("f6h5", 0.1, None)}))
    assert "Black threatens Nxh5 — taking the white queen h5 if White ignores it" in facts
    assert "Qxf7# is mate" in facts


@pytest.mark.unit
def test_describe_move_names_mate_check_and_single_targets():
    assert describe_move(chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"), chess.Move.from_uci("d1d8")) == "Rd8# — mate"
    black_to_move = chess.Board(SCREENSHOT.replace(" w ", " b "))
    assert describe_move(black_to_move, chess.Move.from_uci("b5b4")) == "b4 — attacking the white knight c3"


@pytest.mark.unit
def test_the_engine_line_carries_the_facts():
    from src import voice_engine_note

    top = {"lines": [{"pv": "c3b5 d7d6 f2f4", "score": 1.8, "depth": 16},
                     {"pv": "d3d4", "score": 0.8, "depth": 16}]}
    board = chess.Board(SCREENSHOT)
    after = board.copy()
    after.push_san("Nxb5")
    passed_after = after.copy()
    passed_after.push(chess.Move.null())
    fake = _engine({passed_after.fen(): ("b5c7", 7.5, None)})
    with patch.object(voice_engine_note, "analyze_timed", return_value=top), \
            patch.object(voice_engine_note, "_threat_analysis", side_effect=fake):
        note = voice_engine_note.engine_note(SCREENSHOT, movetime_ms=1500)
    assert note["best"] == "Nxb5"
    assert "Facts (verified on the board and by the engine):" in note["note"]
    assert "Nxc7+" in note["note"] and "not defended" in note["note"]
    assert any("fork" in f for f in note["facts"])
