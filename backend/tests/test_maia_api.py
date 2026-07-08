"""
Tests for the server-side Maia inference fallback (services/maia_engine.py +
api/maia.py blueprint).

These exercise the real ONNX model, so they require onnxruntime + the model
file to be present; they skip cleanly if the model is missing.
"""

import os
import random
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import maia_engine  # noqa: E402
from api.maia import maia_bp  # noqa: E402

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"

_model_missing = not os.path.exists(maia_engine.MODEL_PATH)
requires_model = pytest.mark.skipif(_model_missing, reason="Maia ONNX model not present")


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(maia_bp)
    return app.test_client()


# ── Pure helpers (no model needed) ───────────────────────────────────────────


def test_mirror_square():
    assert maia_engine.mirror_square("e2") == "e7"
    assert maia_engine.mirror_square("a1") == "a8"
    assert maia_engine.mirror_square("h8") == "h1"


def test_mirror_move_handles_promotion():
    assert maia_engine.mirror_move("e2e4") == "e7e5"
    assert maia_engine.mirror_move("a7a8q") == "a2a1q"


def test_mirror_fen_swaps_colors_and_side():
    mirrored = maia_engine.mirror_fen(START_FEN)
    # Start position is symmetric except the side to move flips w -> b.
    assert mirrored.split(" ")[1] == "b"
    assert mirrored.split(" ")[0] == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


def test_preprocess_legal_mask_matches_legal_move_count():
    import chess

    tokens, legal = maia_engine.preprocess_maia3(START_FEN)
    assert tokens.shape == (64 * 12,)
    # 20 legal opening moves, all mapped into the vocabulary.
    assert int(legal.sum()) == chess.Board(START_FEN).legal_moves.count() == 20


def test_select_move_is_seed_deterministic():
    policy = {"e2e4": 0.6, "d2d4": 0.3, "c2c4": 0.1}
    a = maia_engine.select_move(policy, 1.0, random.Random(123))
    b = maia_engine.select_move(policy, 1.0, random.Random(123))
    assert a == b


# ── Model-backed inference ───────────────────────────────────────────────────


@requires_model
def test_evaluate_start_position_top_move():
    policy, value = maia_engine.evaluate(START_FEN, 1500, 1500)
    # Maia strongly favours 1.e4 / 1.d4 from the start; e4 is the argmax.
    assert next(iter(policy)) == "e2e4"
    assert 0.0 <= value <= 1.0
    # Every returned move must be legal UCI on the board.
    import chess

    legal = {m.uci() for m in chess.Board(START_FEN).legal_moves}
    assert set(policy).issubset(legal)


@requires_model
def test_evaluate_black_to_move_returns_black_moves():
    policy, _ = maia_engine.evaluate(AFTER_E4_FEN, 1500, 1500)
    import chess

    legal = {m.uci() for m in chess.Board(AFTER_E4_FEN).legal_moves}
    assert set(policy).issubset(legal)
    # e7e5 is a black move (mirroring applied correctly), and top choice.
    assert next(iter(policy)) == "e7e5"


@requires_model
def test_move_endpoint_returns_legal_move(client):
    resp = client.post("/api/maia/move", json={"fen": START_FEN, "seed": 7})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["top_move"] == "e2e4"
    assert body["move"] in body["policy"]
    assert 0.0 <= body["value"] <= 1.0


@requires_model
def test_move_endpoint_seed_is_deterministic(client):
    payload = {"fen": START_FEN, "seed": 99, "temperature": 1.0}
    a = client.post("/api/maia/move", json=payload).get_json()["move"]
    b = client.post("/api/maia/move", json=payload).get_json()["move"]
    assert a == b


@requires_model
def test_move_endpoint_accepts_camelcase_elo(client):
    resp = client.post(
        "/api/maia/move", json={"fen": START_FEN, "eloSelf": 1100, "eloOppo": 1900}
    )
    assert resp.status_code == 200


def test_move_endpoint_requires_fen(client):
    resp = client.post("/api/maia/move", json={})
    assert resp.status_code == 400
    assert "fen" in resp.get_json()["error"].lower()
