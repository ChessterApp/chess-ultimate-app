"""Tests for review_insights: distillation + fail-open persistence (CL Phase 1,
Slice 2). No network, no Supabase, no Stockfish."""

from unittest.mock import MagicMock, patch

import pytest

from services import review_insights as ri


def _move(ply, cls, best_cp, played_cp, san="Xx", fen="fen", best_uci="a1a2", phase="middlegame"):
    """Build a minimal review move dict with White-POV evals."""
    return {
        "ply": ply,
        "san": san,
        "fen": fen,
        "classification": cls,
        "phase": phase,
        "eval": {"type": "cp", "value": played_cp},
        "best": {"uci": best_uci, "eval": {"type": "cp", "value": best_cp}},
    }


# ---------------------------------------------------------------------------
# cp-loss + blunder selection
# ---------------------------------------------------------------------------
def test_cp_loss_white_move():
    # White (ply 1): best +300, played +50 → lost 250 from White's POV.
    mv = _move(1, "blunder", best_cp=300, played_cp=50)
    assert ri._cp_loss(mv, mover_is_white=True) == pytest.approx(250.0)


def test_cp_loss_black_move_flips_pov():
    # Black (ply 2): White-POV best -300 (great for Black), played -50 → Black
    # lost 250 in its own POV.
    mv = _move(2, "blunder", best_cp=-300, played_cp=-50)
    assert ri._cp_loss(mv, mover_is_white=False) == pytest.approx(250.0)


def test_cp_loss_mate_uses_large_magnitude():
    mv = {
        "ply": 1,
        "classification": "blunder",
        "eval": {"type": "cp", "value": 0},
        "best": {"uci": "a1a2", "eval": {"type": "mate", "value": 1}},
    }
    assert ri._cp_loss(mv, mover_is_white=True) == pytest.approx(ri._MATE_CP)


def test_select_blunders_worst_first_and_capped():
    moves = [
        _move(1, "blunder", 500, 0, san="A"),      # loss 500
        _move(3, "mistake", 200, 50, san="B"),     # loss 150
        _move(5, "inaccuracy", 100, 90, san="C"),  # ignored (not kept class)
        _move(7, "blunder", 900, 100, san="D"),    # loss 800
        _move(9, "mistake", 300, 250, san="E"),    # loss 50
        _move(11, "blunder", 600, 200, san="F"),   # loss 400
        _move(13, "mistake", 400, 380, san="G"),   # loss 20
    ]
    out = ri.select_blunders({"moves": moves}, limit=5)
    assert [b["move_played"] for b in out] == ["D", "A", "F", "B", "E"]
    assert all("inaccuracy" not in b["classification"] for b in out)
    assert out[0]["cp_loss"] == 800
    assert out[0]["classification"] == "blunder"
    assert out[0]["theme"] == "middlegame"


def test_select_blunders_color_filter():
    moves = [
        _move(1, "blunder", 500, 0, san="white-blunder"),   # White
        _move(2, "blunder", -500, 0, san="black-blunder"),  # Black
    ]
    white = ri.select_blunders({"moves": moves}, color="white")
    assert [b["move_played"] for b in white] == ["white-blunder"]
    black = ri.select_blunders({"moves": moves}, color="b")
    assert [b["move_played"] for b in black] == ["black-blunder"]


def test_select_blunders_skips_unparseable_evals():
    moves = [{"ply": 1, "classification": "blunder", "eval": None, "best": None}]
    assert ri.select_blunders({"moves": moves}) == []


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------
def test_build_summary_is_capped():
    blunders = [{"classification": "blunder", "move_played": "Q" * 50, "best_move": "b" * 50, "cp_loss": 900}]
    summary = ri.build_summary("O" * 500, 42.0, "0-1", blunders)
    assert len(summary) <= ri.SUMMARY_CHAR_LIMIT


def test_build_summary_no_blunders():
    summary = ri.build_summary("Sicilian", 88.0, "1-0", [])
    assert "No blunders" in summary


# ---------------------------------------------------------------------------
# distillation
# ---------------------------------------------------------------------------
def test_distill_insight_shape():
    review = {
        "opening": {"name": "Sicilian Defense", "eco": "B20"},
        "accuracy": {"w": 91.0, "b": 78.0},
        "moves": [_move(2, "blunder", -400, 0, san="Qd7")],  # Black move
    }
    row = ri.distill_insight("u1", "rev1", review, color="black", result="0-1")
    assert row["user_id"] == "u1"
    assert row["game_ref"] == "rev1"
    assert row["source"] == "review"
    assert row["color"] == "b"
    assert row["opening"] == "Sicilian Defense"
    assert row["accuracy"] == 78.0
    assert row["result"] == "0-1"
    assert len(row["blunders"]) == 1
    assert row["blunders"][0]["move_played"] == "Qd7"
    assert isinstance(row["summary"], str) and row["summary"]


def test_distill_insight_unknown_color_leaves_accuracy_none():
    review = {"opening": {"name": "X"}, "accuracy": {"w": 90.0, "b": 90.0}, "moves": []}
    row = ri.distill_insight("u1", "r", review)
    assert row["color"] is None
    assert row["accuracy"] is None


# ---------------------------------------------------------------------------
# persistence (fail-open, gated, anonymous skip)
# ---------------------------------------------------------------------------
_REVIEW = {"opening": {"name": "X"}, "accuracy": {"w": 90.0, "b": 90.0}, "moves": []}


def test_persist_skips_anonymous():
    with patch("services.supabase_client.get_supabase_client") as gc:
        assert ri.persist_review_insight("", "r", _REVIEW) is False
        assert ri.persist_review_insight(None, "r", _REVIEW) is False
        assert ri.persist_review_insight("   ", "r", _REVIEW) is False
    gc.assert_not_called()


def test_persist_disabled_by_flag(monkeypatch):
    monkeypatch.setenv("REVIEW_PERSIST_INSIGHTS", "false")
    with patch("services.supabase_client.get_supabase_client") as gc:
        assert ri.persist_review_insight("u1", "r", _REVIEW) is False
    gc.assert_not_called()


def test_persist_failopen_on_supabase_error():
    with patch("services.supabase_client.get_supabase_client", side_effect=RuntimeError("no creds")):
        assert ri.persist_review_insight("u1", "r", _REVIEW) is False


def test_persist_success_upserts_on_unique_key():
    client = MagicMock()
    with patch("services.supabase_client.get_supabase_client", return_value=client):
        ok = ri.persist_review_insight("u1", "rev1", _REVIEW, color="white", result="1-0")
    assert ok is True
    client.table.assert_called_once_with("coach_game_insights")
    upsert = client.table.return_value.upsert
    assert upsert.call_args.kwargs["on_conflict"] == "user_id,game_ref,source"
    row = upsert.call_args.args[0]
    assert row["user_id"] == "u1"
    assert row["game_ref"] == "rev1"


# ---------------------------------------------------------------------------
# game_review worker hook: user_id is threaded and persist fires on completion
# ---------------------------------------------------------------------------
def test_worker_persists_insight_with_user_id(monkeypatch, tmp_path):
    import time

    from services import game_review

    monkeypatch.setattr(game_review, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(game_review, "analyze_game", lambda pgn, depth=14, progress_cb=None: _REVIEW)
    with game_review._JOBS_LOCK:
        game_review._JOBS.clear()

    calls = []
    monkeypatch.setattr(
        ri, "persist_review_insight", lambda uid, rid, rev, **kw: calls.append((uid, rid)) or True
    )

    pgn = "1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0"
    review_id, _ = game_review.submit_review(pgn, user_id="student-42")

    deadline = time.time() + 5.0
    while time.time() < deadline and not calls:
        time.sleep(0.02)

    assert calls == [("student-42", review_id)]
