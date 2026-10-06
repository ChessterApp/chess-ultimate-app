"""Rules of the position the engine line does not say, decided by python-chess.

Production check of 2026-10-06 (eval/bench/2026-10-06-blind-spots): the coach
told the student "Yes — you can castle here, it's perfectly legal" with f1
attacked by the bishop on c4, answered «нет, не можешь» to an en passant
capture and then «есть exd6!», called the d-file "half-open for White" with a
white pawn on d5, and called a wrong-bishop ending a win because Stockfish
showed +1.13 (a tablebase draw). Each of these is a fact of the board:

  * castling — available or not, and why (rights lost, pieces in between,
    king in check, an attacked square on the king's way);
  * en passant — the capture available right now;
  * pawn structure — passed pawns, open and half-open files;
  * the game state — checkmate, stalemate, insufficient material;
  * known endgames — Lucena, Philidor, the wrong bishop, two knights — with
    their verdict, method and the knowledge-base topic;
  * the endgame tablebase (Lichess, Syzygy ≤ 7 pieces) — the exact result.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

import chess

logger = logging.getLogger(__name__)

WINGS = {"O-O": chess.G1, "O-O-O": chess.C1}


def _color(color: chess.Color) -> str:
    return "White" if color == chess.WHITE else "Black"


def _piece(board: chess.Board, sq: chess.Square) -> str:
    p = board.piece_at(sq)
    if p is None:
        return chess.square_name(sq)
    return f"the {_color(p.color).lower()} {chess.piece_name(p.piece_type)} on {chess.square_name(sq)}"


# ── Castling ────────────────────────────────────────────────────────────────

def castling_status(board: chess.Board, color: Optional[chess.Color] = None) -> dict:
    """{'O-O': (legal, reason), 'O-O-O': (legal, reason)} for *color* (default:
    the side to move). The reason names what forbids it; '' when legal.

    For the side not to move the answer is "could it castle on its move" — the
    same rules, judged with that side to move.
    """
    color = board.turn if color is None else color
    b = board.copy(stack=False)
    if b.turn != color:
        b.turn = color
        b.ep_square = None
    rank = 0 if color == chess.WHITE else 7
    king_sq = chess.square(4, rank)
    out = {}
    for wing, rook_file, king_to_file, path_files in (
        ("O-O", 7, 6, (5, 6)), ("O-O-O", 0, 2, (3, 2)),
    ):
        rook_sq = chess.square(rook_file, rank)
        has_right = (b.has_kingside_castling_rights(color) if wing == "O-O"
                     else b.has_queenside_castling_rights(color))
        if not has_right:
            king = b.piece_at(king_sq)
            rook = b.piece_at(rook_sq)
            if king is None or king.piece_type != chess.KING or king.color != color:
                why = "the king is not on its starting square"
            elif rook is None or rook.piece_type != chess.ROOK or rook.color != color:
                why = f"there is no {_color(color).lower()} rook on {chess.square_name(rook_sq)}"
            else:
                why = ("the right to castle is lost — the king or this rook has already moved "
                       "(even though both stand on their squares now)")
            out[wing] = (False, why)
            continue
        between = [s for s in chess.SquareSet.between(king_sq, rook_sq) if b.piece_at(s) is not None]
        if between:
            out[wing] = (False, "pieces stand between the king and the rook: "
                         + ", ".join(_piece(b, s) for s in between))
            continue
        if b.is_check():
            out[wing] = (False, "the king is in check (castling out of check is not allowed)")
            continue
        attacked = None
        for f in path_files:
            sq = chess.square(f, rank)
            attackers = b.attackers(not color, sq)
            if attackers:
                attacked = (sq, attackers)
                break
        if attacked:
            sq, attackers = attacked
            lands = chess.square_file(sq) == king_to_file
            who = ", ".join(_piece(b, a) for a in attackers)
            out[wing] = (False, f"{chess.square_name(sq)} is attacked by {who} — the king may not "
                         + ("land on" if lands else "pass through") + " an attacked square")
            continue
        move = chess.Move(king_sq, chess.square(king_to_file, rank))
        legal = b.is_legal(move)
        out[wing] = (legal, "" if legal else "not legal here")
    return out


def castling_facts(board: chess.Board) -> list[str]:
    """Castling of the side to move, when it is a real question.

    A wing whose only obstacle is its own pieces in between is obvious and left
    out; a legal castling, one forbidden by an attacked square or by check, and
    a right lost while king and rook stand at home are said."""
    color = board.turn
    rank = 0 if color == chess.WHITE else 7
    king_home = board.piece_at(chess.square(4, rank)) == chess.Piece(chess.KING, color)
    if not king_home:
        return []
    st = castling_status(board, color)
    parts = []
    for wing, label, rook_file in (("O-O", "short castling (O-O)", 7), ("O-O-O", "long castling (O-O-O)", 0)):
        legal, why = st[wing]
        rook_home = board.piece_at(chess.square(rook_file, rank)) == chess.Piece(chess.ROOK, color)
        if legal:
            parts.append(f"{label} is legal now")
        elif why.startswith("pieces stand between") or not rook_home:
            continue
        else:
            parts.append(f"{label} is NOT possible now — {why}")
    return [f"{_color(color)}: " + "; ".join(parts)] if parts else []


# ── En passant ──────────────────────────────────────────────────────────────

def en_passant_moves(board: chess.Board) -> list[chess.Move]:
    return [m for m in board.legal_moves if board.is_en_passant(m)]


def en_passant_facts(board: chess.Board) -> list[str]:
    moves = en_passant_moves(board)
    if not moves:
        return []
    ep = board.ep_square
    victim = chess.square(chess.square_file(ep), chess.square_rank(ep) + (-1 if board.turn == chess.WHITE else 1))
    sans = ", ".join(board.san(m) for m in moves)
    return [f"en passant is available now: {sans} takes the pawn on {chess.square_name(victim)} that has just "
            f"moved two squares (the capturing pawn lands on {chess.square_name(ep)}); only on this move"]


# ── Pawn structure ──────────────────────────────────────────────────────────

def is_passed(board: chess.Board, sq: chess.Square) -> bool:
    p = board.piece_at(sq)
    if p is None or p.piece_type != chess.PAWN:
        return False
    f, r = chess.square_file(sq), chess.square_rank(sq)
    for s in board.pieces(chess.PAWN, not p.color):
        if abs(chess.square_file(s) - f) <= 1:
            rr = chess.square_rank(s)
            if (rr > r) if p.color == chess.WHITE else (rr < r):
                return False
    return True


def file_kind(board: chess.Board, file_index: int) -> str:
    """'open', 'half-open for White', 'half-open for Black' or 'closed'."""
    w = any(chess.square_file(s) == file_index for s in board.pieces(chess.PAWN, chess.WHITE))
    k = any(chess.square_file(s) == file_index for s in board.pieces(chess.PAWN, chess.BLACK))
    if not w and not k:
        return "open"
    if not w:
        return "half-open for White"
    if not k:
        return "half-open for Black"
    return "closed"


def structure(board: chess.Board) -> dict:
    passed = {c: sorted(chess.square_name(s) for s in board.pieces(chess.PAWN, c) if is_passed(board, s))
              for c in (chess.WHITE, chess.BLACK)}
    files = {"abcdefgh"[f]: file_kind(board, f) for f in range(8)}
    return {"passed": passed, "files": files}


def structure_facts(board: chess.Board) -> list[str]:
    """Passed pawns and open / half-open files — only when there are any."""
    st = structure(board)
    opened = [f for f, k in st["files"].items() if k == "open"]
    half_w = [f for f, k in st["files"].items() if k == "half-open for White"]
    half_b = [f for f, k in st["files"].items() if k == "half-open for Black"]
    has_passed = any(st["passed"].values())
    if not (has_passed or opened or half_w or half_b):
        return []
    passed = "; ".join(f"{_color(c)} {', '.join(st['passed'][c]) or 'none'}" for c in (chess.WHITE, chess.BLACK))
    bits = [f"passed pawns — {passed}", f"open files (no pawns) — {', '.join(opened) or 'none'}"]
    if half_w:
        bits.append(f"half-open for White (no white pawn, a black one) — {', '.join(half_w)}")
    if half_b:
        bits.append(f"half-open for Black (no black pawn, a white one) — {', '.join(half_b)}")
    return ["pawn structure: " + "; ".join(bits)]


# ── Game state ──────────────────────────────────────────────────────────────

def game_state_facts(board: chess.Board) -> list[str]:
    if board.is_checkmate():
        return [f"{_color(board.turn)} is checkmated — {_color(not board.turn)} has won"]
    if board.is_stalemate():
        return [f"{_color(board.turn)} is STALEMATED — no legal move and not in check: the game is a draw, not a mate"]
    if board.is_insufficient_material():
        return ["neither side has enough material to mate: the game is a draw"]
    return []


# ── Known endgames ──────────────────────────────────────────────────────────

def _material(board: chess.Board, color: chess.Color) -> dict:
    return {pt: len(board.pieces(pt, color)) for pt in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)}


def _only(board: chess.Board, color: chess.Color, **want) -> bool:
    names = {"p": chess.PAWN, "n": chess.KNIGHT, "b": chess.BISHOP, "r": chess.ROOK, "q": chess.QUEEN}
    m = _material(board, color)
    return all(m[names[k]] == want.get(k, 0) for k in names)


def known_endgame(board: chess.Board) -> Optional[dict]:
    """{'slug', 'name', 'verdict', 'method'} for a textbook ending, else None.

    Pattern tests only — the tablebase (when reachable) gives the exact result;
    this gives the name and the method a coach teaches.
    """
    for strong in (chess.WHITE, chess.BLACK):
        weak = not strong
        up = 1 if strong == chess.WHITE else -1
        sk, wk = board.king(strong), board.king(weak)
        if sk is None or wk is None:
            return None
        # Bishop + rook pawn whose promotion square the bishop does not control.
        if _only(board, strong, b=1, p=1) and _only(board, weak):
            pawn = next(iter(board.pieces(chess.PAWN, strong)))
            bishop = next(iter(board.pieces(chess.BISHOP, strong)))
            pf = chess.square_file(pawn)
            if pf in (0, 7):
                queen_sq = chess.square(pf, 7 if strong == chess.WHITE else 0)
                bishop_light = (chess.square_file(bishop) + chess.square_rank(bishop)) % 2 == 1
                corner_light = (chess.square_file(queen_sq) + chess.square_rank(queen_sq)) % 2 == 1
                if bishop_light != corner_light and chess.square_distance(wk, queen_sq) <= 1:
                    return {"slug": "wrong-bishop", "name": "wrong bishop with a rook pawn",
                            "verdict": "draw",
                            "method": (f"the bishop does not control the promotion square {chess.square_name(queen_sq)}, "
                                       "and the defending king in that corner cannot be driven out — a draw "
                                       "whatever the engine's number says")}
        # Two knights against a bare king.
        if _only(board, strong, n=2) and _only(board, weak):
            return {"slug": "basic-checkmates", "name": "two knights against a bare king", "verdict": "draw",
                    "method": "two knights cannot force mate; mate happens only if the defender walks into it"}
        # Rook and pawn against rook.
        if _only(board, strong, r=1, p=1) and _only(board, weak, r=1):
            pawn = next(iter(board.pieces(chess.PAWN, strong)))
            pf, pr = chess.square_file(pawn), chess.square_rank(pawn)
            rel = pr if strong == chess.WHITE else 7 - pr  # 1..6
            queen_sq = chess.square(pf, 7 if strong == chess.WHITE else 0)
            # Lucena: pawn on the 7th, own king on the promotion square, the
            # defending king cut off by at least one file.
            if rel == 6 and sk == queen_sq and abs(chess.square_file(wk) - pf) >= 2:
                return {"slug": "lucena-position", "name": "the Lucena position", "verdict": f"{_color(strong)} wins",
                        "method": ("building a bridge: the rook goes to the fourth rank from the king's side "
                                   "(after a check that pushes the defending king one more file away), the king "
                                   "steps out from in front of the pawn, and the rook blocks the checks")}
            # Philidor: pawn not yet on the 6th, defending king on the queening
            # file or next to it in front of the pawn.
            if rel <= 4 and abs(chess.square_file(wk) - pf) <= 1 and (
                    (chess.square_rank(wk) - pr) * up > 0):
                third = 5 if strong == chess.WHITE else 2  # the defender's third rank
                return {"slug": "philidor-position", "name": "the Philidor position", "verdict": "draw",
                        "method": (f"the defending rook holds its third rank (rank {third + 1}) so the attacking king "
                                   "cannot come forward; once the pawn steps onto that rank, the rook goes to the "
                                   "far end and checks from behind")}
    return None


def known_endgame_facts(board: chess.Board) -> list[str]:
    ke = known_endgame(board)
    if not ke:
        return []
    return [f"textbook ending — {ke['name']}: {ke['verdict']}; method: {ke['method']} "
            f"(knowledge-base topic get_topic('{ke['slug']}'))"]


# ── Endgame tablebase ───────────────────────────────────────────────────────

TABLEBASE_URL = os.environ.get("COACH_TABLEBASE_URL", "https://tablebase.lichess.ovh/standard")
TABLEBASE_TIMEOUT_S = float(os.environ.get("COACH_TABLEBASE_TIMEOUT_S", "1.5"))
_tb_cache: dict[str, Optional[dict]] = {}
_tb_lock = threading.Lock()
_tb_down_until = 0.0


def tablebase_enabled() -> bool:
    return os.environ.get("COACH_TABLEBASE", "1").strip().lower() not in ("0", "false", "no", "off")


def tablebase(board: chess.Board) -> Optional[dict]:
    """The Lichess tablebase's answer for ≤ 7 pieces: {'category', 'dtz', 'dtm',
    'best_san', 'best_category'} from the side to move, or None (too many
    pieces, castling rights, switched off, unreachable)."""
    global _tb_down_until
    if not tablebase_enabled() or len(board.piece_map()) > 7 or board.castling_rights:
        return None
    key = board.epd()
    with _tb_lock:
        if key in _tb_cache:
            return _tb_cache[key]
    if time.monotonic() < _tb_down_until:
        return None
    url = f"{TABLEBASE_URL}?fen={urllib.parse.quote(board.fen())}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "chesster-coach"}),
                                    timeout=TABLEBASE_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — the tablebase is a bonus; back off a minute
        logger.info("tablebase unavailable: %s", exc)
        _tb_down_until = time.monotonic() + 60
        return None
    cat = data.get("category")
    if cat not in ("win", "loss", "draw", "cursed-win", "blessed-loss"):
        out = None
    else:
        moves = data.get("moves") or []
        best = moves[0] if moves else {}
        out = {"category": cat, "dtz": data.get("dtz"), "dtm": data.get("dtm"),
               "best_san": best.get("san"), "best_category": best.get("category")}
    with _tb_lock:
        if len(_tb_cache) > 2000:
            _tb_cache.clear()
        _tb_cache[key] = out
    return out


def tablebase_white_result(board: chess.Board, tb: dict) -> str:
    """'White wins', 'Black wins' or 'draw' (cursed wins and blessed losses are draws by the 50-move rule)."""
    cat = tb["category"]
    if cat in ("draw", "cursed-win", "blessed-loss"):
        return "draw"
    mover_wins = cat == "win"
    return f"{_color(board.turn if mover_wins else not board.turn)} wins"


def tablebase_facts(board: chess.Board, tb: Optional[dict]) -> list[str]:
    if not tb:
        return []
    result = tablebase_white_result(board, tb)
    text = f"endgame tablebase (exact, perfect play): {result.upper()}"
    if result == "draw":
        text += " — whatever the engine's evaluation shows, this is not a win"
    elif tb.get("best_san"):
        text += f"; the winning move here is {tb['best_san']}" if result.startswith(_color(board.turn)) \
            else f"; the best defence is {tb['best_san']}"
    return [text]


def rule_facts(board: chess.Board, with_tablebase: bool = True) -> list[str]:
    """Every rule fact above for *board*, in the order a coach needs them."""
    facts = game_state_facts(board)
    if facts:
        return facts
    facts += castling_facts(board)
    facts += en_passant_facts(board)
    tb = tablebase(board) if with_tablebase else None
    facts += tablebase_facts(board, tb)
    facts += known_endgame_facts(board)
    facts += structure_facts(board)
    return facts
