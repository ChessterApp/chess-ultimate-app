"""The position resolver (WP-B): a claim's textual ``Pos`` → the boards it can mean, built from the CheckContext (the
board now, the board the coach showed, the game and the lines of the turn, the line the sentence before told, the
solution lines), and the memory of what a sentence set up for the next one.

    Pos(at, moves, alts, tense, plies_back) ──► BoardSet(primary, where, alternatives, shown)

The primary board is the one the words name; the alternatives are the boards the words may also mean. The judge
(src/claim_judge.py) reports a claim only when it is false on the primary board, true on no alternative and
judgeable on the board the coach showed (plan 30.10, §3.1). So an alternative only ever removes a flag: every
reading the sentence leaves open is one, and a claim that is true in one of them is not cut.

Where the primary board comes from:
  now / after   ctx.current — or the board the coach showed when the board now is only the default initial position —
                then the moves told: a move the game already made → the board right after it; a numbered move → that
                move in a line or game of the turn (or another move played at that point: «на 5-м ходу 5.O-O»); a move
                of the side not to move → its idea, after a null move; a move already on the board → skipped;
  shown(_after) the board the coach showed: a given position other than the board now (not another session's board);
  back          the game's position N plies before the board now (or before the shown board);
  then          the end of the line the sentence before told (this module's memory), else the answer's scene;
  plan          no board: the judge uses empty-board geometry; so does a past the turn has no record of
                (ANY_POSITION): only what no position can make true is false there.
Alternatives (each a reading the words leave open):
  - the «X или Y» branches (Pos.alts); a bare pawn move both sides can make, played for both (unless the turn asks for
    the side to move's move);
  - the board shown, the start position it stands in for, the boards the student's message leads to (a line it
    spells out, a move it names), and the told line played from each of them;
  - in a turn that asks for the solution: the boards after the first one and two moves of the solution lines (or of
    the line the answer tells); with no solution known (voice, a late engine), the boards after the moves the answer
    named so far and after each forcing move of the side to move (a check, a capture, a promotion) — a puzzle answer
    describes the board after its unnamed first move; never for a denial or a «which» presupposition, never every
    legal move (any claim some quiet move makes true would go unreported — review 30.10, miss F1);
  - for a «с sq» subject with no move told, the boards after each legal move of that piece;
  - for the past tense, the game's last two positions;
  - the board just before a told move, when the claim names the square it captured on or the square it left;
  - an implicit move: the named piece is absent and one move (at most MAX_READINGS) puts it on the named square — for
    the subject only when the words tell an intent (aim, threat, chase, the future) or the turn asks for a move; for an
    object only by a capture of the side to move (en passant). A present attack or defence by a piece that is not
    there is the error itself («Пешку d4 защищает конь f3» with Nf3 a move away — review 30.10, miss F2).
A move the words leave ambiguous («конь идёт на b5» with two knights that can) is played every way (MAX_READINGS),
the first the primary board — never as the other side's idea move. The line a sentence without a claim writes is
remembered lazily (played when a later sentence needs it, on the board it was told on).

No BoardSet (None, never reported): an unplayable move, a numbered move from no line the turn has, a «then» with
nothing before it, a skipped Pos, a yes/no question, a claim on the default initial position with no line written
from it (a lesson's diagram told in words, which the turn does not have), and — the board now being that default and
an example board shown — a claim about pieces the example does not have (another diagram of the lesson told in words),
unless the words point at the board («Смотри на доску», Pos.at 'shown').
"""
from __future__ import annotations

import re
from typing import Any, Optional

import chess

from src.claim_types import PIECE_TYPE, BoardSet, Claim, MoveRef, Pos, Ref

# The memory this module keeps in ctx.relation_state (immutable values only; keys namespaced so the parser's own
# memory, src/claim_grammar.py, never collides): the end of the last line a sentence told, as
# (FEN, where, age, FEN before its last move, that move's UCI).
THEN_KEY = "scene.then"
THEN_MAX_AGE = 2  # sentences: «Тогда …» two sentences later still continues that line, three no longer
HISTORY_LOOKBACK = 3  # plies: «чёрные ответили Nc6» names one of the game's last moves
MAX_FROM_SQ_ALTS = 32
MAX_ONE_MOVE_ALTS = 48
# The question asks for the move of the side to move: a bare pawn move in the answer is that side's, not both sides'.
_ASKS_MOVE = re.compile(r"как(?:ой|ая|ие)\s+(?:здесь\s+|тут\s+|теперь\s+|сейчас\s+|у\s+меня\s+)?(?:\w+\s+)?ход|"
                        r"что\s+(?:мне\s+|здесь\s+|тут\s+|теперь\s+)?(?:играть|сыграть|делать|ходить)|как\s+(?:решить|выиграть|"
                        r"мне\s+(?:играть|ходить))|чем\s+(?:ходить|играть)|реши\w*|решени\w*|задач\w*|best\s+move|"
                        r"what\s+(?:should\s+i\s+|to\s+)?play|first\s+move|which\s+move|solve|puzzle", re.IGNORECASE)


_CHOICE = re.compile(r"(?<![\w-])(?:или|либо|or)(?![\w-])|/", re.IGNORECASE)


# ── boards with their story ────────────────────────────────────────────────────────────────────────────────────
def _after(board: chess.Board, move: chess.Move) -> chess.Board:
    """The board after *move*, without a move stack (cheap to copy), remembering the move and the board before it
    (the judge binds «пешка бьёт слона» to the pawn that just moved, the castling rook to the castling)."""
    out = board.copy(stack=False)
    out.push(move)
    out.clear_stack()
    out.rel_last = move  # type: ignore[attr-defined]
    out.rel_prev = board  # type: ignore[attr-defined]
    return out


def last_move(board: chess.Board) -> Optional[chess.Move]:
    """The move that led to *board* in the story the resolver built, if any."""
    return getattr(board, "rel_last", None)


def board_before(board: chess.Board) -> Optional[chess.Board]:
    return getattr(board, "rel_prev", None)


def _key(board: chess.Board) -> tuple:
    """The position as a cheap structural key (pieces and side to move): board_fen() costs ~50 µs a board."""
    return (board.pawns, board.knights, board.bishops, board.rooks, board.queens, board.kings,
            board.occupied_co[chess.WHITE], board.occupied_co[chess.BLACK], board.turn)


def _ctx_key(board: chess.Board) -> str:
    """The key CheckContext files positions under (its shown_keys, state_keys, …)."""
    return board.board_fen() + (" w" if board.turn else " b")


def _passed(board: chess.Board) -> Optional[chess.Board]:
    """The same position with the other side to move (an idea move «...Bg4» while White is to move)."""
    if board.is_check():
        return None
    out = board.copy(stack=False)
    out.push(chess.Move.null())
    out.clear_stack()
    for attr in ("rel_last", "rel_prev"):
        if hasattr(board, attr):
            setattr(out, attr, getattr(board, attr))
    return out


def _num(board: chess.Board) -> str:
    return f"{board.fullmove_number}." if board.turn == chess.WHITE else f"{board.fullmove_number}..."


def _san_where(board: chess.Board, move: chess.Move) -> str:
    try:
        return _num(board) + board.san(move)
    except Exception:  # noqa: BLE001
        return move.uci()


# ── a move told in the text → a move on a board ──────────────────────────────────────────────────────────────────
_RU_LETTERS = str.maketrans({"К": "N", "С": "B", "Л": "R", "Ф": "Q"})


def _clean_san(san: str) -> str:
    t = re.sub(r"^\d{1,3}\s?(?:\.\.\.|…|\.)\s?|^(?:\.\.\.|…)", "", (san or "").strip())
    t = t.replace("Кр", "K").translate(_RU_LETTERS).replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    return t.rstrip("+#!?")


_TO_MOVE: dict = {}  # (position, MoveRef) → move: the same told line is read again sentence after sentence


def to_move(board: chess.Board, m: MoveRef) -> Optional[chess.Move]:
    """*m* as a legal move on *board* (the side to move's), or None: SAN first, then the piece, its square and its
    destination as the words gave them; ambiguous (two knights can go to f6, none named) → None. Memoised by the
    position (pieces, side, castling, en passant) and the MoveRef."""
    try:
        key = (board._transposition_key(), m)
        if key in _TO_MOVE:
            return _TO_MOVE[key]
    except Exception:  # noqa: BLE001 — an unhashable ref: no memo
        return _to_move(board, m)
    got = _to_move(board, m)
    if len(_TO_MOVE) >= 4096:
        _TO_MOVE.clear()
    _TO_MOVE[key] = got
    return got


def _to_move(board: chess.Board, m: MoveRef) -> Optional[chess.Move]:
    if m.castle:
        try:
            return board.parse_san("O-O" if m.castle == "short" else "O-O-O")
        except ValueError:
            return None
    if m.san:
        san = _clean_san(m.san)
        try:
            mv = board.parse_san(san)
            if m.frm and chess.square_name(mv.from_square) != m.frm:
                return None  # «Nd5: конь с f3 прыгает на d5» — the square the words start it from is part of the move
            return mv
        except ValueError:
            pass
        if re.fullmatch(r"[a-h][1-8][-–]?[a-h][1-8]", san):  # «e4-e5», «g8f6»
            fr, to = chess.parse_square(san[:2]), chess.parse_square(san[-2:])
            ms = [x for x in board.legal_moves if x.from_square == fr and x.to_square == to]
            return ms[0] if ms else None
    if not m.to:
        return None
    try:
        to = chess.parse_square(m.to)
        frm = chess.parse_square(m.frm) if m.frm else None
    except ValueError:
        return None
    pt = PIECE_TYPE.get(m.piece or "") if m.piece else None
    ms = [x for x in board.legal_moves if x.to_square == to and (pt is None or board.piece_type_at(x.from_square) == pt)
          and (frm is None or x.from_square == frm) and (not m.capture or board.is_capture(x))]
    if len({(x.from_square, x.to_square) for x in ms}) != 1:
        return None
    queen = [x for x in ms if x.promotion in (None, chess.QUEEN)]
    return (queen or ms)[0]


MAX_READINGS = 4  # a move the words leave ambiguous («конь идёт на b5» with two knights): each reading, up to this many


def move_readings(board: chess.Board, m: MoveRef) -> list:
    """Every legal move of the side to move *m* can name on *board*: one when the words say which, several when they
    do not («Nb5», «конь на b5» with knights on c3 and d4 — each is a reading), [] when none. Ambiguous is not
    illegal: the other side's idea move is no reading of an ambiguous move."""
    one = to_move(board, m)
    if one is not None:
        return [one]
    if m.castle or not m.to:
        return []
    if m.san:
        san = _clean_san(m.san)
        mm = re.fullmatch(r"([KQRBN])?([a-h])?([1-8])?(x)?([a-h][1-8])(?:=([QRBN]))?", san)
        if not mm or (mm.group(2) and mm.group(3)):
            return []
    try:
        to = chess.parse_square(m.to)
        frm = chess.parse_square(m.frm) if m.frm else None
    except ValueError:
        return []
    pt = PIECE_TYPE.get(m.piece or "") if m.piece else None
    out, seen = [], set()
    for x in board.legal_moves:
        if x.to_square != to or (pt is not None and board.piece_type_at(x.from_square) != pt) or \
                (frm is not None and x.from_square != frm) or (m.capture and not board.is_capture(x)) or \
                x.promotion not in (None, chess.QUEEN):
            continue
        if (x.from_square, x.to_square) not in seen:
            seen.add((x.from_square, x.to_square))
            out.append(x)
    return out


def _same_move(board: chess.Board, m: MoveRef, move: chess.Move) -> bool:
    """*m* names *move* played on *board*."""
    if m.castle:
        return board.is_castling(move) and (chess.square_file(move.to_square) > 4) == (m.castle == "short")
    # cheap rejections first (to_move parses SAN against the legal moves)
    if m.to and m.to != chess.square_name(move.to_square):
        return False
    if m.piece and PIECE_TYPE.get(m.piece) != board.piece_type_at(move.from_square):
        return False
    if m.frm and m.frm != chess.square_name(move.from_square):
        return False
    found = to_move(board, m)
    return found is not None and (found == move or (found.from_square, found.to_square) == (move.from_square, move.to_square))


def _repeats(m: MoveRef, board: chess.Board) -> bool:
    """*m* names the move that led to *board* again («h3 — чёрные ответили Nc6: конь с b8 встал на c6»)."""
    last, prev = last_move(board), board_before(board)
    if last is None or prev is None:
        return False
    if m.castle:
        return prev.is_castling(last)
    if not m.to or chess.parse_square(m.to) != last.to_square:
        return False
    pt = PIECE_TYPE.get(m.piece or "") if m.piece else None
    if pt is not None and board.piece_type_at(last.to_square) != pt and not last.promotion:
        return False
    return not m.frm or chess.parse_square(m.frm) == last.from_square


def _already_there(board: chess.Board, m: MoveRef) -> bool:
    """The piece *m* moves already stands on its destination («Я сыграл Qb6» on the board after it)."""
    if m.castle:
        for side in (board.turn, not board.turn):
            rank = 0 if side == chess.WHITE else 7
            king_to = chess.square(6 if m.castle == "short" else 2, rank)
            rook_to = chess.square(5 if m.castle == "short" else 3, rank)
            if board.piece_at(king_to) == chess.Piece(chess.KING, side) and board.piece_at(rook_to) == chess.Piece(chess.ROOK, side):
                return True
        return False
    if not m.to:
        return False
    p = board.piece_at(chess.parse_square(m.to))
    if p is None:
        return False
    pt = PIECE_TYPE.get(m.piece or "P")
    if p.piece_type != pt:
        return False
    return m.side is None or p.color == m.side


# ── the turn's history: the games and lines it has ─────────────────────────────────────────────────────────────
def _records(ctx: Any) -> list:
    """Every line and game the turn has, walked once: [(start, [(board before, move), …])]; cached on the context
    (not in relation_state, which holds only immutable values)."""
    records = getattr(ctx, "line_records", None) or []
    cache = getattr(ctx, "_rel_records", None)
    if cache is not None and cache[0] == len(records):
        return cache[1]
    out = []
    for start, sans in records:
        b = start.copy(stack=False)
        steps = []
        for san in sans:
            try:
                mv = b.parse_san(san)
            except ValueError:
                break
            before = b.copy(stack=False)
            steps.append((before, mv))
            b.push(mv)
        out.append((start, steps, _key(b)))
    try:
        ctx._rel_records = (len(records), out)
    except Exception:  # noqa: BLE001
        pass
    return out


def _history_to(ctx: Any, board: Optional[chess.Board]) -> list:
    """The (board before, move) steps of a game or line the turn has that ends on *board* (its story), else []."""
    if board is None:
        return []
    key = _key(board)
    best: list = []
    for _start, steps, end in _records(ctx):
        if end == key and len(steps) > len(best):
            best = steps
    return best


def _numbered(ctx: Any, m: MoveRef) -> Optional[tuple]:
    """«135...Qg1»: the board right after that move in a line or game of the turn, (board, where), or None."""
    mm = re.fullmatch(r"(\d{1,3})(\.\.\.|\.)", m.number or "")
    if not mm:
        return None
    n, side = int(mm.group(1)), chess.BLACK if mm.group(2) == "..." else chess.WHITE
    at = []
    for _start, steps, _end in _records(ctx):
        for before, mv in steps:
            if before.fullmove_number == n and before.turn == side:
                if _same_move(before, m, mv):
                    return _after(before, mv), f"right after {_san_where(before, mv)} was played"
                at.append((before, mv))
    # «на 5-м ходу надо было играть 5.O-O»: another move at that point of the game — the board after it.
    for before, played in at:
        mv = to_move(before, m)
        if mv is not None:
            return _after(before, mv), f"after {_san_where(before, mv)} (instead of {_san_where(before, played)})"
    return None


def _has_number(ctx: Any, n: int, side: bool) -> bool:
    """A line or game of the turn has a move numbered *n* for *side*."""
    return any(before.fullmove_number == n and before.turn == side for _s, steps, _e in _records(ctx) for before, _mv in steps)


def _shown_boards(ctx: Any) -> list:
    """The boards the coach showed this turn other than the board now: positions given as positions (not a line's
    passing positions, not a tool's text, not another session's board, not the start position the context adds)."""
    cur = getattr(ctx, "current", None)
    shown = getattr(ctx, "shown_keys", set()) or set()
    state = getattr(ctx, "state_keys", set()) or set()
    given = getattr(ctx, "given", set()) or set()
    other = getattr(ctx, "other_board_keys", set()) or set()
    text = getattr(ctx, "text_keys", set()) or set()
    boards = getattr(ctx, "boards", None) or []
    sig = (id(cur), len(boards), len(shown), len(state), len(given), len(other), len(text))
    cache = getattr(ctx, "_rel_shown", None)
    if cache is not None and cache[0] == sig:
        return cache[1]
    keys = (shown & state & given) - other - text
    keys.discard(_ctx_key(chess.Board()))
    if cur is not None:
        keys.discard(_ctx_key(cur))
    out = []
    if keys:
        want = set()
        for k in keys:
            try:
                want.add(_key(chess.Board(k + " - - 0 1")))
            except ValueError:
                continue
        for b in boards:
            if b is not cur and _key(b) in want and _ctx_key(b) in keys:
                out.append(b)
    try:
        ctx._rel_shown = (sig, out)
    except Exception:  # noqa: BLE001
        pass
    return out


def _question_boards(ctx: Any) -> list:
    """The positions the student's message leads to when they are not the board now — «the board» of the answer may
    be any of them: the end of a line it spells out («1. e4 e5 2. Кf3 Кc6 3. Сb5 — что это?»), and the board after
    each move it names that is legal now («А если бы я сейчас сыграл Кg5?», «d4»: the student's idea, which the server
    also passes as the board after it). Cached on the context."""
    q = getattr(ctx, "question_raw", "") or ""
    cache = getattr(ctx, "_rel_qboards", None)
    if cache is not None and cache[0] == q:
        return cache[1]
    out: list = []
    cur = getattr(ctx, "current", None)
    if q and re.search(r"[a-h][1-8]|O-O|0-0", q.replace("е", "e").replace("с", "c").replace("а", "a")):
        try:
            from src.answer_check import _MOVE, _to_san

            converted, _ = _to_san(q)
            converted = converted.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
            sans = [m.group("san") for m in _MOVE.finditer(converted)]
            if re.search(r"(?<![0-9])1\s?\.", q) and len(sans) >= 2:
                for start in (chess.Board(), cur):
                    if start is None:
                        continue
                    b = start.copy(stack=False)
                    try:
                        for san in sans:
                            b.push_san(san)
                    except ValueError:
                        continue
                    b.clear_stack()
                    out.append(b)
                    break
            if cur is not None:
                for san in sans[:4]:
                    try:
                        mv = cur.parse_san(san)
                    except ValueError:
                        continue
                    out.append(_after(cur, mv))
        except Exception:  # noqa: BLE001
            out = []
    if cur is not None:
        out = [b for b in out if _key(b) != _key(cur)]
    try:
        ctx._rel_qboards = (q, out)
    except Exception:  # noqa: BLE001
        pass
    return out


def _side_fixed(ctx: Any) -> bool:
    """The turn asks for the side to move's move (a puzzle, «какой здесь первый ход», a solution on the board): a
    bare pawn move in the answer is that side's."""
    if getattr(ctx, "puzzle_solution", None) or getattr(ctx, "solution_lines", None):
        return True
    return _asks_move(ctx)


# ── playing a line ───────────────────────────────────────────────────────────────────────────────────────────────
class _Unplayable(Exception):
    pass


def _play(board: chess.Board, m: MoveRef, ctx: Any, history: list, first: bool, loose: bool = False) -> list:
    """The boards after *m* from *board*: [(board, where)], the first the reading the words name, the rest the other
    readings (a bare pawn move both sides can make). [] when the move is already on the board (skipped). Raises
    _Unplayable when no reading plays it."""
    # A move the game made: the board right after it («чёрные ответили Nc6», «c4 — идея …» told about the game). A
    # numbered move is that move at that number only (below).
    if history and not m.number:
        here = _key(board)
        idx = next((i for i, (b0, _mv) in enumerate(history) if _key(b0) == here), None)
        if idx is not None:
            b0, mv = history[idx]
            if _same_move(b0, m, mv):
                return [(_after(b0, mv), f"right after {_san_where(b0, mv)} was played")]
        if first:
            for b0, mv in reversed(history[-HISTORY_LOOKBACK:]):
                if _same_move(b0, m, mv):
                    return [(_after(b0, mv), f"right after {_san_where(b0, mv)} was played")]
    if m.number:
        hit = _numbered(ctx, m)
        if hit is not None:
            return [hit]
        mm = re.fullmatch(r"(\d{1,3})(\.\.\.|\.)", m.number)
        if mm and (int(mm.group(1)) != board.fullmove_number
                   or (chess.BLACK if mm.group(2) == "..." else chess.WHITE) != board.turn):
            n, side = int(mm.group(1)), chess.BLACK if mm.group(2) == "..." else chess.WHITE
            # «После 3.Bg5» on move 2: a move number off by one (models miscount) is the move on this board, when no
            # line of the turn has that move number and the move is legal here
            if not loose or side != board.turn or abs(n - board.fullmove_number) > 1 or _has_number(ctx, n, side):
                raise _Unplayable(f"{m.number} is from a line the turn does not have")
    out = []
    readings = [] if (m.side is not None and m.side != board.turn) else move_readings(board, m)
    if len(readings) > MAX_READINGS:
        raise _Unplayable(f"{m.san or m.to}: too many readings")
    if len(readings) > 1:
        # «конь идёт на b5» with two knights that can: each move is a reading (the first the primary board) — never
        # the other side's idea move instead
        return [(_after(board, x), "after " + _san_where(board, x)) for x in readings]
    mine = readings[0] if readings else None
    if mine is not None:
        out.append((_after(board, mine), "after " + _san_where(board, mine)))
    other_side = _passed(board)
    theirs = None
    if other_side is not None and (m.side is None or m.side == other_side.turn):
        theirs = to_move(other_side, m)
        if theirs is None and mine is None and len(move_readings(other_side, m)) > 1:
            raise _Unplayable(f"{m.san or m.to}: whose and which piece the words do not say")
    if mine is None and theirs is not None:
        out.append((_after(other_side, theirs), "after the idea " + _san_where(other_side, theirs)))
    elif mine is not None and theirs is not None and _bare_pawn(m) and not _side_fixed(ctx):
        # «Ход a5» on a board where both sides can play a5: whose pawn the words do not say — both readings.
        out.append((_after(other_side, theirs), "after " + _san_where(other_side, theirs)))
    if out:
        return out
    if _already_there(board, m) or _repeats(m, board):
        return []
    raise _Unplayable(f"{m.san or m.to} cannot be played")


def _bare_pawn(m: MoveRef) -> bool:
    return (m.piece in (None, "P")) and not m.capture and not m.number and m.side is None and not m.castle and \
        bool(m.to) and not m.frm and bool(m.san) and re.fullmatch(r"[a-h][1-8]", _clean_san(m.san) or "") is not None


def _walk(base: chess.Board, where: str, moves: tuple, ctx: Any, history: list, loose: bool = False) -> Optional[list]:
    """Every reading of *moves* played from *base*: [[(board, where), …] per branch, its positions in order], the
    first branch the words' own reading; None when the line cannot be played."""
    branches = [[(base, where)]]
    for i, m in enumerate(moves):
        nxt = []
        for path in branches:
            board, w = path[-1]
            if i > 0 and _repeats(m, board):
                nxt.append(path)  # the move told again in words
                continue
            try:
                steps = _play(board, m, ctx, history if i == 0 or w.startswith("right after") else
                              _history_from(board, history), i == 0, loose)
            except _Unplayable:
                if path is branches[0]:
                    return None
                continue
            if not steps:
                nxt.append(path)
                continue
            nxt.extend(path + [s] for s in steps)
        if not nxt:
            return None
        branches = nxt
    return branches


def _history_from(board: chess.Board, history: list) -> list:
    """The game's steps from *board* on, when *board* is one of its positions (the line goes on along the game)."""
    k = _key(board)
    for i, (b0, _mv) in enumerate(history):
        if _key(b0) == k:
            return history[i:]
    return []


# ── the base board of each position kind ────────────────────────────────────────────────────────────────────────
class _Frozen:
    """The context as it was when a told line was remembered: the answer's scene then, not now (a lazy told line is
    played only when a later sentence needs it — most never do)."""

    def __init__(self, ctx: Any):
        object.__setattr__(self, "_ctx", ctx)

    def __getattr__(self, name):
        if name in ("forced_line", "scene_before"):
            return None
        return getattr(object.__getattribute__(self, "_ctx"), name)

    def __setattr__(self, name, value):  # the caches go to the real context
        setattr(object.__getattribute__(self, "_ctx"), name, value)


def _materialize(then: tuple, ctx: Any) -> Optional[tuple]:
    """A lazy told line ``(None, 'lazy', age, moves, base, before)`` as the concrete memory ``(fen, where, age, fen
    before, uci)``: the line played on the board it was told on (*base*, frozen as FEN when it was told), its age
    the lazy record's; when it cannot be played, the memory there was before it (*before*), aged as if kept. Cached
    on the context."""
    cache = getattr(ctx, "_rel_lazy", None)
    if cache is None:
        cache = {}
        try:
            ctx._rel_lazy = cache
        except Exception:  # noqa: BLE001
            pass
    key = then[3:5]
    if key in cache:
        got = cache[key]
    else:
        moves, base = then[3], then[4]
        got = None
        try:
            res = _resolve(Pos(at="now", moves=moves), ctx if base else _Frozen(ctx), {THEN_KEY: base} if base else {})
        except Exception:  # noqa: BLE001
            res = None
        if res is not None and last_move(res[0]):
            prev, last = board_before(res[0]), last_move(res[0])
            got = (res[0].fen(), res[1], 0, prev.fen() if prev is not None else "", last.uci())
        if len(cache) < 64:
            cache[key] = got
    if got is not None:
        return got[:2] + (then[2],) + tuple(got[3:])
    before = then[5]
    if not before:
        return None
    return before[:2] + (before[2] + then[2] + 1,) + tuple(before[3:])


def _then_board(ctx: Any, state: dict) -> Optional[tuple]:
    """The end of the line the sentence before told: this module's memory, else the answer's scene."""
    then = state.get(THEN_KEY) if isinstance(state, dict) else None
    if then and then[1] == "lazy":
        then = _materialize(then, ctx)
    if then:
        fen, where, age = then[:3]
        if age <= THEN_MAX_AGE:
            try:
                board = chess.Board(fen)
                if len(then) > 4 and then[3] and then[4]:  # the board before its last move, and that move
                    prev = chess.Board(then[3])
                    board.rel_last, board.rel_prev = chess.Move.from_uci(then[4]), prev  # type: ignore[attr-defined]
                return board, where
            except ValueError:
                pass
    forced = getattr(ctx, "forced_line", None)
    if forced and forced[0] is not None and forced[2] <= THEN_MAX_AGE:
        return _with_story(forced[0]), "at the end of the line before"
    before = getattr(ctx, "scene_before", None)
    if before and before[0] is not None and before[2] <= THEN_MAX_AGE:
        return _with_story(before[0]), f"after {before[1]}" if before[1] else "at the end of the line before"
    return None


def _with_story(board: chess.Board) -> chess.Board:
    """A copy of a scene board without its stack, remembering its last move and the board before it."""
    out = board.copy(stack=False)
    if board.move_stack:
        prev = board.copy()
        mv = prev.pop()
        prev = prev.copy(stack=False)
        out.rel_last, out.rel_prev = mv, prev  # type: ignore[attr-defined]
    return out


def _back(ctx: Any, board: Optional[chess.Board], plies: int) -> Optional[chess.Board]:
    hist = _history_to(ctx, board)
    if plies <= 0 or len(hist) < plies:
        return None
    return hist[len(hist) - plies][0].copy(stack=False)


def _base(pos: Pos, ctx: Any, state: dict) -> Optional[tuple]:
    """(board, where, history) the moves of *pos* start from, or None."""
    cur = getattr(ctx, "current", None)
    shown = _shown_boards(ctx)
    if pos.at in ("now", "after"):
        if cur is None:
            return None
        if shown and _bare_start(cur, ctx):
            # The board now is only the default initial position (no game, no line) and the coach showed a board
            # this turn: that board is the one the answer is about.
            return shown[0], "on the board shown", _history_to(ctx, shown[0])
        return cur, "on the board now", _history_to(ctx, cur)
    if pos.at in ("shown", "shown_after"):
        board = shown[0] if shown else cur
        if board is None:
            return None
        where = "on the board shown" if shown else "on the board now"
        if pos.plies_back:
            before = _back(ctx, board, pos.plies_back)
            if before is None:
                return None
            return before, f"{pos.plies_back} {'ply' if pos.plies_back == 1 else 'plies'} before the board shown", []
        return board, where, _history_to(ctx, board)
    if pos.at == "back":
        before = _back(ctx, cur, pos.plies_back or 1)
        if before is None:
            return None
        n = pos.plies_back or 1
        return before, f"{n} {'ply' if n == 1 else 'plies'} ago", _history_to(ctx, before)
    if pos.at == "then":
        got = _then_board(ctx, state)
        if got is None:
            return None
        return got[0], got[1], []
    return None


# ── the subject's square, for the implicit move and the from-square boards ──────────────────────────────────────
def _ref_square(ref) -> Optional[tuple]:
    if ref is None or not ref.sq or not ref.piece:
        return None
    try:
        return chess.parse_square(ref.sq), PIECE_TYPE[ref.piece]
    except (ValueError, KeyError):
        return None


# Relations that tell what a piece is set to do (an aim, a threat, a chase, a plan): the words may place the piece
# where its move puts it. Present-tense attack/defence of a piece that is not there is the very error the claim makes
# («Пешку d4 защищает конь f3» with no knight on f3, Nf3 a move away).
_INTENT_RELATIONS = ("aim", "threat", "chase", "plan_reach")


def _implicit(board: chess.Board, claim: Claim, ctx: Any = None) -> list:
    """The named piece is absent and one move (at most MAX_READINGS legal moves) puts it on the named square: the
    boards after them — alternatives, never the primary board. For the subject only when the words tell an intent (an
    aim, a threat, a chase, the future) or the turn asks for the move (the answer may describe the board after the
    move it recommends: «Конь на b5 атакует d6 и c7» answering «Куда пойти конём?»). For an object only when a
    capture of the side to move puts it there («пешку d6 никто не защищает» answering about exd6 e.p.)."""
    if claim.rel in ("occupied",):
        return []
    refs = []
    if claim.rel in _INTENT_RELATIONS or claim.pos.tense == "future" or (ctx is not None and _asks_move(ctx)):
        refs.append((claim.subj, False))
    if claim.pos.at == "now" and not claim.pos.moves:
        refs += [(o, True) for o in claim.objs]
    out = []
    for ref, capture_only in refs:
        got = _ref_square(ref)
        if got is None:
            continue
        sq, pt = got
        p = board.piece_at(sq)
        if p is not None and p.piece_type == pt:
            continue
        side = ref.side
        for b in (board, _passed(board)):
            if b is None or (side is not None and b.turn != side) or (capture_only and b is not board):
                continue
            ms = [m for m in b.legal_moves if m.to_square == sq and b.piece_type_at(m.from_square) == pt
                  and m.promotion in (None, chess.QUEEN) and (not capture_only or b.is_capture(m))]
            if 1 <= len(ms) <= MAX_READINGS:
                out.extend(_after(b, m) for m in ms)
                break
    return out


def _from_square(board: chess.Board, claim: Claim) -> list:
    """«конь с g5 нападает на …» with no move told: the boards after each legal move of the piece on g5 — the words
    may describe it where it goes (prevent's one-move rule, restricted to the named piece)."""
    s = claim.subj
    if s is None or not s.from_sq or not s.sq:
        return []
    sq = chess.parse_square(s.sq)
    p = board.piece_at(sq)
    if p is None:
        return []
    b = board if board.turn == p.color else _passed(board)
    if b is None:
        return []
    out = []
    for m in b.legal_moves:
        if m.from_square == sq and m.promotion in (None, chess.QUEEN):
            out.append(_after(b, m))
            if len(out) >= MAX_FROM_SQ_ALTS:
                break
    return out


def _solution_boards(ctx: Any, cur: chess.Board) -> list:
    """The boards after the first one and two moves of the solution lines: a puzzle answer that describes the board
    after its unnamed solution move («ферзь e5 атакован» after the unnamed 1.f4)."""
    lines = [list(x) for x in (getattr(ctx, "solution_lines", None) or []) if x]
    sol = getattr(ctx, "puzzle_solution", None)
    if sol:
        lines.append(list(sol))
    out, seen = [], set()
    for line in lines:
        b = cur
        for san in line[:2]:
            try:
                mv = b.parse_san(_clean_san(san) if not san.startswith("O-O") else san.rstrip("+#!?"))
            except ValueError:
                break
            b = _after(b, mv)
            k = _key(b)
            if k not in seen:
                seen.add(k)
                out.append(b)
    return out


def _asks_move(ctx: Any) -> bool:
    """The student's message asks for the move (a puzzle, «какой здесь первый ход», «что играть», «Белые начинают и
    выигрывают», «Найди двойной удар»): this module's words and the wiring's (one notion of «asks for a move»)."""
    q = getattr(ctx, "question_raw", "") or getattr(ctx, "question", "") or ""
    if _ASKS_MOVE.search(q):
        return True
    from src.answer_check_relations import asks_for_a_move

    return asks_for_a_move(q)


NAMED_KEY = "scene.named"  # (UCI, …): the moves of the board now the answer's sentences named so far
MAX_NAMED = 8


def _unnamed_solution_boards(board: chess.Board, state: dict, ctx: Any = None) -> list:
    """With the solution unknown, the boards an answer about its unnamed first move may describe: after each move of
    the board now the answer named so far («Лучший ход — Nf3. Конь там …»), and after each forcing move of the side to
    move (a check, a capture, a promotion — the first move of a tactic). Not every legal move: any claim some quiet
    move makes true would never be reported. Cached on the context per board and named moves."""
    named = tuple((state.get(NAMED_KEY) or ()) if isinstance(state, dict) else ())
    cache = getattr(ctx, "_rel_unnamed", None) if ctx is not None else None
    if cache is not None and cache[0] == (id(board), named):
        return cache[1]
    out = _unnamed_now(board, named)
    if ctx is not None:
        try:
            ctx._rel_unnamed = ((id(board), named), out)
        except Exception:  # noqa: BLE001
            pass
    return out


def _unnamed_now(board: chess.Board, named: tuple) -> list:
    out, seen = [], set()
    for uci in named:
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError:
            continue
        if mv in board.legal_moves and mv not in seen:
            seen.add(mv)
            out.append(_after(board, mv))
    for m in board.legal_moves:
        if m in seen or m.promotion not in (None, chess.QUEEN):
            continue
        if m.promotion or board.is_capture(m) or board.gives_check(m):
            seen.add(m)
            out.append(_after(board, m))
            if len(out) >= MAX_ONE_MOVE_ALTS:
                break
    return out


def _remember_named(text: str, ctx: Any, state: dict) -> None:
    """Add the moves of the board now that *text* names (each read one way) to NAMED_KEY."""
    cur = getattr(ctx, "current", None)
    if cur is None or not re.search(r"[a-h][1-8]|O-O|0-0", text or "") or not _asks_move(ctx):
        return  # (read only where the turn asks for the move: _unnamed_solution_boards)
    from src.claim_grammar import written_moves

    try:
        found = written_moves(text)
    except Exception:  # noqa: BLE001
        return
    named = list(state.get(NAMED_KEY) or ())
    for m in found:
        try:
            got = move_readings(cur, m)
        except Exception:  # noqa: BLE001
            continue
        if len(got) == 1 and got[0].uci() not in named:
            named.append(got[0].uci())
    if named:
        state[NAMED_KEY] = tuple(named[-MAX_NAMED:])


def _past_boards(ctx: Any, cur: chess.Board) -> Optional[list]:
    hist = _history_to(ctx, cur)
    if not hist:
        return None
    return [b0.copy(stack=False) for b0, _mv in hist[-2:]]


# A position the turn cannot build (the past with no record of it): the judge decides only what holds in every
# position — the empty-board geometry of the named piece («пешка b2 прикрывала c2» is false whatever the board).
ANY_POSITION = BoardSet(primary=None, where="in any position")


_START = _key(chess.Board())[:-1]


def _bare_start(cur: Optional[chess.Board], ctx: Any) -> bool:
    """The board now is the initial position by default: nothing was played to reach it (no game is on it)."""
    return cur is not None and _key(cur)[:-1] == _START and not getattr(ctx, "game_moves", None)


def _diagram_only(claim: Claim, primary: chess.Board, cur: Optional[chess.Board], shown: list, ctx: Any) -> bool:
    """The board now is the initial position by default (no game, no line, no board shown: a lesson or a concept told
    in words) and the claim is not about a line written from it: the answer describes a diagram the turn does not
    have («слон чёрных на c4 прикрывает своего короля на c7», «Лучше всего Кс3: … нападает на слона»), not this
    board. A line from the start («после 1.e4 e5 2.Кf3 конь нападает на e5») is still judged."""
    if shown or not _bare_start(cur, ctx):
        return False
    moves = claim.pos.moves
    if claim.pos.at in ("now", "after") and (len(moves) >= 2 or any(m.number for m in moves)):
        return False
    return True


# ── entry points ─────────────────────────────────────────────────────────────────────────────────────────────────
def _resolve(pos: Pos, ctx: Any, state: dict) -> Optional[tuple]:
    """(primary, where, alternatives) of one Pos, without the context's own alternatives; memoised on the context
    for the sentence (the claims of one sentence share their Pos, and remember() resolves it again)."""
    cur = getattr(ctx, "current", None)
    sig = (id(cur), len(getattr(ctx, "boards", None) or ()), len(getattr(ctx, "line_records", None) or ()),
           id(getattr(ctx, "scene_before", None)), id(getattr(ctx, "forced_line", None)),
           state.get(THEN_KEY) if isinstance(state, dict) else None)
    memo = getattr(ctx, "_rel_memo", None)
    if memo is None or memo[0] != sig:
        memo = (sig, {})
        try:
            ctx._rel_memo = memo
        except Exception:  # noqa: BLE001
            pass
    try:
        if pos in memo[1]:
            got = memo[1][pos]
            return None if got is None else (got[0], got[1], list(got[2]))
    except TypeError:  # an unhashable Pos (a list where a tuple belongs): no memo
        return _resolve_now(pos, ctx, state)
    got = _resolve_now(pos, ctx, state)
    if len(memo[1]) < 64:
        memo[1][pos] = None if got is None else (got[0], got[1], tuple(got[2]))
    return got


def _resolve_now(pos: Pos, ctx: Any, state: dict) -> Optional[tuple]:
    base = _base(pos, ctx, state)
    if base is None:
        return None
    board, where, history = base
    if not pos.moves:
        return board, where, []
    branches = _walk(board, where, pos.moves, ctx, history)
    if branches is not None and len(branches[0]) == 1 and pos.at in ("now", "after") and \
            any(board is b for b in _shown_boards(ctx)) and _bare_start(getattr(ctx, "current", None), ctx):
        # Every move told is "already on" a lesson's example board, which has no story: the board cannot say whether
        # the move was played on it or the words propose it on another diagram of the lesson («Сравните варианты за
        # белых: … Ла1 защищает коня … Кс3 нападает на слона» on a board where Ra1 and Nc3 already stand).
        return None
    if branches is None and pos.at in ("now", "after"):
        # The move is not playable on the board now but is on the board shown (or after the line before): the
        # sentence is about that board.
        then = _then_board(ctx, state)
        for alt in [(b, "on the board shown") for b in _shown_boards(ctx)] + ([then] if then else []):
            branches = _walk(alt[0], alt[1], pos.moves, ctx, [])
            if branches is not None:
                break
    if branches is None and pos.at in ("now", "after") and any(m.number for m in pos.moves):
        # «После 3.Bg5 …» on move 2 with no line of the turn at move 3: a number off by one, read on this board — only
        # when no board of the turn has the line as written
        branches = _walk(board, where, pos.moves, ctx, history, loose=True)
    if branches is None:
        return None
    main = branches[0]
    primary, pwhere = main[-1]
    alts = [path[-1][0] for path in branches[1:]]
    # A turn that asks for the solution (a puzzle, «какой здесь первый ход»): the line the answer tells is that
    # solution, and its narration («в это время …») may describe the board after its first or second move, as for
    # the solution lines of the context.
    if _side_fixed(ctx):
        for path in branches:
            alts.extend(b for b, _w in path[1:3] if b is not path[-1][0])
    # The same line told from the other boards of the turn — the board shown, the board after the student's own
    # move: the words do not say which board the line starts from.
    if pos.at in ("now", "after"):
        for other in _shown_boards(ctx) + _question_boards(ctx):
            if other is board:
                continue
            more = _walk(other, "", pos.moves, ctx, [])
            if more is not None:
                alts.extend(path[-1][0] for path in more)
    if primary is board and len(main) == 1:
        pwhere = where
    return primary, pwhere, alts


def _before_last(primary: chess.Board, claim: Claim) -> list:
    """«Qxf7# — ферзь бьёт на f7, … пешка f7 прикрыта только королём», «Nxd4: ты забираешь коня, который нападал на
    твоего коня f3»: a sentence that tells a move describes the board just before it when it names the square the move
    captured on or the square the moving piece left — what was there is gone after it."""
    mv, prev = last_move(primary), board_before(primary)
    if mv is None or prev is None:
        return []
    named = {chess.parse_square(r.sq) for r in [claim.subj] + list(claim.objs) + [claim.to] if r is not None and r.sq}
    captured = prev.piece_at(mv.to_square) is not None or prev.is_en_passant(mv)
    if (captured and mv.to_square in named) or (mv.from_square in named and not _from_sq_mover(claim, mv)):
        return [prev]
    return []


def _words_only_diagram(claim: Claim, primary: chess.Board, cur: Optional[chess.Board], shown: list, ctx: Any) -> bool:
    """A lesson or a concept with an example board shown (the board now is only the default initial position) and a
    claim, with no move told, about pieces that are not on that board: the words describe another diagram of the
    lesson («в продолжении урока … слон b2 связывает пешку g7»), which the turn does not have. A piece of the right
    kind but the wrong side is still judged («чёрный король на g2» where White's king stands), and so is a claim whose
    words point at the board shown («Смотри на доску: …», Pos.at 'shown')."""
    if not shown or not _bare_start(cur, ctx) or claim.pos.moves or claim.pos.at != "now" or \
            not any(primary is b for b in shown):
        return False
    for ref in [claim.subj] + list(claim.objs):
        got = _ref_square(ref)
        if got is None:
            continue
        p = primary.piece_at(got[0])
        if p is None or p.piece_type != got[1]:
            return True
    return False


def _from_sq_mover(claim: Claim, mv: chess.Move) -> bool:
    s = claim.subj
    return s is not None and s.from_sq and bool(s.sq) and chess.parse_square(s.sq) == mv.from_square


def boards_for(claim: Claim, ctx: Any, state: dict) -> Optional[BoardSet]:
    """The boards *claim* is about, or None when its position cannot be built (an unplayable move, the past with no
    history, a skipped claim): an unresolved claim is never reported."""
    pos = claim.pos
    if claim.question == "yesno":
        return None
    state = state if isinstance(state, dict) else {}
    if claim.kind == "idea_scope":
        return _idea_boards(claim, ctx, state)
    if pos.at == "skip":
        return _line_boards(claim, ctx, state)
    if pos.at == "plan":
        return BoardSet(primary=None, where="as a plan")
    if no_longer(claim, state):
        loaded = _loaded_before(claim, ctx, state)
        if loaded is not None:
            # «Ферзь пожертвован, чтобы ладья больше не защищала поле d8»: the board before the told move of the game
            # the turn loaded — the judge reads the relation the denial presupposes there (claim_judge, no_longer)
            return BoardSet(primary=loaded[0], where=loaded[1])
    got = _resolve(pos, ctx, state)
    if got is None:
        if pos.at in ("back", "shown") and pos.plies_back and not pos.moves:
            return ANY_POSITION  # an earlier position the turn has no record of
        return None
    primary, where, alts = got
    for alt_pos in pos.alts:
        other = _resolve(alt_pos, ctx, state)
        if other is not None:
            alts.append(other[0])
            alts.extend(other[2])
        elif any(m.number for m in alt_pos.moves):
            # «The knight on f7 attacks the queen on d8 …, so Black takes it: 6...Kxf7» with no 6...Kxf7 on any board
            # of the turn: the sentence is about a line the turn does not have.
            return None
    cur = getattr(ctx, "current", None)
    shown = _shown_boards(ctx)
    shown_board = None
    if pos.at in ("shown", "shown_after") and not pos.moves and not pos.plies_back and shown:
        shown_board = primary
    if _diagram_only(claim, primary, cur, shown, ctx) or _words_only_diagram(claim, primary, cur, shown, ctx):
        cued = _start_cued(claim, primary, where, alts, ctx, state)
        if cued is None:
            return None
        # «Сейчас, в самом начале партии, … поле занято своими же фигурами»: the words point at the board the turn
        # has (start_cue) — judged there, with the alternatives the words leave open
        primary, where, alts = cued
        then = _then_board(ctx, state)
        alts = alts + ([then[0]] if then is not None else []) + _question_boards(ctx) + _from_square(primary, claim)
        return BoardSet(primary=primary, where=where, alternatives=tuple(alts + _implicit(primary, claim, ctx)))
    if cur is not None and primary is cur and pos.at in ("now", "after") and _earlier_moment(ctx, primary):
        from src.claim_judge import _binds, ghosted

        if ghosted(claim, primary) and \
                not any(_binds(claim, b) for b in _question_boards(ctx) + (_past_boards(ctx, primary) or [])):
            # «А что было бы, если бы на 8-м ходу я взял слоном на g5?», «А что надо было играть на 5-м ходу?» on a board
            # without that moment: a piece the claim names and the board now lacks stands on the board the question
            # is about, which the turn does not have.
            return None
    if pos.at == "now" and not pos.moves:
        if pos.tense == "past":
            past = _past_boards(ctx, primary)
            if past is None:
                # «конь f6 держал поле g6»: a past we have no record of — only what no position can make true.
                return ANY_POSITION
            alts.extend(past)
        alts.extend(shown)
        shown_board = shown[0] if shown else None
        if cur is not None and primary is not cur and pos.at == "now":
            alts.append(cur)
        then = _then_board(ctx, state)
        if then is not None:
            # «Да, есть — Nc7+. Это вилка: конь бьёт и короля на e8, и ладью на a8»: the sentence after a told move may
            # describe the board after it.
            alts.append(then[0])
        if pos.tense != "past":
            from src.claim_judge import ghosted

            if ghosted(claim, primary):
                # A piece the claim names is not on the board now but the game's last positions may have it: the
                # words describe the move just made («его пешка d5 бьёт по e4 и по твоему слону» told about ...dxc4).
                alts.extend(_past_boards(ctx, primary) or [])
        alts.extend(_question_boards(ctx))
        if cur is not None and primary is cur:
            sol = _solution_boards(ctx, cur)
            if not sol and _asks_move(ctx) and not claim.neg and claim.question != "which":
                # The turn asks for the move and its solution is not known here (voice, a late engine): the answer
                # may describe the board after its unnamed first move — one it named, or a forcing one. A denial or
                # a «which» presupposition is about the board now.
                sol = _unnamed_solution_boards(cur, state, ctx)
            alts.extend(sol)
        alts.extend(_from_square(primary, claim))
    if pos.moves or pos.at == "then":
        alts.extend(_before_last(primary, claim))
    alts.extend(_implicit(primary, claim, ctx))
    return BoardSet(primary=primary, where=where, alternatives=tuple(alts), shown=shown_board)


def remember(text: str, claims: list[Claim], ctx: Any, state: dict) -> None:
    """Record in *state* what the next sentence may refer to: the end of the line this sentence told (a «Тогда …»
    goes on from there), aged by one sentence each time. Only immutable values go into *state*: ``check_sentence``
    restores a shallow copy when the sentence is cut."""
    if not isinstance(state, dict):
        return
    try:
        _remember_named(text, ctx, state)
    except Exception:  # noqa: BLE001
        pass
    told = None
    for c in claims:
        if c.pos.moves and c.pos.at in ("now", "after", "then", "shown_after"):
            try:
                got = _resolve(c.pos, ctx, state)
            except Exception:  # noqa: BLE001
                got = None
            if got is not None:
                prev, last = board_before(got[0]), last_move(got[0])
                told = (got[0].fen(), got[1], 0, prev.fen() if prev is not None else "", last.uci() if last else "")
    if told is None:
        told = _told_line(text, ctx, state)
    if told is None:
        told = _told_bare_line(text, ctx, state)
    try:
        _remember_advice(text, ctx, state)
        idea = _remember_idea(text, ctx, state)
    except Exception:  # noqa: BLE001
        idea = None
    if idea is not None:
        told = idea  # «А почему не Nxd4 сразу?»: the next sentence is about the board after 3...Nxd4, and only it
    if told is not None:
        state[THEN_KEY] = told
    elif state.get(THEN_KEY):
        then = state[THEN_KEY]
        if then[2] + 1 > THEN_MAX_AGE:
            state.pop(THEN_KEY, None)
        else:
            state[THEN_KEY] = then[:2] + (then[2] + 1,) + tuple(then[3:])


__all__ = ["boards_for", "remember", "to_move", "last_move", "board_before", "THEN_KEY"]


def _told_line(text: str, ctx: Any, state: dict) -> Optional[tuple]:
    """The end of the line a sentence with no claim writes («Да, есть — но только одна: Nc7+.», «Чёрные вынуждены
    взять: Kxh7», «Сыграй d3.»), as remember() keeps it; None when it writes none or it cannot be played. A bare square
    is a move only where the parser's words make it one (claim_grammar.written_moves)."""
    from src.claim_grammar import written_moves

    try:
        # what is written as a move: a piece letter, a capture, a check, castling, a move number, «e4-e5», a move told
        # in words, a bare square the words make a move («Сыграй d3. Тогда …», «Лучший ход — d3»)
        moves = written_moves(text)
    except Exception:  # noqa: BLE001
        return None
    if not moves or len(moves) > 8:
        return None
    if len(moves) > 1 and _CHOICE.search(text):
        return None  # «У чёрных всего два ответа: Крg5 или Л:h7» — choices, not a line
    # Played later, when a sentence needs it (_then_board): on the board the line was told on — the line the sentence
    # before told, else the answer's scene then, kept here as FEN.
    prev_then = state.get(THEN_KEY) if isinstance(state, dict) else None
    if prev_then and prev_then[1] == "lazy":
        prev_then = _materialize(prev_then, ctx)
    base = None
    got = _then_board(ctx, {THEN_KEY: prev_then} if prev_then else {})
    if got is not None:
        b, where = got
        lm, pb = last_move(b), board_before(b)
        base = (b.fen(), where, 0, pb.fen() if pb is not None else "", lm.uci() if lm else "")
    return (None, "lazy", 0, moves, base, prev_then)


_EARLIER = re.compile(r"(?<![\w-])(?:если\s+бы|было\s+бы|what\s+if|would\s+have|had\s+i)(?![\w-])|"
                      r"(?<![\w-])на\s+(?P<n>\d{1,3})-?\w*\s+ходу(?![\w-])|(?<![\w-])(?:on|at)\s+move\s+(?P<m>\d{1,3})(?![\w-])",
                      re.IGNORECASE)


def _earlier_moment(ctx: Any, board: chess.Board) -> bool:
    """The question is about another moment than the board: a counterfactual («если бы …», "what if I had …") or an
    earlier move of the game («на 5-м ходу» with the board past move 5)."""
    q = getattr(ctx, "question_raw", "") or getattr(ctx, "question", "") or ""
    for m in _EARLIER.finditer(q):
        n = m.group("n") or m.group("m")
        if n is None or int(n) < board.fullmove_number:
            return True
    return False


# ── plan 31.10 (P3B): the scene's own words ─────────────────────────────────────────────────────────────────────
# What the sentence says about WHICH board it means, read by this module from the words (src/answer_check_relations
# .extract_claims calls extract() for every sentence, before its claims are judged):
#   start_cue       «в самом начале партии», «в начальной/исходной позиции», «на доске сейчас»: the board is the one
#                   the turn has — the guards for a lesson's diagram told in words (_diagram_only, _words_only_diagram)
#                   do not apply; a start-position cue means the initial position even when an example board is shown;
#   idea_scope      «(А) почему не X?», «А если X?», «А X?»: the next sentence (that one only) is about the board after
#                   X (X played on the board now). A piece it names on X's own from-square (of X's kind and side), with
#                   a later move named whose piece would hit that square and not the one X went to, is reasoned about
#                   where it no longer stands — «А почему не Nxd4 сразу? Подумай, что случится с твоим конём c6 после
#                   d5»: after 3...Nxd4 c6 is empty. The from-square is the signal, not the later move («после d5» is
#                   still reachable as exd5); a piece named by the square it left with nothing said about that square is
#                   the moved piece, named the usual way («А почему не bxa7? Тогда слон бьёт твою пешку b6»);
#   bare_pawn_line  «Если чёрные сыграют d5, ты ответишь e5, … слон c8 останется запертым»: after a verb of playing
#                   with a side named, a bare square is that side's pawn move when exactly one legal pawn move goes
#                   there — played from the board now or after the move the sentence before advised («лучший план —
#                   d4»); a claim the words leave conditional is judged at the end of that line;
#   loaded_line     «Ферзь пожертвован, чтобы ладья больше не защищала поле d8» about a game the turn loaded: the move
#                   the sentence before told («ферзь идёт на b8») anchored at its single ply of that game, and «больше
#                   не» judged as the positive relation on the board before it (presup no_longer).
# Each has its switch (src/config.detector_mode): off — this module does nothing for it; shadow — the board it builds
# is marked, and the judge logs a false verdict there instead of reporting it (claim_judge.decide); on — reported.
TEXT_KEY = "scene.text"  # the sentence being checked (immutable str), for the cues of its claims
IDEA_KEY = "scene.idea"  # (FEN before X, X's UCI, where): «почему не X?» of the sentence before — for one sentence only
ADVISED_KEY = "scene.advised"  # (FEN, UCI): the bare pawn move the sentence before advised — for one sentence only
DETECTOR_ATTR = "rel_detector"  # a board built by one of these mechanisms carries its name

# «в начале партии» alone is the opening phase in general; with «самом» or «сейчас» it is the initial position now.
_START_CUE = re.compile(
    r"(?<![\w-])(?:в\s+начале\s+партии(?=[^.!?]*\bсейчас\b)|(?<=сейчас,\s)в\s+начале\s+партии|"
    r"в\s+самом\s+начале\s+партии|в\s+(?:самой\s+)?(?:начальн|исходн|стартов)\w*\s+позици\w*|"
    r"(?:in|at)\s+the\s+(?:starting|initial|start)\s+position|at\s+the\s+very\s+start\s+of\s+the\s+game)(?![\w-])",
    re.IGNORECASE)
_BOARD_CUE = re.compile(r"(?<![\w-])(?:на\s+доске\s+(?:прямо\s+)?сейчас|сейчас\s+на\s+доске|on\s+the\s+board\s+(?:right\s+)?now)"
                        r"(?![\w-])", re.IGNORECASE)


def _mode(name: str, ctx: Any = None) -> str:
    try:
        from src.config import detector_mode

        return detector_mode(name, ctx)
    except Exception:  # noqa: BLE001 — a broken switch is off, never on
        return "off"


def _marked(board: chess.Board, name: str) -> chess.Board:
    """A copy of *board* (its story kept) that names the mechanism which built it."""
    out = board.copy()
    for attr in ("rel_last", "rel_prev"):
        if hasattr(board, attr):
            setattr(out, attr, getattr(board, attr))
    setattr(out, DETECTOR_ATTR, name)
    return out


def detector_of(board: Optional[chess.Board]) -> Optional[str]:
    """The plan-31.10 mechanism that built *board* (claim_judge gates its verdict by that detector's switch)."""
    return getattr(board, DETECTOR_ATTR, None) if board is not None else None


def _text(state: dict) -> str:
    t = state.get(TEXT_KEY) if isinstance(state, dict) else None
    return t if isinstance(t, str) else ""


def _cue(state: dict) -> str:
    """'start' (the initial position), 'board' (the board now) or ''."""
    t = _text(state).replace("ё", "е")
    if not t:
        return ""
    if _START_CUE.search(t):
        return "start"
    if _BOARD_CUE.search(t):
        return "board"
    return ""


def _start_cued(claim: Claim, primary: chess.Board, where: str, alts: list, ctx: Any, state: dict) -> Optional[tuple]:
    """(primary, where, alternatives) of a claim the diagram guards would drop, when the sentence's words point at the
    board the turn has (start_cue); None otherwise. The board now must be the default initial position (nothing played):
    then «в начальной позиции» names that very board."""
    cue = _cue(state)
    cur = getattr(ctx, "current", None)
    if not cue or cur is None or not _bare_start(cur, ctx) or _mode("start_cue", ctx) == "off":
        return None
    from src.claim_judge import _binds

    shown = _shown_boards(ctx)
    if cue == "start" and shown and any(primary is b for b in shown):
        if claim.pos.moves or not _binds(claim, cur):
            return None
        # «в начальной позиции» while an example board is shown: the initial position, the board shown an alternative
        return _marked(cur, "start_cue"), "in the initial position", alts + list(shown)
    if not _binds(claim, primary):
        # «На доске сейчас первая задача урока: ферзь на d3, слон на b2 …» with neither there: the words point at a
        # board the turn does not have (the lesson's), not at this one
        return None
    return _marked(primary, "start_cue"), where if primary is not cur else (
        "in the initial position" if cue == "start" else "on the board now"), alts


# ── idea scope ───────────────────────────────────────────────────────────────────────────────────────────────────
_IDEA_Q = re.compile(r"^\W*(?:(?:а|и)\s+)?(?:почему\s+(?:бы\s+)?(?:не|нельзя)|если|что\s+если|как\s+насч[её]т|"
                     r"why\s+not|what\s+about|what\s+if|and\s+if|how\s+about)\s+(?P<x>[^?]{1,40})\?\W*$|"
                     r"^\W*а\s+(?P<y>[^\s?]{2,8})(?:\s+(?:сразу|сейчас|здесь|тут))?\s*\?\W*$", re.IGNORECASE)
_IDEA_TAIL = re.compile(r"^(?:ход\s+)?(?P<m>\S{2,9})(?:\s+(?:сразу|сейчас|здесь|тут|сначала|first|now|here|instead))?\s*$",
                        re.IGNORECASE)


def _idea_move(text: str, ctx: Any) -> Optional[tuple]:
    """«А почему не Nxd4 сразу?»: (board before X, X) for X legal on the board now (one reading), else None."""
    m = _IDEA_Q.match((text or "").strip().replace("ё", "е"))
    if not m:
        return None
    tail = (m.group("x") or m.group("y") or "").strip()
    t = _IDEA_TAIL.match(tail)
    if not t:
        return None
    from src.claim_types import find_moves

    try:
        found = find_moves(t.group("m"))
    except Exception:  # noqa: BLE001
        return None
    if len(found) != 1:
        return None
    cur = getattr(ctx, "current", None)
    for board in ([cur] if cur is not None else []) + _shown_boards(ctx):
        if found[0].side is not None and found[0].side != board.turn:
            continue
        got = move_readings(board, found[0])
        if len(got) == 1:
            return board, got[0]
    return None


_PIECE_WORDS = {
    chess.KNIGHT: r"кон(?:ь|я|ю|[её]м|е)|knight",
    chess.BISHOP: r"слон(?:а|у|ом|е)?|bishop",
    chess.ROOK: r"ладь(?:я|ю|и|[её]й|е)|rook",
    chess.QUEEN: r"ферз(?:ь|я|ю|[её]м|е)|queen",
    chess.PAWN: r"пешк(?:а|у|и|ой|е)|pawn",
    chess.KING: r"корол(?:ь|я|ю|[её]м|е)|king",
}
# The piece named is said to leave or be traded: the sentence tells the move itself, not a board where it still stands.
_LEAVES = re.compile(r"^[^.;:!?—–]{0,30}?(?<![\w-])(?:уход\w*|уйд\w*|уш[её]л\w*|отход\w*|отойд\w*|отош\w*|прыга\w*|прыгн\w*|"
                     r"исчез\w*|покида\w*|покин\w*|разменя\w*|меня\w*|бь[её]т|берет|забира\w*|встал\w*|станет|leaves|goes|jumps|"
                     r"takes|captures)(?![\w-])", re.IGNORECASE)


def _idea_claims(text: str, ctx: Any, state: dict) -> list:
    """Occupied claims for the pieces the sentence names on the from-square of the idea move «почему не X?» of the
    sentence before (X's kind and side), judged on the board after X (kind 'idea_scope')."""
    idea = state.get(IDEA_KEY)
    if not idea or not text:
        return []
    try:
        before, mv = chess.Board(idea[0]), chess.Move.from_uci(idea[1])
    except ValueError:
        return []
    p = before.piece_at(mv.from_square)
    if p is None:
        return []
    low = text.replace("ё", "е").lower()
    try:
        san = before.san(mv).rstrip("+#")
    except Exception:  # noqa: BLE001
        return []
    from src.claim_types import find_moves

    try:
        if any(_same_move(before, m, mv) for m in find_moves(text)):
            return []  # the sentence tells X again: it narrates the move, and the piece is named where it starts
    except Exception:  # noqa: BLE001
        return []
    if not _hits_old_square(text, before, mv, p):
        return []
    frm = chess.square_name(mv.from_square)
    pat = re.compile(r"(?<![\w-])(?P<w>" + _PIECE_WORDS[p.piece_type] + r")\s+(?:(?P<prep>на|с|со|from|on)\s+)?" + frm
                     + r"(?![\w0-9])", re.IGNORECASE)
    out = []
    for m in pat.finditer(low):
        if m.group("prep") in ("с", "со", "from"):
            continue  # «конь с c6»: the piece that came from c6 — the mover itself
        if _LEAVES.match(low, m.end()):
            continue
        out.append(Claim(rel="occupied", subj=None, objs=(Ref(sq=frm, piece=_LETTER[p.piece_type], side=p.color,
                                                                 text=m.group("w")),),
                         pos=Pos(at="then"), span=(m.start(), m.end()), source="rules", kind="idea_scope"))
        break
    return out


def _hits_old_square(text: str, before: chess.Board, mv: chess.Move, p: chess.Piece) -> bool:
    """The sentence names a later move Y of the other side whose piece, on Y's square, would hit X's from-square and
    not the square X went to — the reason it gives is about the piece where it stood before X («что случится с твоим
    конём c6 после d5» after 3...Nxd4: a pawn on d5 hits c6, not d4). A piece named by the square it left is otherwise
    the moved piece, named the usual way («А почему не bxa7? Тогда слон бьёт твою пешку b6»: the pawn now on a7)."""
    from src.claim_types import find_moves

    try:
        found = find_moves(text)
    except Exception:  # noqa: BLE001
        return False
    for y in found:
        if not y.to or y.castle:
            continue
        try:
            to = chess.parse_square(y.to)
        except ValueError:
            continue
        pt = PIECE_TYPE.get(y.piece or "P", chess.PAWN)
        empty = chess.Board(None)
        empty.set_piece_at(to, chess.Piece(pt, not p.color))
        hits = empty.attacks(to)
        if mv.from_square in hits and mv.to_square not in hits and to not in (mv.from_square, mv.to_square):
            return True
    return False


_LETTER = {chess.PAWN: "P", chess.KNIGHT: "N", chess.BISHOP: "B", chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}


def _idea_boards(claim: Claim, ctx: Any, state: dict) -> Optional[BoardSet]:
    idea = state.get(IDEA_KEY)
    if not idea:
        return None
    try:
        before, mv = chess.Board(idea[0]), chess.Move.from_uci(idea[1])
        after = _after(before, mv)
    except ValueError:
        return None
    return BoardSet(primary=_marked(after, "idea_scope"), where=idea[2])


# ── bare pawn moves in a told line ───────────────────────────────────────────────────────────────────────────────
_PLAY_VERB = (r"(?:сыгра\w*|игра(?:ют|ет|ешь|ть)|ответ(?:ит|ят|ишь|ите|ить|ь)|пойд(?:[её]т|ут|[её]шь)|пойти|"
              r"двин(?:ет|ут|ешь|уть)\w*|продвин\w*|толкн\w*|plays?|play|answers?|replies|reply|pushe?s?)")
_SIDE_WORD = (r"(?P<side>бел(?:ые|ым|ых)|ч[её]рн(?:ые|ым|ых)|соперник|противник|ты|вы|white|black|you|your\s+opponent)")
_BARE_STEP = re.compile(r"(?<![\w-])" + _SIDE_WORD + r"(?:\s+[\w-]+){0,3}?\s+" + _PLAY_VERB +
                        r"(?:\s+(?:ходом|пешкой|пешку))?\s+(?P<sq>[a-h][1-8])(?![\w0-9-])", re.IGNORECASE)
_ADVICE = re.compile(r"(?<![\w-])(?:(?:лучш|сильн|главн|правильн|естественн)\w*\s+(?:план|ход|продолжение|ответ)\w*|"
                     r"(?:играй|сыграй|двигай|толкай|best\s+(?:move|plan)\s+is))\s*(?:[—–:-]|это)?\s*(?P<sq>[a-h][1-8])"
                     r"(?![\w0-9-])", re.IGNORECASE)


def _side_of(word: str, ctx: Any, board: chess.Board) -> Optional[bool]:
    w = word.lower().replace("ё", "е")
    if w.startswith(("бел", "white")):
        return chess.WHITE
    if w.startswith(("черн", "black")):
        return chess.BLACK
    me = getattr(ctx, "student_color", None)
    cur = getattr(ctx, "current", None)
    if me is None:
        me = (cur if cur is not None else board).turn
    if w in ("ты", "вы", "you"):
        return me
    return not me  # соперник, противник, your opponent


def _pawn_move(board: chess.Board, side: bool, sq: str) -> Optional[chess.Move]:
    """The single legal pawn move of *side* to *sq* on *board* (a push before a capture), or None."""
    if board.turn != side:
        return None
    to = chess.parse_square(sq)
    ms = [m for m in board.legal_moves if m.to_square == to and board.piece_type_at(m.from_square) == chess.PAWN
          and m.promotion in (None, chess.QUEEN)]
    quiet = [m for m in ms if not board.is_capture(m)]
    pick = quiet or ms
    return pick[0] if len(pick) == 1 else None


def _bare_steps(text: str, ctx: Any, upto: Optional[int] = None) -> list:
    """[(side, square, end offset)] of the bare pawn moves the words tell after a verb of playing with a side named."""
    low = (text or "").replace("ё", "е")
    out = []
    for m in _BARE_STEP.finditer(low):
        if upto is not None and m.end() > upto:
            break
        out.append((m.group("side"), m.group("sq").lower(), m.end()))
    return out


def _play_bare(start: chess.Board, steps: list, ctx: Any) -> Optional[chess.Board]:
    b = start
    for word, sq, _end in steps:
        side = _side_of(word, ctx, b)
        if side is None:
            return None
        mv = _pawn_move(b, side, sq)
        if mv is None:
            return None
        b = _after(b, mv)
    return b


def _advised_board(ctx: Any, state: dict) -> Optional[chess.Board]:
    adv = state.get(ADVISED_KEY) if isinstance(state, dict) else None
    if not adv:
        return None
    try:
        b = chess.Board(adv[0])
        return _after(b, chess.Move.from_uci(adv[1]))
    except ValueError:
        return None


def _line_ends(steps: list, ctx: Any, state: dict) -> list:
    """The boards at the end of the bare line *steps*: played after the move the sentence before advised, or from the
    board now (the first one is the primary reading)."""
    if not steps:
        return []
    cur = getattr(ctx, "current", None)
    starts = [b for b in (_advised_board(ctx, state), cur) if b is not None]
    out, seen = [], set()
    for s in starts:
        end = _play_bare(s, steps, ctx)
        if end is not None and _key(end) not in seen:
            seen.add(_key(end))
            out.append(end)
    return out


_LINE_SKIPS = ("conditional", "future")


def _line_boards(claim: Claim, ctx: Any, state: dict) -> Optional[BoardSet]:
    """A claim the grammar left conditional («Если чёрные сыграют d5, ты ответишь e5, … слон c8 останется запертым»):
    the board at the end of the bare line the sentence tells before it (bare_pawn_line), else None."""
    if claim.pos.skip_reason not in _LINE_SKIPS or _mode("bare_pawn_line", ctx) == "off":
        return None
    text = _text(state)
    if not text:
        return None
    try:
        from src.claim_grammar import normalize

        text = normalize(text)
    except Exception:  # noqa: BLE001
        pass
    upto = claim.span[0] if tuple(claim.span) != (0, 0) else None
    steps = _bare_steps(text, ctx, upto)
    if not steps:
        return None
    ends = _line_ends(steps, ctx, state)
    if not ends:
        return None
    primary = _marked(ends[0], "bare_pawn_line")
    lm, prev = last_move(ends[0]), board_before(ends[0])
    where = "after " + (_san_where(prev, lm) if lm is not None and prev is not None else "the line told")
    alts = list(ends[1:]) + _before_last(primary, claim) + _implicit(primary, claim, ctx)
    return BoardSet(primary=primary, where=where, alternatives=tuple(alts))


def _advised(text: str, ctx: Any) -> Optional[tuple]:
    """«лучший план — d4»: the bare pawn move of the side to move the sentence advises, as (FEN, UCI)."""
    cur = getattr(ctx, "current", None)
    if cur is None or not text:
        return None
    m = _ADVICE.search(text.replace("ё", "е"))
    if not m:
        return None
    mv = _pawn_move(cur, cur.turn, m.group("sq").lower())
    return (cur.fen(), mv.uci()) if mv is not None else None


# ── a move of a loaded game told in words, and «больше не» ─────────────────────────────────────────────────────
_NO_LONGER = re.compile(r"(?<![\w-])(?:больше|уже)\s+не(?![\w-])|no\s+longer", re.IGNORECASE)


def no_longer(claim: Claim, state: dict) -> bool:
    """«больше не защищала»: the denial presupposes the relation held before (presup no_longer) — given by the
    grammar, or read here in the words right before the claim's verb."""
    if claim.presup == "no_longer":
        return True
    if not claim.neg or tuple(claim.span) == (0, 0):
        return False
    text = _text(state)
    if not text:
        return False
    try:
        from src.claim_grammar import normalize

        text = normalize(text)
    except Exception:  # noqa: BLE001
        pass
    head = text[max(0, claim.span[0] - 40):claim.span[1] + 1].lower()
    return bool(_NO_LONGER.search(head))


def _anchored(ctx: Any, m: MoveRef) -> Optional[tuple]:
    """A move told in words with no number («ферзь идёт на b8») anchored at its single ply of a game or line the turn
    loaded: (board before, move), or None when no record or more than one ply of the records has it."""
    hits = {}
    for _start, steps, _end in _records(ctx):
        for before, mv in steps:
            if _same_move(before, m, mv):
                hits[(_key(before), mv)] = (before, mv)
    return next(iter(hits.values())) if len(hits) == 1 else None


def _loaded_before(claim: Claim, ctx: Any, state: dict) -> Optional[tuple]:
    """For a «больше не» claim: (board before the move told, where) — the first move of the line the sentence before
    told («ферзь идёт на b8, конь вынужден её взять, и тогда ладья врывается на d8»), anchored in a loaded game."""
    if _mode("loaded_line", ctx) == "off" or not getattr(ctx, "line_records", None):
        return None
    then = state.get(THEN_KEY) if isinstance(state, dict) else None
    if not then or then[1] != "lazy" or then[2] > 1:
        return None
    for m in then[3][:1]:
        if m.number:
            continue
        hit = _anchored(ctx, m)
        if hit is not None:
            before, mv = hit
            return _marked(before.copy(stack=False), "loaded_line"), "before " + _san_where(before, mv)
    return None


# ── entry point for the words (src/answer_check_relations.extract_claims) ────────────────────────────────────────
def extract(text: str, ctx: Any, state: dict) -> list:
    """Record the sentence for the cues of its claims, and return the claims the scene itself reads from it (the idea
    scope's pieces). Never raises."""
    if not isinstance(state, dict):
        return []
    state[TEXT_KEY] = text or ""
    try:
        if state.get(IDEA_KEY) and _mode("idea_scope", ctx) != "off":
            return _idea_claims(text, ctx, state)
    except Exception:  # noqa: BLE001
        return []
    return []


def _told_bare_line(text: str, ctx: Any, state: dict) -> Optional[tuple]:
    """The end of a line told with bare pawn moves («Если чёрные сыграют d5, ты ответишь e5»), as remember() keeps it
    — only with bare_pawn_line on (in shadow the next sentence's board stays as before)."""
    if _mode("bare_pawn_line", ctx) != "on":
        return None
    try:
        from src.claim_grammar import normalize

        ends = _line_ends(_bare_steps(normalize(text), ctx), ctx, state)
    except Exception:  # noqa: BLE001
        return None
    if not ends:
        return None
    end = ends[0]
    lm, prev = last_move(end), board_before(end)
    where = "after " + (_san_where(prev, lm) if lm is not None and prev is not None else "the line told")
    return (end.fen(), where, 0, prev.fen() if prev is not None else "", lm.uci() if lm is not None else "")


def _remember_advice(text: str, ctx: Any, state: dict) -> None:
    adv = _advised(text, ctx)
    if adv is not None:
        state[ADVISED_KEY] = adv
    else:
        state.pop(ADVISED_KEY, None)


def _remember_idea(text: str, ctx: Any, state: dict) -> Optional[tuple]:
    """«(А) почему не X?»: keep X for the next sentence (IDEA_KEY), and — idea_scope on — the board after X as the line
    it goes on from, for that sentence only (its age is the last one a «тогда» still reads). Else forget the idea."""
    if not _IDEA_Q.match((text or "").strip().replace("ё", "е")):  # cheap: most sentences ask no «почему не X?»
        state.pop(IDEA_KEY, None)
        return None
    mode = _mode("idea_scope", ctx)
    got = _idea_move(text, ctx) if mode != "off" else None
    if got is None:
        state.pop(IDEA_KEY, None)
        return None
    before, mv = got
    p = before.piece_at(mv.from_square)
    went = f" (the {chess.piece_name(p.piece_type)} from {chess.square_name(mv.from_square)} now stands on " \
           f"{chess.square_name(mv.to_square)})" if p is not None else ""
    where = f"after {_san_where(before, mv)}{went}, the move the question is about"
    state[IDEA_KEY] = (before.fen(), mv.uci(), where)
    if mode != "on":
        return None
    after = _after(before, mv)
    return (after.fen(), where, THEN_MAX_AGE, before.fen(), mv.uci())
