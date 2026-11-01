"""The game's own record, read for the answer check (plan 31.10, WP-0; frozen — a change needs every owner's consent).

The checks of P1 (game record), P2 (openings), P6 (trades) and the facts of P8 read the score the same way:

  recap_end(ctx, prefix)      the written moves of *prefix* are the game's own record, in order at their numbers:
                              the ply they end at (len(ctx.game_moves) = "the board now"), else None
  captures(ctx)               every capture of the game (ctx.game_moves), with its owner
  last_capture(ctx, told)     the capture a sentence is about: one it names, else the one the answer last told, else
                              the last ply played (or the ply before it) when that was a capture
  exchanges(moves, start)     the maximal runs of captures of a game; a quiet check and its reply inside a run do not
                              end it (80.Rxf7+ Kxf7 81.Rb7+ Kg6 82.Rxa7 is one run)
  side_words(ctx, text)       the side the words name: ты/твой (the student), я/мой (the coach), белые/чёрные,
                              ақтар/қаралар, the players of a recorded famous game
  material(board)             the material on a board, by side, and who has more of what

Plies are 1-based: the ply of a move is its index in the game's move list plus one.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional, Sequence, Union

import chess

from src.board_math import VALUE

PIECE_LETTER = {chess.PAWN: "P", chess.KNIGHT: "N", chess.BISHOP: "B", chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}


@dataclass(frozen=True)
class Capture:
    ply: int  # 1-based: game_moves[ply - 1] is the capture
    san: str
    mover: bool  # the colour that captured
    piece: int  # the capturing piece type
    captured: int  # the captured piece type (a pawn for en passant)
    square: int  # where the captured piece stood (the en passant pawn's own square)
    by_student: Optional[bool]  # None when the student's colour is not known
    from_square: int = -1  # where the capturing piece came from (fix 01.11: «пешка e5 съела коня» names it)
    to_square: int = -1  # where it landed (the captured piece's square but for en passant)

    @property
    def label(self) -> str:
        """«4.exf6», «5...Nxe4»."""
        return f"{(self.ply - 1) // 2 + 1}{'.' if self.ply % 2 else '...'}{self.san}"


@dataclass(frozen=True)
class Exchange:
    start_ply: int  # 1-based, both ends included
    end_ply: int
    sans: tuple
    lost: dict = field(default_factory=dict)  # {chess.WHITE: Counter[piece_type], chess.BLACK: Counter[piece_type]}

    @property
    def text(self) -> str:
        """«26.Qxc8 Rxc8 27.Rxc8»."""
        out, ply = [], self.start_ply
        for i, san in enumerate(self.sans):
            p = ply + i
            if p % 2 == 1:
                out.append(f"{(p - 1) // 2 + 1}.{san}")
            elif i == 0:
                out.append(f"{(p - 1) // 2 + 1}...{san}")
            else:
                out.append(san)
        return " ".join(out)


def _sans(ctx) -> list:
    return [str(m) for m in (getattr(ctx, "game_moves", None) or [])]


def _converted(prefix: str) -> str:
    from src.answer_check import _to_san

    converted, _ = _to_san(prefix or "")
    return converted


def recap_end(ctx, prefix: str, converted: bool = False) -> Optional[int]:
    """The written moves of *prefix* are the game's own record — in its order, each numbered move at its number, one
    run with no gap after the first: the ply (count of game moves) they end at; None otherwise (no game, no moves,
    an invented line, a gap). A lone bare pawn move («e4») counts only when it is numbered or one of several.
    *converted*: *prefix* is already in SAN (src.answer_check._to_san)."""
    from src.answer_check import _MOVE

    rec = [m.rstrip("+#") for m in _sans(ctx)]
    if not rec:
        return None
    text = prefix if converted else _converted(prefix)
    toks = list(_MOVE.finditer(text))
    toks = [m for m in toks if m["num"] or m["bdots"] or m["san"][0] in "KQRBNO" or "x" in m["san"] or len(toks) > 1]
    if not toks:
        return None
    j = None
    for m in toks:
        san = m["san"].rstrip("+#")
        if j is None:
            cands = [i for i, r in enumerate(rec) if r == san]
            if m["num"]:
                black = (m["dots"] or "") in ("...", "…")
                cands = [i for i in cands if i // 2 + 1 == int(m["num"]) and (i % 2 == 1) == black]
            elif m["bdots"]:
                cands = [i for i in cands if i % 2 == 1]
            if not cands:
                return None
            j = cands[-1]
        else:
            j += 1
            if j >= len(rec) or rec[j] != san:
                return None
            if m["num"] and j // 2 + 1 != int(m["num"]):
                return None
    return j + 1


def _walk(sans: Sequence[str], start: Optional[chess.Board] = None):
    """(ply, board before, move, SAN) for each move that parses; stops at the first that does not."""
    board = (start or chess.Board()).copy(stack=False)
    for i, san in enumerate(sans):
        try:
            mv = board.parse_san(san)
        except ValueError:
            return
        yield i + 1, board, mv, board.san(mv)
        board.push(mv)


def captures(ctx) -> list:
    """Every capture of the game on the board (ctx.game_moves from the initial position), in order."""
    student = getattr(ctx, "student_color", None)
    out = []
    for ply, board, mv, san in _walk(_sans(ctx)):
        if not board.is_capture(mv):
            continue
        if board.is_en_passant(mv):
            square = mv.to_square + (-8 if board.turn == chess.WHITE else 8)
            victim = chess.PAWN
        else:
            square = mv.to_square
            victim = board.piece_type_at(mv.to_square)
        out.append(Capture(ply=ply, san=san, mover=board.turn, piece=board.piece_type_at(mv.from_square),
                           captured=victim, square=square,
                           by_student=None if student is None else board.turn == student,
                           from_square=mv.from_square, to_square=mv.to_square))
    return out


def last_capture(ctx, told: Optional[str] = None) -> Optional[Capture]:
    """The capture a sentence is about: a capture of the game written in *told* (the last one written), else the move
    the answer last wrote (ctx.scene_san) when it is a capture of the game, else the last ply played — or the ply
    before it — when that was a capture. None when there is no game or no such capture."""
    caps = captures(ctx)
    if not caps:
        return None
    n = len(_sans(ctx))

    def by_san(san: str) -> Optional[Capture]:
        san = (san or "").rstrip("+#")
        hits = [c for c in caps if c.san.rstrip("+#") == san]
        return hits[-1] if hits else None

    if told:
        from src.answer_check import _MOVE

        found = None
        for m in _MOVE.finditer(_converted(told)):
            if "x" in m["san"]:
                found = by_san(m["san"]) or found
        if found is not None:
            return found
    scene = getattr(ctx, "scene_san", "") or ""
    if "x" in scene:
        hit = by_san(scene)
        if hit is not None:
            return hit
    for c in reversed(caps):
        if c.ply >= n - 1:
            return c
    return None


def _victim(board: chess.Board, mv: chess.Move) -> Optional[chess.Piece]:
    if board.is_en_passant(mv):
        return chess.Piece(chess.PAWN, not board.turn)
    return board.piece_at(mv.to_square)


def exchanges(moves: Sequence[Union[chess.Move, str]], start: Optional[chess.Board] = None, max_gap: int = 2) -> list:
    """The maximal runs of captures of the game *moves* (chess.Move or SAN) played from *start* (the initial position by
    default). A quiet check and the reply to it inside a run do not end it, when a capture follows them at once
    (80.Rxf7+ Kxf7 81.Rb7+ Kg6 82.Rxa7). Each run gives what each side lost in it."""
    board = (start or chess.Board()).copy(stack=False)
    plies = []  # (san, victim, gives check)
    for mv in moves:
        if isinstance(mv, str):
            try:
                mv = board.parse_san(mv)
            except ValueError:
                break
        victim = _victim(board, mv)
        san = board.san(mv)
        board.push(mv)
        plies.append((san, victim, board.is_check()))
    out, i = [], 0
    while i < len(plies):
        if plies[i][1] is None:
            i += 1
            continue
        last, k = i, i + 1
        while k < len(plies):
            if plies[k][1] is not None:
                last = k
                k += 1
                continue
            if k - last <= max_gap and plies[k][2] and k + 2 < len(plies) and plies[k + 2][1] is not None:
                k += 2
                continue
            break
        lost = {chess.WHITE: Counter(), chess.BLACK: Counter()}
        for _, v, _ in plies[i:last + 1]:
            if v is not None:
                lost[v.color][v.piece_type] += 1
        out.append(Exchange(start_ply=i + 1, end_ply=last + 1, sans=tuple(p[0] for p in plies[i:last + 1]), lost=lost))
        i = last + 1
    return out


# ── the side the words name ──────────────────────────────────────────────────────────────────────────────────────
_W = r"(?<![а-яёәғқңөұүһіa-z])"
_E = r"(?![а-яёәғқңөұүһіa-z])"
_SIDE_WORDS = re.compile(
    _W + r"(?:(?P<w>бел(?:ые|ых|ым|ыми|ый|ого|ому|ая|ой|ую|ое)|white|ақтар\w*|ақ)"
    r"|(?P<b>ч[её]рн(?:ые|ых|ым|ыми|ый|ого|ому|ая|ой|ую|ое)|black|қаралар\w*|қара)"
    r"|(?P<you>ты|тебе|тебя|тобой|твой|твоя|тво[её]|твои|твоего|твоей|твоим|твоих|сен|сенің|you|your)"
    r"|(?P<me>я|мне|меня|мной|мой|моя|мо[её]|мои|моего|моей|моим|моих))" + _E, re.IGNORECASE)


_FAMOUS: Optional[list] = None


def _famous_sans() -> list:
    """(game, its moves in SAN without +/#) for src/famous_games.GAMES, computed once."""
    global _FAMOUS
    if _FAMOUS is None:
        out = []
        try:
            from src.famous_games import GAMES, _replay

            for g in GAMES:
                _, moves = _replay(g)
                b, sans = chess.Board(), []
                for mv in moves:
                    sans.append(b.san(mv).rstrip("+#"))
                    b.push(mv)
                out.append((g, sans))
        except Exception:  # noqa: BLE001 — the players are a bonus
            out = []
        _FAMOUS = out
    return _FAMOUS


def _players(ctx) -> list:
    """(name stem, colour) for the players of the famous games among the turn's records (src/famous_games.GAMES): the
    record's moves are that game's from the initial position (at least 8 plies of it, or all of a shorter one). The
    English names, the Russian names in the game's title («Карлсен — Непомнящий») and white_ru/black_ru when the
    record has them."""
    records = list(getattr(ctx, "line_records", None) or [])
    if not records:
        return []
    out = []
    for g, fam in _famous_sans():
        hit = False
        for rb, rs in records:
            if rb.board_fen() != chess.STARTING_BOARD_FEN or rb.turn != chess.WHITE:
                continue
            rec = [str(x).rstrip("+#") for x in rs]
            n = min(len(rec), len(fam))
            if n >= min(8, len(fam)) and rec[:n] == fam[:n]:
                hit = True
                break
        if not hit:
            continue
        names = [(g.get("white", ""), chess.WHITE), (g.get("black", ""), chess.BLACK)]
        for key, colour in (("white_ru", chess.WHITE), ("black_ru", chess.BLACK)):
            if g.get(key):
                names.append((g[key], colour))
        ru = re.search(r"\(([А-ЯЁ][а-яё]+)\s+[—–-]\s+([А-ЯЁ][а-яё]+)", g.get("name", ""))
        if ru:
            names += [(ru.group(1), chess.WHITE), (ru.group(2), chess.BLACK)]
        for name, colour in names:
            for part in re.findall(r"[A-Za-zА-Яа-яЁё]{4,}", name or ""):
                if part.lower() in ("duke", "count", "karl", "and", "james", "robert", "isouard", "brunswick"):
                    continue
                out.append((part.lower().replace("ё", "е")[:5], colour))
    return out


def side_words(ctx, text: str) -> Optional[bool]:
    """The side the first side word of *text* names: chess.WHITE / chess.BLACK, or None when no side is named or the
    words name the student (or the coach) while the student's colour is not known."""
    t = (text or "").lower().replace("ё", "е")
    found = []
    m = _SIDE_WORDS.search(t)
    if m:
        student = getattr(ctx, "student_color", None)
        if m.group("w"):
            found.append((m.start(), chess.WHITE))
        elif m.group("b"):
            found.append((m.start(), chess.BLACK))
        elif m.group("you"):
            found.append((m.start(), student))
        elif m.group("me"):
            found.append((m.start(), None if student is None else not student))
    for stem, colour in _players(ctx):
        pm = re.search(r"(?<![а-яa-z])" + re.escape(stem), t)
        if pm:
            found.append((pm.start(), colour))
    if not found:
        return None
    return min(found, key=lambda x: x[0])[1]


def material(board: chess.Board) -> dict:
    """The material on *board*: {"white": points, "black": points, "diff": white − black, "counts": {"white": {"P": 8,
    …}, "black": {…}}, "more": {"white": {"N": 1}, "black": {"P": 2}}} — "more" lists the units a side has more of
    than the other (kings not counted)."""
    counts = {"white": Counter(), "black": Counter()}
    for p in board.piece_map().values():
        if p.piece_type != chess.KING:
            counts["white" if p.color else "black"][PIECE_LETTER[p.piece_type]] += 1
    pts = {s: sum(VALUE[t] * counts[s][PIECE_LETTER[t]] for t in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK,
                                                                    chess.QUEEN)) for s in counts}
    more = {"white": {}, "black": {}}
    for letter in ("Q", "R", "B", "N", "P"):
        d = counts["white"][letter] - counts["black"][letter]
        if d > 0:
            more["white"][letter] = d
        elif d < 0:
            more["black"][letter] = -d
    return {"white": pts["white"], "black": pts["black"], "diff": pts["white"] - pts["black"],
            "counts": {s: dict(counts[s]) for s in counts}, "more": more}
