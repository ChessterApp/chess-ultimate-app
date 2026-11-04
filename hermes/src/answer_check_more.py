"""Claims the answer check did not read before fix1103 (review-miss 03.11 on next-1031 0af5b5f0), each judged exactly
on the board the answer is about. One entry, more_issues, called by src/answer_check._check_sentence after the other
detectors (fail-open); none of it runs in the /learn tutor (relation_surface "lesson": its checks stay main's).

- a check told in words («Ход Qb3 даёт шах», «Rc7 — с шахом», "Bd5 gives check") — gives_check;
- a square a piece is said to be able to go to («Слон g5 может отступить на e3») — the piece's own move;
- a move told to be played now («Сыграй Qxd5», «Рокируйся — O-O», «Отступи конём: Nb1») — legal now;
- «силы равны» with a piece missing — material and the engine's evaluation;
- a trade told on a line of the board now («Размен Rxd6 cxd6 — ладья за слона») — what the line takes;
- a plan's precondition («План белых — длинная рокировка» with no right to it, «c4-c5» with no c-pawn, «по открытой
  линии d» with a pawn on d4, «большинство на ферзевом фланге») — the board's rights and pawns.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any, Optional

import chess

from src.answer_check import (_B2, _MOVE, _NAMES, CheckContext, _fmt_eval, _geometry_move, _imbalance, _is_hypothetical,
                              _lesson, _mat_cond_after, _to_san)
from src.answer_check_rules import _E, _SQ_LIST, _W, _WRITTEN_MOVE, _negated_before
from src.trade_claims import _NAME, _unit, _units

logger = logging.getLogger(__name__)


def _fail_open(fn, *args) -> list:
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001 — a broken reader never blocks an answer
        logger.debug("%s failed", getattr(fn, "__name__", "reader"), exc_info=True)
        return []


def more_issues(text: str, lowered: str, ctx: CheckContext, issues: list) -> list[str]:
    """The issues of the readers below for *text* (the sentence as _check_sentence reads it; *lowered* its lower case),
    leaving out a move another check named already (*issues*)."""
    if ctx is None or ctx.current is None or _lesson(ctx):
        return []
    out = []
    out += _fail_open(_check_word_issues, text, ctx)
    out += _fail_open(_retreat_reach_issues, lowered, ctx)
    for san, issue in _fail_open(_advice_illegal_issues, text, ctx):
        if not any(san in i for i in issues + out):
            out.append(issue)
    for san, issue in _fail_open(_line_move_issues, text, ctx):
        if not any(san in i for i in issues + out):
            out.append(issue)
    out += _fail_open(_forces_issues, text, text, ctx)
    out += _fail_open(line_trade_issues, text, ctx)
    out += _fail_open(plan_issues, lowered, ctx)
    out += _fail_open(_structure_issues, text, ctx)
    out += _fail_open(_material_word_issues, text, ctx)
    return [i for i in out if i not in issues]


# ── checks told in words ─────────────────────────────────────────────────────────────────────────────────────────
# A check told in words («Ход Qb3 даёт шах королю g8», «Rc7 — с шахом», «Bc4 — шах», "Qb3 gives check") with the e6
# bishop in the way (review-miss 03.11: 5 of 27 such claims caught, and those by the engine judging the move — only
# a «+» after the move was ever compared with gives_check). The move is the first one written in its clause, legal on
# the board the answer is about, with no «+» (the suffix has its own check); the words are a statement about it — not
# denied («не даёт шаха»), not a condition, a question or a wish. It holds when the move checks there, or on the
# scene the sentence before left where it is legal too.
_CHECK_WORDS = re.compile(
    r"\s*(?:[—–:,-]\s*)?(?:(?:это|и|тут|здесь|сразу|уже|причём|причем|ид[её]т|пойд[её]т|будет|is|it'?s|and|that'?s|"
    r"goes|comes|comes\s+with|is\s+played)\s+)*"
    r"(?:(?:сразу\s+)?(?:да[её]т|дает|объявляет|ставит|gives|delivers)\s+(?:сразу\s+)?(?:шах|check)(?![а-яёa-z])"
    r"|с\s+шахом(?![а-яё])|шах(?![а-яё])|(?:a\s+)?check(?![a-z])|with\s+check(?![a-z]))", re.IGNORECASE)
# what may stand before the move in its clause: nothing, a dash or emphasis, «Ход», "The move" — not «ладья идёт на h4»
_CHECK_HEAD = re.compile(r"[\s*_>#—–-]*(?:(?:ход(?:ом)?|move|the\s+move)\s+)?[*_]*", re.IGNORECASE)
_CHECK_NOT = re.compile(r"(?<![а-яёa-z])(?:не|нет|ни|без|not|no|never|если|когда|после|бы|чтобы|хотел\w*|можно\s+ли|"
                        r"if|when|after|would|could|unless|instead)(?![а-яёa-z])", re.IGNORECASE)


def _check_word_issues(text: str, ctx: CheckContext) -> list[str]:
    board = ctx.current
    if board is None or _lesson(ctx) or "?" in text:
        return []
    conv, _ = _to_san(text)
    out = []
    for m in _MOVE.finditer(conv):
        if m["check"] or m["num"]:
            continue
        cs = max(conv.rfind(c, 0, m.start()) for c in ".;!\n") + 1
        head = conv[cs: m.start()]
        advice = _ADVICE_FRAME.search(head)
        if not (_CHECK_HEAD.fullmatch(head) or (advice and not _ADVICE_PAST.search(head))) or _MOVE.search(head):
            continue  # not the first move of its clause («после Nf3 Bc4 — шах»), or words before it of a line
        if _CHECK_NOT.search(head):
            continue
        cw = _CHECK_WORDS.match(conv, m.end())
        if cw is None:
            continue
        end = min([i for i in (conv.find(c, m.end()) for c in ".;!\n") if i >= 0] or [len(conv)])
        tail = conv[cw.end(): end]
        if _CHECK_NOT.search(conv[m.end(): cw.end()]) or re.match(r"\s*(?:и\s+)?мат|\s*(?:and\s+)?mate", tail, re.IGNORECASE):
            continue  # «… не даёт шаха», «шах и мат» (the mate words have their own check)
        san = m["san"]
        boards = [board]
        before = ctx.scene_before
        if before is not None and before[0] is not None and before[2] <= 2:
            boards.append(before[0])
        legal = []
        for b in boards:
            try:
                legal.append((b, b.parse_san(san)))
            except ValueError:
                continue
        if not legal or legal[0][0] is not board:
            continue  # not a move of the board the answer is about
        if any(b.gives_check(mv) for b, mv in legal):
            continue
        out.append(f"{san} gives no check")
    return out


# A move told to be played now («Сыграй Qxd5 — конь висит», «Играй Bxh5», «Рокируйся в короткую — O-O», «Отступи конём:
# Nb1», «Лучший ход — Qe2») that is not a legal move of the board now: the queen's way blocked by the d4 pawn, the
# bishop and knight between king and rook, the knight pinned (review-miss 03.11: 13 of 28 such sentences caught —
# «Хорошо Qxd5» was, «Сыграй Qxd5» was not: the imperative made the move «hypothetical», and a move legal nowhere was
# let be as a plan of another position). The board is the one the answer is about now; a move in the past tense, after
# a condition or a line, or for the side not to move is not this frame.
_ADVICE_FRAME = re.compile(
    r"(?<![а-яёa-z])(?:сыграй(?:те)?|играй(?:те)?|возьми(?:те)?|бери(?:те)?|отступи(?:те)?|отведи(?:те)?|уведи(?:те)?|"
    r"рокируйся|рокируйтесь|делай|сделай(?:те)?|ходи(?:те)?|"
    r"(?:лучший|сильнейший|правильный|верный)\s+ход(?:\s+(?:здесь|сейчас|тут|в\s+этой\s+позиции))?(?:\s*[—–:-]|\s+это)?|"
    r"лучше\s+всего|сильнее\s+всего|play|take|retreat|castle|the\s+best\s+move(?:\s+here)?\s+is|best\s+is)"
    r"(?:\s+(?:сейчас|сразу|здесь|now|here|right\s+away))?"
    r"(?:\s+(?:в\s+(?:короткую|длинную)(?:\s+сторону)?|кон[её]м|слоном|ладь[её]й|ферз[её]м|корол[её]м|пешкой|"
    r"with\s+the\s+\w+|on\s+the\s+(?:king|queen)side|short|long|ходом))?"
    r"\s*[—–:,-]?\s*$", re.IGNORECASE)
_ADVICE_PAST = re.compile(r"(?<![а-яёa-z])(?:был\w*|стоил\w*|надо\s+было|следовал\w*|нужно\s+было|вместо|тогда|если|после|"
                          r"когда|бы|в\s+партии|ходу|не|нельзя|could|should|would|was|were|instead|if|after|when|then|"
                          r"don'?t|not|never|in\s+the\s+game)(?![а-яёa-z])", re.IGNORECASE)


def _not_legal_reason(board: chess.Board, san: str, latin: bool = True) -> Optional[str]:
    """Why *san* is no move of *board* (its side to move): castling's reason, a pinned or blocked piece, no such piece
    at all (*latin*: the piece letter was written as such, not a Russian «К» that may be the king), or None when the
    words cannot be placed."""
    norm = san.replace("0", "O").rstrip("+#")
    if norm in ("O-O", "O-O-O"):
        from src.board_rules import castling_status

        legal, why = castling_status(board).get(norm, (True, ""))
        return None if legal else f"castling {'short' if norm == 'O-O' else 'long'} is not possible: {why}"
    m = re.fullmatch(r"([KQRBN])?([a-h])?([1-8])?x?([a-h][1-8])(=[QRBN])?", norm)
    if not m:
        return None
    ptype = chess.PIECE_SYMBOLS.index(m.group(1).lower()) if m.group(1) else chess.PAWN
    to = chess.parse_square(m.group(4))
    froms = [sq for sq in board.pieces(ptype, board.turn)
             if (m.group(2) is None or chess.square_file(sq) == chess.FILE_NAMES.index(m.group(2)))
             and (m.group(3) is None or chess.square_rank(sq) == int(m.group(3)) - 1)
             and (ptype != chess.PAWN or chess.square_file(sq) in (chess.square_file(to) - 1, chess.square_file(to),
                                                                   chess.square_file(to) + 1))]
    if ptype != chess.PAWN and latin and not board.pieces(ptype, board.turn) and m.group(2) is None and m.group(3) is None:
        return f"{'White' if board.turn else 'Black'} has no {_NAMES[ptype]}"
    reasons = []
    for frm in froms:
        if ptype != chess.PAWN and not _geometry_move(ptype, frm, to):
            continue
        if ptype == chess.PAWN:
            continue  # a pawn's move has its own words (captures, pushes): left to the other checks
        why = _why_not_reach(board, frm, to)
        if why is None:
            return None
        if "not a" in why and "move" in why:
            continue
        reasons.append(f"the {_NAMES[ptype]} on {chess.square_name(frm)}: {why}")
    return "; ".join(reasons) if reasons else None


def _advice_illegal_issues(text: str, ctx: CheckContext) -> list[tuple]:
    board = ctx.current
    if board is None or _lesson(ctx) or "?" in text or getattr(ctx, "board_moved", False):
        return []
    if ctx.student_color is not None and board.turn != ctx.student_color:
        return []  # the student is not to move: the move told comes after a reply
    conv, cyr_k = _to_san(text)
    out = []
    for m in _MOVE.finditer(conv):
        if m["num"] or (m["bdots"] and board.turn != chess.BLACK):
            continue
        cs = max(conv.rfind(c, 0, m.start()) for c in ".;!\n") + 1
        head = conv[cs: m.start()]
        fr = _ADVICE_FRAME.search(head)
        if fr is None or _MOVE.search(head) or _ADVICE_PAST.search(conv[cs: fr.start()] + " " + fr.group(0)):
            continue
        if re.match(r"[*_]*[?!]*\?", conv[m.end():]):
            continue
        san = m["san"]
        try:
            mv = board.parse_san(san)
        except ValueError:
            mv = None
        if mv is not None:
            if m["check"] == "+" and not board.gives_check(mv):
                out.append((san, f"{san}+ gives no check here"))  # «Сыграй ...Rd8+ — шах» on the board now
            break
        why = _not_legal_reason(board, san, latin=m.start("san") not in cyr_k)
        if why:
            out.append((san, f"{san} is not a legal move here: {why}"))
        break
    return out



# ── «силы равны» ───────────────────────────────────────────────────────────────────────────────────────────
# «Силы равны», «Силы примерно равны», «Соотношение сил равное», «По силам примерно паритет», "The forces are equal" with
# a piece missing (review-miss 03.11: never read — «силы» was no material anchor; VERDICT §7.4 lists it as a live
# major). «Силы» may mean material or the evaluation, so the claim is wrong only when both are: a piece's worth or more
# down in material (3 points) and the engine's evaluation beyond ±1.5 (without the engine: a rook's worth, 5 points).
_FORCES_EQ = re.compile(
    _B2 + r"(?:(?:силы|соотношение\s+сил|по\s+силам|the\s+forces|forces)\s+(?:(?:у\s+сторон|сторон|сейчас|здесь|тут|"
    r"по-прежнему|пока|примерно|почти|практически|приблизительно|в\s+целом|are|roughly|about|almost|basically|still)\s+)*"
    r"(?P<eq>равн\w*|поровну|паритет\w*|равенств\w*|одинаков\w*|сбалансирован\w*|equal|even|level|balanced)"
    r"|(?P<eq2>равн\w+|одинаков\w+)\s+силы)(?![а-яa-z])", re.IGNORECASE)


def _forces_issues(text: str, original: str, ctx: CheckContext) -> list[str]:
    if ctx.current is None or _lesson(ctx):
        return []
    out = []
    for m in _FORCES_EQ.finditer(text):
        if _is_hypothetical(text, original, m.start(), ctx=ctx) \
                or re.search(r"(?<![а-яёa-z])(?:не|нет|ни|not|never|no)(?![а-яёa-z])|n't", text[max(0, m.start() - 20): m.end()]) \
                or "?" in text[m.end():] or _mat_cond_after(text, m.end()):
            continue
        from src.game_record import material as _material_of

        diff = _material_of(ctx.current)["diff"]
        ev = ctx.engine_eval
        if abs(diff) < 3 or (ev is not None and abs(ev) < 1.5) or (ev is None and abs(diff) < 5):
            continue
        tail = f"; the engine evaluates the position at {_fmt_eval(ev)}" if ev is not None else ""
        out.append(f"material: {_imbalance(ctx.current)} ({'White' if diff > 0 else 'Black'} +{abs(diff)} in points){tail}"
                   f" — the forces are not equal")
    return out



# ── where a piece can go ────────────────────────────────────────────────────────────────────────────────────────
# «Слон g5 может отступить на e3» with White's own pawn on e3, «Конь c3 может уйти на b1» with the knight pinned, «Слон d3
# может отступить на b1» with the queen on c2 between (review-miss 03.11, r01–r32: 0 of 32 caught — the check above
# judges only whether a square the piece reaches is safe, and drops a square it cannot reach). A square a piece is said
# to be able to go to is checked for the piece's own move: its geometry, its own piece there, a piece in the way, a pin.
_REACH_SUBJ = re.compile(
    _W + r"(?:(?P<own>тво(?:й|я|е|его|ей)|ваш(?:а|е)?|мо(?:й|я|е)|your|my|бел(?:ый|ая|ое)|ч[её]рн(?:ый|ая|ое)|white'?s?|black'?s?)\s+)?"
    r"(?:the\s+)?(?P<n>слон|конь|ладья|ферзь|король|bishop|knight|rook|queen|king)"
    r"(?:\s+(?:на\s+|с\s+|on\s+|from\s+)?(?P<sq>[a-h][1-8]))?(?![0-9а-яёa-z])", re.IGNORECASE)
_REACH_VERB = re.compile(
    r"(?:(?:может|сможет|могут|можно|could|can|may|is\s+able\s+to)\s+(?:(?:спокойно|всегда|ещё|еще|просто|still|always|"
    r"easily|simply|safely)\s+)?(?:отступить|отойти|уйти|вернуться|спрятаться|перейти|переместиться|перебраться|"
    r"пойти|прыгнуть|retreat|go\s+back|drop\s+back|return|move|go|jump)"
    r"|отступит|отойд[её]т|retreats|will\s+retreat)"
    r"\s+(?:обратно\s+|назад\s+|back\s+)?(?:на|в|to)\s+(?:пол[еяю]\s+|the\s+)?(?P<sqs>" + _SQ_LIST + r")(?![0-9])",
    re.IGNORECASE)
_REACH_NOT = re.compile(_W + r"(?:если|когда|после|как\s+только|пусть|допустим|иначе|бы|if|when|after|once|unless|would|"
                        r"should|чтобы|в\s+случае)" + _E, re.IGNORECASE)
_REACH_TYPES = {"сло": chess.BISHOP, "кон": chess.KNIGHT, "лад": chess.ROOK, "фер": chess.QUEEN, "кор": chess.KING,
                "bis": chess.BISHOP, "kni": chess.KNIGHT, "roo": chess.ROOK, "que": chess.QUEEN, "kin": chess.KING}
_RU_PIECE = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook",
             chess.QUEEN: "queen", chess.KING: "king"}


def _why_not_reach(b: chess.Board, frm: int, to: int) -> Optional[str]:
    """Why the piece on *frm* cannot go to *to* on *b* (its owner to move); None when it can (or it would capture)."""
    piece = b.piece_at(frm)
    if piece is None:
        return None
    if chess.Move(frm, to) in b.legal_moves:
        return None
    name = _RU_PIECE[piece.piece_type]
    if not _geometry_move(piece.piece_type, frm, to) or (piece.piece_type == chess.KING and chess.square_distance(frm, to) > 1):
        return f"that is not a {name}'s move"
    there = b.piece_at(to)
    if there is not None and there.color == piece.color:
        return f"its own {_RU_PIECE[there.piece_type]} stands on {chess.square_name(to)}"
    if piece.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        between = [sq for sq in chess.SquareSet(chess.between(frm, to)) if b.piece_at(sq) is not None]
        if between:
            sq = between[0]
            p = b.piece_at(sq)
            return f"the {'white' if p.color else 'black'} {_RU_PIECE[p.piece_type]} on {chess.square_name(sq)} is in the way"
    if piece.piece_type != chess.KING and b.is_pinned(piece.color, frm):
        ray = b.pin(piece.color, frm)
        pinner = next((sq for sq in ray if b.piece_at(sq) is not None and b.color_at(sq) != piece.color), None)
        by = f" by the {_RU_PIECE[b.piece_type_at(pinner)]} on {chess.square_name(pinner)}" if pinner is not None else ""
        return f"it is pinned to its king{by}"
    if piece.piece_type == chess.KING and b.is_attacked_by(not piece.color, to):
        return f"{chess.square_name(to)} is attacked"
    if b.is_check():
        return "its king is in check and that move does not answer it"
    return None


def _not_lesson(ctx) -> bool:
    """The coach's surfaces, not the /learn tutor's (its checks stay main's; the team's, 19.10)."""
    return getattr(ctx, "relation_surface", "text") != "lesson"


def _retreat_reach_issues(text: str, ctx) -> list[str]:
    board = getattr(ctx, "current", None)
    if board is None or "?" in text or not _not_lesson(ctx):
        return []
    out = []
    for vm in _REACH_VERB.finditer(text):
        cs = max(text.rfind(c, 0, vm.start()) for c in ".;!\n") + 1
        clause_head = text[cs: vm.start()]
        # the piece: the last one named before the verb in its clause, with nothing but a few words between
        subs = list(_REACH_SUBJ.finditer(clause_head))
        if not subs or len(clause_head) - subs[-1].end() > 30:
            continue
        sm = subs[-1]
        if _negated_before(text, vm.start()) or re.search(_W + r"не" + _E, text[sm.end(): vm.start()]):
            continue
        end = min([i for i in (text.find(c, vm.end()) for c in ".;!\n") if i >= 0] or [len(text)])
        if _REACH_NOT.search(text[cs: end]):
            continue  # a condition or a line («после e5 конь отступит на d5»): another board
        if _WRITTEN_MOVE.search(text[cs: end]) or re.search(r"(?<![0-9])\d{1,3}\s?\.{1,3}\s?[a-hkqrbnкфлс]", text[cs: end]):
            continue  # a move written in the clause: the board after it
        ptype = _REACH_TYPES[sm["n"].lower()[:3]]
        own = (sm["own"] or "").lower().replace("ё", "е")
        color = None
        if own.startswith(("тво", "ваш", "your")):
            color = getattr(ctx, "student_color", None)
            if color is None:
                continue
        elif own.startswith(("мо", "my")):
            sc = getattr(ctx, "student_color", None)
            if sc is None:
                continue
            color = not sc
        elif own.startswith(("бел", "white")):
            color = chess.WHITE
        elif own.startswith(("черн", "black")):
            color = chess.BLACK
        if sm["sq"]:
            frm = chess.parse_square(sm["sq"])
            p = board.piece_at(frm)
            if p is None or p.piece_type != ptype or (color is not None and p.color != color):
                continue  # the piece is not there: another check's business
            cands = [frm]
        else:
            cands = [sq for c in ((color,) if color is not None else (chess.WHITE, chess.BLACK))
                     for sq in board.pieces(ptype, c)]
        targets = [chess.parse_square(x) for x in re.findall(r"[a-h][1-8]", vm["sqs"])]
        if not cands or not targets:
            continue
        verdicts = []
        for frm in cands:
            b = board.copy(stack=False)
            b.turn = board.color_at(frm)
            b.ep_square = None
            verdicts.append((frm, [(t, _why_not_reach(b, frm, t)) for t in targets]))
        if any(all(w is None for _, w in v) for _, v in verdicts):
            continue  # some piece of that kind does reach every square named
        if len(verdicts) != 1:
            continue  # several pieces it may be about: which one is not said
        frm, v = verdicts[0]
        bad = [(t, w) for t, w in v if w]
        if bad:
            out.append(f"the {_RU_PIECE[ptype]} on {chess.square_name(frm)} cannot go to "
                       + "; ".join(f"{chess.square_name(t)} — {w}" for t, w in bad))
    return out




# ── a trade told on a line of the board now ─────────────────────────────────────────────────────────
# «Размен Nxe5 Nxe5 — это просто обмен коней, материал остаётся равным» (a knight for a pawn), «Размен Rxd6 cxd6 —
# ладья за слона, равный обмен», «Qxd5 — это размен ферзя на слона» with nothing to take back (review-miss 03.11: 2–3
# of 22 such claims caught — a trade line is legal, so the line checks pass, and the balance it states was never
# compared with what its captures take). The written moves are played from the board now; what each side loses is
# counted exactly; the balance said — equal («равный обмен», «материал остаётся равным», «обмен коней», "even
# trade") or «A за/на B» — must be what the line takes. A single capture said to be a trade is judged by whether
# anything can take back on its square.
_LT_SAN = re.compile(r"(?<![\w-])(?:\d{1,3}\s*\.{1,3}\s*|\.\.\.\s*)?([KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)[+#!?]*(?![\w-])")
_LT_TRADE = re.compile(r"(?<![\w-])(?:размен\w*|обмен\w*|меня\w*|разменива\w*|trade\w*|exchang\w*|swap\w*)(?![\w-])",
                       re.IGNORECASE)
_LT_EQUAL = re.compile(
    r"(?<![\w-])(?:равн\w+\s+(?:обмен|размен)\w*|(?:обмен|размен)\w*\s+(?:на\s+)?равн\w+|материал\w*\s+(?:(?:при\s+этом|"
    r"так\s+и|по-прежнему|снова|опять)\s+)*(?:оста[её]тся|останется|остал\w+|будет|сохраня\w+|не\s+меня\w+)\s*(?:равн\w*)?|"
    r"по\s+материалу\s+(?:ничего\s+не\s+меняется|без\s+изменений|равенство)|even\s+trade|equal\s+trade|"
    r"material\s+(?:stays|remains)\s+(?:equal|level|even|the\s+same))(?![\w-])", re.IGNORECASE)
_LT_PAIR = re.compile(r"(?<![\w-])(?:обмен|размен)\w*\s+(?P<u>коней|слонов|ладей|ферзей|пешек|knights|bishops|rooks|queens|pawns)"
                      r"(?![\w-])", re.IGNORECASE)
_LT_FOR = re.compile(r"(?P<a>(?:(?:[\w'’-]+)\s+){0,2}?[\w'’-]+)\s+(?:за|на|for)\s+(?P<b>[\w'’-]+(?:\s+(?:и|and)\s+[\w'’-]+)?)",
                     re.IGNORECASE)
_LT_NOT = re.compile(r"(?<![\w-])(?:не|ни|нет|бы|если|когда|после\s+того|чтобы|вместо|можно\s+ли|not|no|if|when|would|could|"
                     r"instead|unless)(?![\w-])", re.IGNORECASE)
_LT_TYPE = {"N": chess.KNIGHT, "B": chess.BISHOP, "R": chess.ROOK, "Q": chess.QUEEN, "P": chess.PAWN}
_LT_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def _lt_fits(lost: Counter, slots: list) -> bool:
    """*lost* (piece type → count, one side) is exactly what *slots* (from _units) name."""
    want: Counter = Counter()
    for s in slots:
        if s in ("P+",):
            want[chess.PAWN] += 1
        elif s in _LT_TYPE:
            want[_LT_TYPE[s]] += 1
        elif s == "minor":
            if lost[chess.KNIGHT] + lost[chess.BISHOP] < 1:
                return False
            want["minor"] += 1
        else:
            return False  # «фигуру», «качество»: not read here
    got = Counter(lost)
    if want.get("minor"):
        m = want.pop("minor")
        for pt in (chess.KNIGHT, chess.BISHOP):
            while m and got[pt] > want[pt]:
                got[pt] -= 1
                m -= 1
        if m:
            return False
    return all(got[k] == want[k] for k in set(got) | set(want) if k != "minor")


def _lt_phrase(lost: Counter) -> str:
    parts = [f"{n} {_NAME[pt][0] if n == 1 else _NAME[pt][1]}" for pt, n in sorted(lost.items(), key=lambda x: -_LT_VALUE[x[0]]) if n]
    return ", ".join(parts) if parts else "nothing"


def line_trade_issues(sentence: str, ctx: Any) -> list[str]:
    board = getattr(ctx, "current", None)
    if board is None or not sentence or getattr(ctx, "relation_surface", "text") == "lesson" or "?" in sentence:
        return []
    if not _LT_TRADE.search(sentence) and not re.search(r"(?<![\w-])(?:за|for)(?![\w-])", sentence):
        return []
    out = []
    for clause in re.split(r"(?<=[.!;])\s+|\n", sentence):
        sans = list(_LT_SAN.finditer(clause))
        if not sans:
            continue
        # the line: the written moves one after another (commas and spaces between), from the first
        line = [sans[0]]
        for x in sans[1:]:
            if re.fullmatch(r"[\s,]*", clause[line[-1].end(): x.start()]):
                line.append(x)
            else:
                break
        words = clause[line[-1].end():]
        head = clause[: line[0].start()]
        if _LT_NOT.search(head + " " + words):
            continue
        if not (_LT_TRADE.search(head) or _LT_TRADE.search(words) or _LT_FOR.search(words)):
            continue
        b = board.copy(stack=False)
        lost = {chess.WHITE: Counter(), chess.BLACK: Counter()}
        try:
            for x in line:
                mv = b.parse_san(x.group(1))
                if b.is_capture(mv):
                    victim = chess.PAWN if b.is_en_passant(mv) else b.piece_type_at(mv.to_square)
                    lost[not b.turn][victim] += 1
                b.push(mv)
        except ValueError:
            continue  # not a line of the board now: the other checks' business
        if not any(lost.values()):
            continue
        label = " ".join(x.group(1) for x in line)
        net = sum(_LT_VALUE[pt] * n for pt, n in lost[chess.BLACK].items()) - \
            sum(_LT_VALUE[pt] * n for pt, n in lost[chess.WHITE].items())
        said = f"after {label} White loses {_lt_phrase(lost[chess.WHITE])} and Black loses {_lt_phrase(lost[chess.BLACK])}"
        # a single capture called a trade: something must be able to take back
        if len(line) == 1 and _LT_TRADE.search(head + words):
            sq = b.peek().to_square
            if not any(m.to_square == sq for m in b.legal_moves if b.is_capture(m)):
                out.append(f"after {label} nothing can take back on {chess.square_name(sq)} — it is no trade, a piece is simply won")
            continue
        pair = _LT_PAIR.search(words)
        if _LT_EQUAL.search(words) or pair:
            if pair:
                pt = _LT_TYPE[_unit(pair["u"]) or "P"]
                if not (lost[chess.WHITE][pt] >= 1 and lost[chess.BLACK][pt] >= 1 and net == 0):
                    out.append(f"{said} — not a trade of {_NAME[pt][1]}")
                    continue
            if net != 0:
                out.append(f"{said} — the trade is not equal ({'White' if net > 0 else 'Black'} gains {abs(net)} in points)")
            continue
        fm = _LT_FOR.match(re.sub(r"^[\s,]*[—–:-]+\s*(?:(?:это|здесь|тут|итого|it'?s|that'?s)\s+)?", "", words)) \
            if re.match(r"[\s,]*[—–:-]", words) else None
        if fm and (len(line) < 2 or re.search(r"(?<![\w-])(?:после|after)(?![\w-])", head, re.IGNORECASE)):
            fm = None  # «После Nxd5 его бьёт конь f6 … ты отдаёшь коня за пешку»: replies told in words — another line
        if fm:
            give = _units(fm["a"].split()[-1], False)
            get = _units(fm["b"], False)
            if not give or not get or any(s in ("piece", "exchange") for s in give + get):
                continue
            if not any(_lt_fits(lost[c], give) and _lt_fits(lost[not c], get) for c in (chess.WHITE, chess.BLACK)):
                out.append(said)
    return out


# ── a plan's precondition ─────────────────────────────────────────────────────────────────────────────────────────
# «План белых — длинная рокировка» with the white king on d2, «План — c4-c5» with no white c-pawn, «сдвоить ладьи по
# открытой линии d» with a pawn on d4, «использовать пешечное большинство на ферзевом фланге» when it is on the other
# wing (review-miss 03.11: 1 of 23 such plans caught — plans had no reader). Only what the board fixes for good is
# read: a right to castle that is gone, a pawn that is not on its file, the pawns on a file and on a wing. A plan of the
# other side is read for that side; a negation, a condition, a question or a move written before it leaves it alone.
_PLAN_WORD = re.compile(_W + r"(?:план\w*|иде\w+|задач\w+|стратеги\w*|plan\w*|idea\w*)" + _E, re.IGNORECASE)
_PLAN_SIDE = re.compile(_W + r"(?P<s>бел\w+|ч[её]рн\w+|white|black|тво\w+|ваш\w*|your|соперник\w*|противник\w*|opponent\w*)"
                        + _E, re.IGNORECASE)
_PLAN_NOT = re.compile(_W + r"(?:не|нет|ни|без|уже\s+не|если|когда|после|бы|был\w*|not|no|never|if|when|after|would|once|"
                       r"instead|вместо|нельзя|невозможн\w*)" + _E, re.IGNORECASE)
_PLAN_LONG = re.compile(_W + r"(?:длинн\w+\s+рокировк\w*|рокировк\w*\s+в\s+длинную(?:\s+сторону)?|рокир\w+\s+длинно|"
                        r"o-o-o|0-0-0|castl\w*\s+(?:long|queenside)|queenside\s+castl\w*|long\s+castl\w*)" + _E, re.IGNORECASE)
_PLAN_SHORT = re.compile(_W + r"(?:коротк\w+\s+рокировк\w*|рокировк\w*\s+в\s+короткую(?:\s+сторону)?|рокир\w+\s+коротко|"
                         r"o-o(?!-)|0-0(?!-)|castl\w*\s+(?:short|kingside)|kingside\s+castl\w*|short\s+castl\w*)" + _E,
                         re.IGNORECASE)
_PLAN_ANY_CASTLE = re.compile(_W + r"(?:рокировк\w*|рокироваться|castl\w*)" + _E, re.IGNORECASE)
_PLAN_PAWN_FILE = re.compile(_W + r"(?P<f>[a-h])-?пешк\w*|(?<![a-z0-9])(?P<ef>[a-h])-pawn(?![a-z])", re.IGNORECASE)
_PLAN_PUSH = re.compile(r"(?<![a-zа-яё0-9.])(?:\.\.\.\s*)?(?P<a>[a-h])(?P<ra>[1-8])\s*-\s*(?P=a)(?P<rb>[1-8])(?![0-9])")
_PLAN_PUSH_CUE = re.compile(_W + r"(?:прорыв\w*|продвиж\w*|продвига\w*|наступ\w*|пешк\w*|break\w*|push\w*|advanc\w*|pawn\w*|"
                            r"план\w*|plan\w*|штурм\w*|storm\w*)" + _E, re.IGNORECASE)
_PLAN_OPEN = re.compile(_W + r"(?P<half>полу)?открыт\w*\s+(?:лини\w+|вертикал\w+|файл\w*)\s+(?P<f>[a-h])(?![a-z0-9])"
                        r"|(?<![a-z0-9])(?:the\s+)?(?P<ehalf>half-|semi-)?open\s+(?P<ef>[a-h])-?file", re.IGNORECASE)
_PLAN_MAJ = re.compile(_W + r"(?:пешечн\w+\s+)?большинств\w*\s+на\s+(?P<w>ферзев\w+|королевск\w+)\s+фланг\w*"
                       r"|(?P<ew>queenside|kingside|queen-side|king-side)\s+(?:pawn\s+)?majority", re.IGNORECASE)


def _plan_side(clause: str, ctx) -> Optional[bool]:
    """The side whose plan the clause tells: a side named in it, the student («твой план»), else the side to move."""
    sides = [m["s"].lower().replace("ё", "е") for m in _PLAN_SIDE.finditer(clause)]
    student = getattr(ctx, "student_color", None)
    for s in sides:
        if s.startswith(("бел", "white")):
            return chess.WHITE
        if s.startswith(("черн", "black")):
            return chess.BLACK
        if s.startswith(("тво", "ваш", "your")):
            return student if student is not None else ctx.current.turn
        if s.startswith(("соперник", "противник", "opponent")):
            return None if student is None else not student
    return student if student is not None else ctx.current.turn


def plan_issues(lowered: str, ctx) -> list[str]:
    board = ctx.current
    if board is None or "?" in lowered or not _PLAN_WORD.search(lowered):
        return []
    out = []
    for clause in re.split(r"[.;!\n]", lowered):
        if _PLAN_NOT.search(clause) or _WRITTEN_MOVE.search(re.sub(r"o-o(?:-o)?|0-0(?:-0)?", " ", clause)):
            continue
        side = _plan_side(clause, ctx)
        if side is None:
            continue
        name = "White" if side == chess.WHITE else "Black"
        from src.board_rules import castling_status

        status = castling_status(board, side)
        if _PLAN_LONG.search(clause) and not (board.has_queenside_castling_rights(side)):
            out.append(f"{name} can no longer castle long: {status['O-O-O'][1]}")
        elif _PLAN_SHORT.search(clause) and not board.has_kingside_castling_rights(side):
            out.append(f"{name} can no longer castle short: {status['O-O'][1]}")
        elif _PLAN_ANY_CASTLE.search(clause) and not _PLAN_LONG.search(clause) and not _PLAN_SHORT.search(clause) \
                and not board.has_castling_rights(side) and re.search(_W + r"(?:рокировк\w+|castling)" + _E, clause):
            out.append(f"{name} can no longer castle: {status['O-O'][1]}")
        pawns = board.pieces(chess.PAWN, side)
        for m in _PLAN_PAWN_FILE.finditer(clause):
            f = chess.FILE_NAMES.index((m["f"] or m["ef"]).lower())
            if not pawns & chess.BB_FILES[f]:
                out.append(f"{name} has no {chess.FILE_NAMES[f]}-pawn")
        if _PLAN_PUSH_CUE.search(clause):
            for m in _PLAN_PUSH.finditer(clause):
                f = chess.FILE_NAMES.index(m["a"])
                ra, rb = int(m["ra"]), int(m["rb"])
                forward = rb > ra if side == chess.WHITE else rb < ra
                if not forward or abs(rb - ra) > 2:
                    continue  # not a pawn's step: «a1-a8», a rook's or another reading
                if not pawns & chess.BB_FILES[f]:
                    out.append(f"{name} has no {chess.FILE_NAMES[f]}-pawn for {m.group(0).strip()}")
        for m in _PLAN_OPEN.finditer(clause):
            f = chess.FILE_NAMES.index((m["f"] or m["ef"]).lower())
            half = bool(m["half"] or m["ehalf"])
            on_file = board.pieces(chess.PAWN, side) & chess.BB_FILES[f] if half else \
                (board.pieces(chess.PAWN, chess.WHITE) | board.pieces(chess.PAWN, chess.BLACK)) & chess.BB_FILES[f]
            if on_file:
                sq = chess.square_name(next(iter(on_file)))
                out.append(f"the {chess.FILE_NAMES[f]}-file is not {'half-' if half else ''}open: a pawn stands on {sq}")
        for m in _PLAN_MAJ.finditer(clause):
            w = (m["w"] or m["ew"]).lower()
            files = range(0, 4) if w.startswith(("ферз", "queen")) else range(4, 8)
            mask = 0
            for f in files:
                mask |= chess.BB_FILES[f]
            mine = len(board.pieces(chess.PAWN, side) & mask)
            theirs = len(board.pieces(chess.PAWN, not side) & mask)
            if mine <= theirs:
                wing = "queenside" if w.startswith(("ферз", "queen")) else "kingside"
                out.append(f"{name} has no pawn majority on the {wing}: {mine} pawns against {theirs}")
    return out


# ── a written line with an impossible move ────────────────────────────────────────────────────────────────────────
# «Продолжение Bxf6 Nxf6 Qxc7 …» with the c4 pawn between the queen and c7, «Линия Nxg4 Nxg4 Qxg4 …» where no black
# knight reaches g4 (review-miss 03.11: only the «После … играют X» frame replayed every move; in a named line only the
# first went to the engine). A line named as a line, its moves written one after another right after the noun, starting
# with a legal move of the board now: the first move it cannot make is reported. («после …» is not read here: a move
# told in words may come first — «конь f6 забирает пешку e4, а после Nxe4 d5 …».)
_LINE_HEAD = re.compile(r"(?<![а-яёa-z])(?:лини(?:я|и|ю|ей)|вариант(?:е|а|ом)?|продолжени(?:е|я|ю|ем)|"
                        r"последовательност(?:ь|и|ью)(?:\s+ход(?:ов|ами))?|line|variation|continuation)"
                        r"\s*[:—–-]?\s*$", re.IGNORECASE)


def _line_move_issues(text: str, ctx: CheckContext) -> list[tuple]:
    board = ctx.current
    if board is None:
        return []
    conv, _ = _to_san(text)
    moves = list(_MOVE.finditer(conv))
    out, i = [], 0
    while i < len(moves):
        m = moves[i]
        cs = max(conv.rfind(c, 0, m.start()) for c in ";!?\n") + 1
        if not _LINE_HEAD.search(conv[max(cs, m.start() - 40): m.start()]):
            i += 1
            continue
        seq, j = [m], i + 1
        while j < len(moves) and re.fullmatch(r"\s+", conv[seq[-1].end(): moves[j].start()]):
            seq.append(moves[j])
            j += 1
        i = j
        if len(seq) < 2 or (seq[0]["bdots"] and board.turn != chess.BLACK) or seq[0]["num"]:
            continue
        if re.match(r"\s*(?:,|или|либо|or)(?![а-яёa-z])", conv[seq[-1].end():], re.IGNORECASE):
            continue  # «продолжения — c4, d3, b3 или Bc4»: alternatives listed, not one line
        b = board.copy(stack=False)
        done = []
        for k, x in enumerate(seq):
            san = x["san"] + (x["check"] or "")
            try:
                mv = b.parse_san(san)
            except ValueError:
                if k > 0:
                    out.append((x["san"], f"{x['san']} is impossible after {' '.join(done)} in this line"))
                break
            done.append(b.san(mv))
            b.push(mv)
    return out


# ── the pawn structure after a written line ───────────────────────────────────────────────────────────────────────
# «После Bxe7 Qxe7 у чёрных появятся сдвоенные пешки», «После cxd5 у белых сдвоенные пешки на вертикали c», «После dxe5
# dxe5 у чёрных изолированная пешка e5» (fresh-miss-2: 2 of 17 such claims caught). The written moves are played from
# the board now; doubled pawns are two of the side's pawns on one file (the file named, if any), an isolated pawn one
# with none of its side's pawns on the files next to it (the square named, if any).
_STRUCT = re.compile(
    r"(?<![а-яёa-z])(?:у\s+)?(?P<side>белых|ч[её]рных|тебя|white|black)\s+(?:(?:появ\w+|будут|будет|окажутся|окажется|"
    r"получ\w+|оста\w+|сразу|уже|тоже|ещё|еще|will\s+have|gets?|has|have)\s+)*"
    r"(?:(?P<dbl>сдвоенн\w+\s+пешк\w*|doubled\s+pawns?)|(?P<iso>изолированн\w+\s+пешк\w*|(?:an\s+)?isolated\s+pawn))"
    r"(?:\s+(?:на\s+)?(?:вертикали|линии|on\s+the)\s+(?P<file>[a-h])(?:-?file)?)?(?:\s+(?:на\s+)?(?P<sq>[a-h][1-8]))?",
    re.IGNORECASE)


def _structure_issues(text: str, ctx: CheckContext) -> list[str]:
    board = ctx.current
    if board is None or not re.search(r"(?<![а-яёa-z])(?:после|after)(?![а-яёa-z])", text, re.IGNORECASE):
        return []
    conv, _ = _to_san(text)
    out = []
    for sm in _STRUCT.finditer(conv):
        head = conv[: sm.start()]
        cs = max(head.rfind(c) for c in ".;!?\n") + 1
        clause = head[cs:]
        am = list(re.finditer(r"(?<![а-яёa-z])(?:после|after)\s+", clause, re.IGNORECASE))
        if not am or re.search(r"(?<![а-яёa-z])(?:не|нет|если|бы|not|no|if|would)(?![а-яёa-z])", conv[cs: sm.end()], re.IGNORECASE):
            continue
        rest = clause[am[-1].end():]
        moves = list(_MOVE.finditer(rest))
        if not moves or moves[0].start() > 0 or any(not re.fullmatch(r"[\s,]*", rest[a.end(): b.start()])
                                                    for a, b in zip(moves, moves[1:])):
            continue  # «после размена на f6»: which capture is not written
        if not re.fullmatch(r"[\s,]*", rest[moves[-1].end():]):
            continue
        b = board.copy(stack=False)
        try:
            for x in moves:
                b.push_san(x["san"] + (x["check"] or ""))
        except ValueError:
            continue
        w = sm["side"].lower().replace("ё", "е")
        side = chess.WHITE if w.startswith(("бел", "white")) else chess.BLACK if w.startswith(("черн", "black")) else \
            getattr(ctx, "student_color", None)
        if side is None:
            continue
        pawns = b.pieces(chess.PAWN, side)
        files = [len(pawns & chess.BB_FILES[f]) for f in range(8)]
        label = " ".join(x["san"] for x in moves)
        name = "White" if side == chess.WHITE else "Black"
        if sm["dbl"]:
            want = [chess.FILE_NAMES.index(sm["file"].lower())] if sm["file"] else range(8)
            if not any(files[f] >= 2 for f in want):
                where = f" on the {sm['file'].lower()}-file" if sm["file"] else ""
                out.append(f"after {label} {name} has no doubled pawns{where}")
        else:
            def isolated(sq):
                f = chess.square_file(sq)
                return not any(files[g] for g in (f - 1, f + 1) if 0 <= g < 8)
            if sm["sq"]:
                sq = chess.parse_square(sm["sq"].lower())
                if sq in pawns and not isolated(sq):
                    out.append(f"after {label} {name}'s pawn on {sm['sq'].lower()} is not isolated")
            elif not any(isolated(sq) for sq in pawns):
                out.append(f"after {label} {name} has no isolated pawn")
    return out


# ── material said in other words: «всё ровно», «столько же», pawn counts ─────────────────────────────────────────────
# «По материалу всё ровно» on a queen for a rook, «У тебя примерно столько же материала, сколько у соперника» on the
# exchange, «У белых пять пешек» with six, «У каждой стороны по четыре пешки» with three each (review-miss 03.11: these
# forms had no reader). Judged on the board now, as the material reader judges («примерно» within a pawn — see
# answer_check._about_equal), never after a condition, a written move, a past tense or a negation.
_NUMW = {"одна": 1, "одну": 1, "один": 1, "две": 2, "два": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7,
         "восемь": 8, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
_NUM_RX = r"(?P<n>[1-8]|" + "|".join(sorted(_NUMW, key=len, reverse=True)) + r")"
_EVEN_WORDS = re.compile(
    r"(?<![а-яёa-z])(?:(?:по\s+материалу|материально|материал\w*)\s+(?:(?:у\s+вас|у\s+сторон|сейчас|здесь|тут|всё|все|"
    r"примерно|почти|практически)\s+)*ровн\w*|(?:всё|все)\s+ровно\s+по\s+материалу|"
    r"(?P<same>столько\s+же\s+(?:материала|фигур|пешек))(?:\s*,?\s*сколько\s+(?:и\s+)?у\s+\w+)?)(?![а-яёa-z])", re.IGNORECASE)
_SIDE_COUNT = re.compile(
    r"(?<![а-яёa-z])у\s+(?P<side>белых|ч[её]рных|тебя|соперника|противника)\s+(?:(?:сейчас|здесь|тут|всего|только|"
    r"осталось|остались|осталась|ровно)\s+)*" + _NUM_RX + r"\s+(?P<u>пешк\w*|пешек)(?![а-яёa-z])"
    r"|(?<![а-яёa-z])у\s+(?:каждой\s+(?:из\s+)?сторон\w*|обеих\s+сторон|обоих|сторон)\s+(?:(?:сейчас|здесь|осталось|ровно)\s+)*"
    r"по\s+" + _NUM_RX.replace("?P<n>", "?P<m>") + r"\s+(?:пешк\w*|пешек)(?![а-яёa-z])", re.IGNORECASE)
# «У чёрных лишняя лёгкая фигура»: a knight or a bishop more than the other side (review-miss m30: «лёгкая» stood
# between «лишняя» and the unit, and nothing read it)
_EXTRA_MINOR = re.compile(r"(?<![а-яёa-z])у\s+(?P<side>белых|ч[её]рных|тебя|соперника|противника)\s+(?:(?:сейчас|здесь|тут|"
                          r"уже|ещё|еще|целая)\s+)*лишн\w+\s+л[её]гк\w+\s+фигур\w*|(?P<eside>white|black)\s+(?:is|has)\s+"
                          r"(?:an?\s+)?(?:extra\s+minor\s+piece|minor\s+piece\s+up)", re.IGNORECASE)
_MAT_BAD_FRAME = re.compile(r"(?<![а-яёa-z])(?:если|после|когда|бы|был\w*|не|нет|ни|станет|будет|будут|"
                            r"окажется|if|after|when|would|was|were|not|no)(?![а-яёa-z])", re.IGNORECASE)


def _material_word_issues(text: str, ctx: CheckContext) -> list[str]:
    board = ctx.current
    if board is None or "?" in text:
        return []
    from src.answer_check import _about_equal, _counts

    out = []
    for m in _EVEN_WORDS.finditer(text):
        cs = max(text.rfind(c, 0, m.start()) for c in ".;!\n") + 1
        end = min([i for i in (text.find(c, m.end()) for c in ".;!\n") if i >= 0] or [len(text)])
        if _MAT_BAD_FRAME.search(text[cs: end]) or _WRITTEN_MOVE.search(text[cs: end].lower()):
            continue
        hedged = re.search(r"(?<![а-яё])(?:примерно|почти|практически|приблизительно|более-менее|плюс-минус)(?![а-яё])",
                           text[max(cs, m.start() - 30): m.end()], re.IGNORECASE)
        w, b = _counts(board, chess.WHITE), _counts(board, chess.BLACK)
        same = (m["same"] or "").lower()
        if "пешек" in same:
            holds = abs(w[chess.PAWN] - b[chess.PAWN]) <= (1 if hedged else 0)
        elif "фигур" in same:
            holds = abs(w["nonpawn"] - b["nonpawn"]) <= (1 if hedged else 0)
        else:
            holds = _about_equal(board) if hedged else w["nonpawn"] + w[chess.PAWN] == b["nonpawn"] + b[chess.PAWN]
        if not holds:
            out.append(f"material: {_imbalance(board)} (not {'about ' if hedged else ''}equal: {m.group(0).strip()})")
    for m in _EXTRA_MINOR.finditer(text):
        cs = max(text.rfind(c, 0, m.start()) for c in ".;!\n") + 1
        end = min([i for i in (text.find(c, m.end()) for c in ".;!\n") if i >= 0] or [len(text)])
        if _MAT_BAD_FRAME.search(text[cs: end]) or _WRITTEN_MOVE.search(text[cs: end].lower()):
            continue
        s = (m["side"] or m["eside"]).lower().replace("ё", "е")
        student = getattr(ctx, "student_color", None)
        side = chess.WHITE if s.startswith(("бел", "white")) else chess.BLACK if s.startswith(("черн", "black")) else \
            (student if s.startswith("теб") else (None if student is None else not student))
        if side is None:
            continue
        minors = [len(board.pieces(chess.KNIGHT, c)) + len(board.pieces(chess.BISHOP, c)) for c in (side, not side)]
        if minors[0] <= minors[1]:
            out.append(f"{'White' if side else 'Black'} has {minors[0]} minor pieces against {minors[1]} — no extra minor "
                       f"piece ({_imbalance(board)})")
    for m in _SIDE_COUNT.finditer(text):
        cs = max(text.rfind(c, 0, m.start()) for c in ".;!\n,—–:") + 1
        end = min([i for i in (text.find(c, m.end()) for c in ".;!\n") if i >= 0] or [len(text)])
        if _MAT_BAD_FRAME.search(text[cs: end]) or _WRITTEN_MOVE.search(text[cs: end].lower()):
            continue
        if not re.fullmatch(r"[\s*_«\"-]*(?:(?:сейчас|здесь|тут|теперь|итак|но|а|и|при\s+этом|в\s+итоге|так\s+что)\s+)*",
                            text[cs: m.start()], re.IGNORECASE):
            continue  # «Чёрные выиграли у тебя две пешки»: what was taken, not a count
        raw = (m["n"] or m["m"]).lower()
        n = int(raw) if raw.isdigit() else _NUMW.get(raw)
        if n is None:
            continue
        if m["m"]:
            have = [len(board.pieces(chess.PAWN, c)) for c in (chess.WHITE, chess.BLACK)]
            if any(h != n for h in have):
                out.append(f"White has {have[0]} pawns and Black {have[1]} (not {n} each)")
            continue
        s = m["side"].lower().replace("ё", "е")
        student = getattr(ctx, "student_color", None)
        side = chess.WHITE if s.startswith("бел") else chess.BLACK if s.startswith("черн") else \
            (student if s.startswith("теб") else (None if student is None else not student))
        if side is None:
            continue
        have = len(board.pieces(chess.PAWN, side))
        if have != n:
            out.append(f"{'White' if side else 'Black'} has {have} pawns (not {n})")
    return out
