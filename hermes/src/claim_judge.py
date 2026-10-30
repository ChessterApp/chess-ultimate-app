"""The judge (WP-B): one claim on its boards → true / false / undecided, with the board truth for the rewrite.

A claim is false only when it is false on the primary board, true on no alternative board and judgeable on the board
the coach showed (plan 30.10, §3.1). When it is false on the primary board only because a piece it names is not there,
an alternative on which it binds but cannot be judged leaves it undecided. The board-rule relations (``RULE_RELATIONS``) go to ``claim_rules.RULE_JUDGES``
under the same rule.

What each relation means on one board (python-chess attack maps):
  attack / chase / threat  the subject reaches the object now (en passant counts); an enemy piece named as the object
                           must be the enemy's — a piece never attacks its own; an empty square is reached also through
                           the enemy king (the king cannot stand on the line behind itself). «бьёт» right after the
                           subject captured the object is the capture told, and true;
  aim                      the subject is on its line with the object, at most one enemy piece in between (x-ray); its
                           own pieces do not count — they can step aside (the Dragon bishop «целится в c3» through Nf6);
                           the same for an object named by kind only («ладья e1 смотрит на короля»);
  defend                   same colour required (a piece never defends the enemy's); a battery counts (Q behind B);
                           a bare square («прикрывает поле h7») is control of it, by either side;
  hold                     either side; a battery counts; an empty square also through the enemy king; a square the
                           enemy king stands on is hit like any square («поле f8 под боем»), a named king is not
                           («держит короля»: confines it — undecided);
  undefended / attacked / hanging  the object's defenders (battery counts) / attackers;
  pinned / pins / pin_after an enemy line piece, the object, and behind it the king or a more valuable piece (absolute
                           and relative pins), or any piece behind a front piece worth more than the attacker (what
                           coaches call a pin too: «ладья связывает ферзя с ладьёй e8»);
  locked_by / blocks       the named blockers stand on the subject's lines (kings excluded) / the blocker is the first
                           piece on the line piece's line;
  locked / trapped         no move / no safe move for the piece (kings and pawns excluded);
  capture_with             a piece of that kind (of that side) reaches the square;
  gives_check              the side to move is in check;
  plan_reach (and any claim about a plan or a position the turn cannot build)  the piece on an empty board reaches
                           the target: «слон на g2 будет бить по e6» is false in every position.
A piece named on a square where it does not stand («конь f6» with no knight on f6) makes the claim false on that board
(the implicit move and the other alternatives may still make it true elsewhere); in a denial it is undecided. A «с sq»
subject the last move took away from sq is the moved piece. An unbound subject («конь» with two knights) is
existential: some knight of that side; the piece that just moved is the one meant when it is of that kind. A subject
standing on its own target, a king as the object of a defence or of «держит», a square with no piece as the object of
«не защищён»: undecided. The truth line names what the subject really attacks or defends (at most four), truth first.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import chess

from src.claim_types import PIECE_TYPE, RULE_RELATIONS, UNDECIDED, BoardSet, Claim, Ref, Verdict

VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
NAME = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook", chess.QUEEN: "queen",
        chess.KING: "king"}
SLIDERS = (chess.BISHOP, chess.ROOK, chess.QUEEN)
MAX_LIST = 4
_HOSTILE = ("attack", "chase", "threat", "aim", "pins", "pin_after", "attacked", "capture_with")


class _Undecided(Exception):
    pass


# ── words for the truth line ─────────────────────────────────────────────────────────────────────────────────────
def _side(c: bool) -> str:
    return "White" if c == chess.WHITE else "Black"


def who(board: chess.Board, sq: int, own: Optional[bool] = None) -> str:
    """«White's knight on f6»; «Black's own queen on h4» when *own* is the piece's side."""
    p = board.piece_at(sq)
    if p is None:
        return chess.square_name(sq)
    mine = " own" if own is not None and own == p.color else ""
    return f"{_side(p.color)}'s{mine} {NAME[p.piece_type]} on {chess.square_name(sq)}"


def _names(board: chess.Board, sqs, cap: int = MAX_LIST) -> str:
    sqs = list(sqs)
    words = [who(board, s) for s in sqs[:cap]]
    if len(sqs) > cap:
        words.append(f"{len(sqs) - cap} more")
    return ", ".join(words[:-1]) + (" and " + words[-1] if len(words) > 1 else (words[0] if words else ""))


def _sqnames(sqs, cap: int = MAX_LIST) -> str:
    names = [chess.square_name(s) for s in sorted(sqs)]
    if len(names) > cap:
        names = names[:cap] + ["…"]
    return ", ".join(names[:-1]) + (" and " + names[-1] if len(names) > 1 else (names[0] if names else ""))


def _hits(board: chess.Board, a: int) -> str:
    """What the piece on *a* really attacks: the enemy pieces it hits, else (a pawn) the squares it hits."""
    p = board.piece_at(a)
    if p is None:
        return "nothing"
    enemies = [s for s in board.attacks(a) if board.piece_at(s) is not None and board.color_at(s) != p.color]
    if enemies:
        return _names(board, enemies)
    if p.piece_type in (chess.PAWN, chess.KNIGHT, chess.KING):
        return _sqnames(board.attacks(a)) + " (no enemy piece)"
    return "no enemy piece"


# ── geometry ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _on_line(pt: int, a: int, t: int) -> bool:
    df = abs(chess.square_file(a) - chess.square_file(t))
    dr = abs(chess.square_rank(a) - chess.square_rank(t))
    diag, straight = df == dr and df > 0, (df == 0) != (dr == 0)
    return (pt == chess.BISHOP and diag) or (pt == chess.ROOK and straight) or (pt == chess.QUEEN and (diag or straight))


def _between(board: chess.Board, a: int, t: int) -> list:
    return [s for s in chess.SquareSet(chess.between(a, t)) if board.piece_at(s) is not None]


def _reaches(board: chess.Board, a: int, t: int) -> bool:
    """The piece on *a* attacks *t* now; a pawn also takes en passant."""
    if t in board.attacks(a):
        return True
    p = board.piece_at(a)
    if p is not None and p.piece_type == chess.PAWN and board.ep_square is not None and \
            board.ep_square in board.attacks(a) and p.color == board.turn:
        return t == board.ep_square + (-8 if board.turn == chess.WHITE else 8)
    return False


def _through_king(board: chess.Board, a: int, t: int) -> bool:
    """An empty *t* the line piece on *a* reaches through the enemy king alone: the king cannot step there."""
    p = board.piece_at(a)
    if p is None or p.piece_type not in SLIDERS or board.piece_at(t) is not None or not _on_line(p.piece_type, a, t):
        return False
    mid = _between(board, a, t)
    return len(mid) == 1 and board.piece_type_at(mid[0]) == chess.KING and board.color_at(mid[0]) != p.color


def _battery(board: chess.Board, a: int, t: int) -> bool:
    """*a* reaches *t* directly, or through its own line pieces of the same line kind (Q+B, R+R, Q+R)."""
    if t in board.attacks(a):
        return True
    p = board.piece_at(a)
    if p is None or p.piece_type not in SLIDERS or not _on_line(p.piece_type, a, t):
        return False
    diag = chess.square_file(a) != chess.square_file(t) and chess.square_rank(a) != chess.square_rank(t)
    for s in _between(board, a, t):
        q = board.piece_at(s)
        if q.color != p.color:
            return False
        if diag and q.piece_type not in (chess.BISHOP, chess.QUEEN):
            return False
        if not diag and q.piece_type not in (chess.ROOK, chess.QUEEN):
            return False
    return True


def _xray(board: chess.Board, a: int, t: int, through: int = 1) -> bool:
    """*a* aims at *t*: on its line with at most *through* enemy pieces in between («смотрит на f7» through e6). The
    aimer's own pieces do not count — they can step aside (a discovered attack: the Dragon bishop g7 «целится в c3»
    through its own Nf6)."""
    if t in board.attacks(a):
        return True
    p = board.piece_at(a)
    if p is None or p.piece_type not in SLIDERS or not _on_line(p.piece_type, a, t):
        return False
    return sum(1 for s in _between(board, a, t) if board.color_at(s) != p.color) <= through


def _shields(board: chess.Board, a: int, t: int) -> bool:
    """The piece on *a* stands alone on an enemy line piece's line to *t*: it covers *t* from it («3...e6 — пешка
    прикрыла поле f7 от твоего слона на c4»; «прикрывать» is both to defend and to shield)."""
    p = board.piece_at(a)
    if p is None or a == t:
        return False
    for e, q in board.piece_map().items():
        if q.color == p.color or q.piece_type not in SLIDERS or not _on_line(q.piece_type, e, t):
            continue
        if _between(board, e, t) == [a] and a in chess.SquareSet(chess.between(e, t)):
            return True
    return False


def _open_line_to(board: chess.Board, t: int) -> bool:
    """An enemy bishop, rook or queen reaches the piece on *t* along an open line: nothing shields it from it."""
    p = board.piece_at(t)
    if p is None:
        return False
    for a, q in board.piece_map().items():
        if q.color != p.color and q.piece_type in SLIDERS and _on_line(q.piece_type, a, t) and \
                all(board.color_at(m) == q.color for m in _between(board, a, t)):
            return True  # in the line's reach, or behind the attacker's own pieces (a discovered attack)
    return False


def defenders(board: chess.Board, t: int, color: bool) -> list:
    """The pieces of *color* that defend *t* (a battery counts)."""
    return [s for s, p in board.piece_map().items() if p.color == color and s != t and _battery(board, s, t)]


def pin_behind(board: chess.Board, a: int, t: int) -> Optional[int]:
    """The square of what the line piece on *a* pins the piece on *t* to (the king, or a more valuable piece behind
    it: absolute and relative pins), or None."""
    pa, pt = board.piece_at(a), board.piece_at(t)
    if pa is None or pt is None or pa.color == pt.color or pa.piece_type not in SLIDERS:
        return None
    if not _on_line(pa.piece_type, a, t) or t not in board.attacks(a):
        return None
    df = (chess.square_file(t) > chess.square_file(a)) - (chess.square_file(t) < chess.square_file(a))
    dr = (chess.square_rank(t) > chess.square_rank(a)) - (chess.square_rank(t) < chess.square_rank(a))
    f, r = chess.square_file(t) + df, chess.square_rank(t) + dr
    while 0 <= f < 8 and 0 <= r < 8:
        q = chess.square(f, r)
        x = board.piece_at(q)
        if x is not None:
            if x.color != pt.color:
                return None
            # the king or a more valuable piece behind (absolute and relative pins); or a piece behind a front piece
            # worth more than the attacker («ладья связывает ферзя e5 с ладьёй e8»: the queen must go and the rook
            # behind is lost — what coaches call a pin too)
            # A piece behind worth as much as the front one and left undefended is lost when the front one steps
            # aside — a pin too («ладья b5 связана — за ней на b8 стоит вторая ладья», nothing guards b8).
            if x.piece_type == chess.KING or VAL[x.piece_type] > VAL[pt.piece_type] or \
                    (x.piece_type != chess.PAWN and VAL[pt.piece_type] > VAL[pa.piece_type]) or \
                    (x.piece_type != chess.PAWN and VAL[x.piece_type] >= VAL[pt.piece_type] and
                     not [d for d in board.attackers(x.color, q) if d != t]):
                return q
            return None
        f, r = f + df, r + dr
    return None


def _pinners(board: chess.Board, t: int) -> list:
    pt = board.piece_at(t)
    if pt is None:
        return []
    return [s for s, p in board.piece_map().items() if p.color != pt.color and pin_behind(board, s, t) is not None]


def _moves_of(board: chess.Board, sq: int) -> Optional[list]:
    """The legal moves of the piece on *sq*, as if its side were to move (None when that cannot be set up)."""
    p = board.piece_at(sq)
    if p is None:
        return None
    b = board
    if board.turn != p.color:
        if board.is_check():
            return None
        b = board.copy(stack=False)
        b.push(chess.Move.null())
    return [m for m in b.legal_moves if m.from_square == sq]


# ── who the words name on a board ───────────────────────────────────────────────────────────────────────────────
def _colour(ref: Optional[Ref], ctx: Any, board: chess.Board) -> Optional[bool]:
    """The side a ref names: an explicit side; «твой» → the student (else the side to move); «их», «соперника» → the
    other side. «свой» is relative and left to the relation."""
    if ref is None:
        return None
    if ref.side is not None:
        return ref.side
    if ref.owner in ("you", "their"):
        me = getattr(ctx, "student_color", None)
        cur = getattr(ctx, "current", None)
        if me is None:
            me = (cur if cur is not None else board).turn
        return me if ref.owner == "you" else (not me)
    return None


def _moved_from(board: chess.Board, ref: Optional[Ref]) -> Optional[int]:
    """«конь с c4 бьёт с шахом» told with Na3+: a «с sq» piece that the last move took away from sq is the piece now
    on its destination."""
    if ref is None or not ref.from_sq or not ref.sq:
        return None
    from src.claim_scene import last_move

    mv = last_move(board)
    if mv is not None and mv.from_square == chess.parse_square(ref.sq):
        return mv.to_square
    return None


def _rebound(claim: Claim, board: chess.Board) -> Optional[Claim]:
    """*claim* with a piece named by the square the last move took it from read as that piece where it went: «А почему
    не bxa7? Тогда чёрный слон бьёт твою пешку b6» — the pawn from b6, now on a7; «после Rxb5 Rxb5 ладья b7 …» — the
    rook from b7. Another reading of the words on the same board (the board just before the move is the other one,
    claim_scene._before_last); None when no ref names the square the last move left."""
    from dataclasses import replace

    from src.claim_scene import last_move

    mv = last_move(board)
    if mv is None or board.piece_at(mv.from_square) is not None or mv.promotion is not None:
        return None
    moved = board.piece_at(mv.to_square)
    if moved is None:
        return None
    left, went = chess.square_name(mv.from_square), chess.square_name(mv.to_square)

    def fix(ref: Optional[Ref]) -> Optional[Ref]:
        if ref is None or ref.sq != left or ref.from_sq or not ref.piece or PIECE_TYPE[ref.piece] != moved.piece_type \
                or (ref.side is not None and ref.side != moved.color):
            return ref
        return replace(ref, sq=went)

    subj, objs = fix(claim.subj), tuple(fix(o) for o in claim.objs)
    if subj is claim.subj and all(a is b for a, b in zip(objs, claim.objs)):
        return None
    return replace(claim, subj=subj, objs=objs)


def _ref_square(board: chess.Board, ref: Ref) -> int:
    moved = _moved_from(board, ref)
    return moved if moved is not None else chess.parse_square(ref.sq)


def ghost(board: chess.Board, ref: Optional[Ref], colour: Optional[bool] = None) -> Optional[str]:
    """«конь f6» with no knight on f6: what stands there instead, or None when the named piece is there."""
    if ref is None or not ref.sq:
        return None
    sq = _ref_square(board, ref)
    p = board.piece_at(sq)
    if ref.piece:
        want = PIECE_TYPE[ref.piece]
        if p is None:
            return f"there is no {NAME[want]} on {chess.square_name(sq)}: the square is empty"
        if p.piece_type != want:
            return f"on {chess.square_name(sq)} stands {who(board, sq)}, not a {NAME[want]}"
    if ref.side is not None and p is not None and p.color != ref.side:
        return f"the piece on {ref.sq} is {_side(p.color)}'s, not {_side(ref.side)}'s"
    return None


def _candidates(board: chess.Board, ref: Optional[Ref], colour: Optional[bool], kings: bool = True) -> list:
    """The squares an unsquared ref can mean on *board*: the piece that just moved when it is of that kind, else
    every piece of that kind and side."""
    if ref is None:
        return []
    if ref.sq:
        return [_ref_square(board, ref)]
    pt = PIECE_TYPE.get(ref.piece) if ref.piece else None
    from src.claim_scene import last_move

    mv = last_move(board)
    if mv is not None and pt is not None:
        p = board.piece_at(mv.to_square)
        if p is not None and p.piece_type == pt and (colour is None or p.color == colour):
            return [mv.to_square]
        prev = getattr(board, "rel_prev", None)
        if pt == chess.ROOK and prev is not None and prev.is_castling(mv):
            rook = chess.square(5 if chess.square_file(mv.to_square) == 6 else 3, chess.square_rank(mv.to_square))
            return [rook]
    return [s for s, p in board.piece_map().items()
            if (pt is None or p.piece_type == pt) and (colour is None or p.color == colour)
            and (kings or pt == chess.KING or p.piece_type != chess.KING)]


def _targets(claim: Claim) -> list:
    return [o for o in claim.objs if o is not None]


# ── the relations on one board: (True | False | None, truth) ─────────────────────────────────────────────────────
def _judge_attack(claim: Claim, board: chess.Board, ctx: Any) -> tuple:
    rel = claim.rel
    objs = _targets(claim)
    if not objs:
        raise _Undecided
    s = claim.subj
    if s is not None and s.pronoun and not s.sq and not s.piece:
        raise _Undecided  # «он бьёт по слону d6» with «он» unresolved
    scol = _colour(s, ctx, board)
    # The subject is a side or nothing («d6 под контролем», «f8 прострелено»): any piece of that side (or either).
    if s is None or (not s.sq and not s.piece):
        cols = [scol] if scol is not None else [chess.WHITE, chess.BLACK]
        for o in objs:
            if not o.sq:
                raise _Undecided
            t = _ref_square(board, o)
            tp = board.piece_at(t)
            if tp is not None and tp.piece_type == chess.KING and rel == "hold" and o.piece:
                raise _Undecided
            sides = [c for c in cols if not (rel != "hold" and tp is not None and tp.color == c)]
            hit = any((_battery(board, a, t) if rel == "hold" else _reaches(board, a, t)) or _through_king(board, a, t)
                      for c in sides for a in _side_squares(board, c))
            if not hit:
                by = " or ".join(_side(c) for c in sides) or "either side"
                reach = sorted(board.attackers(chess.WHITE, t) | board.attackers(chess.BLACK, t))
                return False, f"no piece of {by if len(sides) == 1 else 'either side'} reaches {who(board, t)}; " \
                              f"what reaches it: {_names(board, reach) or 'nothing'}"
        return True, ""
    # Which side the subject is on, when the words do not say: the enemy of a hostile relation's object.
    want = scol
    if want is None and s.owner != "own" and objs[0].sq and rel in _HOSTILE:
        tp = board.piece_at(chess.parse_square(objs[0].sq))
        if tp is not None and not s.sq:
            want = not tp.color
    subj = _candidates(board, s, want)
    if not subj:
        what = (_side(want) + "'s " if want is not None else "") + (NAME[PIECE_TYPE[s.piece]] if s.piece else "piece")
        return False, f"there is no {what} on the board"
    for o in objs:
        if o.sq:
            t = _ref_square(board, o)
            tp = board.piece_at(t)
            if tp is not None and tp.piece_type == chess.KING and rel == "hold" and o.piece:
                raise _Undecided
            if t in subj and (len(subj) == 1 or not o.piece):
                raise _Undecided  # «поле h7 держит пешка» with the pawn on h7: it occupies the square
            ok_any = False
            for a in subj:
                ap = board.piece_at(a)
                if ap is None:
                    continue
                if rel == "aim":
                    ok = _xray(board, a, t, 1) or _through_king(board, a, t)
                elif rel == "hold":
                    ok = _battery(board, a, t) or _through_king(board, a, t)
                else:
                    ok = _reaches(board, a, t) or _through_king(board, a, t)
                    if ok and tp is not None and tp.color == ap.color and o.piece:
                        ok = False  # «пешка g3 нападает на ферзя h4»: its own queen («бьёт по d4» is the square)
                ok_any = ok_any or ok
            if not ok_any:
                if len(subj) == 1:
                    a = subj[0]
                    verb = {"aim": "is on a line with", "hold": "reaches"}.get(rel, "attacks")
                    target = who(board, t, own=board.color_at(a)) if tp is not None else chess.square_name(t)
                    if rel == "aim":
                        return False, f"{who(board, a)} is not on a line with {target} (or more than one piece is in between)"
                    return False, f"{who(board, a)} {verb} {_hits(board, a)} — not {target}"
                return False, f"no {_kind(s)} reaches {who(board, t)}"
        elif o.piece:
            # «атакует … и ладью»: some enemy piece of that kind is hit
            if rel == "hold":
                raise _Undecided  # «держат короля» (confine it) is not the attack map
            pt = PIECE_TYPE[o.piece]
            ok_any = False
            for a in subj:
                ap = board.piece_at(a)
                if ap is None:
                    continue
                hit = set(board.attacks(a))
                if rel == "aim":  # «ладья e1 смотрит на короля» through one piece, as for a named square
                    hit |= {t for t, tp in board.piece_map().items() if tp.color != ap.color and _xray(board, a, t, 1)}
                if ap.piece_type == chess.PAWN and board.ep_square is not None and ap.color == board.turn and \
                        board.ep_square in hit:
                    hit.add(board.ep_square + (-8 if board.turn == chess.WHITE else 8))  # en passant
                for t in hit:
                    tp = board.piece_at(t)
                    if tp is not None and tp.piece_type == pt and tp.color != ap.color and \
                            (o.side is None or tp.color == o.side):
                        ok_any = True
            if not ok_any:
                if len(subj) == 1:
                    return False, f"{who(board, subj[0])} attacks {_hits(board, subj[0])} — no {NAME[pt]}"
                return False, f"no {_kind(s)} attacks a {NAME[pt]}"
        else:
            raise _Undecided
    return True, ""


def _side_squares(board: chess.Board, c: bool) -> list:
    return [s for s, p in board.piece_map().items() if p.color == c]


def _kind(ref: Ref) -> str:
    return NAME[PIECE_TYPE[ref.piece]] if ref and ref.piece else "piece"


def _judge_defend(claim: Claim, board: chess.Board, ctx: Any) -> tuple:
    objs = [o for o in _targets(claim) if o.sq]
    if not objs:
        raise _Undecided
    s = claim.subj
    if s is None:
        raise _Undecided
    for o in objs:
        t = _ref_square(board, o)
        tp = board.piece_at(t)
        if tp is not None and tp.piece_type == chess.KING:
            raise _Undecided  # «прикрывает короля» is about lines and checks, not the attack map
        if not o.piece:
            # «прикрывает поле h7», «защищает e4» with no piece named: control of the square, by either side
            tp = None
        scol = _colour(s, ctx, board)
        want = scol if scol is not None else (tp.color if tp is not None else None)
        subj = _candidates(board, s, want)
        if not subj:
            what = (_side(want) + "'s " if want is not None else "") + _kind(s)
            return False, f"there is no {what} on the board"
        if t in subj and (len(subj) == 1 or not o.piece):
            raise _Undecided  # «c6 прикрыт только ферзём» with the queen on c6: it stands there, a word for occupying
        ok = False
        for a in subj:
            ap = board.piece_at(a)
            if ap is None or a == t:
                continue
            if tp is not None and ap.color != tp.color:
                continue  # a piece never defends the enemy's
            if _battery(board, a, t) or (tp is None and _through_king(board, a, t)) or _shields(board, a, t):
                ok = True
        if not ok:
            occupant = board.piece_at(t)
            dfs = defenders(board, t, occupant.color) if tp is not None and occupant is not None else \
                sorted(board.attackers(chess.WHITE, t) | board.attackers(chess.BLACK, t))
            if len(subj) == 1:
                a = subj[0]
                ap = board.piece_at(a)
                if tp is not None and ap is not None and ap.color != tp.color:
                    if o.pronoun or s.pronoun:
                        # «А защищают его только чёрная ладья с f7 и ферзь с d8» with «его» read as White's bishop: a
                        # defender of the other side says the pronoun means another piece — not a board fact.
                        raise _Undecided
                    return False, f"{who(board, a)} is {_side(ap.color)}'s — it cannot defend {who(board, t)}; " + \
                        (f"{who(board, t)} is defended by {_names(board, dfs)}" if dfs else f"nothing defends {who(board, t)}")
                if tp is None:
                    return False, f"{who(board, a)} does not reach {chess.square_name(t)}; what reaches it: " + \
                        (_names(board, dfs) or "nothing")
                return False, f"{who(board, a)} does not defend {who(board, t)}; " + \
                    (f"it is defended by {_names(board, dfs)}" if dfs else "nothing defends it")
            side = _side(want) + "'s " if want is not None else ""
            return False, (f"no {side}{_kind(s)} defends {who(board, t)}; " +
                           (f"it is defended by {_names(board, dfs)}" if dfs else "nothing defends it"))
    return True, ""


def _target_square(claim: Claim) -> Optional[Ref]:
    objs = [o for o in _targets(claim) if o.sq]
    if objs:
        return objs[0]
    if claim.subj is not None and claim.subj.sq:
        return claim.subj
    return None


def _judge_undefended(claim: Claim, board: chess.Board, ctx: Any) -> tuple:
    refs = [o for o in _targets(claim) if o.sq] or ([claim.subj] if claim.subj is not None and claim.subj.sq else [])
    if not refs:
        raise _Undecided
    for r in refs:
        if not r.piece and not r.pronoun:
            raise _Undecided  # «поле f7 не защищено»: a square, defended by whom the words do not say
        t = _ref_square(board, r)
        tp = board.piece_at(t)
        if tp is None or tp.piece_type == chess.KING:
            raise _Undecided
        dfs = defenders(board, t, tp.color)
        if claim.kind == "cover" and not claim.neg and _open_line_to(board, t):
            continue  # «ферзь e3 ничем не прикрыт: ладья e8 смотрит прямо на него» — nothing stands in the line's way
        if claim.rel == "hanging":
            att = board.attackers(not tp.color, t)
            if not att:
                return False, f"nothing attacks {who(board, t)}"
        if dfs:
            return False, f"{who(board, t)} is defended by {_names(board, dfs)}"
    return True, ""


def _judge_attacked(claim: Claim, board: chess.Board, ctx: Any) -> tuple:
    refs = [o for o in _targets(claim) if o.sq]
    if not refs:
        raise _Undecided
    s = claim.subj
    for r in refs:
        t = _ref_square(board, r)
        tp = board.piece_at(t)
        if tp is None:
            raise _Undecided
        att = sorted(board.attackers(not tp.color, t))
        if s is not None and (s.sq or s.piece):
            att_ok = [a for a in _candidates(board, s, not tp.color) if a in att]
            if not att_ok:
                by = _names(board, att) or "nothing"
                return False, f"{who(board, t)} is attacked by {by}" + ("" if s.sq else f" — not by a {_kind(s)}")
            continue
        if claim.count is not None:
            if len(att) != claim.count:
                return False, f"{who(board, t)} is attacked {len(att)} time{'s' if len(att) != 1 else ''}" + \
                    (f": by {_names(board, att)}" if att else "")
        elif not att:
            dfs = defenders(board, t, tp.color)
            return False, f"nothing attacks {who(board, t)}" + (f"; it is defended by {_names(board, dfs)}" if dfs else "")
    return True, ""


def _judge_pinned(claim: Claim, board: chess.Board, ctx: Any) -> tuple:
    r = _target_square(claim) if claim.rel == "pinned" else None
    if r is None:
        raise _Undecided
    t = _ref_square(board, r)
    tp = board.piece_at(t)
    if tp is None:
        raise _Undecided
    pinners = _pinners(board, t)
    s = claim.subj if (claim.subj is not None and claim.objs) else None
    if s is not None and s.piece == "K":
        raise _Undecided  # «пешка h3 связана королём»: a king pins nothing — tied to the king, guarded by it
    if s is not None and (s.sq or s.piece):
        pinners = [a for a in pinners if a in _candidates(board, s, not tp.color)]
    if claim.to is not None and claim.to.sq:
        pinners = [a for a in pinners if pin_behind(board, a, t) == chess.parse_square(claim.to.sq)]
    if pinners:
        return True, ""
    return False, f"{who(board, t)} is not pinned: no enemy bishop, rook or queen holds it on a line to the king or to a more valuable piece"


def _judge_pins(claim: Claim, board: chess.Board, ctx: Any) -> tuple:
    s = claim.subj
    if s is None or (not s.sq and not s.piece) or s.piece == "K":
        raise _Undecided  # a king pins nothing: «связан королём» is «tied to the king»
    objs = [o for o in _targets(claim) if o.sq]
    subj = _candidates(board, s, _colour(s, ctx, board))
    if not subj:
        return False, f"there is no {_kind(s)} on the board"
    if not objs:
        side = next((o.side for o in _targets(claim) if o.side is not None), None)
        for a in subj:
            for t in board.attacks(a):
                tp = board.piece_at(t)
                if tp is not None and (side is None or tp.color == side) and pin_behind(board, a, t) is not None:
                    return True, ""
        a = subj[0]
        return False, f"{who(board, a)} pins nothing; it attacks {_hits(board, a)}"
    for o in objs:
        t = _ref_square(board, o)
        if board.piece_at(t) is None:
            return False, f"{o.sq} is empty: there is nothing to pin"
        ok = False
        for a in subj:
            behind = pin_behind(board, a, t)
            if behind is not None and (claim.to is None or not claim.to.sq or chess.square_name(behind) == claim.to.sq):
                ok = True
        if not ok:
            a = subj[0]
            tp, ap = board.piece_at(t), board.piece_at(a)
            if ap is not None and tp.color == ap.color:
                pins = _pinners(board, t)
                return False, f"{who(board, t)} is {_side(ap.color)}'s own piece — {who(board, a)} cannot pin it" + \
                    (f"; it is pinned by {_names(board, pins)}" if pins else "")
            if t not in board.attacks(a):
                return False, f"{who(board, a)} does not even reach {who(board, t)}; it attacks {_hits(board, a)}"
            return False, f"{who(board, a)} attacks {who(board, t)} but pins it to nothing: no king or more valuable piece stands behind it"
    return True, ""


def _judge_locked_by(claim: Claim, board: chess.Board, ctx: Any) -> tuple:
    s = claim.subj
    if s is None or not s.sq:
        raise _Undecided
    a = chess.parse_square(s.sq)
    p = board.piece_at(a)
    if p is None or p.piece_type == chess.KING:
        raise _Undecided
    blockers = [chess.parse_square(o.sq) for o in _targets(claim) if o.sq]
    if not blockers:
        raise _Undecided
    empty = chess.Board(None)
    empty.set_piece_at(a, p)
    rays = set(empty.attacks(a))
    if p.piece_type == chess.PAWN:
        step = 8 if p.color == chess.WHITE else -8
        if 0 <= a + step < 64:
            rays.add(a + step)
    if not any(b in rays for b in blockers):
        moves = _moves_of(board, a) or []
        to = _sqnames({m.to_square for m in moves})
        return False, f"{_sqnames(blockers)} {'is' if len(blockers) == 1 else 'are'} not on any line of {who(board, a)}; " \
                      f"it can go to {to or 'no square'}"
    return True, ""


def _judge_blocks(claim: Claim, board: chess.Board, ctx: Any) -> tuple:
    """«пешка e6 перекрыла слону f8»: the blocker is the first piece on one of the line piece's lines."""
    s = claim.subj
    objs = [o for o in _targets(claim) if o.sq]
    if s is None or not s.sq or not objs:
        raise _Undecided
    b = chess.parse_square(s.sq)
    t = chess.parse_square(objs[0].sq)
    sl = board.piece_at(t)
    if sl is None or sl.piece_type not in SLIDERS or board.piece_at(b) is None:
        raise _Undecided
    if b in board.attacks(t):
        return True, ""
    moves = _moves_of(board, t) or []
    return False, f"{who(board, b)} is not on a line of {who(board, t)}; it can go to " + \
        (_sqnames({m.to_square for m in moves}) or "no square")


def _judge_locked(claim: Claim, board: chess.Board, ctx: Any) -> tuple:
    s = claim.subj
    if s is None or not s.sq:
        raise _Undecided
    a = chess.parse_square(s.sq)
    p = board.piece_at(a)
    if p is None or p.piece_type in (chess.KING, chess.PAWN):
        raise _Undecided
    if claim.objs and any(o.sq for o in claim.objs):
        return _judge_locked_by(claim, board, ctx)
    moves = _moves_of(board, a)
    if moves is None:
        raise _Undecided
    if claim.rel == "locked":
        if moves:
            return False, f"{who(board, a)} can go to {_sqnames({m.to_square for m in moves})}"
        return True, ""
    safe = [m for m in moves if not board.is_attacked_by(not p.color, m.to_square)]
    if safe:
        return False, f"{who(board, a)} can go safely to {_sqnames({m.to_square for m in safe})}"
    return True, ""


def _judge_capture_with(claim: Claim, board: chess.Board, ctx: Any) -> tuple:
    s = claim.subj
    objs = [o for o in _targets(claim) if o.sq]
    if s is None or not s.piece or not objs:
        raise _Undecided
    pt = PIECE_TYPE[s.piece]
    t = chess.parse_square(objs[0].sq)
    col = _colour(s, ctx, board)
    sides = [col] if col is not None else [chess.WHITE, chess.BLACK]
    if any(board.piece_type_at(a) == pt for c in sides for a in board.attackers(c, t)):
        return True, ""
    tp = board.piece_at(t)
    if tp is not None and tp.piece_type == pt and tp.color in sides:
        raise _Undecided
    reach = sorted(board.attackers(chess.WHITE, t) | board.attackers(chess.BLACK, t))
    by = _side(col) if col is not None else "either side"
    return False, f"no {NAME[pt]} of {by} can take on {chess.square_name(t)}; what reaches it: " + (_names(board, reach) or "nothing")


def _judge_check(claim: Claim, board: chess.Board, ctx: Any) -> tuple:
    if board.is_check():
        return True, ""
    return False, f"{_side(board.turn)}'s king is not in check"


_JUDGES: dict = {
    "attack": _judge_attack, "chase": _judge_attack, "threat": _judge_attack, "aim": _judge_attack,
    "hold": _judge_attack, "defend": _judge_defend, "undefended": _judge_undefended, "hanging": _judge_undefended,
    "attacked": _judge_attacked, "pinned": _judge_pinned, "pins": _judge_pins, "pin_after": _judge_pins,
    "locked_by": _judge_locked_by, "blocks": _judge_blocks, "locked": _judge_locked, "trapped": _judge_locked,
    "capture_with": _judge_capture_with, "gives_check": _judge_check,
}
# Relations whose named pieces must stand where the words put them (the board-rule and the "who can take" ones read
# the board their own way).
_GHOST_CHECKED = set(_JUDGES) - {"capture_with", "gives_check"}


def _just_took(claim: Claim, board: chess.Board) -> bool:
    """«пешка с e5 на f6 бьёт твоего коня», «ферзь бьёт пешку e4 с шахом»: the subject is the piece that has just
    captured, and what it took is the object — «бьёт» told as the capture, true on the board right after it."""
    from src.claim_scene import board_before, last_move

    mv, prev = last_move(board), board_before(board)
    s = claim.subj
    if mv is None or prev is None or s is None or not claim.objs or claim.neg:
        return False
    taken_sq = mv.to_square
    if prev.is_en_passant(mv):
        taken_sq = mv.to_square + (-8 if prev.turn == chess.WHITE else 8)
    taken = prev.piece_at(taken_sq)
    mover = board.piece_at(mv.to_square)
    if taken is None or mover is None or taken.color == mover.color:
        return False
    if s.sq and chess.parse_square(s.sq) not in (mv.to_square, mv.from_square):
        return False
    if s.piece and PIECE_TYPE[s.piece] != prev.piece_type_at(mv.from_square):
        return False
    o = claim.objs[0]
    if o is None or (o.sq and chess.parse_square(o.sq) != taken_sq) or (o.piece and PIECE_TYPE[o.piece] != taken.piece_type):
        return False
    return bool(o.sq or o.piece) and len(claim.objs) == 1


def ghosted(claim: Claim, board: chess.Board) -> bool:
    """A piece the claim names is not where the words put it on *board* (the claim does not bind there)."""
    if claim.rel not in _GHOST_CHECKED:
        return False
    return any(ghost(board, ref) for ref in [claim.subj] + list(claim.objs))


def judge_on(claim: Claim, board: chess.Board, ctx: Any) -> tuple:
    """(True | False | None, truth) of *claim* on one board, negation applied."""
    fn = _JUDGES.get(claim.rel)
    if fn is None:
        return None, ""
    if claim.rel in ("attack", "threat", "capture_with") and _just_took(claim, board):
        return True, ""
    if claim.rel in _GHOST_CHECKED:
        for ref in [claim.subj] + list(claim.objs):
            g = ghost(board, ref)
            if g:
                # «пешка b3 не защищает слона» with no pawn on b3: a denial about a piece that is not there denies
                # nothing about this board.
                return (None, "") if claim.neg else (False, g)
    try:
        v, truth = fn(claim, board, ctx)
    except _Undecided:
        return None, ""
    if claim.neg:
        if v is None:
            return None, ""
        return (not v), ("" if not v else _negated_truth(claim, board, ctx))
    return v, truth


# the relation as a verb, for one piece and for several
_VERB = {"attack": ("attacks", "attack"), "chase": ("attacks", "attack"), "threat": ("attacks", "attack"),
         "aim": ("is on a line with", "are on a line with"), "hold": ("reaches", "reach"), "defend": ("defends", "defend")}


def _negated_truth(claim: Claim, board: chess.Board, ctx: Any = None) -> str:
    """The truth of a denied relation that holds: «конь f6 не защищён» while e7 defends it; «ферзь больше не держит
    a2» while Black's queen on a5 reaches it."""
    s = claim.subj.sq if claim.subj is not None and claim.subj.sq else None
    t = next((o.sq for o in claim.objs if o is not None and o.sq), None)
    if claim.rel in _VERB and t and claim.subj is not None and (claim.subj.sq or claim.subj.piece):
        sq = chess.parse_square(t)
        tp = board.piece_at(sq)
        cands = _candidates(board, claim.subj, _colour(claim.subj, ctx, board))
        if claim.rel == "aim":
            doers = [a for a in cands if _xray(board, a, sq, 1) or _through_king(board, a, sq)]
        elif claim.rel in ("hold", "defend"):
            doers = [a for a in cands if _battery(board, a, sq) or (tp is None and _through_king(board, a, sq))]
        else:
            doers = [a for a in cands if _reaches(board, a, sq) or _through_king(board, a, sq)]
        if doers:
            target = who(board, sq) if tp is not None else chess.square_name(sq)
            return f"{_names(board, doers)} {_VERB[claim.rel][0 if len(doers) == 1 else 1]} {target}"
    if claim.rel in ("undefended", "hanging") and t:
        sq = chess.parse_square(t)
        p = board.piece_at(sq)
        if p is not None:
            return f"{who(board, sq)} is not defended" + (f"; it is attacked by {_names(board, sorted(board.attackers(not p.color, sq)))}"
                                                           if board.attackers(not p.color, sq) else "")
    if claim.rel == "pinned" and t:
        sq = chess.parse_square(t)
        pins = _pinners(board, sq)
        return f"{who(board, sq)} is pinned by {_names(board, pins)}" if pins else f"{who(board, sq)} is pinned"
    if claim.rel == "attacked" and t:
        sq = chess.parse_square(t)
        p = board.piece_at(sq)
        if p is not None:
            return f"{who(board, sq)} is attacked by {_names(board, sorted(board.attackers(not p.color, sq)))}"
    if s and t:
        return f"{who(board, chess.parse_square(s))} does {claim.rel} {who(board, chess.parse_square(t))}"
    return f"the board shows the opposite: the {claim.rel} holds"


# ── plans: empty-board geometry ─────────────────────────────────────────────────────────────────────────────────
def _plan(claim: Claim, ctx: Any = None) -> tuple:
    """A plan («слон на g2 будет бить по e6») or a position the turn cannot build: what the named piece reaches on an
    empty board — false only when no position can make the claim true."""
    s = claim.subj
    objs = [o for o in _targets(claim) if o.sq]
    if claim.rel not in ("attack", "aim", "hold", "plan_reach", "chase", "threat", "defend") or s is None or not s.sq \
            or not s.piece or not objs or claim.neg:
        return None, ""  # a denial («не будет бить») is true in some position whatever the geometry
    pt = PIECE_TYPE[s.piece]
    a = chess.parse_square(s.sq)
    colour = s.side
    if pt == chess.PAWN and colour is None:
        cur = getattr(ctx, "current", None)
        here = cur.piece_at(a) if cur is not None else None
        if here is None or here.piece_type != chess.PAWN:
            return None, ""  # whose pawn, and so its direction, is not told
        colour = here.color
    empty = chess.Board(None)
    empty.set_piece_at(a, chess.Piece(pt, chess.WHITE if colour is None else colour))
    reach = empty.attacks(a)
    for o in objs:
        if chess.parse_square(o.sq) not in reach:
            kind = NAME[pt] if pt != chess.PAWN else f"{_side(colour)} pawn"
            return False, f"a {kind} on {s.sq} never reaches {o.sq}, whatever stands between: " \
                          f"{o.sq} is not on a line or a move of the {NAME[pt]}"
    return True, ""


# ── the decision ────────────────────────────────────────────────────────────────────────────────────────────────
def _rule_judge(claim: Claim) -> Optional[Callable]:
    from src import claim_rules

    return claim_rules.RULE_JUDGES.get(claim.rel)


def _on(claim: Claim, board: chess.Board, ctx: Any, rule: Optional[Callable]) -> tuple:
    if rule is not None:
        try:
            v = rule(claim, board, ctx)
        except Exception:  # noqa: BLE001 — a broken rule judge is undecided, never false
            return None, ""
        status = getattr(v, "status", "undecided")
        return {"true": True, "false": False}.get(status), getattr(v, "truth", "") or ""
    return judge_on(claim, board, ctx)


def decide(claim: Claim, boards: BoardSet, ctx: Any) -> Verdict:
    """The verdict on *claim* over *boards*: false only when false on the primary board, true on no alternative and
    judgeable on the board the coach showed."""
    if claim.question == "yesno" or boards is None:
        return UNDECIDED
    if claim.rel == "plan_reach" or claim.pos.at == "plan" or boards.primary is None:
        if boards.primary is not None and claim.rel != "plan_reach":
            return UNDECIDED
        v, truth = _plan(claim, ctx)
        if v is False:
            return Verdict("false", boards.where or "as a plan", truth)
        return Verdict("true") if v else UNDECIDED
    rule = None
    if claim.rel in RULE_RELATIONS:
        rule = _rule_judge(claim)
        if rule is None:
            return UNDECIDED
    elif claim.rel not in _JUDGES:
        return UNDECIDED
    v, truth = _on(claim, boards.primary, ctx, rule)
    if v is None:
        return UNDECIDED
    if v:
        return Verdict("true", boards.where)
    if boards.shown is not None and boards.shown is not boards.primary:
        sv, _ = _on(claim, boards.shown, ctx, rule)
        if sv is None:
            return UNDECIDED  # the board the coach showed cannot judge it: the claim may be about something else
    # False on the primary board only because a named piece is not there: the words may mean another board where it
    # is — a board on which the claim binds but cannot be judged leaves the claim undecided, not false.
    unbound = rule is None and ghosted(claim, boards.primary)
    # Not one of the pieces the claim names stands where it names them («Удар конём на f7: конь на f7 бьёт ферзя d8 и
    # ладью h8» on a board with none of them): the words describe another position — a line explained, not this board.
    gone = rule is None and _all_gone(claim, boards.primary)
    other = _rebound(claim, boards.primary) if rule is None else None
    if other is not None and _on(other, boards.primary, ctx, rule)[0]:
        return Verdict("true", "")
    if rule is None and any(_on(c, boards.primary, ctx, rule)[0] for c in _from_home(claim, boards.primary)):
        return Verdict("true", "")
    for alt in boards.alternatives:
        if alt is None:
            continue
        av, _ = _on(claim, alt, ctx, rule)
        if av:
            return Verdict("true", "")
        if av is None and unbound and not ghosted(claim, alt):
            return UNDECIDED
    if gone and not any(alt is not None and _binds(claim, alt) for alt in boards.alternatives):
        return UNDECIDED
    if claim.question == "which" and truth:
        truth += " (the question takes this for granted)"
    return Verdict("false", boards.where, truth)


def _from_home(claim: Claim, board: chess.Board) -> list:
    """«Конь с g8 сразу бьёт в e4» with no knight on g8 and no move told: the piece of that kind that came from g8 —
    one standing a move away from it (the knight f6) — read in its place."""
    from dataclasses import replace

    s = claim.subj
    if s is None or not s.from_sq or not s.sq or not s.piece or claim.pos.moves or not ghost(board, s):
        return []
    pt = PIECE_TYPE[s.piece]
    if pt == chess.PAWN:
        return []
    sq = chess.parse_square(s.sq)
    out = []
    for a, p in board.piece_map().items():
        if p.piece_type == pt and (s.side is None or p.color == s.side) and sq in board.attacks(a):
            out.append(replace(claim, subj=replace(s, sq=chess.square_name(a), from_sq=False)))
    return out[:4]


def _binds(claim: Claim, board: chess.Board) -> bool:
    """Every piece the claim names on a square stands there."""
    return not any(ghost(board, r) for r in [claim.subj] + list(claim.objs) if r is not None and r.sq and r.piece)


def _all_gone(claim: Claim, board: chess.Board) -> bool:
    """Two or more pieces named on their squares, and none of them is there."""
    refs = [r for r in [claim.subj] + list(claim.objs) if r is not None and r.sq and r.piece]
    return len(refs) >= 2 and all(ghost(board, r) for r in refs)
