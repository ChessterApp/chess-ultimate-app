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

def pawn_held_back(board: chess.Board, holder: chess.Square, pawn: chess.Square) -> bool:
    """The piece on *holder* holds the pawn on *pawn* back: it stands on, or attacks, the square the pawn advances to
    («её держит пешка e6», «пешка c6 держит пешку d4» — review-fp 03.11). False when there is no pawn there."""
    p = board.piece_at(pawn)
    if p is None or p.piece_type != chess.PAWN or board.piece_at(holder) is None:
        return False
    ahead = pawn + (8 if p.color == chess.WHITE else -8)
    return 0 <= ahead < 64 and (holder == ahead or ahead in board.attacks(holder))


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


def castling_facts(board: chess.Board, explicit: bool = False) -> list[str]:
    """Castling of the side to move, when it is a real question.

    A wing whose only obstacle is its own pieces in between is obvious and left
    out; a legal castling, one forbidden by an attacked square or by check, and
    a right lost while king and rook stand at home are said.

    *explicit* (the voice and text coach's facts, voice 02.11) names the king's squares that decide the wing and
    closes the door on attacked squares next to them: the note said «f1 is attacked by the bishop d3» for O-O and,
    apart, «the pawn f2 is attacked by the bishop c5», and the voice coach said castling was impossible because of
    f2. Off, the text is as it was (the lesson tutor's facts stay untouched)."""
    color = board.turn
    rank = 0 if color == chess.WHITE else 7
    king_home = board.piece_at(chess.square(4, rank)) == chess.Piece(chess.KING, color)
    if not king_home:
        if explicit:
            # «могу ли я рокироваться?» with the king gone: the note said nothing, and the coach made up a reason
            # (review-facts 03.11)
            return [f"{_color(color)}: no castling any more — the king has left {chess.square_name(chess.square(4, rank))}"]
        return []
    st = castling_status(board, color)
    parts, blocked = [], []
    for wing, label, rook_file in (("O-O", "short castling (O-O)", 7), ("O-O-O", "long castling (O-O-O)", 0)):
        legal, why = st[wing]
        rook_home = board.piece_at(chess.square(rook_file, rank)) == chess.Piece(chess.ROOK, color)
        if explicit and rook_home:
            text, own_only = _explicit_castling(board, color, wing, label, legal, why)
            (blocked if own_only else parts).append(text)
            continue
        if legal:
            # «Поле b1 же бьёт ладья» — the rook's square, not the king's: it does not matter (prod, 2026-10-13).
            rook_path = [chess.square(f, rank) for f in ((1,) if wing == "O-O-O" else ())]
            hit = [s for s in rook_path if board.is_attacked_by(not color, s)]
            note = (f" ({', '.join(chess.square_name(s) for s in hit)} is attacked, but only the rook passes it — "
                    "that does not matter)") if hit else ""
            parts.append(f"{label} is legal now{note}")
        elif not rook_home:
            continue
        elif why.startswith("pieces stand between"):
            # Obvious alone; said exactly next to the other wing — the coach added «and b1 — the knight»
            # with b1 empty (prod, 2026-10-13).
            blocked.append(f"{label} is NOT possible now — {why}, and nothing else stands there")
        else:
            parts.append(f"{label} is NOT possible now — {why}" + _chased_still_attacks(board, why, color))
    if parts or (explicit and blocked):
        # explicit: a wing barred only by its own pieces is said even alone — with no castling line at all the coach
        # had nothing to answer «могу ли я рокироваться?» from (review-facts 03.11: 23 of 54 positions)
        parts += blocked
    out = [f"{_color(color)}: " + "; ".join(parts)] if parts else []
    if explicit:
        other = _other_side_castling(board)
        if other:
            out.append(other)
    return out


def _other_side_castling(board: chess.Board) -> str:
    """One short line on the castling of the side NOT to move (for its next move), when its king is at home with a right:
    the coach was asked about the opponent's castling and had no fact (review-facts 03.11)."""
    color = not board.turn
    rank = 0 if color == chess.WHITE else 7
    if board.piece_at(chess.square(4, rank)) != chess.Piece(chess.KING, color):
        return ""
    if not (board.has_kingside_castling_rights(color) or board.has_queenside_castling_rights(color)):
        return ""
    st = castling_status(board, color)
    bits = []
    for wing in ("O-O", "O-O-O"):
        has = board.has_kingside_castling_rights(color) if wing == "O-O" else board.has_queenside_castling_rights(color)
        if not has:
            continue
        legal, why = st[wing]
        if legal:
            bits.append(f"{wing} possible")
        elif why.startswith("pieces stand between"):
            continue  # obvious, and every opening position has it (size)
        elif " is attacked by " in why:
            bits.append(f"{wing} barred — {why.split(' — ')[0]}")
        else:
            bits.append(f"{wing} not possible — {why}")
    return f"{_color(color)} (on its next move): " + "; ".join(bits) if bits else ""


# The king's squares that decide each wing, and the squares next to them a coach mixes up with them: the rook's
# path and the pawns in front (voice 02.11: «рокировка невозможна — поле f2 под боем слона»; f2 is not on the way).
_KING_SQUARES = {"O-O": (4, 5, 6), "O-O-O": (4, 3, 2)}
_NEIGHBOUR_FILES = {"O-O": ((7,), (4, 5, 6, 7)), "O-O-O": ((0, 1), (1, 2, 3, 4))}


def _explicit_castling(board: chess.Board, color: chess.Color, wing: str, label: str, legal: bool,
                       why: str) -> tuple[str, bool]:
    """(text, own_only) for one wing's castling of the side to move, its deciding squares said (castling_facts,
    explicit). *own_only*: barred only by its own pieces in between — said only next to the other wing, as before."""
    rank = 0 if color == chess.WHITE else 7
    ahead = 1 if color == chess.WHITE else 6
    king_sqs = [chess.square(f, rank) for f in _KING_SQUARES[wing]]
    names = ", ".join(chess.square_name(s) for s in king_sqs)
    rook_files, pawn_files = _NEIGHBOUR_FILES[wing]
    near = [chess.square(f, rank) for f in rook_files] + [chess.square(f, ahead) for f in pawn_files]
    # The squares next to them that are attacked, by square only and scoped to castling: «an attack on the rook a1 does
    # not matter» read apart from its sentence as a safety verdict on a rook the same note calls undefended (review-facts
    # 03.11). A square whose piece is attacked and not safe is left out — that attack matters, just not for castling.
    try:
        from src.position_facts import exposed_pieces

        unsafe = {sq for sq, _kind, _a, _d in exposed_pieces(board, color)}
    except Exception:  # noqa: BLE001
        unsafe = set(near)
    hit = [s for s in near if board.is_attacked_by(not color, s) and s not in unsafe]
    door = ""
    if hit:
        door = (f"castling depends only on {names}; an attack on " + ", ".join(chess.square_name(s) for s in hit)
                + " does not stop it")
    if legal:
        return f"{label} is legal now" + (f" ({door})" if door else ""), False
    if why.startswith("pieces stand between"):
        # Not «and nothing else stands there» alone: with them gone the king may still be in check or land on an
        # attacked square (review-facts 03.11: g1 hit by Bc5 behind the knight g1).
        more = []
        if board.is_check():
            more.append("the king is in check now")
        for sq in king_sqs[1:]:
            attackers = board.attackers(not color, sq)
            if attackers:
                verb = "land on" if sq == king_sqs[-1] else "pass"
                more.append(f"the king would {verb} {chess.square_name(sq)}, which "
                            + " and ".join(_piece(board, a) for a in attackers) + " attacks")
        tail = ("; even with them gone it stays impossible: " + " and ".join(more)) if more else ", and nothing else stops it"
        return f"{label} is NOT possible now — {why}{tail}", True
    if why.startswith("the king is in check"):
        return f"{label} is NOT possible now — {why}", False
    if " is attacked by " in why:
        bits = []
        for sq in king_sqs[1:]:
            attackers = board.attackers(not color, sq)
            if attackers:
                verb = "land on" if sq == king_sqs[-1] else "pass"
                who = " and ".join(_piece(board, a) for a in attackers)
                bits.append(f"{verb} {chess.square_name(sq)}, which {who} attacks")
        if bits:
            return (f"{label} is NOT possible now — the king would " + " and ".join(bits)
                    + (f"; {door}" if door else "") + _chased_still_attacks(board, why, color, explicit=True)), False
    return f"{label} is NOT possible now — {why}", False


def _chased_still_attacks(board: chess.Board, why: str, color: chess.Color, explicit: bool = False) -> str:
    """For castling barred by an attacked square: where the attacker, once chased, still attacks it.

    «Сыграй b3 — слон уйдёт, и рокировка станет возможна» (prod, 2026-10-06 and 2026-10-13): after b3 the
    bishop c4 retreats to a6 or b5 and still hits f1."""
    import re as _re

    m = _re.match(r"([a-h][1-8]) is attacked by", why)
    if not m:
        return ""
    target = chess.parse_square(m.group(1))
    b = board.copy(stack=False)
    b.turn = not color
    b.ep_square = None
    keeps = []
    by_piece: dict = {}
    for attacker in board.attackers(not color, target):
        piece = board.piece_at(attacker)
        if piece is None or piece.piece_type in (chess.PAWN, chess.KING):
            continue
        for mv in b.pseudo_legal_moves:
            if mv.from_square != attacker or b.piece_at(mv.to_square) is not None:
                continue
            after = b.copy(stack=False)
            after.push(mv)
            if mv.to_square in after.attackers(not color, target) or target in after.attacks(mv.to_square):
                keeps.append(piece.symbol().upper() + chess.square_name(mv.to_square))
                by_piece.setdefault(attacker, []).append(chess.square_name(mv.to_square))
    if not explicit:
        if not keeps:
            return ""
        return (f"; chasing the attacker away does not by itself allow it — it can step to {', '.join(keeps[:5])} "
                f"and still attack {chess.square_name(target)}")
    # explicit: the opponent's retreats told as the opponent's, not in bare SAN («it can step to Be2» read as White's
    # Be2), and the side to move's own moves that do make castling legal next move — a block (review-facts 03.11)
    out = ""
    for attacker, squares in list(by_piece.items())[:1]:
        squares = squares[:5]
        listed = ", ".join(squares[:-1]) + " or " + squares[-1] if len(squares) > 1 else squares[0]
        out += (f"; chasing the attacker away does not by itself allow it — {_piece(board, attacker)} could retreat to "
                f"{listed} and still attack {chess.square_name(target)}")
    opens = []
    if board.turn == color and not board.is_check():
        rank = 0 if color == chess.WHITE else 7
        for mv in board.legal_moves:
            if board.is_castling(mv) or board.piece_type_at(mv.from_square) == chess.KING:
                continue
            after = board.copy(stack=False)
            after.push(mv)
            if after.is_check():
                continue
            after.push(chess.Move.null())
            for wing, to_file in (("O-O", 6), ("O-O-O", 2)):
                castle = chess.Move(chess.square(4, rank), chess.square(to_file, rank))
                path = chess.SquareSet.between(castle.from_square, castle.to_square) | chess.SquareSet([castle.to_square])
                if target in path and not board.is_legal(castle) and after.is_legal(castle):
                    try:
                        from src.position_facts import exposed_pieces

                        lost = mv.to_square in {sq for sq, *_ in exposed_pieces(after, color)}
                    except Exception:  # noqa: BLE001
                        lost = True
                    if not lost:  # not a block that hangs the blocker (02.11: Qe2 is taken by Bxe2)
                        opens.append((board.san(mv), wing))
            if len(opens) >= 3:
                break
    if opens:
        out += "; " + ", ".join(f"after {san} {wing} becomes legal (if the opponent does nothing about it)" for san, wing in opens[:3])
    return out


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


# ── The moves of the side to move ───────────────────────────────────────────

def _san_list(board: chess.Board, moves: list, marks: bool = True) -> list[str]:
    """*moves* in SAN, in board order; a promotion once, as «c8=Q (or =R, =B, =N)» — «the only pawn moves: c8=Q+» read
    as «only a queen» (review-facts 03.11). *marks* False: no «+»/«#» (the game note names no mate: review-facts 03.11)."""
    keep = [m for m in moves if m.promotion in (None, chess.QUEEN)]
    keep.sort(key=lambda m: (chess.square_file(m.from_square), m.from_square, chess.square_file(m.to_square),
                             m.to_square))
    out = []
    for m in keep:
        san = board.san(m)
        if not marks:
            san = san.rstrip("+#")
        if m.promotion == chess.QUEEN:
            san += " (or =R, =B, =N)"
        out.append(san)
    return out


def placement_facts(board: chess.Board) -> list[str]:
    """Where every piece stands, both sides: «Pieces — White: Ke1, Qd1, Ra1, …; pawns a2 b2 …. Black: …». The note
    listed the queen's and the pawns' moves only, so «конь на d4», «слоном на e3», «ладья на f1» had nothing to be
    checked against but the raw FEN the model misread on 02.11 (review-facts 03.11)."""
    order = (chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
    sides = []
    for color in (chess.WHITE, chess.BLACK):
        pieces = [chess.piece_symbol(t).upper() + chess.square_name(sq)
                  for t in order for sq in sorted(board.pieces(t, color))]
        pawns = " ".join(chess.square_name(sq) for sq in sorted(board.pieces(chess.PAWN, color),
                                                                key=lambda q: (chess.square_file(q), q)))
        sides.append(f"{_color(color)}: " + ", ".join(pieces) + (f"; pawns {pawns}" if pawns else "; no pawns"))
    return ["Pieces on the board — " + ". ".join(sides)]


def move_facts(board: chess.Board, marks: bool = True, placement: bool = False) -> list[str]:
    """The pawn moves and the queen's moves the side to move has now, and the pawns that cannot move with why.

    Voice 02.11 (prod, White's move 9): «пойди ферзём на d1» with the queen already on d1, then twice «пешкой с d2
    на d3» with Black's bishop on d3. The coach proposes pawn pushes and queen moves from its head; this says which
    ones are there (python-chess, the legal moves) and where the queen stands. Nothing when the game is over."""
    if board.is_game_over():
        return []
    color = board.turn
    legal = list(board.legal_moves)
    bits = []
    for q in sorted(board.pieces(chess.QUEEN, color)):
        sans = _san_list(board, [m for m in legal if m.from_square == q], marks)
        bits.append(f"the queen {chess.square_name(q)} can play only " + ", ".join(sans) if sans else
                    f"the queen {chess.square_name(q)} has no legal move now")
    pawns = sorted(board.pieces(chess.PAWN, color))
    if pawns:
        sans = _san_list(board, [m for m in legal if m.from_square in pawns], marks)
        bits.append("the only pawn moves: " + (", ".join(sans) if sans else "none"))
        if not board.is_check():
            stuck = []
            step = 8 if color == chess.WHITE else -8
            for sq in sorted(pawns, key=lambda q: (chess.square_file(q), q)):
                if any(m.from_square == sq for m in legal):
                    continue
                ahead = sq + step
                occupant = board.piece_at(ahead) if 0 <= ahead < 64 else None
                if occupant is not None and placement and occupant.color == color:
                    continue  # its own piece in front: the placement line says it (size, review-facts 03.11)
                if occupant is not None:
                    stuck.append(f"{chess.square_name(sq)} ({chess.square_name(ahead)} is taken by "
                                 f"the {_color(occupant.color).lower()} {chess.piece_name(occupant.piece_type)})")
                elif board.is_pinned(color, sq):
                    stuck.append(f"{chess.square_name(sq)} (pinned)")
            if stuck:
                # with the placement line, a pawn behind its own piece is left to it: the list is then the pawns the
                # opponent stops — said so, not as every pawn that cannot move (review-facts 03.11)
                bits.append(("pawns stopped by the opponent: " if placement else "pawns that cannot move: ") + ", ".join(stuck))
    if not bits:
        return []
    return [f"{_color(color)} to move — " + "; ".join(bits)]


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
               "best_san": best.get("san"), "best_category": best.get("category"),
               # Every move that keeps the result, not the best one alone: «1...Kd6 — и пешка проходит» with
               # Kd6 as good a draw as Kd5 (stand, 2026-10-13).
               "keeping": [m.get("san") for m in moves if m.get("category") == best.get("category") and m.get("san")]}
    with _tb_lock:
        if len(_tb_cache) > 2000:
            _tb_cache.clear()
        _tb_cache[key] = out
    return out


def tablebase_cached(board: chess.Board) -> Optional[tuple]:
    """(True, answer) when the tablebase has been asked about *board* this process (the answer may be None:
    not in the tablebase), None when it has not — never a network call: a synchronous check reads only what the
    turn has already fetched (src/endgame_claims.py, 2026-10-30)."""
    key = board.epd()
    with _tb_lock:
        if key in _tb_cache:
            return True, _tb_cache[key]
    return None


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
    keeping = [m for m in (tb.get("keeping") or []) if m]
    total = board.legal_moves.count()
    if result == "draw":
        text += " — whatever the engine's evaluation shows, this is not a win"
        if keeping and len(keeping) < total:
            text += (f"; the moves that hold the draw for {_color(board.turn)}: {', '.join(keeping[:8])} "
                     f"— every other move loses")
    elif tb.get("best_san"):
        mover_wins = result.startswith(_color(board.turn))
        text += f"; the winning move here is {tb['best_san']}" if mover_wins else f"; the best defence is {tb['best_san']}"
        if mover_wins and len(keeping) > 1:
            text += f" (moves that also win: {', '.join(k for k in keeping[:8] if k != tb['best_san'])})"
    return [text]


def rule_facts(board: chess.Board, with_tablebase: bool = True, explicit: bool = False, game: bool = False) -> list[str]:
    """Every rule fact above for *board*, in the order a coach needs them.

    *explicit* (the coach's voice and text facts; voice 02.11): castling with the squares that decide it, and the
    pawn and queen moves of the side to move (move_facts). Off — the lesson tutor, the knowledge topics — the facts
    are as they were."""
    facts = game_state_facts(board)
    if facts:
        return facts
    if explicit:
        try:
            from src import config

            explicit = bool(getattr(config, "COACH_EXPLICIT_RULES", True))
        except Exception:  # noqa: BLE001
            pass
    facts += castling_facts(board, explicit=explicit)
    facts += en_passant_facts(board)
    if explicit:
        # *game*: the voice game note — no «+»/«#» on the moves (it names no best move, and a marked mate is one) and no
        # pawn structure (review-facts 03.11: 191 of its 438 chars, in 61 of 78 positions)
        facts += placement_facts(board)
        facts += move_facts(board, marks=not game, placement=True)
    tb = tablebase(board) if with_tablebase else None
    facts += tablebase_facts(board, tb)
    facts += known_endgame_facts(board)
    if not (explicit and game):
        facts += structure_facts(board)
    return facts
