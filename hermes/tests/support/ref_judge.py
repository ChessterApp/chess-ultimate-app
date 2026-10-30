"""The reference judge (test-only): design-llm/claim_verify.py (30.10) adapted to src/claim_types.

WP-A's parser is measured with it (``scripts/eval_relations.py --parser grammar --judge ref``), so the parser can
be judged before WP-B's resolver and judge land. The judging code below is the prototype's, unchanged; only the
entry point is new: ``verify(claim, env, text)`` takes a ``Claim`` and returns a ``Verdict``. A claim is turned back
into the prototype's JSON (``to_llm``) and judged there.

env: {'fen': the board now, 'shown': the board the coach showed (or None), 'game_moves': SAN from the start,
      'me': the student's colour (else the side to move), 'alt_boards': FENs the question spells out} — ``env_for``.
text: the sentence with the previous one and the question, for grounding (every square must be written there).
"""
from __future__ import annotations

import re

import chess

PIECE = {"P": chess.PAWN, "N": chess.KNIGHT, "B": chess.BISHOP, "R": chess.ROOK, "Q": chess.QUEEN, "K": chess.KING}
NAME = {v: k for k, v in PIECE.items()}
VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
RELS = {"attacks", "aims", "defends", "attacked", "undefended", "hanging", "pins", "pinned", "controls",
        "can_capture", "gives_check", "locked", "trapped", "blocks", "only_move", "occupies", "can_move"}
RU_SAN = str.maketrans({"К": "N", "С": "B", "Л": "R", "Ф": "Q"})
CYR_FILES = {"а": "a", "б": "b", "в": "b", "с": "c", "ц": "c", "д": "d", "е": "e", "э": "e", "ф": "f", "г": "g", "х": "h"}


# ---------- position resolution ----------
def _san(board: chess.Board, tok: str) -> chess.Move | None:
    t = re.sub(r"^\d+\s*\.(\.\.)?\s*|^…|^\.\.\.", "", tok.strip()).replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    t = t.replace("Кр", "K").translate(RU_SAN).rstrip("!?")
    try:
        return board.parse_san(t)
    except ValueError:
        return None


def resolve(pos: dict, env: dict):
    """The board a claim is about, or (None, why). env: fen, shown, game_moves (SAN from the start), prev_fens."""
    at = (pos or {}).get("at", "now")
    if at in ("if", "general") or at.startswith("shb"):
        return None, "not about a board we have"
    if at == "plan":
        return "PLAN", ""
    if at in ("now", "after"):
        base = env.get("fen")
    elif at in ("shown", "shown_after"):
        base = env.get("shown")
    elif at == "back":
        gm = env.get("game_moves") or []
        n = int(pos.get("plies") or 1)
        if len(gm) < n:
            return None, "no game history"
        b = chess.Board()
        for m in gm[: len(gm) - n]:
            b.push_san(m)
        base = b.fen()
    else:
        return None, "unknown position kind"
    if not base:
        return None, "base board missing"
    b = chess.Board(base)
    for tok in pos.get("moves") or []:
        m = _san(b, tok)
        if m is None:
            # A plan move by the side NOT to move («...Nf6» while White is to move): one null move, once.
            nb = b.copy(stack=False)
            nb.push(chess.Move.null())
            m = _san(nb, tok)
            if m is None:
                if _already_played(b, tok):
                    continue  # «Я сыграл Qb6» with the queen already on b6: the board is after the move
                return None, f"move {tok} not legal"
            b = nb
        b.push(m)
    return b, ""


def _already_played(board, tok):
    t = re.sub(r"^\d+\s*\.(\.\.)?\s*|^…|^\.\.\.|[+#!?]", "", tok).replace("Кр", "K").translate(RU_SAN)
    m = re.match(r"^([KQRBN])?[a-h]?[1-8]?x?([a-h][1-8])", t)
    if not m:
        return False
    p = board.piece_at(chess.parse_square(m.group(2)))
    return p is not None and p.piece_type == PIECE[m.group(1) or "P"]


# ---------- grounding ----------
def _norm_text(s: str) -> str:
    s = s.replace("Кр", "K").translate(RU_SAN)
    s = re.sub(r"(?<![А-Яа-яЁёA-Za-z])([абвсцдеэфгх])(?=[1-8](?![0-9]))", lambda m: CYR_FILES[m.group(1)], s)
    return s


def grounded(claim: dict, text: str) -> bool:
    """Every square the claim names appears in the sentence (+ previous sentence + question) — the extractor
    may not bring in squares of its own; a move of the position must appear too."""
    t = _norm_text(text)
    sqs = set()
    for k in ("subj", "obj", "to"):
        if (claim.get(k) or {}).get("sq"):
            sqs.add(claim[k]["sq"])
    for o in claim.get("objs") or []:
        if o.get("sq"):
            sqs.add(o["sq"])
    mv = " ".join((claim.get("pos") or {}).get("moves") or [])
    if "O-O-O" in mv or "0-0-0" in mv:
        t += " c1 d1 c8 d8"
    elif "O-O" in mv or "0-0" in mv:
        t += " f1 g1 f8 g8"
    for sq in sqs:
        if sq not in t:
            return False
    for mv in (claim.get("pos") or {}).get("moves") or []:
        core = re.sub(r"^\d+\s*\.(\.\.)?\s*|^…|^\.\.\.|[+#!?]", "", mv).replace("x", "")
        dest = re.findall(r"[a-h][1-8]|O-O", core)
        if dest and dest[-1] not in t.replace("0-0", "O-O"):
            return False
    return True


# ---------- piece selection ----------
def _pieces(board: chess.Board, ref: dict | None, strict_sq=True):
    """Squares the reference can mean on *board*: a square (with the piece kind/side it was called, if any)
    → that square; a kind/side only → every such piece (existential)."""
    if not ref:
        return None
    sq, pk, side = ref.get("sq"), ref.get("piece"), ref.get("side")
    color = {"w": chess.WHITE, "b": chess.BLACK}.get(side)
    if sq:
        s = chess.parse_square(sq)
        return [s]
    out = []
    for s, p in board.piece_map().items():
        if pk and p.piece_type != PIECE[pk]:
            continue
        if color is not None and p.color != color:
            continue
        out.append(s)
    return out


def _mismatch(board, ref):
    """«конь f6» with no knight on f6 — the claim's subject is not there."""
    if not ref or not ref.get("sq"):
        return None
    p = board.piece_at(chess.parse_square(ref["sq"]))
    if ref.get("piece"):
        if p is None:
            return f"there is no piece on {ref['sq']}"
        if p.piece_type != PIECE[ref["piece"]]:
            return f"on {ref['sq']} stands a {chess.piece_name(p.piece_type)}, not a {chess.piece_name(PIECE[ref['piece']])}"
    if ref.get("side") and p is not None and p.color != (ref["side"] == "w"):
        return f"the piece on {ref['sq']} is {'White' if p.color else 'Black'}'s"
    return None


def _battery_hits(board, s, t):
    """s hits t directly, or through own sliders of the same line kind (Q+B, R+R, Q+R batteries)."""
    if t in board.attacks(s):
        return True
    p = board.piece_at(s)
    if not p or p.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False
    between = chess.SquareSet(chess.between(s, t))
    if not between or not chess.SquareSet.ray(s, t):
        return False
    diag = chess.square_file(s) != chess.square_file(t) and chess.square_rank(s) != chess.square_rank(t)
    if (diag and p.piece_type == chess.ROOK) or (not diag and p.piece_type == chess.BISHOP):
        return False
    for b in between:
        q = board.piece_at(b)
        if q is None:
            continue
        if q.color != p.color:
            return False
        if diag and q.piece_type not in (chess.BISHOP, chess.QUEEN):
            return False
        if not diag and q.piece_type not in (chess.ROOK, chess.QUEEN):
            return False
    return True


def _aligned(board, s, t):
    p = board.piece_at(s)
    if not p:
        return False
    if p.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        ray = chess.SquareSet.ray(s, t)
        if not ray:
            return False
        diag = chess.square_file(s) != chess.square_file(t) and chess.square_rank(s) != chess.square_rank(t)
        return (diag and p.piece_type != chess.ROOK) or (not diag and p.piece_type != chess.BISHOP)
    return t in board.attacks(s)


def _defenders(board, t, color):
    return [s for s in board.pieces(chess.PAWN, color) | board.pieces(chess.KNIGHT, color) | board.pieces(chess.BISHOP, color)
            | board.pieces(chess.ROOK, color) | board.pieces(chess.QUEEN, color) | board.pieces(chess.KING, color)
            if s != t and _battery_hits(board, s, t)]


def _pin_of(board, s, p_sq):
    """Does the slider on s pin the piece on p_sq (to the king, or to a more valuable piece behind)?"""
    sp, pp = board.piece_at(s), board.piece_at(p_sq)
    if not sp or not pp or sp.color == pp.color or not _aligned(board, s, p_sq) or p_sq not in board.attacks(s):
        return None
    if sp.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return None
    ray = chess.SquareSet.ray(s, p_sq)
    # walk beyond p_sq away from s
    step_f = (chess.square_file(p_sq) > chess.square_file(s)) - (chess.square_file(p_sq) < chess.square_file(s))
    step_r = (chess.square_rank(p_sq) > chess.square_rank(s)) - (chess.square_rank(p_sq) < chess.square_rank(s))
    f, r = chess.square_file(p_sq) + step_f, chess.square_rank(p_sq) + step_r
    while 0 <= f < 8 and 0 <= r < 8:
        q = chess.square(f, r)
        x = board.piece_at(q)
        if x is not None:
            if x.color == pp.color and (x.piece_type == chess.KING or VAL[x.piece_type] > VAL[pp.piece_type]
                                        or (x.piece_type in (chess.ROOK, chess.QUEEN) and VAL[x.piece_type] >= VAL[pp.piece_type] and VAL[x.piece_type] > VAL[sp.piece_type])):
                return q
            return None
        f += step_f
        r += step_r
    return None


def _legal_from(board, s, color):
    b = board.copy(stack=False)
    if b.turn != color:
        b.push(chess.Move.null()) if not b.is_check() else None
        if b.turn != color:
            return None
    return [m for m in b.legal_moves if m.from_square == s]


# ---------- relations ----------
def _side_of(ref, env):
    side = (ref or {}).get("side")
    if side == "me":
        return env.get("me")
    return {"w": chess.WHITE, "b": chess.BLACK}.get(side)


def _typed_objs(c):
    return [o for o in ([c["obj"]] if c.get("obj") else []) + (c.get("objs") or []) if not o.get("sq") and o.get("piece")]


def _rel(board, c, env):
    """True/False/None for the positive form of the claim on *board*."""
    r = c["rel"]
    sref = dict(c.get("subj") or {})
    if sref.get("side") == "me":
        sref["side"] = "w" if env.get("me") else "b"
    subj = _pieces(board, sref) if c.get("subj") else None
    objs = [c["obj"]] if c.get("obj") else []
    objs += c.get("objs") or []
    T = [chess.parse_square(o["sq"]) for o in objs if o.get("sq")]
    typed = _typed_objs(c)

    if r in ("attacks", "controls", "aims"):
        def hit(s, t):
            if r == "aims":
                return _aligned(board, s, t)
            return _battery_hits(board, s, t) if r == "controls" else t in board.attacks(s)
        if subj is None or (subj == [] and not sref.get("sq")) and False:
            pass
        if not T and not typed:
            return None
        if not sref or (not sref.get("sq") and not sref.get("piece")):
            # «d6 под контролем», «f8 прострелено пешкой белых» — any piece of a side (or of either side)
            col = _side_of(sref, env) if sref else None
            cols = [chess.WHITE, chess.BLACK] if col is None else [col]
            return all(any(board.attackers(cl, t) for cl in cols) for t in T) if T else None
        if not subj:
            return False
        ok_all = True
        for t in T:
            ok = any(hit(s, t) for s in subj)
            tp = board.piece_at(t)
            if r == "attacks" and ok and tp is not None and all(board.piece_at(s).color == tp.color for s in subj if board.piece_at(s) and hit(s, t)):
                ok = False  # «attacks» its own piece
            ok_all = ok_all and ok
        for o in typed:
            # «атакует ... и ладью» — some enemy piece of that kind is hit
            got = False
            for s in subj:
                sp = board.piece_at(s)
                if not sp:
                    continue
                for t in board.attacks(s):
                    tp = board.piece_at(t)
                    if tp and tp.piece_type == PIECE[o["piece"]] and tp.color != sp.color:
                        got = True
            ok_all = ok_all and got
        return ok_all
    if r == "defends":
        if not T:
            return None
        if subj is None:
            return None
        for t in T:
            tp = board.piece_at(t)
            if tp is None:
                if not any(_battery_hits(board, s, t) for s in subj):
                    return False
                continue
            if not any(board.piece_at(s) and board.piece_at(s).color == tp.color and _battery_hits(board, s, t) for s in subj):
                return False
        return True
    if r in ("attacked", "undefended", "hanging"):
        if not T:
            return None
        res = []
        for t in T:
            tp = board.piece_at(t)
            if tp is None:
                return None
            n_att = len(board.attackers(not tp.color, t))
            dfn = bool(_defenders(board, t, tp.color))
            if r == "attacked":
                res.append(n_att == c["n"] if c.get("n") else n_att > 0)
            else:
                res.append((not dfn) if r == "undefended" else (n_att > 0 and not dfn))
        return all(res)
    if r in ("pins", "pinned"):
        tgt = T[:1]
        if not tgt:
            # «связка ...Сg4» — the subject pins *something* of the named side/kind
            if not subj:
                return None
            for s in subj:
                for t in board.attacks(s):
                    if board.piece_at(t) and _pin_of(board, s, t) is not None:
                        return True
            return False
        t = tgt[0]
        if board.piece_at(t) is None:
            return False
        cands = subj if subj else [s for s, p in board.piece_map().items() if p.color != board.piece_at(t).color]
        for s in cands:
            behind = _pin_of(board, s, t)
            if behind is not None and (not c.get("to") or not c["to"].get("sq") or chess.square_name(behind) == c["to"]["sq"]):
                return True
        return False
    if r == "can_capture":
        if not T:
            return None
        for t in T:
            tp = board.piece_at(t)
            if tp is None:
                return False
            if subj is None:
                col = _side_of(sref, env)
                froms = [s for s, p in board.piece_map().items() if p.color != tp.color and (col is None or p.color == col)]
            else:
                froms = subj
            got = False
            for s in froms:
                p = board.piece_at(s)
                if not p or p.color == tp.color:
                    continue
                ms = _legal_from(board, s, p.color)
                if ms and any(m.to_square == t for m in ms):
                    got = True
            if not got:
                return False
        return True
    if r == "can_move":
        # «уведи ферзя с d8 на c7 или b6» — every named square is a legal move of that piece
        if not subj or len(subj) != 1 or not T:
            return None
        p = board.piece_at(subj[0])
        if p is None:
            return None
        ms = _legal_from(board, subj[0], p.color) or []
        return all(any(m.to_square == t for m in ms) for t in T)
    if r == "gives_check":
        return board.is_check()
    if r in ("locked", "trapped"):
        if not subj or len(subj) != 1:
            return None
        p = board.piece_at(subj[0])
        if p is None or p.piece_type == chess.KING or p.piece_type == chess.PAWN:
            return None
        ms = _legal_from(board, subj[0], p.color)
        if ms is None:
            return None
        if r == "locked":
            return len(ms) == 0
        # trapped: no move to a square no enemy piece attacks
        safe = [m for m in ms if not board.is_attacked_by(not p.color, m.to_square)]
        return not safe
    if r == "blocks":
        # «пешка e6 перекрыла слону f8»: the blocker is the first piece on one of the slider's lines
        if not subj or len(subj) != 1 or not T:
            return None
        sl = board.piece_at(T[0])
        if not sl or sl.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN) or board.piece_at(subj[0]) is None:
            return None
        return subj[0] in board.attacks(T[0])
    if r == "only_move":
        mv = c.get("move")
        m = _san(board, mv) if mv else None
        if m is None:
            return None
        kind = c.get("kind", "any")
        legal = list(board.legal_moves)
        if kind == "block" and board.is_check():
            ks = board.king(board.turn)
            legal = [x for x in legal if x.from_square != ks and not board.is_capture(x)]
        return len(legal) == 1 and legal[0] == m
    if r == "occupies":
        col = _side_of(sref, env)
        if not T:
            return None
        for o in objs:
            if not o.get("sq"):
                continue
            p = board.piece_at(chess.parse_square(o["sq"]))
            if p is None:
                return False
            if o.get("piece") and p.piece_type != PIECE[o["piece"]]:
                return False
            if col is not None and p.color != col:
                return False
        return True
    return None


def _plan_geometry(c):
    """A plan («фианкетто ... слон на g2 будет целиться в e6»): only the piece's pattern on an empty board."""
    s, o = c.get("subj") or {}, c.get("obj") or {}
    if c["rel"] not in ("attacks", "aims", "controls") or not s.get("sq") or not s.get("piece") or not o.get("sq"):
        return None
    pt, a, b = PIECE[s["piece"]], chess.parse_square(s["sq"]), chess.parse_square(o["sq"])
    if pt == chess.PAWN:
        return None  # side unknown
    bb = chess.Board(None)
    bb.set_piece_at(a, chess.Piece(pt, chess.WHITE))
    return b in bb.attacks(a)


def truth_text(board, c):
    """The board truth the rewrite gets: what the subject really attacks / who really attacks and defends the target."""
    bits = []
    for s in (_pieces(board, c.get("subj")) or [] if (c.get("subj") or {}).get("sq") else []):
        p = board.piece_at(s)
        if p:
            hits = ", ".join(chess.square_name(x) for x in board.attacks(s) if board.piece_at(x)) or "no pieces"
            bits.append(f"the {chess.piece_name(p.piece_type)} on {chess.square_name(s)} hits {hits}")
    for o in ([c["obj"]] if c.get("obj") else []) + (c.get("objs") or []):
        if o.get("sq"):
            t = chess.parse_square(o["sq"])
            p = board.piece_at(t)
            if p:
                a = [chess.square_name(x) for x in board.attackers(not p.color, t)]
                d = [chess.square_name(x) for x in _defenders(board, t, p.color)]
                bits.append(f"{o['sq']} ({'White' if p.color else 'Black'} {chess.piece_name(p.piece_type)}) is attacked by {', '.join(a) or 'nothing'} and defended by {', '.join(d) or 'nothing'}")
            else:
                bits.append(f"{o['sq']} is empty")
    return "; ".join(bits)


def verify_llm(c: dict, env: dict, text: str, *, require_grounding=True):
    if c.get("rel") not in RELS:
        return "UNKNOWN", "relation not judged"
    if require_grounding and not grounded(c, text):
        return "UNKNOWN", "not grounded"
    board, why = resolve(c.get("pos") or {}, env)
    if board == "PLAN":
        v = _plan_geometry(c)
        if v is None:
            return "UNKNOWN", "plan"
        return ("TRUE", "") if v != bool(c.get("neg")) else ("FALSE", "geometry: that piece on that square does not reach the target")
    if board is None:
        return "UNKNOWN", why
    board = _implicit_move(board, c)
    v, why = _judge(board, c, env)
    if v == "FALSE" and (c.get("pos") or {}).get("at", "now") == "now":
        # Two boards could be «now» (the board vs the line the question spells out): both must say false.
        for alt in env.get("alt_boards") or []:
            if _judge(_implicit_move(chess.Board(alt), c), c, env)[0] != "FALSE":
                return "UNKNOWN", "true on another board of the turn"
    return v, why


def _implicit_move(board, c):
    """«слон на g7 целится в c3» with no bishop on g7 but ...Bg7 legal in one move: the sentence is about the
    position after that move (a plan described as a fact). Unique move only."""
    s = c.get("subj") or {}
    if not s.get("sq") or not s.get("piece") or c["rel"] in ("occupies",):
        return board
    sq = chess.parse_square(s["sq"])
    p = board.piece_at(sq)
    if p is not None and p.piece_type == PIECE[s["piece"]]:
        return board
    for b in (board, _passed(board)):
        if b is None:
            continue
        ms = [m for m in b.legal_moves if m.to_square == sq and b.piece_type_at(m.from_square) == PIECE[s["piece"]]
              and (s.get("side") is None or b.turn == (s["side"] == "w"))]
        if len(ms) == 1:
            nb = b.copy(stack=False)
            nb.push(ms[0])
            return nb
    return board


def _passed(board):
    if board.is_check():
        return None
    nb = board.copy(stack=False)
    nb.push(chess.Move.null())
    return nb


def _judge(board, c, env):
    # The piece the claim names is not there (subject, or a typed object) — false whatever the relation says.
    if c["rel"] not in ("occupies", "can_capture", "gives_check", "only_move") and not (c["rel"] == "can_move" and c.get("neg")):
        for ref in [c.get("subj")] + ([c["obj"]] if c.get("obj") else []) + (c.get("objs") or []):
            mm = _mismatch(board, ref)
            if mm:
                return "FALSE", mm
    try:
        v = _rel(board, c, env)
    except Exception as e:  # noqa: BLE001
        return "UNKNOWN", f"error {e}"
    if v is None:
        return "UNKNOWN", "underspecified"
    if c.get("neg"):
        v = not v
    return ("TRUE", "") if v else ("FALSE", truth_text(board, c))


# ---------- claim_types adapter (WP-0) ----------
from src.claim_types import TO_LLM_RELATIONS, Claim, MoveRef, Pos, Ref, Verdict  # noqa: E402

_STATUS = {"TRUE": "true", "FALSE": "false", "UNKNOWN": "undecided"}


def _ref_llm(r: Ref | None) -> dict | None:
    if r is None:
        return None
    d = {}
    if r.side is not None:
        d["side"] = "w" if r.side else "b"
    elif r.owner == "you":
        d["side"] = "me"
    if r.piece:
        d["piece"] = r.piece
    if r.sq:
        d["sq"] = r.sq
    return d


def _move_llm(m: MoveRef) -> str:
    if m.san:
        return m.san
    if m.castle:
        return "O-O" if m.castle == "short" else "O-O-O"
    return ("" if (m.piece or "P") == "P" else m.piece) + (m.frm or "") + ("x" if m.capture else "") + (m.to or "")


def _pos_llm(p: Pos) -> dict:
    if p.at == "skip":
        return {"at": "if" if p.skip_reason == "if" else "general"}
    if p.at == "shown" and p.plies_back:
        return {"at": f"shb{p.plies_back}"}
    d = {"at": p.at}
    if p.moves:
        d["moves"] = [_move_llm(m) for m in p.moves]
    if p.at == "back":
        d["plies"] = p.plies_back
    return d


def to_llm(c: Claim) -> dict:
    """The claim in the prototype's JSON (relation names, obj + objs, sides 'w'/'b', moves as SAN)."""
    d = {"span": None, "rel": TO_LLM_RELATIONS.get(c.rel, c.rel), "subj": _ref_llm(c.subj), "pos": _pos_llm(c.pos)}
    if c.objs:
        d["obj"] = _ref_llm(c.objs[0])
        d["objs"] = [_ref_llm(o) for o in c.objs[1:]]
    if c.to is not None:
        d["to"] = _ref_llm(c.to)
    if c.neg:
        d["neg"] = True
    if c.question:
        d["question"] = True
    if c.count is not None:
        d["n"] = c.count
    if c.move is not None:
        d["move"] = _move_llm(c.move)
    if c.kind:
        d["kind"] = c.kind
    return d


def question_line(fen: str, question: str | None) -> list:
    """The position the question spells out («1. e4 e5 2. Кf3 Кc6 3. Сb5 — что это?») when it differs from the
    board (design-llm/run_eval.py)."""
    q = (question or "").replace("Кр", "K").translate(str.maketrans({"К": "N", "С": "B", "Л": "R", "Ф": "Q"}))
    toks = [t for t in re.sub(r"\d+\.(\.\.)?", " ", q).split()
            if re.match(r"^([KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](=[QRBN])?|O-O(-O)?)[+#]?$", t)]
    if len(toks) < 2:
        return []
    for start in (chess.STARTING_FEN, fen):
        b = chess.Board(start)
        try:
            for t in toks:
                b.push_san(t)
        except ValueError:
            continue
        if b.board_fen() != chess.Board(fen).board_fen():
            return [b.fen()]
        return []
    return []


def env_for(fen: str, shown: str | None = None, game_moves: list | None = None, student: str | bool | None = None,
            question: str | None = None) -> dict:
    """The prototype's env for one answer: the board, the shown board, the game, the student, the question's line."""
    if isinstance(student, str):
        student = {"w": chess.WHITE, "b": chess.BLACK}.get(student)
    me = student if student is not None else chess.Board(fen).turn
    return {"fen": fen, "shown": shown, "game_moves": list(game_moves or []), "me": me,
            "alt_boards": question_line(fen, question)}


def verify(claim: Claim, env: dict, text: str, *, require_grounding: bool = True) -> Verdict:
    """The prototype's verdict on *claim* as a Verdict (UNKNOWN is 'undecided'; the reason goes in truth)."""
    status, why = verify_llm(to_llm(claim), env, text, require_grounding=require_grounding)
    return Verdict(_STATUS[status], "", why or "")
