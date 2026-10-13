"""
Tests for the Game Review engine pipeline (Phase 1).

Unit tests use pure math; the pipeline test uses the REAL Stockfish binary at
/usr/games/stockfish at a low depth so it runs in seconds. Endpoint tests
monkeypatch the analysis function to keep the queue/cache flow fast and
deterministic (the pipeline test is the one that exercises the real engine).
"""

import time

import pytest

from services import game_review, move_classify

# Scholar's mate — a 7-ply miniature ending in checkmate, White winning.
SCHOLARS_MATE_PGN = (
    "1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0"
)


# ---------------------------------------------------------------------------
# Win% conversion
# ---------------------------------------------------------------------------
def test_win_percent_zero_cp_is_fifty():
    assert game_review.win_percent_white({"type": "cp", "value": 0}) == pytest.approx(50.0)


def test_win_percent_mate_clamps():
    assert game_review.win_percent_white({"type": "mate", "value": 3}) == 100.0
    assert game_review.win_percent_white({"type": "mate", "value": -3}) == 0.0


def test_win_percent_symmetry():
    for cp in (10, 43, 150, 800, -37, -1200):
        w = game_review.win_percent_white({"type": "cp", "value": cp})
        b = game_review.win_percent_white({"type": "cp", "value": -cp})
        assert w + b == pytest.approx(100.0)


def test_win_percent_advantage_direction():
    assert game_review.win_percent_white({"type": "cp", "value": 300}) > 50.0
    assert game_review.win_percent_white({"type": "cp", "value": -300}) < 50.0


# ---------------------------------------------------------------------------
# Per-move accuracy
# ---------------------------------------------------------------------------
def test_move_accuracy_no_loss_is_full():
    assert game_review.move_accuracy(50.0, 50.0) > 99.0


def test_move_accuracy_big_loss_is_low():
    assert game_review.move_accuracy(90.0, 40.0) < 20.0


def test_move_accuracy_gain_clamps_to_100():
    # A move that improves the mover's win% cannot score above 100.
    assert game_review.move_accuracy(40.0, 70.0) == 100.0


def test_black_move_sign_correctness():
    """
    A Black move that IMPROVES Black's position must score high, and a Black
    blunder must score low. Inputs are White-POV win% before/after; the flip to
    the mover's POV is what gets the sign right.
    """
    # White-POV 60 -> 30 means Black went from 40% to 70% (Black improved).
    good = game_review.accuracy_for_move(60.0, 30.0, mover_is_white=False)
    assert good > 99.0

    # White-POV 30 -> 80 means Black went from 70% to 20% (Black blundered).
    bad = game_review.accuracy_for_move(30.0, 80.0, mover_is_white=False)
    assert bad < 20.0

    # Same numbers scored as White (naively, without the flip) would be wrong:
    # verify the White interpretation of the "good" Black move is actually a loss.
    as_white = game_review.accuracy_for_move(60.0, 30.0, mover_is_white=True)
    assert as_white < 40.0


# ---------------------------------------------------------------------------
# Full pipeline against the real Stockfish binary
# ---------------------------------------------------------------------------
def test_pipeline_scholars_mate():
    result = game_review.analyze_game(SCHOLARS_MATE_PGN, depth=8)

    assert result["plies"] == 7
    assert result["engine"] == "sf-d8"
    assert len(result["moves"]) == 7
    assert set(result["accuracy"].keys()) == {"w", "b"}

    expected_keys = {
        "ply", "san", "uci", "fen", "eval", "best", "second",
        "winPercent", "accuracy", "classification", "phase",
    }
    for i, move in enumerate(result["moves"], start=1):
        assert move["ply"] == i
        assert set(move.keys()) == expected_keys
        assert move["eval"]["type"] in ("cp", "mate")
        assert isinstance(move["eval"]["value"], int)
        assert 0.0 <= move["winPercent"] <= 100.0
        assert move["accuracy"] is None or 0.0 <= move["accuracy"] <= 100.0
        assert move["classification"] in move_classify.CLASSIFICATIONS
        assert move["phase"] in ("opening", "middlegame", "endgame")

    # White delivers checkmate — the final position is winning for White.
    last = result["moves"][-1]
    assert last["san"].startswith("Qxf7")
    assert last["winPercent"] > 90.0

    # Every non-final ply has an engine best move suggested from the prior position.
    assert result["moves"][0]["best"] is not None
    assert result["moves"][0]["best"]["uci"]

    # Phase 2 top-level schema is present and internally consistent.
    assert result["version"] == 2
    assert set(result["tally"].keys()) == {"w", "b"}
    total_tally = sum(result["tally"]["w"].values()) + sum(result["tally"]["b"].values())
    assert total_tally == result["plies"]
    assert set(result["estRating"].keys()) == {"w", "b"}
    assert set(result["phases"].keys()) == {"opening", "middlegame", "endgame"}
    assert all(m in range(1, result["plies"] + 1) for m in result["keyMoments"])
    assert set(result["opening"].keys()) == {"eco", "name", "lastBookPly"}

    # Opening detected (1. e4 e5 2. Bc4 is a known line) and its book plies are
    # excluded from accuracy (carry accuracy=null).
    assert result["opening"]["lastBookPly"] >= 1
    book_moves = [m for m in result["moves"] if m["classification"] == "book"]
    assert book_moves
    assert all(m["accuracy"] is None for m in book_moves)


# ---------------------------------------------------------------------------
# HTTP endpoints (analysis monkeypatched for speed)
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    from flask import Flask
    from routes.review import review_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(review_bp)
    return app.test_client()


@pytest.fixture
def fast_engine(monkeypatch, tmp_path):
    """Replace the heavy Stockfish analysis with a quick deterministic stub and
    isolate the on-disk cache to a temp dir."""
    monkeypatch.setattr(game_review, "CACHE_DIR", str(tmp_path))

    def fake_analyze(pgn, depth=game_review.DEPTH, progress_cb=None):
        if progress_cb:
            progress_cb(2, 2)
        return {
            "moves": [
                {
                    "ply": 1, "san": "e4", "uci": "e2e4", "fen": "fen1",
                    "eval": {"type": "cp", "value": 20},
                    "best": {"uci": "e2e4", "eval": {"type": "cp", "value": 20}},
                    "second": None, "winPercent": 51.8, "accuracy": None,
                    "classification": "book", "phase": "opening",
                },
            ],
            "accuracy": {"w": 100.0, "b": 90.0},
            "tally": move_classify.empty_tally(),
            "estRating": {"w": 1200, "b": 1200},
            "phases": {p: {"w": None, "b": None} for p in ("opening", "middlegame", "endgame")},
            "keyMoments": [],
            "opening": {"eco": "B00", "name": "King's Pawn Game", "lastBookPly": 1},
            "engine": f"sf-d{depth}",
            "plies": 1,
            "version": 2,
        }

    monkeypatch.setattr(game_review, "analyze_game", fake_analyze)
    # Clear any state carried over from the module-level job dict.
    with game_review._JOBS_LOCK:
        game_review._JOBS.clear()


def _poll_until_done(client, review_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/review/{review_id}")
        data = resp.get_json()
        if data["status"] in ("done", "error"):
            return data
        time.sleep(0.02)
    pytest.fail("review did not finish in time")


def test_post_then_poll_to_done(client, fast_engine):
    resp = client.post("/api/review", json={"pgn": SCHOLARS_MATE_PGN})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] in ("queued", "done")
    review_id = body["review_id"]

    data = _poll_until_done(client, review_id)
    assert data["status"] == "done"
    assert data["result"]["plies"] == 1
    assert data["progress"] == 1.0


def test_cache_hit_returns_same_id_and_done(client, fast_engine):
    first = client.post("/api/review", json={"pgn": SCHOLARS_MATE_PGN}).get_json()
    _poll_until_done(client, first["review_id"])

    # Second request for the same game is an instant cache hit.
    second = client.post("/api/review", json={"pgn": SCHOLARS_MATE_PGN}).get_json()
    assert second["review_id"] == first["review_id"]
    assert second["status"] == "done"


def test_invalid_pgn_returns_400(client, fast_engine):
    assert client.post("/api/review", json={"pgn": "not a real pgn"}).status_code == 400
    assert client.post("/api/review", json={"pgn": ""}).status_code == 400
    assert client.post("/api/review", json={}).status_code == 400


def test_unknown_review_returns_404(client, fast_engine):
    assert client.get("/api/review/deadbeef").status_code == 404


# ---------------------------------------------------------------------------
# Cross-worker status sidecar (fixes the multi-gunicorn-worker 404 storm)
# ---------------------------------------------------------------------------
def test_get_review_falls_back_to_status_sidecar(fast_engine):
    """A poll landing on a worker that never saw the job (empty _JOBS, no cache)
    reads the shared status sidecar instead of returning a spurious None/404."""
    rid = "siblingjob"
    game_review._write_status(rid, "running", 0.4)
    with game_review._JOBS_LOCK:
        game_review._JOBS.clear()  # this worker never received the job

    out = game_review.get_review(rid)
    assert out is not None
    assert out["status"] == "running"
    assert out["progress"] == pytest.approx(0.4)


def test_get_review_none_when_nothing_exists(fast_engine):
    with game_review._JOBS_LOCK:
        game_review._JOBS.clear()
    assert game_review.get_review("genuinely-unknown-id") is None


def test_submit_dedupes_against_sibling_sidecar(fast_engine):
    """A duplicate submit landing on another worker (empty _JOBS) honours the
    sidecar and returns the in-flight status without enqueueing a 2nd analysis."""
    rid = game_review.pgn_hash(SCHOLARS_MATE_PGN)
    game_review._write_status(rid, "running", 0.2)
    with game_review._JOBS_LOCK:
        game_review._JOBS.clear()

    qsize_before = game_review._QUEUE.qsize()
    review_id, status = game_review.submit_review(SCHOLARS_MATE_PGN)
    assert review_id == rid
    assert status == "running"
    assert game_review._QUEUE.qsize() == qsize_before  # not re-enqueued


def test_status_sidecar_removed_when_done(client, fast_engine):
    """Once analysis completes the sidecar is deleted so the full result cache is
    the single source of truth — a later 404 then means genuinely unknown."""
    body = client.post("/api/review", json={"pgn": SCHOLARS_MATE_PGN}).get_json()
    rid = body["review_id"]
    _poll_until_done(client, rid)

    assert game_review._read_status(rid) is None
    assert game_review._read_cache(rid) is not None


# ─── analytics: game_review_completed (tracking plan §4 B) ─────────────────────

def _wait_for(pred, timeout=5.0):
    import time
    deadline = time.time() + timeout
    while time.time() < deadline and not pred():
        time.sleep(0.02)


def test_completed_review_captures_event_for_requester(client, fast_engine, monkeypatch):
    from services import analytics_posthog
    with game_review._JOBS_LOCK:
        game_review._JOBS.clear()
    calls = []
    monkeypatch.setattr(analytics_posthog, "capture", lambda *a: calls.append(a))
    persisted = []
    monkeypatch.setattr(game_review, "_persist_insight", lambda *a: persisted.append(a))

    resp = client.post("/api/review", json={
        "pgn": SCHOLARS_MATE_PGN, "analytics_user_id": "user_rev", "source": "bot",
    })
    assert resp.status_code == 200
    _wait_for(lambda: calls)
    assert calls == [("user_rev", "game_review_completed", {"cached": False, "source": "bot"})]
    # Analytics id never becomes the insight-persistence user id.
    assert persisted and persisted[0][1] is None

    # A second submit of the same game is a cache hit → captured as cached.
    with game_review._JOBS_LOCK:
        game_review._JOBS.clear()
    client.post("/api/review", json={
        "pgn": SCHOLARS_MATE_PGN, "analytics_user_id": "user_rev", "source": "nope",
    })
    assert calls[-1] == ("user_rev", "game_review_completed", {"cached": True})


def test_anonymous_review_captures_nothing(client, fast_engine, monkeypatch):
    from services import analytics_posthog
    with game_review._JOBS_LOCK:
        game_review._JOBS.clear()
    calls = []
    monkeypatch.setattr(analytics_posthog, "capture", lambda *a: calls.append(a))
    rid = client.post("/api/review", json={"pgn": SCHOLARS_MATE_PGN}).get_json()["review_id"]
    _wait_for(lambda: (game_review.get_review(rid) or {}).get("status") == "done")
    assert calls == []
