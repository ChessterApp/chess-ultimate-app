"""
Maia inference API blueprint.

POST /api/maia/move
  Body: {
    "fen": "<FEN>",              (required)
    "elo_self": 1500,            (optional, defaults to 1500; accepts "eloSelf")
    "elo_oppo": 1500,            (optional, defaults to 1500; accepts "eloOppo")
    "temperature": 1.0,          (optional, sampling temperature)
    "seed": 42                   (optional, makes the sampled move deterministic)
  }
  Returns: {
    "move": "<sampled uci>",     temperature-sampled move (what the bot plays)
    "top_move": "<uci>",         highest-probability legal move (deterministic)
    "policy": { "<uci>": prob },  full sorted move distribution
    "value": 0.53                win probability for the side to move
  }

This is the server-side fallback that lets a first-time visitor play a Maia bot
before the browser has finished downloading the ONNX model. See
`services/maia_engine.py` for the (faithful) port of the frontend pipeline.
"""

import logging
import random

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

maia_bp = Blueprint("maia", __name__, url_prefix="/api/maia")


def _coerce_elo(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


@maia_bp.route("/move", methods=["POST"])
def maia_move():
    from services import maia_engine

    data = request.get_json(silent=True) or {}

    fen = data.get("fen")
    if not fen or not isinstance(fen, str):
        return jsonify({"error": "Missing required field: fen"}), 400

    elo_self = _coerce_elo(data.get("elo_self", data.get("eloSelf")), 1500)
    elo_oppo = _coerce_elo(data.get("elo_oppo", data.get("eloOppo")), 1500)

    temperature = data.get("temperature", 1.0)
    try:
        temperature = float(temperature)
        if temperature <= 0:
            temperature = 1.0
    except (TypeError, ValueError):
        temperature = 1.0

    seed = data.get("seed")
    rng = random.Random(seed) if seed is not None else None

    try:
        policy, value = maia_engine.evaluate(fen, elo_self, elo_oppo)
    except ValueError as e:
        return jsonify({"error": f"Invalid position: {e}"}), 400
    except Exception as e:  # inference / model load failure
        logger.exception("Maia inference failed")
        return jsonify({"error": f"Inference failed: {e}"}), 500

    if not policy:
        return jsonify({"error": "No legal moves for position"}), 400

    top_move = next(iter(policy))
    move = maia_engine.select_move(policy, temperature=temperature, rng=rng)

    return jsonify(
        {
            "move": move,
            "top_move": top_move,
            "policy": policy,
            "value": value,
        }
    )
