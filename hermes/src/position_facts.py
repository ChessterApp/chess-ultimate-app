"""Plain, verified facts about a position for the coach's engine line.

The engine line gave the model moves and numbers only, and the model made up
the "why" itself — on production (2026-09-29) the voice coach said the queen
e7 attacked e4 (its own pawn e5 blocks it), that Nxb5 attacked the knight f6
(a knight on b5 does not reach f6) and missed the point of the move, the
threat Nxc7+ forking king and rook. These facts come from the board and the
engine, so the coach explains from them instead of inventing:

  * what hangs (attacked, not defended) and what a cheaper piece attacks;
  * what is attacked but defended, with the attackers and defenders by name;
  * what is defended but still lost to the exchange on its square (two attackers
    against one defender, a defender that is itself hanging);
  * pieces pinned to their king;
  * what the best move threatens — the engine's best move for the same side
    if the opponent passed;
  * what the opponent threatens now — the same with the side to move passing.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

import chess

# Engine time for each threat search: the best reply of a side that moves twice.
THREAT_MOVETIME_MS = int(os.environ.get("COACH_THREAT_MOVETIME_MS", "300"))
# A threat is worth mentioning when it wins at least this much (pawns), mates,
# or wins material outright.
THREAT_MIN_GAIN = 1.0
MAX_ITEMS_PER_KIND = 4

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
MATE = 10000.0


def _color(color: chess.Color) -> str:
    return "White" if color == chess.WHITE else "Black"


def _piece(board: chess.Board, sq: chess.Square) -> str:
    """'the black knight f6'."""
    p = board.piece_at(sq)
    if p is None:
        return chess.square_name(sq)
    return f"the {_color(p.color).lower()} {chess.piece_name(p.piece_type)} {chess.square_name(sq)}"


def _pieces(board: chess.Board, squares) -> str:
    names = [_piece(board, s) for s in sorted(squares, key=lambda s: VALUES[board.piece_type_at(s)])]
    return ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1] if names else ""


def exchange_gain(board: chess.Board, sq: chess.Square) -> Optional[int]:
    """What the opponent of the piece on *sq* wins by starting the exchange there (0: nothing — the piece is
    safe), in pawns. Played out with legal captures, the cheapest capturer first, so pins, x-rays and a king
    that may not take into a defended square all count. None when it cannot be judged (the owner is in check
    and not to move: its opponent could not be given the move)."""
    piece = board.piece_at(sq)
    if piece is None or piece.piece_type == chess.KING:
        return None
    attacker = not piece.color
    b = board.copy(stack=False)
    if b.turn != attacker:
        if b.is_check():
            return None
        b.turn = attacker
        b.ep_square = None
    gains = []
    value = VALUES[piece.piece_type]
    while len(gains) < 32:
        caps = [m for m in b.legal_moves if m.to_square == sq and m.promotion in (None, chess.QUEEN)]
        if not caps:
            break
        move = min(caps, key=lambda m: VALUES[b.piece_type_at(m.from_square)])
        gains.append(value)
        value = VALUES[move.promotion] if move.promotion else VALUES[b.piece_type_at(move.from_square)]
        b.push(move)
    score = 0
    for gain in reversed(gains):  # each side stops when going on loses
        score = max(0, gain - score)
    return score


def exposed_pieces(board: chess.Board, color: Optional[chess.Color] = None) -> list[tuple]:
    """The pieces (not kings) that are attacked and not safe: (square, kind, attackers, defenders) with kind
    'hanging' (no defender), 'cheaper' (a cheaper piece attacks it) or 'outnumbered' (defended, but the
    exchange on its square still wins material — «под ударом только слон c4» with the d5 pawn hit twice and
    held once, by that very bishop: prod 29.10). The answer check reads «больше ничего не висит» against
    this same list (src/answer_check_facts.py)."""
    out = []
    for sq, piece in board.piece_map().items():
        if piece.piece_type == chess.KING or (color is not None and piece.color != color):
            continue
        attackers = board.attackers(not piece.color, sq)
        if not attackers:
            continue
        defenders = board.attackers(piece.color, sq)
        if not defenders:
            out.append((sq, "hanging", attackers, defenders))
        elif min(VALUES[board.piece_type_at(a)] for a in attackers) < VALUES[piece.piece_type]:
            out.append((sq, "cheaper", attackers, defenders))
        elif (exchange_gain(board, sq) or 0) > 0:
            out.append((sq, "outnumbered", attackers, defenders))
    return out


def static_facts(board: chess.Board) -> list[str]:
    """Hanging, attacked and pinned pieces of both sides, as sentences."""
    hanging, outnumbered, cheaper, defended, pinned = [], [], [], [], []
    exposed = {sq: kind for sq, kind, _, _ in exposed_pieces(board)}
    for sq, piece in board.piece_map().items():
        if piece.piece_type == chess.KING:
            continue
        if board.is_pinned(piece.color, sq):
            pinned.append(f"{_piece(board, sq)} is pinned to its king")
        attackers = board.attackers(not piece.color, sq)
        if not attackers:
            continue
        defenders = board.attackers(piece.color, sq)
        who = _pieces(board, attackers)
        # A defender that is itself attacked and not safe holds nothing for long: the d5 pawn «defended by the
        # bishop c4» while the knight a5 hit that bishop read as safe, and the answer left d5 out (prod 29.10).
        weak = [d for d in defenders if d in exposed]
        weak_note = (f" ({_pieces(board, weak)} {'is' if len(weak) == 1 else 'are'} itself attacked and not safe)"
                     if weak else "")
        if not defenders:
            hanging.append(f"{_piece(board, sq)} is attacked by {who} and not defended")
        elif exposed.get(sq) == "cheaper":
            cheaper.append(f"{_piece(board, sq)} is attacked by a cheaper piece: {who}")
        elif exposed.get(sq) == "outnumbered":
            outnumbered.append(f"{_piece(board, sq)} is attacked by {who} and defended only by "
                               f"{_pieces(board, defenders)}{weak_note}: it is NOT safe, the exchange on "
                               f"{chess.square_name(sq)} wins material for {_color(not piece.color)}")
        else:
            defended.append(f"{_piece(board, sq)} is attacked by {who} and defended by {_pieces(board, defenders)}"
                            + weak_note)
    facts = []
    for group in (hanging, outnumbered, cheaper, pinned, defended):
        facts.extend(group[:MAX_ITEMS_PER_KIND])
    facts.extend(fork_facts(board))
    return facts


def fork_facts(board: chess.Board, limit: int = 2) -> list[str]:
    """Forks the side to move has NOW: one move after which the moved piece attacks two or more enemy
    pieces (the king or a piece worth a knight or more) from a square where it is not simply lost —
    «Есть ли здесь вилка?» → «нет» with Nc7+ on the board (prod, 23.10). With check first."""
    if not board.is_valid():
        return []
    mover = board.turn
    found = []
    for move in board.legal_moves:
        if move.promotion:
            continue
        after = board.copy(stack=False)
        after.push(move)
        to = move.to_square
        targets = [s for s in after.attacks(to)
                   if (p := after.piece_at(s)) is not None and p.color != mover
                   and (p.piece_type == chess.KING or VALUES[p.piece_type] >= 3)]
        if len(targets) < 2:
            continue
        moved = VALUES[board.piece_type_at(move.from_square)]
        attackers = after.attackers(not mover, to)
        if attackers:
            cheapest = min(VALUES[after.piece_type_at(a)] for a in attackers)
            defended = bool(after.attackers(mover, to))
            if cheapest < moved or not defended:
                continue  # the forking piece is just taken
        found.append((0 if after.is_check() else 1, -len(targets), board.san(move), targets, after))
    found.sort(key=lambda x: (x[0], x[1], x[2]))
    return [f"a fork is available now: {san} attacks {_pieces(after, targets)}" + (" (with check)" if check == 0 else "")
            for check, _, san, targets, after in found[:limit]]


def _score(line: dict) -> float:
    """A line's score in pawns for the side to move; mates as ±MATE."""
    if line.get("mate_in") is not None:
        return MATE if line["mate_in"] > 0 else -MATE
    return float(line.get("score") or 0.0)


def describe_move(board: chess.Board, move: chess.Move) -> str:
    """'Nxc7+ — a fork of the black king e8 and the black rook a8', 'Qxf7# — mate'."""
    san = board.san(move)
    after = board.copy(stack=False)
    after.push(move)
    if after.is_checkmate():
        return f"{san} — mate"
    bits = []
    captured = board.piece_at(move.to_square)
    if board.is_en_passant(move):
        bits.append("winning a pawn")
    elif captured is not None:
        bits.append(f"taking {_piece(board, move.to_square)}")
    mover = board.turn
    targets = [
        s for s in after.attacks(move.to_square)
        if (p := after.piece_at(s)) is not None and p.color != mover
        and (p.piece_type == chess.KING or VALUES[p.piece_type] >= 3)
    ]
    moved = VALUES[board.piece_type_at(move.from_square)]
    if len(targets) >= 2:
        bits.append(f"a fork of {_pieces(after, targets)}")
    elif after.is_check():
        bits.append("with check")
    elif targets and (VALUES[after.piece_type_at(targets[0])] > moved
                      or not after.is_attacked_by(not mover, targets[0])):
        bits.append(f"attacking {_piece(after, targets[0])}")
    return f"{san} — {', '.join(bits)}" if bits else san


def explain_line(board: chess.Board, pv: list, plies: int = 7) -> Optional[str]:
    """The engine's best line with what each move does, verified on the board (2026-10-08).

    Lesson answers named the right move and made up why (24 of 40 checked on 07.10): «король обязан
    отойти» where the only reply was gxh6, «мат даёт ладья» where the bishop mates, a discovered check
    told as a plain one. 'Rxh6+ (takes the pawn h6, check); gxh6 (the only legal move: takes the rook
    h6); dxc5+ (takes the pawn c5; discovered check by the queen c3); Ne5 (blocks the check); Qxe5#
    (takes the knight e5, mate)'. None for a line of fewer than two moves.
    """
    b = board.copy(stack=False)
    out = []
    for uci in pv[:plies]:
        try:
            move = chess.Move.from_uci(uci) if isinstance(uci, str) else uci
        except ValueError:
            break
        if move not in b.legal_moves:
            break
        san = b.san(move)
        bits = []
        replies = b.legal_moves.count()
        in_check = b.is_check()
        if replies == 1:
            bits.append("the only legal move")
        captured = b.piece_at(move.to_square)
        if b.is_en_passant(move):
            bits.append("takes the pawn en passant")
        elif captured is not None:
            bits.append(f"takes the {chess.piece_name(captured.piece_type)} {chess.square_name(move.to_square)}")
        if in_check and b.piece_type_at(move.from_square) != chess.KING and captured is None and not b.is_en_passant(move):
            bits.append("blocks the check")
        after = b.copy(stack=False)
        after.push(move)
        if after.is_check():
            checkers = list(after.checkers())
            direct = [c for c in checkers if c == move.to_square]
            others = [c for c in checkers if c != move.to_square]
            kind = "mate" if after.is_checkmate() else "check"
            if others and direct:
                bits.append(f"double {kind}")
            elif others:
                bits.append(f"discovered {kind} by the {chess.piece_name(after.piece_type_at(others[0]))} "
                            f"{chess.square_name(others[0])}")
            else:
                bits.append(kind)
        elif after.is_stalemate():
            bits.append("stalemate")
        if move.promotion:
            bits.append(f"promotes to a {chess.piece_name(move.promotion)}")
        out.append(f"{san} ({', '.join(bits)})" if bits else san)
        b = after
        if b.is_game_over():
            break
    return "; ".join(out) if len(out) >= 2 or (out and b.is_checkmate()) else None


Analyse = Callable[[str], Optional[dict]]


def _threat(board: chess.Board, base: float, analyse: Analyse) -> Optional[str]:
    """What the side NOT to move in *board* would play if the side to move passed, when it matters.

    *base* is the current score of *board* for its side to move, in pawns, so the
    threatening side stands at -base now; the threat counts when it gains at least
    THREAT_MIN_GAIN over that, mates, or takes an undefended piece.
    """
    if board.is_check():
        return None
    null = board.copy(stack=False)
    null.push(chess.Move.null())
    if null.is_check() or not null.is_valid():
        return None
    result = analyse(null.fen())
    lines = (result or {}).get("lines") or []
    if not lines or not lines[0].get("pv"):
        return None
    try:
        move = chess.Move.from_uci(lines[0]["pv"].split()[0])
    except ValueError:
        return None
    if move not in null.legal_moves:
        return None
    top = lines[0]
    mate_in = top.get("mate_in")
    if mate_in is not None:
        # Only a mate for the threatening side is a threat; being mated is not.
        if mate_in <= 0:
            return None
        described = describe_move(null, move)
        return described if mate_in == 1 else f"{described}, threatening mate in {mate_in}"
    wins_material = null.piece_at(move.to_square) is not None and not null.is_attacked_by(
        not null.turn, move.to_square)
    # A mate score on the board already (±MATE) makes the pawn gain meaningless.
    gain = _score(top) - (-base) if abs(base) < MATE else 0.0
    if gain < THREAT_MIN_GAIN and not wins_material:
        return None
    described = describe_move(null, move)
    # A threat takes, checks or attacks something; a plain move is not one (the
    # engine's "best move if the opponent passed" was often just saving a piece:
    # "White threatens Be2").
    return described if " — " in described else None


def _forced_replies(board: chess.Board, best: chess.Move, after: chess.Board) -> Optional[str]:
    """«after Rxh6+, Black has only one legal move: gxh6 — it must take the rook»: the reply the lesson
    answers missed (production 07.10: «король обязан отойти на h8» where the only move is gxh6)."""
    if after.is_game_over():
        return None
    replies = list(after.legal_moves)
    if len(replies) > 2:
        return None
    other = _color(after.turn)
    names = " or ".join(after.san(r) for r in replies)
    count = "only one legal move" if len(replies) == 1 else "only two legal moves"
    text = f"after {board.san(best)}, {other} has {count}: {names}"
    moved = board.piece_at(best.from_square)
    if len(replies) == 1 and replies[0].to_square == best.to_square and moved is not None:
        text += f" — it must take the {chess.piece_name(moved.piece_type)} on {chess.square_name(best.to_square)}"
    return text


def dynamic_facts(board: chess.Board, best_uci: Optional[str], best_score: float, analyse: Analyse) -> list[str]:
    """The threat of the best move and the opponent's threat now, as sentences.

    *best_score* is the best line's score for the side to move, in pawns.
    """
    facts = []
    side = _color(board.turn)
    other = _color(not board.turn)
    if best_uci:
        try:
            best = chess.Move.from_uci(best_uci)
        except ValueError:
            best = None
        if best is not None and best in board.legal_moves:
            after = board.copy(stack=False)
            after.push(best)
            best_san = board.san(best)
            if after.is_checkmate():
                facts.append(f"{best_san} is mate")
            elif after.is_check():
                facts.append(f"{describe_move(board, best)} (the best move gives check)")
            else:
                threat = _threat(after, -best_score, analyse)
                if threat:
                    facts.append(f"after {best_san}, {side} threatens {threat}")
            forced = _forced_replies(board, best, after)
            if forced:
                facts.append(forced)
    now = _threat(board, best_score, analyse)
    if now:
        facts.append(f"{other} threatens {now} if {side} ignores it")
    if board.is_check():
        facts.insert(0, f"{side} is in check")
    return facts
