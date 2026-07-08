"""
Server-side Maia3 inference.

This is a faithful CPU port of the frontend Maia pipeline
(`frontend/src/lib/maia/tensor.ts`, `maia.ts` and the temperature-based
`selectMove` in `frontend/src/app/play/page.tsx`). It exists so a brand-new
visitor can play a Maia bot immediately, before the 45MB ONNX model has
finished downloading in the browser. The frontend hot-swaps to local inference
once its own model is ready; because both sides run the *same* fp32 model with
the same preprocessing and softmax, the move distribution is identical.

The InferenceSession is created once (module-level singleton) and reused for
every request — never per request.
"""

import json
import math
import os
import random
import threading

import numpy as np

try:  # python-chess is already a backend dependency (notation parsing)
    import chess
except ImportError:  # pragma: no cover - surfaced clearly at call time
    chess = None

# ── Paths ────────────────────────────────────────────────────────────────────

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)

# The server always uses the full-precision model, even after the client ships a
# quantized (int8/fp16) build — accuracy over size, since there is no download.
MODEL_PATH = os.environ.get(
    "MAIA_MODEL_PATH",
    os.path.join(_REPO_ROOT, "frontend", "public", "maia3", "maia3_simplified.onnx"),
)
_MOVES_PATH = os.path.join(
    _REPO_ROOT, "frontend", "src", "lib", "maia", "data", "all_moves_maia3.json"
)
_MOVES_REVERSED_PATH = os.path.join(
    _REPO_ROOT,
    "frontend",
    "src",
    "lib",
    "maia",
    "data",
    "all_moves_maia3_reversed.json",
)

# ── Move vocabulary ──────────────────────────────────────────────────────────

with open(_MOVES_PATH) as f:
    ALL_MOVES: dict = json.load(f)
with open(_MOVES_REVERSED_PATH) as f:
    # JSON keys are strings; index by int like the frontend does.
    ALL_MOVES_REVERSED: dict = {int(k): v for k, v in json.load(f).items()}

# ── FEN / move mirroring (ported 1:1 from tensor.ts) ─────────────────────────


def mirror_square(square: str) -> str:
    file = square[0]
    rank = str(9 - int(square[1]))
    return file + rank


def mirror_move(move_uci: str) -> str:
    is_promotion = len(move_uci) > 4
    start = move_uci[0:2]
    end = move_uci[2:4]
    promo = move_uci[4:] if is_promotion else ""
    return mirror_square(start) + mirror_square(end) + promo


def _swap_colors_in_rank(rank: str) -> str:
    out = []
    for ch in rank:
        if ch.isalpha():
            out.append(ch.lower() if ch.isupper() else ch.upper())
        else:
            out.append(ch)
    return "".join(out)


def _swap_castling_rights(castling: str) -> str:
    if castling == "-":
        return "-"
    rights = set(castling)
    swapped = set()
    if "K" in rights:
        swapped.add("k")
    if "Q" in rights:
        swapped.add("q")
    if "k" in rights:
        swapped.add("K")
    if "q" in rights:
        swapped.add("Q")
    out = ""
    for c in ("K", "Q", "k", "q"):
        if c in swapped:
            out += c
    return out if out else "-"


def mirror_fen(fen: str) -> str:
    position, active, castling, en_passant, halfmove, fullmove = fen.split(" ")
    ranks = position.split("/")
    mirrored_ranks = [_swap_colors_in_rank(r) for r in reversed(ranks)]
    mirrored_position = "/".join(mirrored_ranks)
    mirrored_active = "b" if active == "w" else "w"
    mirrored_castling = _swap_castling_rights(castling)
    mirrored_ep = mirror_square(en_passant) if en_passant != "-" else "-"
    return f"{mirrored_position} {mirrored_active} {mirrored_castling} {mirrored_ep} {halfmove} {fullmove}"


# ── Board tokenization (ported 1:1 from tensor.ts) ───────────────────────────

_PIECE_TYPES = ["P", "N", "B", "R", "Q", "K", "p", "n", "b", "r", "q", "k"]


def board_to_maia3_tokens(fen: str) -> np.ndarray:
    piece_placement = fen.split(" ")[0]
    tensor = np.zeros(64 * 12, dtype=np.float32)
    rows = piece_placement.split("/")
    for rank in range(8):
        row = 7 - rank
        file = 0
        for ch in rows[rank]:
            if ch.isdigit():
                file += int(ch)
            else:
                piece_idx = _PIECE_TYPES.index(ch) if ch in _PIECE_TYPES else -1
                if piece_idx >= 0:
                    square = row * 8 + file
                    tensor[square * 12 + piece_idx] = 1.0
                file += 1
    return tensor


def preprocess_maia3(fen: str):
    """Returns (board_tokens[64*12], legal_mask[len(ALL_MOVES)])."""
    if chess is None:
        raise RuntimeError("python-chess is required for Maia inference")

    stm = fen.split(" ")[1]
    board = chess.Board(fen)
    if stm == "b":
        board = chess.Board(mirror_fen(board.fen()))
    elif stm != "w":
        raise ValueError(f"Invalid FEN: {fen}")

    board_tokens = board_to_maia3_tokens(board.fen())

    legal_moves = np.zeros(len(ALL_MOVES), dtype=np.float32)
    for move in board.legal_moves:
        idx = ALL_MOVES.get(move.uci())
        if idx is not None:
            legal_moves[idx] = 1.0

    return board_tokens, legal_moves


# ── Output post-processing (ported 1:1 from maia.ts processOutputsMaia3) ──────


def process_outputs(fen: str, logits_move: np.ndarray, logits_value: np.ndarray, legal_moves: np.ndarray):
    wdl = logits_value
    max_wdl = max(wdl[0], wdl[1], wdl[2])
    exp_l = math.exp(wdl[0] - max_wdl)
    exp_d = math.exp(wdl[1] - max_wdl)
    exp_w = math.exp(wdl[2] - max_wdl)
    sum_exp = exp_l + exp_d + exp_w
    win_prob = (exp_w + 0.5 * exp_d) / sum_exp

    black_flag = fen.split(" ")[1] == "b"
    if black_flag:
        win_prob = 1 - win_prob
    win_prob = round(win_prob * 10000) / 10000

    legal_indices = [i for i, v in enumerate(legal_moves) if v > 0]

    legal_moves_mirrored = []
    for move_index in legal_indices:
        move = ALL_MOVES_REVERSED[move_index]
        if black_flag:
            move = mirror_move(move)
        legal_moves_mirrored.append(move)

    legal_logits = [logits_move[i] for i in legal_indices]
    max_logit = max(legal_logits)
    exp_logits = [math.exp(l - max_logit) for l in legal_logits]
    sum_exp_moves = sum(exp_logits)
    probs = [e / sum_exp_moves for e in exp_logits]

    move_probs = {}
    for i in range(len(legal_indices)):
        move_probs[legal_moves_mirrored[i]] = probs[i]

    sorted_moves = sorted(move_probs.keys(), key=lambda k: move_probs[k], reverse=True)
    sorted_move_probs = {k: move_probs[k] for k in sorted_moves}

    return sorted_move_probs, win_prob


# ── Inference session (module-level singleton) ───────────────────────────────

_session = None
_session_lock = threading.Lock()


def get_session():
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                import onnxruntime as ort  # imported lazily so app boots without it

                opts = ort.SessionOptions()
                opts.intra_op_num_threads = int(
                    os.environ.get("MAIA_ORT_THREADS", "2")
                )
                _session = ort.InferenceSession(
                    MODEL_PATH, sess_options=opts, providers=["CPUExecutionProvider"]
                )
    return _session


def evaluate(fen: str, elo_self: float, elo_oppo: float):
    """Runs the model and returns (policy: dict[str,float], value: float)."""
    board_tokens, legal_moves = preprocess_maia3(fen)
    session = get_session()

    feeds = {
        "tokens": board_tokens.reshape(1, 64, 12).astype(np.float32),
        "elo_self": np.array([elo_self], dtype=np.float32),
        "elo_oppo": np.array([elo_oppo], dtype=np.float32),
    }
    logits_move, logits_value = session.run(
        ["logits_move", "logits_value"], feeds
    )
    return process_outputs(fen, logits_move[0], logits_value[0], legal_moves)


def select_move(policy: dict, temperature: float = 1.0, rng: random.Random = None) -> str:
    """Temperature-weighted sampling — mirrors selectMove() in play/page.tsx."""
    if rng is None:
        rng = random
    moves = list(policy.keys())
    if not moves:
        raise ValueError("No legal moves in policy")
    probs = [policy[m] for m in moves]
    scaled = [p ** (1.0 / temperature) for p in probs]
    total = sum(scaled)
    normalized = [p / total for p in scaled]
    r = rng.random()
    for i, m in enumerate(moves):
        r -= normalized[i]
        if r <= 0:
            return m
    return moves[-1]
