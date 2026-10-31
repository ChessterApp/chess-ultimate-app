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
        caps = [m for m in b.generate_legal_moves(to_mask=chess.BB_SQUARES[sq]) if m.promotion in (None, chess.QUEEN)]
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


def static_facts(board: chess.Board, lines: Optional[list] = None) -> list[str]:
    """Hanging, attacked and pinned pieces of both sides, as sentences. *lines* (the engine's lines of the turn, raw
    analyze_* form) vet the fork facts; without them the forks are checked by exchange counts (fork_facts)."""
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
    facts.extend(fork_facts(board, lines=lines))
    return facts


# ── forks (plan 31.10 P8 C1) ────────────────────────────────────────────────────────────────────────────────────
# «a fork is available now: Qxd5+ attacks c6, d8 and e6» was the fact behind mate2-no (29.10): 8...Qxd5 takes the
# queen back and White is −6. Of 92 fork facts on the 318 corpus positions 77 were moves that lose ≥ 1.5 pawns
# against the best one. A fork is an outcome ("it wins something"), so it is told only with its proof:
#   * with the engine's lines of the turn: its move is the first move of one of them, within FORK_ENGINE_MARGIN of
#     the best line (0 ms: the lines exist already);
#   * without them (a live game, where the engine line is withheld; the board-facts fallback): every legal reply
#     is played, and the fork must still win at least FORK_MIN_GAIN by exchange count after the best capture back
#     on the forked squares — the forking piece taken back, a target moved away with a counter-threat, a check in
#     between all count. A mate is kept.
FORK_ENGINE_MARGIN = 1.0
FORK_MIN_GAIN = 2


def _vetting() -> bool:
    try:
        from src import config

        return bool(getattr(config, "COACH_TURN_FACTS", True))
    except Exception:  # noqa: BLE001
        return True


def _fork_targets(after: chess.Board, to: chess.Square, mover: chess.Color) -> list:
    return [s for s in after.attacks(to)
            if (p := after.piece_at(s)) is not None and p.color != mover
            and (p.piece_type == chess.KING or VALUES[p.piece_type] >= 3)]


def fork_candidates(board: chess.Board) -> list[tuple]:
    """Every move after which the moved piece attacks two or more enemy pieces (the king or a piece worth a knight or
    more) from a square where it is not simply lost: (move, targets, after), checks first."""
    if not board.is_valid():
        return []
    mover = board.turn
    found = []
    work = board.copy(stack=False)
    for move in board.legal_moves:
        if move.promotion:
            continue
        work.push(move)
        to = move.to_square
        targets = _fork_targets(work, to, mover)
        if len(targets) < 2:
            work.pop()
            continue
        moved = VALUES[board.piece_type_at(move.from_square)]
        attackers = work.attackers(not mover, to)
        lost = False
        if attackers:
            cheapest = min(VALUES[work.piece_type_at(a)] for a in attackers)
            defended = bool(work.attackers(mover, to))
            lost = cheapest < moved or not defended  # the forking piece is just taken
        check = work.is_check()
        work.pop()
        if lost:
            continue
        after = board.copy(stack=False)
        after.push(move)
        found.append((0 if check else 1, -len(targets), board.san(move), move, targets, after))
    found.sort(key=lambda x: (x[0], x[1], x[2]))
    return [(move, targets, after) for _, _, _, move, targets, after in found]


def _material(board: chess.Board, side: chess.Color) -> int:
    """Material of *side* minus its opponent's, in pawns (kings not counted)."""
    total = 0
    for p in board.piece_map().values():
        if p.piece_type != chess.KING:
            total += VALUES[p.piece_type] if p.color == side else -VALUES[p.piece_type]
    return total


def capture_net(board: chess.Board, move: chess.Move) -> int:
    """What the side to move nets by the capture *move* once the opponent has taken back on that square as long as it
    pays (static exchange from the board after the move; a promotion counts as the piece it makes)."""
    if board.is_en_passant(move):
        taken = 1
    else:
        victim = board.piece_at(move.to_square)
        taken = VALUES[victim.piece_type] if victim is not None and victim.piece_type != chess.KING else 0
    if move.promotion:
        taken += VALUES[move.promotion] - 1
    after = board.copy(stack=False)
    after.push(move)
    if after.is_checkmate():
        return taken
    back = exchange_gain(after, move.to_square)
    return taken - (back or 0)


def _best_capture(board: chess.Board, squares) -> int:
    """The most the side to move nets by one capture on *squares* (0 when none pays)."""
    best = 0
    mask = 0
    for sq in squares:
        mask |= chess.BB_SQUARES[sq]
    for m in board.generate_legal_captures(to_mask=mask):
        best = max(best, capture_net(board, m))
    return best


def fork_holds(board: chess.Board, move: chess.Move, targets=None) -> bool:
    """True when the fork *move* wins at least FORK_MIN_GAIN by exchange count against every legal reply (or mates):
    each reply is played, then the mover's best capture on the forked squares (or on the square the reply went to)."""
    mover = board.turn
    after = board.copy(stack=False)
    after.push(move)
    if after.is_checkmate():
        return True
    if targets is None:
        targets = _fork_targets(after, move.to_square, mover)
    replies = list(after.legal_moves)
    if not replies:
        return False  # stalemate
    start = _material(board, mover)
    for reply in replies:
        b2 = after.copy(stack=False)
        b2.push(reply)
        if b2.is_checkmate() or b2.is_stalemate():
            return False
        squares = {s for s in targets if (p := b2.piece_at(s)) is not None and p.color != mover}
        squares.add(reply.to_square)
        net = _material(b2, mover) + _best_capture(b2, squares) - start
        if net < FORK_MIN_GAIN:
            return False
    return True


def _mates_in_one(board: chess.Board) -> bool:
    for m in board.legal_moves:
        if not board.gives_check(m):
            continue
        board.push(m)
        mate = board.is_checkmate()
        board.pop()
        if mate:
            return True
    return False


def starts_mate_in_two(board: chess.Board, move: chess.Move) -> bool:
    """*move* mates, or every reply to it allows a mate in one."""
    b = board.copy()
    b.push(move)
    if b.is_checkmate():
        return True
    replies = list(b.legal_moves)
    if not replies:
        return False
    for r in replies:
        b.push(r)
        ok = _mates_in_one(b)
        b.pop()
        if not ok:
            return False
    return True


def has_mate_in_two_by_checks(board: chess.Board, skip: Optional[chess.Move] = None) -> bool:
    """The side to move mates in one, or in two starting with a check (other than *skip*)."""
    for m in board.legal_moves:
        if m == skip or not board.gives_check(m):
            continue
        if starts_mate_in_two(board, m):
            return True
    return False


def _in_engine_lines(board: chess.Board, move: chess.Move, lines: list) -> bool:
    """The move starts one of the engine's lines, within FORK_ENGINE_MARGIN of the best of them."""
    scored = []
    for line in lines or []:
        pv = (line.get("pv") or "").split()
        if not pv:
            continue
        try:
            first = chess.Move.from_uci(pv[0])
        except ValueError:
            continue
        scored.append((first, _score(line)))
    if not scored:
        return False
    best = max(s for _, s in scored)
    return any(first == move and best - s <= FORK_ENGINE_MARGIN for first, s in scored)


def vetted_forks(board: chess.Board, lines: Optional[list] = None) -> list[tuple]:
    """The fork candidates that hold: (move, targets, after, source) — source "engine" when *lines* vetted them,
    "see" when the exchange count did."""
    out = []
    for move, targets, after in fork_candidates(board):
        if lines is not None:
            if _in_engine_lines(board, move, lines):
                out.append((move, targets, after, "engine"))
        elif after.is_checkmate() or (after.is_check() and starts_mate_in_two(board, move)):
            out.append((move, targets, after, "see"))  # the fork is the start of a mate
        elif fork_holds(board, move, targets) and not has_mate_in_two_by_checks(board, skip=move):
            # A mate on the board is the point, not a fork beside it (Legal's mate: Nxf7 forks the queen and the
            # rook, Bxf7+ and Nd5# mate).
            out.append((move, targets, after, "see"))
    return out


def fork_text(board: chess.Board, move: chess.Move, targets, after: chess.Board) -> str:
    return (f"a fork is available now: {board.san(move)} attacks {_pieces(after, targets)}"
            + (" (with check)" if after.is_check() else ""))


def fork_facts(board: chess.Board, limit: int = 2, lines: Optional[list] = None) -> list[str]:
    """Forks the side to move has NOW: one move after which the moved piece attacks two or more enemy
    pieces (the king or a piece worth a knight or more) from a square where it is not simply lost —
    «Есть ли здесь вилка?» → «нет» with Nc7+ on the board (prod, 23.10). With check first. Each fork is vetted (see
    vetted_forks) unless COACH_TURN_FACTS is off."""
    if not _vetting():
        found = [(m, t, a) for m, t, a in fork_candidates(board)]
    else:
        found = [(m, t, a) for m, t, a, _ in vetted_forks(board, lines)]
    return [fork_text(board, m, t, a) for m, t, a in found[:limit]]


# ── piece safety, attack balance, captures, check replies, material (plan 31.10 P8 C6, F5, F1, F3, F4) ──────────
# Facts the model reasoned against on 29.10 without having them: «конь на f6 под боем пешки e5, и ты честно не
# захотел терять» (g1-resign: the knight had d5, e4 and g8), «второй раз на неё нападать смысла нет — она защищена»
# (st2#2: attacked once and defended once, so one more attacker wins it). Each is counted on the board by static
# exchange (src/board_math), so its source is "see"; none is told as an engine verdict.
MAX_SAFETY = 2
MAX_BALANCE = 2
MAX_LISTED_MOVES = 3


def _san_list(board: chess.Board, moves) -> list[str]:
    return [board.san(m) for m in moves]


def _or_list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


SAFETY_ENGINE_MARGIN = 1.0


def _endorsed(board: chess.Board, lines: Optional[list]) -> set:
    """The first moves of the engine's lines that are within SAFETY_ENGINE_MARGIN of the best of them."""
    scored = []
    for line in lines or []:
        pv = (line.get("pv") or "").split()
        if not pv:
            continue
        try:
            first = chess.Move.from_uci(pv[0])
        except ValueError:
            continue
        if first in board.legal_moves:
            scored.append((first, _score(line)))
    if not scored:
        return set()
    best = max(sc for _, sc in scored)
    return {m for m, sc in scored if best - sc <= SAFETY_ENGINE_MARGIN}


def safety_items(board: chess.Board, lines: Optional[list] = None) -> list[dict]:
    """For each piece (not a pawn) of the side to move that is attacked and not safe where it stands: the squares
    it can go to without being lost there by exchange count (board_math.safe_squares; a promotion square only when
    every piece it can make is safe), told only when the engine's lines of the turn (*lines*) start with that move
    within SAFETY_ENGINE_MARGIN of the best — a square can be safe and the move still a mistake (Ba4 is right after
    3...a6, Bd3 safe and 1.7 worse; with a mate on the board every retreat is wrong). Without lines only a trapped
    piece is told (no safe square: an exchange-count fact). Not when the side to move is in check (check_replies)."""
    if not board.is_valid() or board.is_check():
        return []
    from src.board_math import move_loss, safe_squares

    endorsed = _endorsed(board, lines) if lines is not None else set()
    out = []
    # Pieces, not pawns: a pawn's "safe square" is a push (or a promotion), not a retreat.
    exposed = sorted((it for it in exposed_pieces(board, board.turn) if board.piece_type_at(it[0]) != chess.PAWN),
                     key=lambda it: -VALUES[board.piece_type_at(it[0])])
    for sq, kind, attackers, _ in exposed[:MAX_SAFETY]:
        safe = [s for s in safe_squares(board, sq)
                if all(move_loss(board, m) == 0 for m in board.legal_moves if m.from_square == sq and m.to_square == s)]
        item = {"sq": chess.square_name(sq), "piece": _piece(board, sq), "kind": kind,
                "attackers": [chess.square_name(a) for a in sorted(attackers)]}
        if not safe:
            out.append({**item, "safe": [], "trapped": True})
            continue
        good = [chess.square_name(s) for s in safe
                if any(m.from_square == sq and m.to_square == s for m in endorsed)]
        if good:
            out.append({**item, "safe": good, "trapped": False,
                        "proof": "safe by exchange count; the move starts an engine line within %.1f of the best"
                                 % SAFETY_ENGINE_MARGIN})
    return out


def safety_text(item: dict) -> str:
    if item["safe"]:
        where = _or_list(item["safe"])
        return (f"{item['piece']} is attacked, and it can go to {where}: safe squares by exchange count, and a move "
                "among the engine's best")
    return (f"{item['piece']} has no safe square to go to: every move of it loses it by exchange count "
            "(it can still be defended or the attacker taken)")


def _adders(board: chess.Board, sq: chess.Square, side: chess.Color, before: int) -> list:
    """The quiet legal moves of *board* (side to move = *side*) after which *side* attacks *sq* more often."""
    out = []
    work = board.copy(stack=False)
    for m in board.legal_moves:
        if m.to_square == sq or m.from_square == sq or m.promotion or board.is_capture(m):
            continue
        work.push(m)
        if len(work.attackers(side, sq)) > before:
            out.append(m)
        work.pop()
    return out


def balance_items(board: chess.Board) -> list[dict]:
    """Pieces of the side NOT to move attacked exactly as often as they are defended (and safe by exchange count):
    the side to move's moves that bring one more attacker and make the exchange there win (the moved piece not lost
    on its new square), and the opponent's moves that would defend it once more."""
    if not board.is_valid() or board.is_check():
        return []
    from src.board_math import _as_side, move_loss

    mover = board.turn
    out = []
    pieces = sorted(((sq, p) for sq, p in board.piece_map().items()
                     if p.color != mover and p.piece_type != chess.KING),
                    key=lambda it: (-VALUES[it[1].piece_type], it[0]))
    owner_view = _as_side(board, not mover)
    for sq, piece in pieces:
        attackers = board.attackers(mover, sq)
        defenders = board.attackers(not mover, sq)
        if not attackers or len(attackers) != len(defenders) or (exchange_gain(board, sq) or 0) > 0:
            continue
        adders = []
        for m in _adders(board, sq, mover, len(attackers)):
            if move_loss(board, m) > 0:
                continue
            after = board.copy(stack=False)
            after.push(m)
            if after.is_check() or (exchange_gain(after, sq) or 0) <= 0:
                continue
            adders.append(m)
        if not adders:
            continue
        guards = []
        if owner_view is not None:
            guards = [m for m in _adders(owner_view, sq, not mover, len(defenders)) if move_loss(owner_view, m) == 0]
        adders.sort(key=lambda m: (VALUES[board.piece_type_at(m.from_square)], board.san(m)))
        guards.sort(key=lambda m: (VALUES[owner_view.piece_type_at(m.from_square)], owner_view.san(m)))
        out.append({"sq": chess.square_name(sq), "piece": _piece(board, sq),
                    "attackers": [chess.square_name(a) for a in sorted(attackers)],
                    "defenders": [chess.square_name(d) for d in sorted(defenders)],
                    "adders": _san_list(board, adders)[:MAX_LISTED_MOVES],
                    "guards": _san_list(owner_view, guards)[:MAX_LISTED_MOVES] if owner_view is not None else []})
        if len(out) >= MAX_BALANCE:
            break
    return out


def _times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def balance_text(item: dict, board: chess.Board) -> str:
    n = len(item["attackers"])
    side, other = _color(board.turn), _color(not board.turn)
    text = (f"{item['piece']} is attacked {_times(n)} and defended {_times(n)}: one more attacker wins it by "
            f"exchange count — {side} can add one with {_or_list(item['adders'])}")
    if item["guards"]:
        text += f", and {other} can defend it once more with {_or_list(item['guards'])}"
    return text


def capture_items(board: chess.Board) -> list[dict]:
    """The captures of the side to move that win material once the exchange on that square is played out
    (capture_net > 0), best first: «4.exf6: Black takes back with gxf6 or Qxf6».""" 
    if not board.is_valid():
        return []
    rows = []
    for m in board.legal_moves:
        if not board.is_capture(m):
            continue
        net = capture_net(board, m)
        if net > 0:
            rows.append((-net, board.san(m), m, net))
    rows.sort()
    return [{"san": san, "uci": m.uci(), "to": chess.square_name(m.to_square), "net": net}
            for _, san, m, net in rows[:MAX_LISTED_MOVES]]


def capture_text(items: list[dict], board: chess.Board) -> str:
    told = ", ".join(f"{it['san']} (+{it['net']})" for it in items)
    return f"captures that win material for {_color(board.turn)} now, the exchange on that square counted: {told}"


def check_reply_item(board: chess.Board) -> Optional[dict]:
    """The legal replies to a check, by kind: take the checker, move the king, block."""
    if not board.is_valid() or not board.is_check():
        return None
    checkers = list(board.checkers())
    take, king, block = [], [], []
    for m in board.legal_moves:
        san = board.san(m)
        if m.to_square in checkers:
            take.append(san)
        elif board.piece_type_at(m.from_square) == chess.KING:
            king.append(san)
        else:
            block.append(san)
    return {"checkers": [chess.square_name(c) for c in checkers], "checker_pieces": [_piece(board, c) for c in checkers],
            "take": sorted(take), "king": sorted(king), "block": sorted(block)}


def check_reply_text(item: dict, board: chess.Board) -> str:
    def told(moves):
        return ", ".join(moves) if moves else "none"
    return (f"{_color(board.turn)} is in check from {' and '.join(item['checker_pieces'])}; the legal replies to the "
            f"check — take the checker: {told(item['take'])}; king moves: {told(item['king'])}; "
            f"blocks: {told(item['block'])}")


_UNIT = {"Q": "queen", "R": "rook", "B": "bishop", "N": "knight", "P": "pawn"}


def _units(more: dict) -> str:
    parts = []
    for letter in ("Q", "R", "B", "N", "P"):
        n = more.get(letter)
        if n:
            word = _UNIT[letter]
            parts.append(f"{'a' if n == 1 else n} {word}{'' if n == 1 else 's'}")
    return " and ".join([", ".join(parts[:-1]), parts[-1]]) if len(parts) > 1 else (parts[0] if parts else "")


def material_item(board: chess.Board) -> dict:
    from src.game_record import material

    return material(board)


def material_text(m: dict) -> str:
    diff = m["diff"]
    head = f"material on the board (counted): White {m['white']}, Black {m['black']}"
    if not m["more"]["white"] and not m["more"]["black"]:
        return head + " — the same pieces on both sides, material is level"
    lead = ("level" if diff == 0 else f"White +{diff}" if diff > 0 else f"Black +{-diff}")
    bits = []
    for side in ("white", "black"):
        if m["more"][side]:
            bits.append(f"{side.capitalize()} has {_units(m['more'][side])} more")
    return f"{head} ({lead}): " + "; ".join(bits)


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
