"""
Guards for the shipped quantized Maia model (produced by scripts/quantize_maia.py).

Skips cleanly when the quantized artifact isn't present (e.g. a fresh checkout
before the build step has run).
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import maia_engine  # noqa: E402

MAIA3_DIR = os.path.join(
    os.path.dirname(maia_engine.MODEL_PATH)
)
INT8_PATH = os.path.join(MAIA3_DIR, "maia3_simplified_int8.onnx")
FP16_PATH = os.path.join(MAIA3_DIR, "maia3_simplified_fp16.onnx")

# The client downloads whichever quantized build shipped.
_shipped = next((p for p in (INT8_PATH, FP16_PATH) if os.path.exists(p)), None)

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

requires_quantized = pytest.mark.skipif(
    _shipped is None, reason="No quantized Maia model shipped yet"
)


@requires_quantized
def test_quantized_model_has_same_io_signature():
    import onnxruntime as ort

    q = ort.InferenceSession(_shipped, providers=["CPUExecutionProvider"])
    fp32 = maia_engine.get_session()

    assert [i.name for i in q.get_inputs()] == [i.name for i in fp32.get_inputs()]
    assert [o.name for o in q.get_outputs()] == [o.name for o in fp32.get_outputs()]


@requires_quantized
def test_quantized_model_is_smaller_than_source():
    assert os.path.getsize(_shipped) < os.path.getsize(maia_engine.MODEL_PATH)


@requires_quantized
def test_quantized_model_agrees_on_start_position():
    import onnxruntime as ort

    q = ort.InferenceSession(_shipped, providers=["CPUExecutionProvider"])
    board_tokens, legal_moves = maia_engine.preprocess_maia3(START_FEN)
    feeds = {
        "tokens": board_tokens.reshape(1, 64, 12).astype(np.float32),
        "elo_self": np.array([1500], dtype=np.float32),
        "elo_oppo": np.array([1500], dtype=np.float32),
    }
    logits_move, logits_value = q.run(["logits_move", "logits_value"], feeds)
    policy, _ = maia_engine.process_outputs(
        START_FEN, logits_move[0], logits_value[0], legal_moves
    )
    # e4 is a wide margin favourite; quantization must not flip the top move here.
    assert next(iter(policy)) == "e2e4"
