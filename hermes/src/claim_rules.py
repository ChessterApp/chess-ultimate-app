"""Board-rule relations (WP-D, plan 30.10): claims judged by the rules of chess — the legal moves, the king's
squares, an exchange count on one square — rather than by the attack map.

    only_move     «закрыться может только ферзь: 34.Qc1», «обязан был встать на c1, у него не было выбора»,
                  «ферзь был единственной защитой»             → the legal moves (or the legal blocks of the check)
    no_flight     «у короля нет ни одного свободного поля», «ферзь загородил королю последний выход»
                                                                → the king's legal squares; the blocker next to it
    confined      «король заперт на последних двух линиях», «отрезан по 7-й горизонтали»
                                                                → where the king can walk with the board standing
    can_capture   «белые могут забрать пешку e5», «e5 можно взять конём»   → a legal capture on the square
    can_exchange  «менять на e4 чёрные могут в любой момент»    → a capture there that does not lose material
    occupied      «поле занято своими фигурами», «поле e5 свободно»          → the piece on the square
    checks_along  «чёрная ладья начнёт шаховать по вертикали d» → the side's checks along that line

``extract(text, state)`` reads one sentence into ``Claim``s (``source='rules'``) with a textual ``Pos``; the boards
come from ``claim_scene.boards_for`` and the verdict from ``claim_judge.decide``, which calls ``RULE_JUDGES[rel]`` on
each board and applies the reporting rule (false on the primary board, true on no alternative, judgeable on the
shown board). A judge returns ``undecided`` whenever the board is not the one the words can be about (the move is
not legal there, the king is not the side to move, no piece of the kind named), so a wrong board never condemns.

Lines: a sentence that writes moves («Решение: 33...Rb1+ 34.Qc1 Rxc1#.») leaves them in ``state['rules_lines']``
(immutable tuples of MoveRef); a later sentence that names one of those moves («закрыться может только ферзь:
34.Qc1», «ферзь обязан был встать на c1») is about the board right before it, so its ``Pos`` is that line's prefix.
A sentence that repeats a move of a line written before continues that line. A claim with no move before it, right
after a sentence that wrote moves, may be about a position of that line: those positions are ``Pos.alts``
(«…единственный ход: Bxa2. Королю некуда шагнуть: a2 занят собственным слоном»).

State keys (all ``rules_*``, immutable values): ``rules_lines``, ``rules_story`` (the answer's line so far),
``rules_last`` (the previous sentence's moves); and, for the judges of the sentence's own claims, ``rules_placed``
(pieces it puts on squares) and ``rules_moves`` (the moves it writes). A judge leaves a board undecided when a piece
the sentence places is not on it (nor on the board now, a shown board, the sentence's line), or when the first move
the sentence writes after the claim cannot be played from it: the words describe another position. Only claims with an explicit legal
sense are read: «единственный ход» alone (the only good move) and «обязан» alone (the engine stage judges forced
replies, answer_check_rules.forced_reply_claim) are not claims here; negated captures («нельзя взять» — usually "it
loses") are not either.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

import chess

from src.claim_types import PIECE_TYPE, UNDECIDED, Claim, MoveRef, Pos, Ref, Verdict, parse_san_token
from src.config import detector_mode

# relation → its judge on one board (claim_judge.decide dispatches the RULE_RELATIONS here).
RULE_JUDGES: dict[str, Callable[[Claim, chess.Board, Any], Verdict]] = {}

MAX_LINES = 6  # lines kept in state
_NAME = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook", chess.QUEEN: "queen",
         chess.KING: "king"}
_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}

# ── text ────────────────────────────────────────────────────────────────────────────────────────────────────────
_W = r"(?<![а-яa-z0-9])"
_E = r"(?![а-яa-z0-9])"
_SQ = r"[a-h][1-8](?![0-9])"
_CYR_SQ = re.compile(r"(?<![а-яА-ЯёЁa-zA-Z])([асебдфгхАСЕБДФГХ])(?=[1-8](?![0-9]))")
_CYR_SQ_MAP = {"а": "a", "с": "c", "е": "e", "б": "b", "д": "d", "ф": "f", "г": "g", "х": "h"}
_EMPH = re.compile(r"\*{1,3}|(?<![a-zа-яё0-9])_{1,2}|_{1,2}(?![a-zа-яё0-9])")

# Piece words by stem (every case; ё is е by now). Instrumental endings tell the tool of a capture («конём»).
_PIECE_STEMS = (("N", r"кон(?:ь|я|ю|е|и|ем|ей|ям|ями|ях)"), ("B", r"слон(?:а|у|ом|е|ы|ов|ам|ами|ах)?"),
                ("R", r"лад(?:ья|ьи|ье|ью|ьей|ей|ьям|ьями|ьях)"), ("Q", r"ферз(?:ь|я|ю|ем|е|и|ей)"),
                ("K", r"корол(?:ь|я|ю|ем|е)"), ("P", r"пеш(?:ка|ки|ке|ку|кой|ек|кам|ками|ках)"))
_PIECE = re.compile(_W + "(?:" + "|".join(f"(?P<{k}>{p})" for k, p in _PIECE_STEMS) + ")" + _E)
_INSTR = re.compile(r"(?:ом|ем|ой|ей|ью|ами|ями)$")
_SIDE = re.compile(_W + r"(?P<w>бел(?:ые|ых|ым|ыми|ый|ого|ому|ая|ой|ую|ое))|(?P<b>черн(?:ые|ых|ым|ыми|ый|ого|ому|ая|ой|ую|ое))"
                   r"|(?P<you>ты|тебе|тебя|вы|вам|вас|твой|твоя|твое|твои|твоего|твоей|твоим)|(?P<their>соперник\w*|противник\w*)" + _E)

# Not a claim about a board: a hypothetical, an example, a rule.
_HYPO = re.compile(_W + r"(?:бы|будь|представь\w*|допустим|предполож\w*|например|к\s+примеру|скажем|в\s+общем\s+случае|"
                   r"как\s+правило|по\s+правил\w*|правил[оау]|обычно|всегда|никогда|в\s+теории|теоретическ\w*)" + _E)
_IF = re.compile(_W + r"(?:если|ежели|коли)" + _E)
_WHEN = re.compile(_W + r"(?:когда|как\s+только|пока\s+не)" + _E)
_WHY = re.compile(_W + r"(?:почему|зачем|отчего|за\s+сч[её]т\s+чего)" + _E)
_FUTURE = re.compile(_W + r"(?:смож\w+|смогут|смогу|будет|будут|станет|станут|начн[её]т|начнут)" + _E)
_THEN = re.compile(r"^\W*(?:затем|потом|дальше|далее|после\s+этого|тогда)" + _E)


def _prep(text: str) -> str:
    """Lower case, ё → е, Markdown emphasis gone, Cyrillic file letters as Latin, moves in SAN letters."""
    from src.answer_check import _to_san

    t = _EMPH.sub("", text or "").replace("ё", "е").replace("Ё", "Е")
    t = _CYR_SQ.sub(lambda m: _CYR_SQ_MAP[m.group(1).lower()], t)
    t = t.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    conv, _ = _to_san(t)
    return conv


def _skip(low: str, at: int, moves_before: bool) -> bool:
    """The words up to *at* (and the sentence) say this is not a claim about a board of the answer."""
    head = low[:at]
    if _HYPO.search(low) or _IF.search(head):
        return True
    if _WHEN.search(head) and not moves_before:
        return True
    q = low.find("?", at)
    if q >= 0 and not _WHY.search(low[:at]):
        return True  # a yes/no question («можно взять e5?») asks, it does not claim
    return False


# ── moves written in the sentence, and the lines of the answer ─────────────────────────────────────────────────
_MOVE_WORD = re.compile(_W + r"(?:после|ходом|ход|игра\w*|сыгра\w*|ответ\w*|отвеча\w*|продвин\w*|толкн\w*)"
                        r"\s*[—–:-]?\s+(?:[а-я]+\s+)?$")


def _moves(conv: str) -> list:
    """[(start, end, MoveRef)] of the moves written in *conv*: SAN with a piece letter, a capture, castling, a move
    number or a check sign; a bare square only inside a run of such moves («1.e4 e5 2.Nf3»)."""
    from src.answer_check import _MOVE

    found = []
    for m in _MOVE.finditer(conv):
        number, side = None, None
        if m.group("num"):
            dots = m.group("dots")
            number = m.group("num") + ("..." if dots in ("...", "…") else ".")
            side = chess.BLACK if dots in ("...", "…") else chess.WHITE
        elif m.group("bdots"):
            side = chess.BLACK
        ref = parse_san_token(m.group("san") + (m.group("check") or ""), number=number, side=side)
        real = bool(ref.piece and ref.piece != "P") or ref.capture or bool(ref.castle) or number is not None \
            or bool(m.group("bdots")) or bool(m.group("check"))
        if ref.castle and re.search(r"(?:рокировк\w*\s*\(?|\()\s*$", conv[max(0, m.start() - 20):m.start()].lower()):
            continue  # «Короткую рокировку (O-O) …»: the name of the move, not a move played
        if not real and _MOVE_WORD.search(conv[max(0, m.start() - 24):m.start()].lower()):
            real = True  # «после b3», «чёрные играют b5»: a pawn move told in words
        found.append([m.start(), m.end(), ref, real])
    # a bare square counts when a real move stands next to it with only spaces / commas between
    for i, f in enumerate(found):
        if f[3]:
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(found) and found[j][3]:
                a, b = (found[j][1], f[0]) if j < i else (f[1], found[j][0])
                if re.fullmatch(r"[\s,]{1,3}", conv[a:b] or "x"):
                    f[3] = True
    return [(s, e, r) for s, e, r, real in found if real]


def _same_move(a: MoveRef, b: MoveRef) -> bool:
    if a.castle or b.castle:
        return a.castle == b.castle and (a.side is None or b.side is None or a.side == b.side)
    if not a.to or a.to != b.to:
        return False
    if (a.piece or "P") != (b.piece or "P"):
        return False
    if a.frm and b.frm and a.frm != b.frm:
        return False
    if a.side is not None and b.side is not None and a.side != b.side:
        return False
    if a.number and b.number and a.number != b.number:
        return False
    return True


def _lines(state: dict) -> tuple:
    lines = state.get("rules_lines") if isinstance(state, dict) else None
    return lines if isinstance(lines, tuple) else ()


def _record(state: dict, moves: list) -> None:
    """Leave the sentence's moves for the next sentences; a sentence that starts with a move of a line written
    before continues that line (it repeats or goes on from there)."""
    if not isinstance(state, dict):
        return
    if not moves:
        state["rules_last"] = ()
        return
    seg = tuple(m for _, _, m in moves)
    lines = _lines(state)
    story = state.get("rules_story") if isinstance(state.get("rules_story"), tuple) else ()
    for line in reversed(lines):
        hit = next((i for i, m in enumerate(line) if _same_move(m, seg[0])), None)
        if hit is not None:
            seg = line[:hit] + seg
            story = seg
            break
    else:
        story = (story + seg)[-2 * MAX_LINES:]  # «…начинается с Ra2+!» then «…единственный ход — Bxa2»: one line
    state["rules_lines"] = (lines + (seg,))[-MAX_LINES:]
    state["rules_last"] = seg
    state["rules_story"] = story


def _find_in_lines(state: dict, pred) -> Optional[tuple]:
    """(line, index) of the latest move of the answer's lines for which *pred* holds."""
    for line in reversed(_lines(state)):
        for i in range(len(line) - 1, -1, -1):
            if pred(line[i]):
                return line, i
    return None


# ── refs from words ────────────────────────────────────────────────────────────────────────────────────────────
def _piece_at(low: str, m) -> Optional[str]:
    return next((k for k in PIECE_TYPE if m.group(k)), None) if m else None


def _side_ref(low: str, a: int, b: int) -> Optional[Ref]:
    """The side the words in low[a:b] name as the actor (the last one): «белые», «чёрные», «ты», «соперник»."""
    last = None
    for m in _SIDE.finditer(low, a, b):
        last = m
    if last is None:
        return None
    if last.group("w"):
        return Ref(side=chess.WHITE, text=last.group(0))
    if last.group("b"):
        return Ref(side=chess.BLACK, text=last.group(0))
    if last.group("you"):
        return Ref(owner="you", text=last.group(0))
    return Ref(owner="their", text=last.group(0))


def _side_word(low: str, a: int, b: int) -> Optional[bool]:
    """A colour adjective in low[a:b] («чёрный король», «белого ферзя»)."""
    ref = _side_ref(low, a, b)
    return ref.side if ref is not None else None


def _piece_ref(low: str, m, *, side: Optional[bool] = None) -> Ref:
    """A piece word and the square written right after it («пешку e5», «конём с f3»)."""
    piece = _piece_at(low, m)
    sq = re.compile(r"\s+(?:(?:на|с|со)\s+)?(?P<sq>" + _SQ + ")").match(low, m.end())
    from_sq = bool(sq) and re.match(r"\s+(?:с|со)\s", low[m.end():sq.start("sq")] + " ") is not None
    return Ref(sq=sq.group("sq") if sq else None, piece=piece, side=side, from_sq=from_sq, text=m.group(0))


# ── extraction ─────────────────────────────────────────────────────────────────────────────────────────────────
def _pos(moves: list, at: int, low: str, state: Optional[dict] = None, *, ends: bool = False) -> Pos:
    """The position the words before *at* point at: after the moves written before it, «затем …» going on from the
    line before; else the board now — or a position of the line the sentence before wrote («Ra2+ … Bxa2. Королю
    некуда шагнуть: a2 занят собственным слоном»), each of which is an alternative. *ends*: only where those lines
    end — a claim about the board now (a move proposed: «Nc3, не давая чёрным сыграть d5») is not about a ply in the
    middle of a line told before (review-miss 01.11: the board after 1.e4 alone excused it)."""
    before = tuple(m for s, _, m in moves if s < at)
    if _THEN.search(low):
        return Pos(at="then", moves=before)  # «Тогда …», «Затем … (Kc7)»: on from where the sentence before ended
    if before:
        return Pos(at="after", moves=before)
    last = state.get("rules_last") if isinstance(state, dict) else None
    if isinstance(last, tuple) and last:
        story = state.get("rules_story") or last
        if ends:
            alts = [story] + ([last] if story[-len(last):] != last else [])
        else:
            alts = [story[:i + 1] for i in range(len(story))][-MAX_LINES:]
            if story[-len(last):] != last:
                alts += [last[:i + 1] for i in range(len(last))]
        return Pos(alts=tuple(Pos(at="after", moves=a) for a in dict.fromkeys(alts)))
    return Pos()


def _pos_for_move(target: MoveRef, moves: list, at: int, low: str, state: dict) -> Pos:
    """The board right before *target* (the move a claim is about): in the sentence's own line, else in a line the
    answer wrote before; else as the words before it say."""
    own = [m for s, _, m in moves if s < at]
    for i, m in enumerate(own):
        if _same_move(m, target):
            return Pos(at="after", moves=tuple(own[:i])) if i else Pos()
    hit = _find_in_lines(state, lambda m: _same_move(m, target))
    if hit is not None:
        line, i = hit
        return Pos(at="after", moves=line[:i]) if i else Pos()
    return _pos(moves, at, low, state)


def _pos_for_piece(piece: str, side: Optional[bool], state: dict, *, after: bool) -> Optional[Pos]:
    """A piece named as the actor of a line the answer wrote before («ферзь был единственной защитой», «он сам
    загородил королю выход»): the board right before (*after* False) or right after its move in the latest line."""
    def pred(m: MoveRef) -> bool:
        return (m.piece or "P") == piece and (side is None or m.side is None or m.side == side)

    hit = _find_in_lines(state, pred)
    if hit is None:
        return None
    line, i = hit
    moves = line[:i + 1] if after else line[:i]
    return Pos(at="after", moves=moves) if moves else Pos()


_PAST_VERB = re.compile(_W + r"(?:был\w*|[а-я]+(?:ил|ыл|ал|ял|ел)(?:а|о|и)?)" + _E)


def _past(pos: Pos, words: str) -> Pos:
    """A told action with no line of the answer to find it in («он сам загородил королю выход»): about the game's
    past — the resolver has it, or skips the claim."""
    if pos.at == "now" and not pos.moves and _PAST_VERB.search(words):
        return Pos(tense="past")
    return pos


def _claim(rel, subj, objs=(), *, pos=Pos(), span=(0, 0), move=None, kind="", neg=False, count=None, to=None):
    return Claim(rel=rel, subj=subj, objs=tuple(objs), pos=pos, span=span, source="rules", move=move, kind=kind,
                 neg=neg, count=count, to=to)


# only_move ────────────────────────────────────────────────────────────────────────────────────────────────────
_BLOCK_ONLY = re.compile(_W + r"(?:закрыться|заслониться|перекрыться|прикрыться|закрыть\s+короля|загородиться)"
                         r"(?:\s+от\s+шах\w*)?\s+(?:[а-я]+\s+)?(?:может|можно|могут|мог|могла|сможет)\s+(?:[а-я]+\s+)?только\s+"
                         r"(?:[а-я]+\s+){0,2}?" + _PIECE.pattern)
_BLOCK_ONLY2 = re.compile(_W + r"только\s+(?:[а-я]+\s+){0,2}?" + _PIECE.pattern + r"\s+(?:[а-я]+\s+)?(?:может|мог|могла|можно)\s+"
                          r"(?:[а-я]+\s+)?(?:закрыться|заслониться|перекрыться|прикрыться|закрыть\s+короля)" + _E)
_PARRY_ONLY = re.compile(_PIECE.pattern + r"\s+(?:[а-я]+\s+){0,2}?(?:был\w*|оставал\w*|являл\w*|—|-)?\s*(?:[а-я]+\s+)?"
                         r"единственн\w+\s+защит\w*(?!\s+(?:от\s+)?(?:пешк|кон|слон|лад|ферз|пол|клет|[a-h][1-8]))")
_NO_CHOICE = re.compile(_W + r"(?:не\s+было\s+(?:другого\s+)?выбора|нет\s+(?:другого\s+)?выбора|выбора\s+(?:у\s+[а-я]+\s+)?(?:нет|не\s+было)|"
                        r"других\s+ходов\s+(?:у\s+[а-я]+\s+)?(?:нет|не\s+было)|нет\s+других\s+ходов|не\s+было\s+других\s+ходов|"
                        r"единственн\w+\s+(?:легальн\w+|возможн\w+|законн\w+|допустим\w+)\s+ход\w*|"
                        r"(?:больше|иначе)\s+(?:ходить|пойти)\s+(?:[а-я]+\s+)?некуда)" + _E)
_OBLIGED_TO = re.compile(_W + r"(?:обязан\w*|вынужден\w*|должен|должна|должны)\s+(?:был\w*\s+)?(?:[а-я]+\s+)?"
                         r"(?:встать|пойти|идти|сыграть|уйти|отойти|отступить|закрыться|перейти|переместиться)\s+на\s+(?P<sq>" + _SQ + ")")
_ONLY_LEGAL_MOVE = re.compile(_W + r"(?:единственн\w+\s+(?:легальн\w+|возможн\w+|законн\w+|допустим\w+)\s+ход\w*"
                              r"|других\s+ходов\s+(?:у\s+[а-я]+\s+)?(?:нет|не\s+было)|нет\s+других\s+ходов)" + _E)


# «Король может пойти только на f8», «королю можно уйти только на f8»: the piece's moves go to that square only
_PIECE_ONLY_TO = re.compile(_PIECE.pattern + r"\s+(?:[а-я]+\s+){0,2}?(?:может|можно|мог|могла|сможет)\s+(?:[а-я]+\s+)?"
                            r"(?:пойти|уйти|отойти|встать|отступить|сходить|шагнуть|двинуться|пройти)\s+только\s+на\s+"
                            r"(?P<sq>" + _SQ + ")")
# «Единственная защита от шаха — Kf8», «Единственный способ уйти от шаха — Kf8»: the move after it parries the check
_PARRY_MOVE = re.compile(_W + r"единственн\w+\s+(?:защит\w*|спасени\w*|способ\w*(?:\s+уйти|\s+защититься)?)\s+от\s+шах\w*"
                         r"\s*(?:[—–:-]|это)\s*")
# «Есть только один легальный ход: Kf8», «только один возможный ход — …»: the legal sense said in words
_ONE_LEGAL = re.compile(_W + r"только\s+один\s+(?:легальн\w+|возможн\w+|законн\w+|допустим\w+)\s+ход\w*" + _E)


def _only_move(conv, low, moves, state):
    out = []
    for m in _PIECE_ONLY_TO.finditer(low):
        if _skip(low, m.start(), any(s < m.start() for s, _, _ in moves)):
            continue
        piece = _piece_at(low, m)
        side = _side_word(low, max(0, m.start() - 20), m.start() + 1)
        target = MoveRef(piece=piece, to=m.group("sq"), side=side)
        out.append(_claim("only_move", Ref(piece=piece, side=side, text=m.group(0)), pos=_pos(moves, m.start(), low, state),
                          span=(m.start(), m.end()), move=target, kind="piece"))
    for rx, kind in ((_PARRY_MOVE, "parry"), (_ONE_LEGAL, "any")):
        for m in rx.finditer(low):
            near = [(s, e, mv) for s, e, mv in moves if 0 <= s - m.end() <= 12 or 0 <= m.start() - e <= 12]
            if not near or _skip(low, m.start(), True):
                continue
            s, e, mv = min(near, key=lambda x: abs(x[0] - m.end()))
            pos = _pos_for_move(mv, moves, s, low, state)
            out.append(_claim("only_move", None, pos=pos, span=(min(s, m.start()), max(e, m.end())), move=mv, kind=kind))
    for rx in (_BLOCK_ONLY, _BLOCK_ONLY2):
        for m in rx.finditer(low):
            moves_before = any(s < m.start() for s, _, _ in moves)
            if _skip(low, m.start(), moves_before):
                continue
            piece = _piece_at(low, m)
            side = _side_word(low, max(0, m.start() - 40), m.end())
            # «…только ферзь: 34.Qc1» — the move after the colon is the claim's move too
            nxt = next(((s, e, mv) for s, e, mv in moves if s >= m.end() and re.fullmatch(r"[\s:—–-]*", conv[m.end():s])), None)
            if nxt is not None and (nxt[2].piece or "P") != piece:
                nxt = None
            if nxt is not None:
                pos = _pos_for_move(nxt[2], moves, nxt[0], low, state)
                out.append(_claim("only_move", Ref(piece=piece, side=side, text=m.group(0)), pos=pos,
                                  span=(m.start(), nxt[1]), move=nxt[2], kind="block"))
            else:
                pos = _pos(moves, m.start(), low, state)
            out.append(_claim("only_move", Ref(piece=piece, side=side, text=m.group(0)), pos=pos,
                              span=(m.start(), m.end()), kind="block"))
    for m in _PARRY_ONLY.finditer(low):
        if _skip(low, m.start(), any(s < m.start() for s, _, _ in moves)):
            continue
        piece = _piece_at(low, m)
        side = _side_word(low, max(0, m.start() - 20), m.start())
        pos = _pos_for_piece(piece, side, state, after=False) or _past(_pos(moves, m.start(), low, state), m.group(0))
        out.append(_claim("only_move", Ref(piece=piece, side=side, text=m.group(0)), pos=pos, span=(m.start(), m.end()),
                          kind="parry"))
    if _NO_CHOICE.search(low):
        for m in _OBLIGED_TO.finditer(low):
            if _skip(low, m.start(), any(s < m.start() for s, _, _ in moves)):
                continue
            pm = None
            for p in _PIECE.finditer(low, max(0, m.start() - 40), m.start()):
                pm = p
            if pm is None:
                continue
            piece = _piece_at(low, pm)
            side = _side_word(low, max(0, pm.start() - 20), pm.start())
            target = MoveRef(piece=piece, to=m.group("sq"), side=side)
            pos = _pos_for_move(target, moves, m.start(), low, state)
            out.append(_claim("only_move", Ref(piece=piece, side=side, text=pm.group(0)), pos=pos,
                              span=(pm.start(), m.end()), move=target, kind="any"))
    for m in _ONLY_LEGAL_MOVE.finditer(low):
        # «других ходов нет: Bxh1», «единственный возможный ход — Kh1»: the nearest written move
        near = [(abs((s if s >= m.end() else m.start()) - (m.end() if s >= m.end() else e)), s, e, mv) for s, e, mv in moves]
        near = [x for x in near if x[0] <= 12]
        if not near or _skip(low, m.start(), True):
            continue
        _, s, e, mv = min(near, key=lambda x: x[0])
        pos = _pos_for_move(mv, moves, s, low, state)
        out.append(_claim("only_move", None, pos=pos, span=(min(s, m.start()), max(e, m.end())), move=mv, kind="any"))
    return out


# no_flight / confined ─────────────────────────────────────────────────────────────────────────────────────────
_KING_WORD = re.compile(_W + r"(?P<k>корол(?:ь|я|ю|ем|е))" + _E)
_NO_FLIGHT = re.compile(_W + r"(?:нет\s+(?:ни\s+одного\s+|ни\s+одной\s+|больше\s+)?(?:свободн\w+\s+(?:пол\w+|клет\w+)|выхода|"
                        r"пол(?:ей|я)\s+для\s+отступлени\w+|отступлени\w+)"
                        r"|некуда\s+(?:[а-я]+\s+)?(?:уйти|отступить|отойти|деться|бежать|убежать|шагнуть|идти|пойти|спрятаться)"
                        r"|(?:уйти|отступить|отойти|деться|бежать|убежать|шагнуть)\s+(?:[а-я]+\s+)?некуда)" + _E)
_BLOCKER = re.compile(_W + r"(?:загородил\w*|закрыл\w*|занял\w*|отнял\w*|отобрал\w*|перекрыл\w*|забрал\w*|"
                      r"загораживает|закрывает|занимает|отнимает|отбирает|перекрывает|забирает)\s+"
                      r"(?:[а-я]+\s+){0,2}?(?:королю|у\s+короля|своему\s+королю)\s+(?:[а-я]+\s+)?"
                      r"(?:последн\w+|единственн\w+)\s+(?:свободн\w+\s+)?(?:выход|поле|клетку|отступление)" + _E)
_PRONOUN = re.compile(_W + r"(?:он|она|оно)" + _E)
_CONFINED = re.compile(_W + r"(?:заперт|отрезан|прижат|зажат)\w*\s+(?:[а-я]+\s+){0,2}?(?:на|в|по)\s+"
                       r"(?:(?P<edge>последн\w+|крайн\w+|перв\w+)\s+)?(?:(?P<n>одн\w+|дв\w+|тр\w+|двух|трех|\d)\s+)?"
                       r"(?:(?P<nth>\d)\s*-?\s*[а-я]{0,3}\s+)?(?P<kind>горизонтал\w*|вертикал\w*|лини\w+|ряд\w*)"
                       r"(?:\s+(?P<file>[a-h])(?![a-z0-9]))?" + _E)
_N_WORDS = {"одн": 1, "дв": 2, "тр": 3}


def _king_ref(low: str, a: int, b: int) -> Optional[Ref]:
    """The king the words in low[a:b] name (the last one), with its colour and square when written."""
    km = None
    for m in _KING_WORD.finditer(low, a, b):
        km = m
    if km is None:
        return None
    side = _side_word(low, max(0, km.start() - 20), km.start())
    sq = re.compile(r"\s+(?:на\s+)?(?P<sq>" + _SQ + ")").match(low, km.end())
    return Ref(sq=sq.group("sq") if sq else None, piece="K", side=side, text=km.group(0))


def _no_flight(conv, low, moves, state):
    out = []
    for m in _NO_FLIGHT.finditer(low):
        clause_start = max(low.rfind(c, 0, m.start()) for c in ".;:—–(") + 1
        king = _king_ref(low, max(clause_start, m.start() - 60), m.start())
        if king is not None and king.text.endswith("ь") and m.start() - low.rfind(king.text, 0, m.start()) > 30:
            king = None  # «Король f6 отнимает у него поля…, так что бежать некуда»: the king named is not the one
        if king is None or _skip(low, m.start(), any(s < m.start() for s, _, _ in moves)):
            continue
        out.append(_claim("no_flight", king, pos=_pos(moves, m.start(), low, state), span=(m.start(), m.end())))
    for m in _BLOCKER.finditer(low):
        if _skip(low, m.start(), any(s < m.start() for s, _, _ in moves)):
            continue
        # the blocker: the piece word (or a pronoun standing for the last piece word) right before the verb
        head = low[max(0, m.start() - 50):m.start()]
        pm = None
        for p in _PIECE.finditer(low, max(0, m.start() - 50), m.start()):
            pm = p
        if pm is None:
            continue
        piece = _piece_at(low, pm)
        if piece == "K":
            continue
        own = re.search(_W + r"(?:сам|сама|своему|собственн\w+)" + _E, head) is not None
        side = _side_word(low, max(0, pm.start() - 20), pm.start())
        ksq = _king_ref(low, m.start(), m.end())
        pos = _pos_for_piece(piece, side, state, after=True) or _past(_pos(moves, m.start(), low, state), m.group(0))
        blocker = Ref(piece=piece, side=side, text=pm.group(0), pronoun=_PRONOUN.search(head) is not None)
        out.append(_claim("no_flight", Ref(piece="K", side=ksq.side if ksq else None, owner="own" if own else None),
                          (blocker,), pos=pos, span=(pm.start(), m.end()), kind="blocker"))
    for m in _CONFINED.finditer(low):
        king = _king_ref(low, max(0, m.start() - 60), m.start())
        if king is None or _skip(low, m.start(), any(s < m.start() for s, _, _ in moves)):
            continue
        word = m.group("kind")
        n = None
        if m.group("n"):
            n = int(m.group("n")) if m.group("n").isdigit() else next((v for k, v in _N_WORDS.items() if m.group("n").startswith(k)), None)
        if m.group("nth") or m.group("file"):  # «отрезан по 7-й горизонтали», «по вертикали e»: a cut line
            if word.startswith("горизонтал") and m.group("nth"):
                kind, line = "cut_rank", int(m.group("nth"))
            elif word.startswith("вертикал") and m.group("file"):
                kind, line = "cut_file", "abcdefgh".index(m.group("file")) + 1
            else:
                continue
            out.append(_claim("confined", king, pos=_pos(moves, m.start(), low, state), span=(m.start(), m.end()), kind=kind,
                              count=line))
            continue
        if not m.group("edge") or not (word.startswith("горизонтал") or word.startswith("лини") or word.startswith("ряд")
                                       or word.startswith("вертикал")):
            continue
        if n is None:
            if re.search(r"(?:ях|ах|ами|ями)$", word):
                continue  # «на последних линиях»: how many is not said
            n = 1
        kind = "files" if word.startswith("вертикал") else "ranks"
        out.append(_claim("confined", king, pos=_pos(moves, m.start(), low, state), span=(m.start(), m.end()), kind=kind,
                          count=n))
    return out


# can_capture / can_exchange ──────────────────────────────────────────────────────────────────────────────────
_CAN = r"(?:может|могут|можешь|можете|можно|могу|сможет|смогут|сможешь)"
_TAKE = r"(?:взять|забрать|побить|съесть|бить|снять)"
_CAPTURE = re.compile(_W + r"(?P<can>" + _CAN + r")\s+(?:[а-я]+\s+){0,2}?" + _TAKE + _E)
_TAKE_FIRST = re.compile(_W + _TAKE + r"\s+(?:[а-я]+\s+){0,2}?" + _CAN + _E)
_OBJ_BEFORE = re.compile(r"(?P<pw>" + "|".join(p for _, p in _PIECE_STEMS) + r")\s+(?:на\s+)?(?P<sq>" + _SQ + r")(?P<more>)")
_EXCHANGE = re.compile(_W + r"(?:(?P<can>" + _CAN + r")\s+(?:[а-я]+\s+){0,2}?(?:менять|разменять|меняться|разменяться|обменять|"
                       r"обменяться)(?:ся)?\s+(?:[а-я]+\s+){0,1}?на\s+(?P<sq>" + _SQ + ")"
                       r"|(?:менять|разменять|меняться|разменяться|обменять|обменяться)(?:ся)?\s+на\s+(?P<sq2>" + _SQ + r")"
                       r"\s+(?:[а-я]+\s+){0,3}?(?P<can2>" + _CAN + r"))")
_NEG_BEFORE = re.compile(r"(?:не|нельзя|никак|нечем|некому|невозможно)\s+(?:[а-я]+\s+)?$")
_OBJ = re.compile(r"\s*(?:(?:[а-я]+\s+){0,2}?(?P<pw>" + "|".join(p for _, p in _PIECE_STEMS) + r")\s+)?(?:на\s+)?"
                  r"(?P<sq>" + _SQ + r")(?P<more>(?:\s*(?:,|или|либо|и)\s*(?:на\s+)?" + _SQ + r")*)")


def _capture_subject(low: str, start: int, end: int) -> Optional[Ref]:
    """Who takes: an instrument after the verb («конём», «пешкой с f2»), else a piece with its square or a side
    named before the modal in the clause («пешка e5 может…», «белые могут…»)."""
    clause_start = max(low.rfind(c, 0, start) for c in ".;:—–(,") + 1
    inst = None
    for p in _PIECE.finditer(low, end, min(len(low), end + 30)):
        if _INSTR.search(p.group(0)):
            inst = p
            break
    if inst is not None:
        return _piece_ref(low, inst)
    pm = None
    for p in _PIECE.finditer(low, clause_start, start):
        pm = p
    if pm is not None and not _INSTR.search(pm.group(0)) and re.search(r"(?:а|ь|н|й|ка|ья)$", pm.group(0)):
        ref = _piece_ref(low, pm, side=_side_word(low, max(0, pm.start() - 20), pm.start()))
        if ref.sq:
            return ref
    return _side_ref(low, clause_start, start)


def _can_capture(conv, low, moves, state):
    out = []
    for rx in (_CAPTURE, _TAKE_FIRST):
        for m in rx.finditer(low):
            if _NEG_BEFORE.search(low[max(0, m.start() - 20):m.start()]) or "ли" in low[m.end():m.end() + 4].split() \
                    or re.search(_W + r"(?:не|нельзя|ли|было|был|были)" + _E, m.group(0)):
                continue  # «можно было взять»: the past, not this board
            moves_before = any(s < m.start() for s, _, _ in moves)
            if _skip(low, m.start(), moves_before):
                continue
            if _FUTURE.search(low[max(0, m.start() - 30):m.end()]) and not moves_before:
                continue
            if re.match(_W + r"(?:смож)", low[m.start():]) and not moves_before:
                continue
            ob = _OBJ.match(low, m.end()) if rx is _CAPTURE else None
            if rx is _TAKE_FIRST:
                # «пешку e5 можно взять конём»: the object before the verb
                ob = None
                for o in _OBJ_BEFORE.finditer(low, max(0, m.start() - 30), m.start()):
                    ob = o
            if ob is None:
                continue
            sqs = [ob.group("sq")] + re.findall(_SQ, ob.group("more") or "")
            anyof = bool(re.search(r"или|либо", ob.group("more") or ""))
            pw = ob.group("pw")
            piece = next((k for k, p in _PIECE_STEMS if pw and re.fullmatch(p, pw)), None)
            objs = tuple(Ref(sq=s, piece=piece) for s in sqs)
            subj = _capture_subject(low, m.start(), ob.end() if rx is _CAPTURE else m.end())
            out.append(_claim("can_capture", subj, objs, pos=_pos(moves, m.start(), low, state), span=(m.start(), ob.end()),
                              kind="any" if anyof else ""))
    for m in _EXCHANGE.finditer(low):
        start = m.start()
        if _NEG_BEFORE.search(low[max(0, start - 20):start]) or _skip(low, start, any(s < start for s, _, _ in moves)):
            continue
        if _FUTURE.search(low[max(0, start - 30):m.end()]) and not any(s < start for s, _, _ in moves):
            continue
        sq = m.group("sq") or m.group("sq2")
        subj = _side_ref(low, max(low.rfind(c, 0, start) for c in ".;:—–(,") + 1, start) if m.group("can") else \
            _side_ref(low, m.end("sq2"), m.end())
        out.append(_claim("can_exchange", subj, (Ref(sq=sq),), pos=_pos(moves, start, low, state), span=(start, m.end())))
    return out


# occupied ─────────────────────────────────────────────────────────────────────────────────────────────────────
_OCCUPIED = re.compile(_W + r"(?P<neg>не\s+)?(?:уже\s+)?(?:занят[оаы]?|занимают|свободн(?:о|а|ы|ое|ая)|пуст(?:о|а|ое|ая|ые|ы))"
                       r"(?:\s+(?P<own>свои\w*|собственн\w*|сво\w+\s+же))?(?:\s+(?:же\s+)?(?P<col>бел(?:ой|ым|ыми)|черн(?:ой|ым|ыми)))?"
                       r"(?:\s+(?:же\s+)?(?P<pw>[а-я]+))?" + _E)
_SQ_LIST_BEFORE = re.compile(r"(?P<list>" + _SQ + r"(?:\s*(?:,|и)\s*" + _SQ + r")*)\s+(?:(?:тоже|уже|сейчас|все|всё)\s+)?$")
_FIELD = re.compile(_W + r"(?:поле|клетка|пункт|поля|клетки)\s+(?:[а-я]+\s+){0,3}?$")


def _occupied(conv, low, moves, state):
    out = []
    for m in _OCCUPIED.finditer(low):
        word = low[m.start():m.end()]
        free = bool(re.search(r"свободн|пуст", word))
        if free and re.search(r"свободн\w*\s+(?:пол|клет)", low[m.start():m.end() + 8]):
            continue  # «свободного поля»: the king's flight, not this
        head = low[max(0, m.start() - 60):m.start()]
        sqs = None
        lst = _SQ_LIST_BEFORE.search(head)
        if lst is not None:
            sqs = re.findall(_SQ, lst.group("list"))
            # «(поле) e5 занято», «f7, g7 и h7 заняты»; the square of «конь на f6 занят» is a piece's, not a field
            before = head[:lst.start()]
            if re.search(r"(?:на|с)\s+$", before) and not _FIELD.search(before):
                continue
        elif _FIELD.search(head) and not free:
            # «поле слишком далеко и занято своими»: the field written before in the sentence
            prev = [x for x in re.finditer(_SQ, low[:m.start()])]
            if not prev:
                continue
            sqs = [prev[-1].group(0)]
        if not sqs:
            continue
        if _skip(low, m.start(), any(s < m.start() for s, _, _ in moves)):
            continue
        pw = m.group("pw") or ""
        piece = next((k for k, p in _PIECE_STEMS if re.fullmatch(p, pw)), None)
        neg = bool(m.group("neg")) != free
        # «занято белой пешкой»: the colour adjective is the occupant's side, the word after it the piece
        col = m.group("col") or ""
        side = (chess.WHITE if col.startswith("бел") else chess.BLACK) if col and piece is not None and not neg else None
        objs = tuple(Ref(sq=s, piece=piece if not neg else None, side=side) for s in sqs)
        out.append(_claim("occupied", None, objs, pos=_pos(moves, m.start(), low, state), span=(m.start(), m.end()), neg=neg))
    return out


# checks_along ─────────────────────────────────────────────────────────────────────────────────────────────────
# A check claim is read by its parts (fix 01.11, review-miss checks_geometry 1/16): the check word in any form (шах,
# шахи, шахов, шахует, шаховать, даст шах), the line bound to it right after it (по / вдоль / с / на + «вертикали d»,
# «линии d», «d-вертикали», «седьмой горизонтали», «7-й горизонтали»), its polarity («шахов не будет», «уйти от
# шахов» are not claims; «закрыть короля от шахов» takes the checks for granted), the checker (a piece word with its
# colour or square, or a side as the subject) and the king the checks are aimed at — told by a king move (SAN), in
# words («король выходит на c7», «короля на c7»), or as the object of the check verb («шахует его»).
_CHECK_WORD = re.compile(_W + r"шах(?!мат)[а-я]*" + _E)
_ORDINAL = {"перв": 1, "втор": 2, "трет": 3, "четверт": 4, "пят": 5, "шест": 6, "седьм": 7, "восьм": 8}
_LINE_PHRASE = re.compile(
    r"(?:по|вдоль|на)\s+(?:(?:всей|всю|той\s+же|одной|открытой|открытую|соседней)\s+)?(?:"
    r"(?P<k1>вертикал[а-я]*|горизонтал[а-я]*|лини[а-я]*)\s+[«\"]?(?P<x1>[a-h1-8])(?![a-z0-9])[»\"]?"
    r"|(?P<x2>[a-h1-8])\s*-?\s*(?:[а-я]{1,3}\s+)?(?P<k2>вертикал[а-я]*|горизонтал[а-я]*|лини[а-я]*)"
    r"|(?P<o3>перв|втор|трет|четверт|пят|шест|седьм|восьм)[а-я]*\s+(?P<k3>горизонтал[а-я]*|лини[а-я]*))" + _E)
_CHECK_NEG = re.compile(_W + r"(?:не|нет|без|никаких|ни\s+одного|ни\s+одной|никакого|никакой)\s+(?:[а-я]+\s+){0,2}$")
_CHECK_NEG_AFTER = re.compile(r"[^.;:!?]{0,40}?" + _W + r"(?:не\s+будет|не\s+будут|нет|не\s+получится|не\s+смож\w*|"
                              r"не\s+может|не\s+могут|невозможн\w*|не\s+грозят|не\s+страшн\w*|не\s+опасн\w*)" + _E)
# «закрыть короля от шахов по вертикали d» takes the checks for granted; «уйти / спрятаться от шахов» says they are
# gone (the king left that line) — only a block or shield verb before «от» is a claim.
_SHIELD_VERB = re.compile(_W + r"(?:закр[а-я]*|прикр[а-я]*|перекр[а-я]*|заслон[а-я]*|защищ[а-я]*|защит[а-я]*|"
                          r"загор[а-я]*|огражд[а-я]*|спаса(?:ет|ют|ть|ла|л|ли)|спасет|спасут|спасти)" + _E)
_KING_MOTION = (r"(?:выход[а-я]*|выйд[а-я]*|выйти|уход[а-я]*|уйд[а-я]*|уйти|ид[её]т|пойд[её]т|пойти|встан[а-я]*|встал[а-я]*|"
                r"вста[её]т|окаж[а-я]*|оказ[а-я]*|прид[её]т|прийти|перейд[а-я]*|перейти|переход[а-я]*|отход[а-я]*|"
                r"отойд[а-я]*|отойти|шагн[а-я]*|шага[а-я]*|бежит|бежать|прячет[а-я]*|спрячет[а-я]*|вернет[а-я]*|"
                r"вернуться|возвращ[а-я]*|подход[а-я]*|подойд[а-я]*|приближ[а-я]*|прорыва[а-я]*|прорв[а-я]*|"
                r"переберет[а-я]*|доберет[а-я]*|добира[а-я]*|становит[а-я]*|станет)")
_KING_STAND = r"(?:стоит|стоял[а-я]*|будет|находит[а-я]*|оказался|уже|теперь|затем|потом|сразу|тогда|сам|своим|ходом)"
# «король выходит на c7», «белый король уже на c7», «короля на c7»: a king put on a square by the words; the words
# between may be a motion verb (a move told), a stand verb or an adverb — not a modal («может выйти»), a negation
# or «с» (where it comes from).
_KING_LOC = re.compile(_W + r"(?P<k>корол(?:ь|я|ю|ем|е))\s+(?P<mid>(?:[а-я]+\s+){0,3}?)(?:на|в)\s+(?:поле\s+|клетку\s+)?"
                       r"(?P<sq>" + _SQ + r")")
_WORD = re.compile(_W + r"[а-я]+" + _E)
_WORD_GAP = re.compile(r" [а-я]+(?= )")
_PUNCT = re.compile(r"[.;:!?]")
_FROM_TAIL = re.compile(_W + r"от\s+(?:[а-я]+\s+){0,2}$")
_KING_NOT = re.compile(_W + r"(?:не|нельзя|может|могут|сможет|мог|могла|должен|должна|хочет|нужно|надо|пытает\w*|"
                       r"попробует|будто|якобы|с|со|из|от)" + _E)
_MOTION_W = re.compile(_KING_MOTION)
_STAND_W = re.compile(_KING_STAND)
_GEN_SIDE = re.compile(r"\s+(?P<s>белых|черных)" + _E)
_CHECK_OBJ = re.compile(r"\s+(?:[а-я]+\s+)?(?P<pr>его|короля)(?:\s+на\s+(?P<sq>" + _SQ + r"))?" + _E)
_KING_WALK = re.compile(_W + r"корол\w*\s+(?:[а-я]+\s+)?" + _KING_MOTION)
_SHIELD_KING = re.compile(_W + r"(?:закр\w*|прикр\w*|заслон\w*|защит\w*)\s+(?:[а-я]+\s+)?(?:короля|его)" + _E)
_SIDE_SUBJ = re.compile(_W + r"(?:(?P<w>белые)|(?P<b>черные))" + _E)
_DEFENDS = re.compile(_W + r"(?:(?P<w>белые)|(?P<b>черные))\s+(?:[а-я]+\s+)?(?:закр|прикр|перекр|отвеча|ответ|спряч|уйд|уход|"
                      r"защища|защит)")
_TEMPORAL = re.compile(_W + r"(?:как\s+только|когда|после\s+того|если|лишь|стоит\s+только|пока)" + _E)


def _line_kind(m) -> Optional[str]:
    """'file:d' / 'rank:7' of a _LINE_PHRASE match, or None when the noun and the letter disagree."""
    if m.group("o3"):
        return f"rank:{_ORDINAL[m.group('o3')]}"
    noun, x = (m.group("k1"), m.group("x1")) if m.group("k1") else (m.group("k2"), m.group("x2"))
    if noun.startswith("вертикал"):
        return f"file:{x}" if x.isalpha() else None
    if noun.startswith("горизонтал"):
        return f"rank:{x}" if x.isdigit() else None
    return f"file:{x}" if x.isalpha() else f"rank:{x}"


def _bound_line(low: str, cw) -> Optional[tuple]:
    """(kind, end) of the line bound to the check word *cw*: right after it, with at most two words between
    («шахи чёрной ладьи по d-вертикали», «шахует его по линии d»), or right before it («по вертикали d шах»)."""
    gaps = [cw.end() + 1]
    for g in _WORD_GAP.finditer(low, cw.end(), min(len(low), cw.end() + 40)):
        if g.start() != gaps[-1] - 1 or len(gaps) > 2:
            break
        gaps.append(g.end() + 1)  # after one, then two words («шахует его по линии d», «шахи чёрной ладьи по …»)
    for at in gaps:
        lm = _LINE_PHRASE.match(low, at)
        if lm is not None and not _PUNCT.search(low, cw.end(), lm.start()):
            kind = _line_kind(lm)
            return (kind, lm.end()) if kind else None
    for lm in _LINE_PHRASE.finditer(low, max(0, cw.start() - 30), cw.start()):
        if re.fullmatch(r"\s*", low[lm.end():cw.start()]):
            kind = _line_kind(lm)
            return (kind, cw.end()) if kind else None
    return None


def _check_polar(low: str, cw, end: int) -> bool:
    """The check word *cw* asserts checks (no denial before or after it; «от шахов» only after a shield verb)."""
    head = low[max(0, cw.start() - 30):cw.start()]
    if _CHECK_NEG.search(head) or _CHECK_NEG_AFTER.match(low, end):
        return False
    if _FROM_TAIL.search(head):
        verb = None
        for v in _WORD.finditer(low, max(0, cw.start() - 45), cw.start()):
            if _SHIELD_VERB.fullmatch(v.group(0)):
                verb = v
        return verb is not None
    return True


def _king_told(low: str, moves: list, at: int, clause: int) -> Optional[tuple]:
    """(square, MoveRef or None, side or None, start, motion, end) of the last king the words put on a square before
    *at* in the clause: a king move written (SAN, its side from its number or a colour word), or «король (выходит)
    на c7» — *motion* when the words move it there rather than say where it stands."""
    best = None
    for s, e, mv in moves:
        if clause <= s < at and (mv.piece or "P") == "K" and not mv.castle and mv.to:
            side = mv.side
            if side is None:
                king = _king_ref(low, max(clause, s - 60), s)
                side = king.side if king is not None else None
            best = (mv.to, mv, side, s, True, e)
    for km in _KING_LOC.finditer(low, clause, at):
        mid = km.group("mid")
        if _KING_NOT.search(mid):
            continue
        words = mid.split()
        if any(not (_MOTION_W.fullmatch(w) or _STAND_W.fullmatch(w) or _SIDE.fullmatch(w)) for w in words):
            continue
        if best is not None and best[3] > km.start():
            continue
        side = _side_word(low, max(clause, km.start() - 20), km.start())
        if side is None:
            side = _side_word(low, km.end("k"), km.end("k") + 12)  # «король белых на c7»
        motion = any(_MOTION_W.fullmatch(w) for w in words)
        best = (km.group("sq"), None, side, km.start(), motion, km.end())
    return best


def _checker(low: str, clause: int, cw, after: int, shield: bool = False) -> Ref:
    """Who checks: a piece word before the check word in the clause (its colour before it, «ладья чёрных» after it,
    its square «ладья a2»), a genitive piece right after it («шахи чёрной ладьи»), or a side as the subject
    («чёрные станут шаховать»)."""
    pm = None
    for p in ([] if shield else _PIECE.finditer(low, max(clause, cw.start() - 45), cw.start())):
        if _piece_at(low, p) != "K":
            pm = p  # (before «от шахов» the piece named is the shield, not the checker)
    if pm is None:
        p = _PIECE.search(low, cw.end(), min(after, cw.end() + 25))
        if p is not None and _piece_at(low, p) != "K":
            pm = p
    if pm is not None:
        side = _side_word(low, max(clause, pm.start() - 20), pm.start())
        if side is None:
            g = _GEN_SIDE.match(low, pm.end())
            side = (chess.WHITE if g.group("s").startswith("бел") else chess.BLACK) if g else None
        ref = _piece_ref(low, pm, side=side)
        return Ref(sq=ref.sq if not ref.from_sq else None, piece=ref.piece, side=side, text=pm.group(0))
    subj = None
    for s in _SIDE_SUBJ.finditer(low, max(clause, cw.start() - 30), cw.start()):
        subj = chess.WHITE if s.group("w") else chess.BLACK
    return Ref(side=subj, text="")


def _defender(low: str, clause: int, end: int) -> Optional[bool]:
    """The side the sentence says answers the checks («белые закрываются», «чёрные закроются ладьёй»)."""
    m = None
    for x in _DEFENDS.finditer(low, clause, end):
        m = x
    if m is None:
        return None
    return chess.WHITE if m.group("w") else chess.BLACK


def _checks_along(conv, low, moves, state):
    out = []
    for cw in _CHECK_WORD.finditer(low):
        bound = _bound_line(low, cw)
        if bound is None:
            continue
        kind, end = bound
        if not _check_polar(low, cw, end):
            continue
        moves_before = any(s < cw.start() for s, _, _ in moves)
        head = low[:cw.start()]
        if _HYPO.search(low) or _IF.search(head) or ("?" in low[cw.start():] and not _WHY.search(head)):
            continue
        clause = max(low.rfind(c, 0, cw.start()) for c in ".;!?") + 1
        shield = _FROM_TAIL.search(low[max(0, cw.start() - 30):cw.start()]) is not None
        subj = _checker(low, clause, cw, end, shield)
        span = (min(cw.start(), max(clause, cw.start() - 45)), end)
        told = _king_told(low, moves, cw.start(), clause) if detector_mode("checks_geometry") != "off" else None
        obj = _CHECK_OBJ.match(low, cw.end())
        if obj is not None and obj.group("sq"):
            told = (obj.group("sq"), None, None, obj.start(), False, obj.end())  # «шахует короля на c7»
        later = low[end:]
        if told is not None and told[5] <= cw.start() and \
                _KING_WALK.search(low, told[5], cw.start()):
            told = None  # the king walks on between the square told and the checks («…, король пойдёт к ладье, а … шах»)
        if told is not None:
            # the king may walk on after the move told, and the checks be about where it goes («…, как только король
            # вернётся на d6»); a king moved again between the move told and the checks is the one they are aimed at
            again = [x for x in moves if x[0] >= end and (x[2].piece or "P") == "K"]
            words = [x for x in _KING_LOC.finditer(low, end) if _MOTION_W.search(x.group("mid") or "")]
            walk = _KING_WALK.search(later)
            if any(_TEMPORAL.search(low[max(end, a - 25):a]) for a in [x[0] for x in again] + [x.start() for x in words]
                   + ([end + walk.start()] if walk else [])):
                told = None
        defender = _defender(low, clause, len(low))
        aimed = bool(obj is not None) or bool(_SHIELD_KING.search(low, clause, cw.start()))
        if told is not None:
            sq, mv, kside, _ks, motion, _ke = told
            if kside is None and defender is not None:
                kside = defender
            if kside is not None and subj.side is not None and kside == subj.side:
                told = None  # the checker's own king walking: the king the checks are aimed at is not told
        if told is not None:
            flags = "|aimed" if aimed else ""
            if not _on_line(kind, chess.parse_square(sq)):
                # C2a (plan 31.10, lucena): the king the checks are aimed at stands where the words put it, off the
                # line — no check along that line can reach it, whatever the rest of the board. Whose king it is the
                # judge reads from the words, else from the board (claim_rules.judge_checks_geometry).
                out.append(_claim("checks_along", subj, pos=Pos(), span=span, kind=kind + flags,
                                  move=mv or (MoveRef(san=None, piece="K", to=sq, side=kside) if motion else None),
                                  to=Ref(sq=sq, piece="K", side=kside, text="king")))
                continue
            if mv is None and not motion:
                continue  # «король на d7»: where it stands in a line not written — no board to judge it on
            if mv is None:
                mv = MoveRef(san="K" + sq, piece="K", to=sq, side=kside)
            if subj.side is None and not subj.sq and kside is not None:
                subj = Ref(piece=subj.piece, side=not kside, text=subj.text)
            if subj.piece is None and subj.side is None:
                continue
            if told[1] is not None:
                pos = _pos(moves, cw.start(), low, state)
            else:
                # «Когда король выйдет на c7, …»: the king move told in words, played after what the sentence wrote
                before = tuple(m for s, _, m in moves if s < _ks)
                pos = Pos(at="then" if _THEN.search(low) else "after", moves=before + (mv,))
            out.append(_claim("checks_along", subj, pos=pos, span=span, kind=kind))
            continue
        if not moves_before or subj.piece is None:
            continue  # a check «when» something happens is about the board after the moves told before it
        out.append(_claim("checks_along", subj, pos=_pos(moves, cw.start(), low, state), span=span, kind=kind))
    return out


def _line_of(kind: str) -> str:
    return (kind or "").split("|")[0]


def _on_line(kind: str, sq: int) -> bool:
    what, _, x = _line_of(kind).partition(":")
    if what == "file":
        return chess.square_file(sq) == "abcdefgh".index(x)
    return chess.square_rank(sq) == int(x) - 1


# retreat_cover (C5, plan 31.10; read by its parts, fix 01.11) ───────────────────────────────────────────────────
# «…белые сразу нападают на слона, и вот тогда он вынужден уйти туда, откуда f1 уже не прикрывает» (castle-ru): the
# piece chased must give up its cover of the square — false when a safe retreat keeps it.
#
# Read by its parts (review-miss: 4/18 with one relative clause read): a chase move written in the sentence (b3,
# «пешкой b3», «подними пешку на b3»), the chased piece named (a piece word, not the chaser's), and any later
# statement in the sentence that its cover is gone:
#   cover   «он (уже / больше) не держит / не сможет контролировать f1», «перестанет держать f1», «f1 он уже не
#           прикрывает», «теряет контроль над f1», «с ним уходит и контроль над f1»;
#   free    «поле f1 освобождается / свободно / больше не под ударом / не будет атаковано / перестанет
#           простреливаться» (judged only when f1 is empty: «свободно» may mean «empty»);
#   line    «покинуть диагональ f1–a6», «уйти с линии f1», «отгоняют слона от f1»;
#   castle  «рокировка станет возможна / снова доступна», «ты спокойно рокируешься» — the squares of the king's
#           path the piece covers;
#   forced  the old «вынужден уйти туда, откуда f1 не прикрывает» and «откуда f1 не прикрыт».
# With a retreat square named and no forcing word («слон отступит на e6, и f1 свободно») the claim is that line's: only
# that retreat is judged. «всё равно / по-прежнему / продолжит держать» are the opposite claim and are not read.
_COVER_VERB = (r"(?:прикрыва\w*|прикро\w*|прикрыть|бь[её]т|бить|держ\w*|контролир\w*|атаку\w*|атаковать|прострелива\w*|"
               r"защища\w*|защити\w*|видит|смотрит)")
_FORCED_AWAY = re.compile(
    _W + r"(?:вынужден\w*|придется|приходится|должен|должна|обязан\w*)\s+(?:будет\s+)?(?:[а-я]+\s+)?"
    r"(?:уйти|отступить|отойти|уходить|отступать|отходить|убраться|бежать)"
    r"(?:\s+(?:на\s+(?:поле\s+)?(?P<to>" + _SQ + r")|туда|куда-то|[а-я]+)){0,2}\s*,?\s*(?:туда\s*,?\s*)?"
    r"(?:откуда|где|с\s+которого|с\s+которой)\s+(?:(?:он|она|оно)\s+)?(?:(?P<sq1>" + _SQ + r")\s+)?"
    r"(?:(?:уже|больше|теперь|тогда|более)\s+)*не\s+(?:(?:сможет|может|будет|станет)\s+)?" + _COVER_VERB
    + r"(?:\s+(?:(?:поле|пункт|клетку)\s+)?(?P<sq2>" + _SQ + r"))?" + _E)
_TOKEN = re.compile(r"(?<![a-zа-я0-9])(?:[kqrbn][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8]|[a-h][1-8]|o-o(?:-o)?)(?![0-9])")
_NO_LONGER = r"(?:(?:уже|больше|теперь|тогда|более|сразу)\s+)*"
_NO_SQ_AFTER = r"(?!\s+(?:(?:поле|пункт|клетку)\s+)?[a-h][1-8])"  # «c4 уже не будет бить f1»: c4 is the piece
_GONE_COVER = [
    # «он (уже) не сможет контролировать f1», «перестанет держать поле f1»
    ("cover", re.compile(_W + r"(?:(?:он|она|оно|слон|конь|ладья|ферзь)\s+)?" + _NO_LONGER +
                         r"(?:не\s+(?:(?:сможет|может|будет|станет)\s+)?(?:[а-я]+\s+)?|перестан\w*\s+|переста\w*\s+)"
                         + _COVER_VERB + r"\s+(?:(?:на|за)\s+)?(?:(?:поле|пункт|клетку|клетки|поля)\s+)?(?P<z>" + _SQ + r")")),
    # «поле f1 он уже не прикрывает»
    ("cover", re.compile(_W + r"(?:(?:поле|пункт)\s+)?(?P<z>" + _SQ + r")\s+(?:(?:он|она|оно)\s+)?" + _NO_LONGER
                         + r"не\s+(?:(?:сможет|может|будет|станет)\s+)?" + _COVER_VERB + _E + _NO_SQ_AFTER)),
    # «теряет контроль над f1», «с ним уходит и контроль над f1»
    ("cover", re.compile(_W + r"(?:теря\w*|потеря\w*|утрат\w*|уход\w*|уйд\w*|пропад\w*|исчез\w*)\s+(?:и\s+)?"
                         r"(?:контрол\w*|защит\w*|давлени\w*|удар\w*)\s+(?:над|на|по)\s+(?:пол\w+\s+)?(?P<z>" + _SQ + r")")),
    # «поле f1 освобождается», «f1 больше не под ударом», «поле f1 больше не будет атаковано», «f1 перестанет
    # простреливаться», «f1 свободно»
    ("free", re.compile(_W + r"(?:(?:поле|пункт|клетка)\s+)?(?P<z>" + _SQ + r")\s+(?:(?:у\s+[а-я]+|для\s+[а-я]+)\s+)?"
                        + _NO_LONGER + r"(?:снова\s+)?(?:освобожда\w*|освобод\w*|станет\s+свободн\w*|будет\s+свободн\w*|"
                        r"свободн\w*|свободен|"
                        r"откро(?:ется|ются)|открыва(?:ется|ются)|"
                        r"(?:не|перестан\w*)\s+(?:будет\s+|станет\s+)?(?:быть\s+|находиться\s+)?(?:под\s+(?:ударом|боем|контролем|атакой|обстрелом)|"
                        r"атакова\w*|атакуе\w*|простреливат\w*|простреливае\w*|контролир\w*|прикрыт\w*|бит\w*)|"
                        r"выход\w*\s+из-под\s+(?:удара|боя|контроля))" + _E + _NO_SQ_AFTER)),
    # «покинуть диагональ f1–a6», «уйти с линии f1», «отгоняют слона от f1» («выгоняет слона с c4» is where it stands)
    ("line", re.compile(_W + r"(?:(?:покин\w*|покида\w*)\s+(?:(?:диагонал\w*|лини\w*|вертикал\w*|горизонтал\w*)\s+)?"
                        r"|(?:уйти|уйд\w*|уход\w*|сойти|сойд\w*|убра\w*)\s+с\s+(?:диагонал\w*|лини\w*|вертикал\w*|горизонтал\w*)\s+"
                        r"|(?:отогна\w*|отгоня\w*|прогна\w*|прогоня\w*|выгна\w*|выгоня\w*|оттесн\w*)\s+(?:[а-я]+\s+)?"
                        r"(?:от\s+|с\s+(?:диагонал\w*|лини\w*|вертикал\w*|горизонтал\w*)\s+))"
                        r"(?P<z>" + _SQ + r")(?:\s*[–—-]\s*(?P<z2>" + _SQ + r"))?")),
    # «рокировка станет возможна», «короткая рокировка снова доступна», «ты спокойно рокируешься»
    ("castle", re.compile(_W + r"(?:рокировк\w*\s+(?:[а-я]+\s+){0,2}?(?:станет|будет|снова|окажется|становится|сразу|уже)\s+"
                          r"(?:[а-я]+\s+)?(?:возможн|доступн|разреш|легальн)\w*"
                          r"|(?:ты|вы)\s+(?:(?:спокойно|сразу|сможешь|сможете|уже|наконец|тогда|смело)\s+)*рокиру\w*"
                          r"|(?:можно|сможешь|сможете)\s+(?:будет\s+)?(?:(?:спокойно|сразу|уже|наконец)\s+)*(?:сделать\s+)?"
                          r"(?:коротк\w+\s+|длинн\w+\s+)?рокир\w*)" + _E)),
    # «… — e6, откуда f1 не прикрыт»
    ("cover", re.compile(_W + r"(?:откуда|где|с\s+которого|с\s+которой)\s+(?P<z>" + _SQ + r")\s+" + _NO_LONGER
                         + r"не\s+(?:прикрыт\w*|защищ\w*|атакован\w*|простреливается|контролируется|под\s+(?:ударом|боем))")),
]
_KEEPS = re.compile(_W + r"(?:вс[её]\s+равно|по-прежнему|продолж\w*|сохран\w*|останет\w*|оста[её]тся|не\s+потеряет|"
                    r"не\s+теряет|не\s+уйд\w*|не\s+уход\w*|не\s+отступ\w*|не\s+освобод\w*|не\s+свободн\w*)" + _E)
_FORCING = re.compile(_W + r"(?:вынужден\w*|придется|приходится|должен|должна|обязан\w*|заставит\w*|заставля\w*|"
                      r"выгоня\w*|выгон\w*|выгна\w*|прогоня\w*|прогон\w*|прогна\w*|отгоня\w*|отогна\w*|"
                      r"только\s+(?:одно|один)|единственн\w*)" + _E)
_RETREAT_TO = re.compile(_W + r"(?:отступ\w*|уйти|уйд\w*|уход\w*|отойд\w*|отойти|отход\w*|пойд\w*|спрячет\w*|отступлени\w*)"
                         r"\s+(?:(?:[а-я]+)\s+){0,2}?(?:на\s+(?:поле\s+)?|[—–-]\s*)(?P<to>" + _SQ + r")")
# a colour adjective right before the piece word («чёрный слон», «белого коня») — not «белые» / «чёрные», the side
# that acts («белые отгоняют слона»)
_ADJ_SIDE = re.compile(r"(?<![а-я])(бел|черн)(?:ый|ого|ому|ым|ом|ая|ой|ую|ое)\s+$")
_RETREAT_IF = re.compile(_W + r"(?:если|при\s+условии|в\s+случае|когда|как\s+только|лишь\s+после|только\s+после)" + _E)
_RETREAT_TAIL = re.compile(r"(?:отступ\w*|уйти|уйд\w*|уход\w*|отойд\w*|отход\w*)\s+(?:[а-я]+\s+)?(?:на\s+(?:поле\s+)?|[—–-]\s*)$")
_LINE_TAIL = re.compile(r"(?:диагонал\w*|лини\w*)\s+(?:[a-h][1-8]\s*[–—-]\s*)?$")
_CHASE_WORDS = re.compile(_W + r"(?:прогон\w*|прогна\w*|выгон\w*|выгна\w*|отгоня\w*|отогна\w*|напад\w*|атаку\w*|гони\w*|"
                          r"гнать|выгоня\w*|прогоня\w*)" + _E)


def _retreat_cover(conv, low, moves, state):
    out = []
    for m in _FORCED_AWAY.finditer(low):
        sq = m.group("sq1") or m.group("sq2")
        if not sq or _skip(low, m.start(), any(s < m.start() for s, _, _ in moves)):
            continue
        clause = max(low.rfind(c, 0, m.start()) for c in ".;!?") + 1
        pm = None
        for p in _PIECE.finditer(low, clause, m.start()):
            pm = p
        if pm is None:
            continue  # «он вынужден уйти» with no piece named in the sentence: the antecedent is not ours to guess
        piece = _piece_at(low, pm)
        if piece in ("P", "K"):
            continue
        ref = _piece_ref(low, pm, side=_side_word(low, max(0, pm.start() - 20), pm.start()))
        # the moves before the claim that may be the chase («Начни с b3 — b3–c4 — белые сразу нападают на слона»)
        chase = list(dict.fromkeys(t.group(0) for t in _TOKEN.finditer(low, clause, m.start())))
        first = min([t.start() for t in _TOKEN.finditer(low, clause, m.start())] + [m.start()])
        to = MoveRef(piece=piece, to=m.group("to")) if m.group("to") else None
        out.append(_claim("retreat_cover", Ref(sq=ref.sq, piece=piece, side=ref.side, text=pm.group(0)),
                          (Ref(sq=sq),), pos=_pos(moves, first, low, state), span=(pm.start(), m.end()), move=to,
                          kind="chase:" + ",".join(chase)))
    if out:
        return out
    return _retreat_consequence(conv, low, moves, state)


def _retreat_consequence(conv, low, moves, state):
    """The chase and the cover it is said to take away, told in any clause after the chase (see above)."""
    cands = sorted(((m.start(), i, what, m) for i, (what, rx) in enumerate(_GONE_COVER) for m in rx.finditer(low)),
                   key=lambda x: (x[0], x[1]))
    for _s, _i, what, m in cands:
        got = _retreat_one(conv, low, moves, state, what, m)
        if got:
            return got
    return []


def _retreat_one(conv, low, moves, state, what, m):
    clause = max(low.rfind(c, 0, m.start()) for c in ".;!?") + 1
    end = re.search(r"[.;!?]", low[m.end():])
    if _KEEPS.search(low[clause:m.end() + (end.start() if end else 0)]) or _HYPO.search(low):
        return []
    if "?" in low[clause:] and not _WHY.search(low[:m.start()]):
        return []
    if _RETREAT_IF.search(low, m.end(), m.end() + (end.start() if end else len(low))) or \
            _HEDGE.search(low, clause, m.start()):
        return []  # «…, но только если слон уйдёт на e6», «слон может уйти, и f1 освободится»: a condition, a hedge
    # the chased piece: the last piece word before the consequence that is neither a pawn nor a king (the chaser
    # «пешкой b3» is passed over)
    pm = None
    for p in _PIECE.finditer(low, clause, m.start()):
        if _piece_at(low, p) not in ("P", "K"):
            pm = p
    if pm is None and what != "castle":
        for p in _PIECE.finditer(low, m.start(), min(len(low), m.end() + 20)):
            if _piece_at(low, p) not in ("P", "K"):
                pm = p  # «отгоняют слона от f1», «перестанет быть под ударом слона»: the piece is in the consequence
                break
    if pm is None:
        return []
    piece = _piece_at(low, pm)
    adj = _ADJ_SIDE.search(low, max(0, pm.start() - 16), pm.start())
    ref = _piece_ref(low, pm, side=(chess.WHITE if adj.group(1) == "бел" else chess.BLACK) if adj else None)
    psq = ref.sq
    # the chase: a move written before the consequence, not the chased piece's own square
    toks = [t for t in _TOKEN.finditer(low, clause, m.start()) if t.group(0) != psq]
    toks = [t for t in toks if not _RETREAT_TAIL.search(low[max(clause, t.start() - 30):t.start()])
            and not _LINE_TAIL.search(low[max(clause, t.start() - 16):t.start()])]
    if not toks:
        return []
    head = low[:toks[0].start()]
    if _IF.search(head + low[toks[0].start():pm.start()]):
        # «Если сыграть b3, слон уйдёт, и поле f1 …»: the condition is the chase move itself
        if not _if_only_move(low, pm.start(), toks[0]):
            return []
    elif _WHEN.search(head):
        return []
    if _RETREAT_IF.search(low, toks[0].end(), m.start()) or _WHEN.search(low, toks[0].end(), m.start()):
        return []  # «после b3 рокировка станет возможна лишь тогда, когда слон уйдёт с диагонали»: a condition
    from src.answer_check_rules import _CASTLE_WILL

    promise = _CASTLE_WILL.search(low, toks[0].end(), pm.start())
    if promise is not None and re.fullmatch(r"[\s,]*", low[toks[0].end():promise.start()]):
        return []  # «После b3 рокировка станет возможна: слон уйдёт …» is the castling promise answer_check_rules judges
    named = _RETREAT_TO.search(low, clause, m.end())
    forced = bool(_FORCING.search(low[clause:m.end()])) or named is None
    zs = [] if what == "castle" else [m.group("z")] + ([m.group("z2")] if "z2" in m.re.groupindex and m.group("z2") else [])
    zs = [z for z in zs if z and z != psq]
    if what != "castle" and not zs:
        return []
    wing = None
    if what == "castle":
        wing = "O-O" if re.search(_W + r"коротк\w*", low) else ("O-O-O" if re.search(_W + r"длинн\w*", low) else "")
    flags = [what] + (["forced"] if forced else ["line_named"]) + ([f"wing={wing}"] if wing else [])
    chase = list(dict.fromkeys(t.group(0) for t in toks))
    mv = MoveRef(piece=piece, to=named.group("to")) if named is not None else None
    first = min(t.start() for t in toks)
    return [_claim("retreat_cover", Ref(sq=psq, piece=piece, side=ref.side, text=pm.group(0)),
                   tuple(Ref(sq=z) for z in zs), pos=_pos(moves, first, low, state, ends=True),
                   span=(pm.start(), m.end()), move=mv, kind="chase:" + ",".join(chase) + "|" + "|".join(flags))]


# prevents (C6, plan 31.10; read by its parts, fix 01.11) ────────────────────────────────────────────────────────
# «лучший план — d4, … не давая чёрным спокойно поставить пешку на d5» (op-show-ck): a move M said to stop the other
# side's move to a square — false when that move stays legal and loses nothing after M, even in a forcing line.
#
# The claim is read by its parts, not by one wording (review-miss: 0/18 with only the participle read):
#   the cue      a denied permission («не даёт / не давая / не позволит / не пускает»), a stopping verb («мешает»,
#                «лишает», «запрещает», «предотвращает», «перекрывает дорогу»), a denied ability («не смогут /
#                нельзя / не удастся» + a move verb), a motion that cannot arrive («не дойдёт до», «не пройдёт на»),
#                a purpose («чтобы чёрные не играли …»), a move that disappears («у чёрных пропадает ход d5», «ход d5
#                отпадёт», «делает d5 невозможным»);
#   the target   the stopped move: a square or a move written after the cue (or before it, for «ход d5 отпадёт»),
#                with its piece (an object «коня на f6», a SAN letter, the actor «коню f6»), its side (a dative,
#                accusative or genitive side word, «у чёрных»; else the other side from the mover);
#   the move     M, the last move written before the cue as a move (sentence start, «ход / ходом / после / сыграй /
#                сыграв / лучший ход — …»), not a square of a piece phrase («пешка d7 не дойдёт»);
#   polarity     a question, a hypothetical, a later time («потом», «со временем»), «всё равно / по-прежнему», a
#                negated stop verb («не мешает»), a piece already standing as the stopper («конь c3 не даёт …») —
#                not read.
_ADVERBS = ("спокойно", "сразу", "легко", "свободно", "просто", "быстро", "никак", "толком", "уже", "больше", "теперь",
            "безнаказанно", "бесплатно", "безопасно", "нормально", "удобно", "выгодно", "даже", "так", "вообще", "и",
            "без", "потерь", "потери", "проблем", "последствий", "здесь", "тут", "сейчас", "активно", "вовремя",
            "будет", "станет")
_LATER_WORDS = re.compile(_W + r"(?:потом|позже|позднее|впоследствии|в\s+дальнейшем|со\s+временем|рано\s+или\s+поздно|"
                          r"когда-нибудь|через\s+(?:[а-я]+\s+)?ход\w*|в\s+будущем|затем)" + _E)
# a hedge: the words say the move may stop it, not that it does («может помешать», «возможно, не даст»)
_HEDGE = re.compile(_W + r"(?:может|могут|можно|возможно|вероятно|иногда|часто|порой|отчасти|частично|скорее)" + _E)
_STILL = re.compile(_W + r"(?:вс[её]\s+равно|по-прежнему|вс[её]\s+же|тем\s+не\s+менее|однако)" + _E)
# the move verbs a stopped move is told with (stems; any ending): play, put, go, take, castle …
_MOVE_STEMS = ("сыгр", "игра", "пойт", "пойд", "пошл", "ходи", "сход", "постав", "став", "заня", "займ", "занима",
               "продвин", "продвига", "двин", "двига", "толкн", "толка", "выдвин", "выдвига", "вста", "встан", "выйт",
               "выход", "выйд", "вывест", "вывод", "вывед", "прыгн", "прыга", "перейт", "переход", "перейд", "перевест",
               "перевод", "перебр", "забр", "забир", "взят", "взя", "брат", "бит", "поби", "съест", "съед", "разменя",
               "меня", "вернут", "верну", "отступ", "уйт", "уйд", "отойт", "отойд", "ответ", "отвеча", "рокир", "развит",
               "развив", "прорват", "прорыв", "вклин", "попаст", "попад", "дойт", "дойд",
               "пройт", "пройд", "добрат", "добер", "пробит", "пробь", "напаст", "напад", "прыжк", "сдела")
_STATE_STEMS = ("стоя", "остават", "остава", "находит", "держ", "контрол", "атаков", "защищ", "дума", "развиват",
                "дыша", "жит", "чувств", "получ", "име", "созда", "готов", "иметь", "начат", "игратьс")
_TARGET_NOUN = re.compile(r"(?:ход|хода|ходу|ходом|продвижени\w*|выход\w*|выпад\w*|прыж\w*|возможност\w*|иде[яюий]\w*|"
                          r"прорыв\w*|рокировк\w*|пол[еяю]|поля|клетк\w*|дорог\w*|путь|пути|контрудар\w*|удар\w*)")
_SIDE_WORD = re.compile(r"(?P<b>черн\w+)|(?P<w>бел\w+)|(?P<their>соперник\w*|противник\w*|ему|ей|им|их|его|ее|они|он|она)"
                        r"|(?P<you>тебе|вам|тебя|вас|ты|вы|твоим|твоему|твоей)")
_OWN_WORD = re.compile(r"(?:сво\w+|собственн\w+)")
_PERMIT = re.compile(_W + r"(?P<neg>не)\s+(?:(?:уже|больше|просто|никак|даже|сразу|будет|станет|так)\s+){0,2}"
                     r"(?:дава\w*|да(?:ет|ют|ст|дут|м|шь|дим|ть|л|ла|ли|ло|вая|ешь)|позвол\w*|пуска\w*|допуска\w*|допуст\w*|"
                     r"пуст(?:ит|ят|ишь|ил|ила|или|ить)|разреш\w*|оставля\w*\s+(?:[а-я]+\s+)?(?:шанс\w*|возможност\w*))" + _E)
_STOP = re.compile(_W + r"(?P<v>(?:по)?меша(?:ет|ют|л|ла|ли|ло|ть|я|ешь|ем)|воспрепятству\w*|препятству\w*|"
                   r"лиша(?:ет|ют|л|ла|ли|ть|я|ешь)|лиши(?:т|л|ла|ли|ть|в)|запреща(?:ет|ют|л|ла|ли|ть|я)|"
                   r"запрет(?:ит|ил|ила|или|ить)|предотвраща\w*|предотврат(?:ит|ил|ила|или|ить|ив)|пресека\w*|"
                   r"пресеч\w*|исключа(?:ет|ют|я)|исключ(?:ит|ил|ила)|отнима(?:ет|ют|я)|отним(?:ет|ут)|"
                   r"отбира(?:ет|ют|я)|отбер(?:ет|ут)|(?:за)?блокиру(?:ет|ют|я|ет)|перекрыва(?:ет|ют|я)|"
                   r"перекро(?:ет|ют)|закрыва(?:ет|ют|я)|закро(?:ет|ют))" + _E)
_NEEDS_NOUN = re.compile(r"(?:за)?блокир|перекр|закр")  # «блокирует продвижение d5», «перекрывает дорогу», not «блокирует d5»
_CANT = re.compile(_W + r"(?:не\s+(?:(?:уже|больше|сразу|просто|так\s+просто|никак)\s+)?(?:смо(?:жет|гут|жешь|жете|г|гла|гли)|"
                   r"сумеет|сумеют|могут|может|можешь|сможет|успе(?:ет|ют|ешь)|удаст(?:ся)?|получит(?:ся)?|"
                   r"будет\s+(?:возможности|шанса)\s+)|(?:будет\s+|станет\s+)?(?:уже\s+)?(?:нельзя|невозможно)|"
                   r"лишен\w*\s+возможности)" + _E)
_REACH_NOT = re.compile(_W + r"не\s+(?:(?:уже|больше|сразу|никак)\s+)?(?:смож\w+\s+)?"
                        r"(?:дойд\w*|дойти|пройд\w*|пройти|попад\w*|попасть|прорв\w*|прорваться|пробь\w*|пробиться|"
                        r"добер\w*|добраться)" + _E)
_PURPOSE = re.compile(_W + r"чтобы\s+(?:(?:[а-я]+)\s+){0,2}?не\s+")
_GONE = re.compile(_W + r"(?:пропада(?:ет|ют)|пропад(?:ет|ут)|исчеза(?:ет|ют)|исчезн(?:ет|ут)|отпада(?:ет|ют)|"
                   r"отпад(?:ет|ут)|снимается)" + _E)
_IMPOSS = re.compile(_W + r"(?:невозможн(?:ым|ой|ыми|ый|ая|ое|ы|а|о)?|невозможен|неосуществим\w*)" + _E)
_TOK = re.compile(r"\.{2,3}|…|(?<![a-zа-я0-9])(?:[kqrbn]?[a-h]?[1-8]?x?[a-h][1-8](?:=[qrbn])?|o-o(?:-o)?)[+#]?(?![a-z0-9])"
                  r"|[а-я]+(?:-[а-я]+)?|[,—–:;()«»\"!?.]")


def _stem_of(word: str, stems: tuple) -> bool:
    return any(word.startswith(s) for s in stems)


_CAPTURE_STEMS = ("забр", "забир", "взят", "взя", "брат", "бит", "поби", "съест", "съед")
_PAWN_VERB_STEMS = ("сыгр", "игра", "продвин", "продвига", "двин", "двига", "толкн", "толка", "ответ", "отвеча", "пойт",
                    "пойд", "сдела")


def _target_after(conv: str, low: str, at: int, *, verb_needed: bool, needs_noun: bool = False) -> Optional[dict]:
    """The stopped move in the words after *at*: {side, own, piece, frm, sq, castle, span} — the side word (a dative
    «чёрным», an accusative «лишает чёрных», «у чёрных»), the actor («коню f6», «пешку на» — a square right after a
    piece word is where it stands), adverbs, the move verb (a move stem) or noun («ход», «продвижение»), the object
    piece (for a capture verb its square is the target), «на / в / до» and the square or SAN. None when a word outside
    these is met first: the words then say something else."""
    side, own, actor, actor_sq, verb, noun, obj, obj_sq, prep, dots = None, False, None, None, None, None, None, None, False, False
    last_piece = None
    words = 0
    for t in _TOK.finditer(low, at):
        w = t.group(0)
        if w in (",", "—", "–", ":", ";", "(", ")", "!", "?", "."):
            return None
        if w in ("...", "…"):
            dots = True
            continue
        if w in ("«", "»", '"'):
            continue
        words += 1
        if words > 9:
            return None
        if re.fullmatch(r"[kqrbn]?[a-h]?[1-8]?x?[a-h][1-8](?:=[qrbn])?[+#]?|o-o(?:-o)?[+#]?", w):
            sq = re.search(r"[a-h][1-8]", w)
            capture = bool(verb) and _stem_of(verb, _CAPTURE_STEMS)
            if last_piece is not None and sq and w == sq.group(0) and not (last_piece == "obj" and capture):
                if last_piece == "actor":
                    actor_sq = w  # «коню f6», «пешке d7»: where the actor stands
                else:
                    obj_sq = w
                last_piece = None
                continue
            if verb_needed and not (verb or noun or prep):
                return None
            if needs_noun and not noun:
                return None
            raw = conv[t.start():t.end()]
            ref = parse_san_token(raw) if re.match(r"[KQRBN]|O-O", raw) else None
            if ref is not None and raw.startswith("O-O"):
                return dict(side=side, own=own, piece="K", frm=None, sq=None, castle=raw.rstrip("+#"), span=(at, t.end()))
            piece = ref.piece if ref is not None and ref.piece and ref.piece != "P" else None
            if piece is None:
                piece = actor if capture else (obj or actor)
            if piece is None and (re.match(r"[a-h]x", w) or dots or not (verb or noun or prep) or
                                  (noun and (noun.startswith("ход") or noun.startswith("продвиж"))) or
                                  (verb and _stem_of(verb, _PAWN_VERB_STEMS))):
                piece = "P"  # «сыграть d5», «ход d5», «...d5», «предотвращает d5»: a bare square written as a move
            frm = actor_sq if (piece is not None and piece == actor) else (obj_sq if piece == obj and not capture else None)
            if ref is not None and ref.frm:
                frm = ref.frm
            return dict(side=side, own=own, piece=piece, frm=frm, sq=sq.group(0) if sq else None, castle=None,
                        span=(at, t.end()))
        if w.startswith("рокир") and (verb is None or verb.startswith("сдела")):
            return dict(side=side, own=own, piece="K", frm=None, sq=None, castle="", span=(at, t.end()))
        sw = _SIDE_WORD.fullmatch(w)
        if sw and side is None and not (verb or noun) and w not in ("он", "она", "они", "ты", "вы"):
            side = "b" if sw.group("b") else "w" if sw.group("w") else "their" if sw.group("their") else "you"
            continue
        if _OWN_WORD.fullmatch(w):
            own = True
            continue
        if w in ("у", "его", "ее", "их") or (w in ("с", "со") and last_piece is not None):
            continue
        pm = _PIECE.fullmatch(w)
        if pm:
            p = _piece_at(w, pm)
            if verb or noun:
                obj, last_piece = p, "obj"
            else:
                actor, last_piece = p, "actor"
            continue
        last_piece = None
        if w in ("на", "в", "до", "к"):
            prep = True
            continue
        if w in ("поле", "клетку"):
            continue
        if noun is None and _TARGET_NOUN.fullmatch(w):
            noun = w
            continue
        if verb is None and _stem_of(w, _MOVE_STEMS) and not _stem_of(w, _STATE_STEMS):
            verb = w
            continue
        if w in _ADVERBS or (w.endswith("о") and len(w) > 4 and not _LATER_WORDS.fullmatch(w)):
            continue
        return None
    return None


def _target_before(conv: str, low: str, start: int, clause: int) -> Optional[dict]:
    """«ход d5 у чёрных отпадёт», «d5 станет невозможен», «делает d5 невозможным»: the move named right before
    the cue (a noun «ход» or a bare move, with at most «у <side>» / «станет» / «будет» between)."""
    seg = low[clause:start]
    m = _BEFORE_CUE.search(seg)
    if m is None:
        return None
    side = None
    if m.group("side"):
        sw = _SIDE_WORD.fullmatch(m.group("side"))
        side = ("b" if sw.group("b") else "w" if sw.group("w") else "their" if sw.group("their") else "you") if sw else None
    raw = conv[clause + m.start("tok"):clause + m.end("tok")]
    ref = parse_san_token(raw) if re.match(r"[KQRBN]", raw) else None
    piece = ref.piece if ref is not None and ref.piece and ref.piece != "P" else "P"
    return dict(side=side, own=False, piece=piece, frm=None, sq=m.group("tok")[-2:], castle=None,
                span=(clause + m.start(), start), tok_start=clause + m.start("tok"), noun=m.group("noun"))


_BEFORE_CUE = re.compile(r"(?:(?P<noun>ход|хода|продвижени\w*|возможност\w*|иде[яи]|прорыв)\s+)?(?:\.{2,3}|…)?"
                         r"(?P<tok>[kqrbn]?x?[a-h][1-8])(?![0-9])\s+(?:(?:у|для)\s+(?P<side>[а-я]+)\s+)?"
                         r"(?:(?:уже|сразу|просто|тогда|будет|станет|становится|делается|окажется|у|для|них|черных|белых)\s+)*$")
_PIECE_TAIL = re.compile(r"(?:" + "|".join(p for _, p in _PIECE_STEMS) + r")\s+(?:(?:на|с|со)\s+)?$")
_INTRO = re.compile(r"(?:^|[—–:;,(]|" + _W + r"(?:играй|играйте|сыграй|сыграйте|играть|сыграть|сыграв|сыграем|играем|"
                    r"ход|ходом|хода|план|после|сначала|продвинь|толкни|двинь|поставь|ставь|лучше|с|через|выбирай|"
                    r"выбери|предлагаю|советую|рекомендую|выбор|ответ|ответь|отвечай|ответив|напрашивается))"
                    r"\s*[*_«\"]*(?:всего\s+)?[*_«\"]*(?:\d{1,3}\s?\.{1,3}\s?)?$")


def _mover_token(low: str, clause: int, end: int, skip_at: Optional[int] = None):
    """The move M before *end* in the clause: the last token written as a move; tokens of a piece phrase («пешка
    d7», «конь на f6») are passed over. None when the last move-like token is an object («атакуя c5»)."""
    toks = [t for t in _TOKEN.finditer(low, clause, end) if t.start() != skip_at]
    for t in reversed(toks):
        before = low[clause:t.start()]
        if _PIECE_TAIL.search(before):
            continue  # the square of a piece phrase («пешка d7», «конь на f6»): not the move
        if not _INTRO.search(before):
            return None, t
        return "move", t
    return None, None


def _stopped_side(d: Optional[str]) -> Optional[Ref]:
    if d == "b":
        return Ref(side=chess.BLACK, text="черные")
    if d == "w":
        return Ref(side=chess.WHITE, text="белые")
    if d == "you":
        return Ref(owner="you", text="ты")
    return None  # «ему», «соперник», none: the other side from the mover


def _if_only_move(low: str, at: int, mover) -> bool:
    """«Если сыграть d4, чёрные не смогут сыграть d5»: the condition is the move itself, nothing else."""
    m = None
    for x in _IF.finditer(low, 0, at):
        m = x
    if m is None:
        return True
    cond = low[m.end():at]
    stop = re.search(r",|\s+то\s", cond)
    cond = cond[:stop.start()] if stop else cond
    if mover is None or not (m.end() <= mover.start() < m.end() + len(cond) + 1):
        return False
    rest = (cond[:mover.start() - m.end()] + cond[mover.end() - m.end():]).split()
    return all(w in ("сыграть", "сыграешь", "сыграем", "играть", "ход", "ходом", "белые", "черные", "ты", "вы", "мы",
                     "пойти", "пойдешь", "сделать", "сделаешь", "сыграют", "сыграет", "сначала", "сразу") for w in rest)


def _prevention_cues(low: str):
    """(kind, match) of every cue of a prevention in *low*, in order."""
    out = []
    for rx, kind in ((_PERMIT, "permit"), (_STOP, "stop"), (_CANT, "cant"), (_REACH_NOT, "reach"), (_PURPOSE, "purpose"),
                     (_GONE, "gone"), (_IMPOSS, "imposs")):
        for m in rx.finditer(low):
            out.append((m.start(), kind, m))
    out.sort(key=lambda x: x[0])
    return [(k, m) for _s, k, m in out]


# "not letting Black play e5", "preventing Black from playing …", "so that Black cannot play …"
_EN_STOP_TAIL = re.compile(r"\b(?:not\s+(?:letting|allowing|permitting)|without\s+(?:letting|allowing)|prevent(?:s|ing)?|"
                           r"stop(?:s|ping)?|so\s+that|denying|deny(?:ing)?)\s+(?:(?:black|white|the\s+opponent|them|him|"
                           r"your\s+opponent|you)\s+)?(?:(?:from|to|can(?:not|'t)|won'?t\s+be\s+able\s+to|the\s+chance\s+to|"
                           r"comfortably|easily|freely|safely)\s+){0,2}$")


def prevention_frame(head: str) -> bool:
    """*head* (lower case, ё → е) ends with the cue of a prevention and the words before its stopped move
    («… не давая чёрным спокойно », «… не позволит чёрным », «чтобы чёрные не »): a move written right after it is
    the move the sentence says is stopped, not advice (answer_check.proposed_move)."""
    low = (head or "").lower().replace("ё", "е")
    tail = low[-80:]
    if _EN_STOP_TAIL.search(tail):
        return True
    for kind, m in _prevention_cues(tail):
        if kind == "stop" and re.search(_W + r"не\s+(?:[а-я]+\s+)?$", tail[max(0, m.start() - 12):m.start()]):
            continue  # «не мешает»
        rest = tail[m.end():]
        if re.search(r"[.;!?,:—–]", rest):
            continue
        words = rest.split()
        if len(words) <= 5 and all(_SIDE_WORD.fullmatch(w) or _PIECE.fullmatch(w) or w in _ADVERBS or
                                   _stem_of(w, _MOVE_STEMS) or w in ("на", "в", "до", "у") or _TARGET_NOUN.fullmatch(w)
                                   or re.fullmatch(r"[a-h][1-8]", w) for w in words):
            return True
    return False


_EN_STOP = re.compile(r"\b(?:not\s+(?:letting|allowing|permitting)|without\s+(?:letting|allowing)|prevent(?:s|ing)?|"
                      r"stop(?:s|ping)?\s+(?:black|white|the\s+opponent|them|him)|so\s+that\s+\w+\s+(?:can(?:not|'t)|won'?t))\b")


def prevention_start(text: str) -> Optional[int]:
    """Where the first cue of a prevention starts in *text* (lower case or not), or None: the words from there name
    the move the sentence says is stopped («…, не давая чёрным поставить коня на f6»), so a proposal read in the same
    clause ends before it (answer_check.proposed_move)."""
    low = (text or "").lower().replace("ё", "е")
    starts = [m.start() for _k, m in _prevention_cues(low)
              if not (_k == "stop" and re.search(_W + r"не\s+(?:[а-я]+\s+)?$", low[max(0, m.start() - 12):m.start()]))]
    en = _EN_STOP.search(low)
    if en is not None:
        starts.append(en.start())
    return min(starts) if starts else None


def _prevents(conv, low, moves, state):
    out = []
    seen = set()
    for kind, m in _prevention_cues(low):
        if kind == "stop" and re.search(_W + r"не\s+(?:[а-я]+\s+)?$", low[max(0, m.start() - 12):m.start()]):
            continue  # «не мешает»: a denied stop says the move stays possible — not this claim
        clause = max(low.rfind(c, 0, m.start()) for c in ".;!?") + 1
        end = re.search(r"[.;!?]", low[m.end():])
        sentence_end = m.end() + end.start() if end else len(low)
        if "?" in low[m.start():] and not _WHY.search(low[:m.start()]):
            continue
        if _HYPO.search(low) or _STILL.search(low[clause:sentence_end]):
            continue
        if kind in ("permit", "stop", "gone", "imposs", "purpose") and _HEDGE.search(low, max(clause, m.start() - 25), m.start()):
            continue  # «d4 может помешать чёрным …»: a hedge, not a claim
        if kind == "gone":
            tgt = None
            if re.match(r"\s*(?:у\s+[а-я]+\s+)?(?:ход\w*|возможност\w*|иде\w+|продвижени\w*|прорыв\w*)", low[m.end():]):
                tgt = _target_after(conv, low, m.end(), verb_needed=False)  # «у чёрных пропадает ход d5»
            if tgt is None:
                tgt = _target_before(conv, low, m.start(), clause)
                if tgt is not None and not tgt.get("noun"):
                    tgt = None  # «ход d5 отпадёт»: the noun says it is a move
        elif kind == "imposs":
            if re.match(r"\s+(?:[а-я]+\s+)?(?:сыгра|игра|пойти|ответ|сдела)", low[m.end():]):
                continue  # «невозможно сыграть d5» is read as a denied ability
            tgt = _target_before(conv, low, m.start(), clause)
        elif kind in ("cant", "reach", "purpose"):
            tgt = _target_after(conv, low, m.end(), verb_needed=kind != "reach")
        else:
            tgt = _target_after(conv, low, m.end(), verb_needed=False,
                                needs_noun=kind == "stop" and bool(_NEEDS_NOUN.match(m.group("v"))))
        if tgt is None or tgt["own"] or (tgt["sq"] is None and tgt["castle"] is None):
            continue
        if "tok_start" in tgt:
            limit = tgt["span"][0]
        else:
            limit = m.start()
        what, t = _mover_token(low, clause, limit)
        if what != "move":
            continue  # no move written as the stopper («атакуя c5 и не давая …», «конь на f6, не давая …»)
        if kind in ("permit", "stop") and re.search(r"(?:" + "|".join(p for _, p in _PIECE_STEMS) + r")\s+(?:на\s+)?"
                                                     + _SQ + r"\s+(?:[а-я]+\s+){0,2}$", low[t.end():m.start()]):
            continue  # «Играй d4: конь c3 не даёт …» — a piece standing is the stopper, not the move
        if _LATER_WORDS.search(low[t.end():tgt["span"][1]]):
            continue  # «d4, чтобы потом не дать …»: a later position
        if _IF.search(low[:m.start()]) and not _if_only_move(low, m.start(), t):
            continue
        if _WHEN.search(low[:t.start()]):
            continue
        mover = parse_san_token(conv[t.start():t.end()])
        if mover.to is None and not mover.castle:
            continue
        side_d = tgt["side"]
        if side_d is None and kind in ("cant", "purpose", "gone", "imposs"):
            # the stopped side as the subject («чёрные не смогут», «у чёрных пропадает», «чтобы чёрные не …»)
            sw = None
            for x in _WORD.finditer(low, max(t.end(), m.start() - 30), m.end()):
                if _SIDE_WORD.fullmatch(x.group(0)):
                    sw = _SIDE_WORD.fullmatch(x.group(0))
            if sw is not None:
                side_d = "b" if sw.group("b") else "w" if sw.group("w") else "their" if sw.group("their") else "you"
        if kind == "reach":
            # «пешка d7 не дойдёт до d5»: the actor is the subject before the cue
            pa = None
            for p in _PIECE.finditer(low, t.end(), m.start()):
                pa = p
            if pa is not None:
                ref = _piece_ref(low, pa)
                tgt = dict(tgt, piece=tgt["piece"] or _piece_at(low, pa), frm=tgt["frm"] or (ref.sq if ref.sq != tgt["sq"] else None))
        key = (t.start(), tgt["sq"], tgt["castle"])
        if key in seen:
            continue
        seen.add(key)
        piece = tgt["piece"]
        to = Ref(sq=tgt["sq"], piece=piece) if tgt["sq"] else Ref(piece="K", text="castle")
        out.append(_claim("prevents", _stopped_side(side_d), (Ref(sq=tgt["sq"], piece=piece) if tgt["sq"] else
                                                              Ref(piece="K", text="castle"),),
                          pos=_pos(moves, next((s0 for s0, e0, _m in moves if s0 <= t.start() < e0), t.start()), low, state,
                                   ends=True), span=(t.start(), tgt["span"][1]),
                          move=mover, to=to,
                          kind=("castle:" + tgt["castle"]) if tgt["castle"] is not None else
                          ("from:" + tgt["frm"] if tgt["frm"] else "")))
    return out


# only_move_orders (F13, plan 31.10) ────────────────────────────────────────────────────────────────────────────
# «Ход Kf8 единственный», «Есть только один ход: Kf8» — the word orders the legal-sense patterns above miss. Bare
# «единственный ход — Qc1» stays unread (as often the only good move: «Kc7 — единственный ход, который держит ничью»),
# and even these two are read only as the reply to a check (the judge leaves any other board undecided), never with
# words that say what the move achieves.
_ORDER_TRIGGER = re.compile(_W + r"(?:(?:лишь|только|ровно)\s+один\s+(?:ход|ответ)\w*"
                            r"|ход\s+(?P<mv>\S+)\s+(?:[—–-]\s*)?(?:(?:здесь|тут|сейчас|был|была|было)\s+)?единственн\w*)" + _E)
_ORDER_GOAL = re.compile(_W + r"(?:котор\w+|что|чтобы|спаса\w*|спасти|спасет|выигр\w*|держ\w*|удерж\w*|нич\w+|реша\w*|"
                         r"форсир\w*|вед\w*|сохран\w*|проигр\w*|теря\w*|лучш\w*|хорош\w*|сильн\w*|точн\w*|правильн\w*|"
                         r"разумн\w*|достойн\w*|защища\w*|защит\w*|мат\w*|побед\w*|позволя\w*|оставля\w*)" + _E)


def _only_move_orders(conv, low, moves, state):
    out = []
    for m in _ORDER_TRIGGER.finditer(low):
        end = re.search(r"[.;!?]|,\s*(?:но|а|и)\s", low[m.end():])
        tail = low[m.end():m.end() + end.start()] if end else low[m.end():]
        if _ORDER_GOAL.search(tail) or _ORDER_GOAL.search(low[max(0, m.start() - 25):m.start()]):
            continue
        if m.group("mv"):
            near = [(s, e, mv) for s, e, mv in moves if s == m.start("mv")]
        else:
            near = [(s, e, mv) for s, e, mv in moves if 0 <= s - m.end() <= 6 or 0 <= m.start() - e <= 6]
        if not near or _skip(low, m.start(), True):
            continue
        s, e, mv = min(near, key=lambda x: abs(x[0] - m.end()))
        if low[e:e + 1] == "!" or not mv.san:
            continue  # «Kf5!» — the annotation of the one good move
        king = re.search(r"(?:у|для)\s+(?:[а-я]+\s+)?корол\w*\s+(?:[а-я]+\s+)?$", low[max(0, m.start() - 40):m.start()])
        pos = _pos_for_move(mv, moves, s, low, state)
        out.append(_claim("only_move", Ref(piece="K") if king else None, pos=pos,
                          span=(min(s, m.start()), max(e, m.end())), move=mv, kind="check_reply"))
    return out


# The cue of the board rules read before fix 01.11 (only move, no flight, can capture, occupied, only-move orders):
# those readers run only under it, as they did — the cue words added for F3's readers below would only make them
# scan more sentences (integration 01.11: relation p99 back under its 1 ms gate).
_CUE_RULES = re.compile(r"тольк|единствен|выбор|ходов|обязан|вынужден|должн|некуда|нет\s|заперт|отрезан|прижат|зажат|"
                        r"загород|закрыл|занял|отнял|перекрыл|забрал|закрывает|занимает|загораживает|забирает|отбирает|"
                        r"отнимает|перекрывает|мож|могу|смож|занят|свободн|пуст|шах|давая|позволяя|мешая|пуская|откуда|"
                        r"придется|приходится")
_HAS_SQUARE = re.compile(r"[a-h][1-8]|o-o|0-0|рокир")
_CUE = re.compile(r"тольк|единствен|выбор|ходов|обязан|вынужден|должн|некуда|нет\s|заперт|отрезан|прижат|зажат|загород|"
                  r"закрыл|занял|отнял|перекрыл|забрал|закрывает|занимает|загораживает|забирает|отбирает|отнимает|перекрывает|"
                  r"мож|могу|смож|занят|свободн|пуст|шах|давая|позволяя|мешая|пуская|откуда|придется|приходится|"
                  # fix 01.11: the parts a prevention or a lost cover is told with
                  r"не\s+да|позвол|пуска|пуст|допус|меша|лиша|лиши|запре|предотвра|пресе|исключ|отним|отбир|отбер|блокир|"
                  r"перекр|закр|смог|сумеют|сумеет|успе|удаст|получит|нельзя|невозможн|чтобы|пропад|исчез|отпад|"
                  r"дойд|пройд|попад|прорв|добер|освобо|простре|перестан|контрол|теря|рокир|покин|отгон|отогна|"
                  r"выгон|выгна|прогон|прогна|держ|прикр|под\s+удар|под\s+бо|атак|свобод|отступ|уйд|уход|отой|отход|бить|бьет|бьют|видит|смотрит")


# Pieces the sentence places on squares («чёрный конь забрался на h5», «пешку e5», «прикрыта пешкой d3»): a board
# without them is not the one the sentence describes (a lesson's diagram the turn does not have).
_PLACED = re.compile(_PIECE.pattern + r"\s+(?:(?P<prep>на|с|со)\s+|(?:забрал\w*|стоит|стоят|стоял\w*|находится|сидит)\s+на\s+)?"
                     r"(?P<sq>" + _SQ + ")")
_DESTINATION = re.compile(r"\s+(?:попасть|пойти|пойдет|идти|встать|встанет|перейти|прыгнуть|уйти|отойти|сходить|"
                          r"может|не\s+может|сможет|нельзя|нужно|надо)" + _E)


def _placed(low: str) -> tuple:
    out = []
    for m in _PLACED.finditer(low):
        word = m.group(0).split()[0]
        if m.group("prep") in ("с", "со") or (m.group("prep") == "на" and _INSTR.search(word)):
            continue  # where it came from, or where it goes («ходом конём на f5»)
        if _DESTINATION.match(low, m.end()):
            continue  # «король на e5 попасть не может»
        out.append((_piece_at(low, m), m.group("sq")))
    return tuple(out)


_NOT_PLAYED = re.compile(r"^[^.;:!?]{0,30}?" + _W + r"(?:нет|невозможн\w*|нельзя|не\s+бывает|не\s+существует)" + _E)


def _mentioned(low: str, s: int, e: int) -> bool:
    """A move the sentence names without playing it: in quotes («хода «Кр:e5» тут просто нет»), or said not to
    exist."""
    return low[max(0, s - 1):s] in ("«", '"') or _NOT_PLAYED.match(low, e) is not None


def extract(text: str, state: dict) -> list[Claim]:
    """The board-rule claims *text* makes (``Claim.source == 'rules'``). Records the moves the sentence writes
    (``rules_lines``, for the sentences after it) and the pieces it places on squares (``rules_placed``, for the
    judges of its own claims) in *state*."""
    conv = _prep(text)
    low = conv.lower()
    moves = _moves(conv) if re.search(r"[a-h][1-8]|O-O", conv) else []
    claims: list[Claim] = []
    if _CUE.search(low):
        st = state if isinstance(state, dict) else {}
        old_cue = bool(_CUE_RULES.search(low))
        for part in ((_only_move, _no_flight, _can_capture, _occupied) if old_cue else ()) + (_checks_along,):
            claims += part(conv, low, moves, st)
        # plan 31.10 (P3D): each detector has its own switch (src/config.py detector_mode; off = not read at all)
        for name, part in (("retreat_cover", _retreat_cover), ("prevents", _prevents),
                           ("only_move_orders", _only_move_orders)):
            if name == "only_move_orders" and not old_cue:
                continue
            if name != "only_move_orders" and not _HAS_SQUARE.search(low):
                continue  # a chase and a stopper are written moves: a sentence with no square or castling has neither
            if detector_mode(name) != "off":
                claims += part(conv, low, moves, st)
    if isinstance(state, dict):
        state["rules_text"] = text if claims else ""
        # a square a prevention claim names is where the other side may go, not where a piece stands
        targets = {c.to.sq for c in claims if c.rel == "prevents" and c.to is not None}
        # the squares a chase moves to («Подними пешку на b3 — слон отойдёт …») are where the move goes
        targets |= {t[-2:] for c in claims if c.rel == "retreat_cover" for t in _retreat_parts(c)[0]}
        state["rules_placed"] = tuple(x for x in _placed(low) if x[1] not in targets) if claims else ()
        state["rules_moves"] = tuple((s, m) for s, e, m in moves if not _mentioned(low, s, e)) if claims else ()
    _record(state, moves)
    return claims


# ── judges ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _who(board: chess.Board, sq: int) -> str:
    p = board.piece_at(sq)
    return f"{'White' if p.color else 'Black'}'s {_NAME[p.piece_type]} on {chess.square_name(sq)}" if p else chess.square_name(sq)


def _colour(c: bool) -> str:
    return "White" if c else "Black"


def _side(ref: Optional[Ref], board: chess.Board, ctx) -> Optional[bool]:
    """The colour a ref names: its side, «ты» (the student, else the side to move on the board now), «соперник»."""
    if ref is None:
        return None
    if ref.side is not None:
        return ref.side
    if ref.owner in ("you", "their"):
        me = getattr(ctx, "student_color", None)
        if me is None:
            cur = getattr(ctx, "current", None)
            me = cur.turn if cur is not None else board.turn
        return me if ref.owner == "you" else (not me)
    if ref.sq:
        p = board.piece_at(chess.parse_square(ref.sq))
        if p is not None and (ref.piece is None or p.piece_type == PIECE_TYPE[ref.piece]):
            return p.color
    return None


def _to_move(board: chess.Board, color: bool) -> Optional[chess.Board]:
    """*board* with *color* to move: as it is, or after a pass when the other side is not in check."""
    if board.turn == color:
        return board
    if board.is_check():
        return None
    b = board.copy(stack=False)
    b.push(chess.Move.null())
    return b


def _captures_on(b: chess.Board, t: int) -> list:
    out = []
    for m in b.legal_moves:
        if m.to_square == t and b.is_capture(m):
            out.append(m)
        elif b.is_en_passant(m) and chess.square(chess.square_file(m.to_square), chess.square_rank(m.from_square)) == t:
            out.append(m)
    return out


def _join(xs: list, word: str = "and") -> str:
    xs = list(xs)
    if len(xs) <= 1:
        return "".join(xs)
    xs = xs[:4]
    return ", ".join(xs[:-1]) + f" {word} " + xs[-1]


def judge_can_capture(claim: Claim, board: chess.Board, ctx) -> Verdict:
    targets = [chess.parse_square(o.sq) for o in claim.objs if o.sq]
    if not targets:
        return UNDECIDED
    subj = claim.subj
    side = _side(subj, board, ctx)
    ptype = PIECE_TYPE.get(subj.piece) if subj is not None and subj.piece else None
    frm = chess.parse_square(subj.sq) if subj is not None and subj.sq else None
    if frm is not None:
        p = board.piece_at(frm)
        if p is None or (ptype is not None and p.piece_type != ptype):
            return UNDECIDED  # the piece named is not there: not this board, or the attack judge's business
    results, truths = [], []
    for t in targets:
        tp = board.piece_at(t)
        o = next(x for x in claim.objs if x.sq == chess.square_name(t))
        if tp is not None and o.piece and tp.piece_type != PIECE_TYPE[o.piece]:
            return UNDECIDED  # «пешку e5» with a knight there: the attack judge says what stands there
        sides = [side] if side is not None else ([not tp.color] if tp is not None else [chess.WHITE, chess.BLACK])
        got = []
        for s in sides:
            b = _to_move(board, s)
            if b is None:
                return UNDECIDED
            if tp is not None and tp.color == s:
                return UNDECIDED  # «белые могут взять e4» with White's own pawn there: the words mean another board
            caps = [m for m in _captures_on(b, t) if (frm is None or m.from_square == frm)
                    and (ptype is None or b.piece_type_at(m.from_square) == ptype)]
            got += [b.san(m) for m in caps]
        results.append(bool(got))
        if not got:
            who = _colour(sides[0]) if len(sides) == 1 else "neither side"
            what = _NAME[ptype] if ptype else ("piece" if len(sides) == 1 else "")
            sq = chess.square_name(t)
            if tp is None:
                truths.append(f"{sq} is empty: there is nothing to take there")
            elif frm is not None:
                truths.append(f"the {_NAME[board.piece_type_at(frm)]} on {chess.square_name(frm)} cannot take on {sq}")
            else:
                truths.append(f"no {who} {what} can take {_who(board, t)}".replace("  ", " "))
    ok = any(results) if claim.kind == "any" else all(results)
    return Verdict("true") if ok else Verdict("false", "", "; ".join(truths))


# The static exchange is shared with the other judges (plan 31.10, WP-0): one copy in src/board_math.py.
from src.board_math import see  # noqa: E402,F401


def judge_can_exchange(claim: Claim, board: chess.Board, ctx) -> Verdict:
    o = claim.objs[0] if claim.objs else None
    if o is None or not o.sq:
        return UNDECIDED
    t = chess.parse_square(o.sq)
    tp = board.piece_at(t)
    if tp is None:
        return Verdict("false", "", f"{o.sq} is empty: there is nothing to exchange on")
    side = _side(claim.subj, board, ctx)
    if side is None:
        side = not tp.color
    if side == tp.color:
        return UNDECIDED
    b = _to_move(board, side)
    if b is None:
        return UNDECIDED
    caps = _captures_on(b, t)
    if not caps:
        return Verdict("false", "", f"{_colour(side)} has no capture on {o.sq}: nothing to exchange there")
    counted = [(m, see(b, m)) for m in caps]
    if any(v >= 0 for _, v in counted):
        return Verdict("true")
    bits = []
    for m, v in counted[:3]:
        bits.append(f"{b.san(m)} loses {-v} point{'s' if -v != 1 else ''}")
    return Verdict("false", "", f"{_colour(side)}'s captures on {o.sq} are not an even exchange: " + "; ".join(bits)
                   + f" ({_who(board, t)} is defended)")


def judge_occupied(claim: Claim, board: chess.Board, ctx) -> Verdict:
    bad = []
    for o in claim.objs:
        if not o.sq:
            continue
        p = board.piece_at(chess.parse_square(o.sq))
        if claim.neg:
            if p is not None:
                bad.append(f"{o.sq} is not empty: {_who(board, chess.parse_square(o.sq))} stands there")
            continue
        if p is None:
            bad.append(f"{o.sq} is empty")
        elif o.piece and p.piece_type != PIECE_TYPE[o.piece]:
            bad.append(f"on {o.sq} stands {_colour(p.color)}'s {_NAME[p.piece_type]}, not a {_NAME[PIECE_TYPE[o.piece]]}")
        elif o.side is not None and p.color != o.side:
            bad.append(f"on {o.sq} stands {_colour(p.color)}'s {_NAME[p.piece_type]}")
    if not any(o.sq for o in claim.objs):
        return UNDECIDED
    return Verdict("false", "", "; ".join(bad)) if bad else Verdict("true")


def _king_sq(ref: Optional[Ref], board: chess.Board, ctx) -> Optional[int]:
    """The king a claim is about: on its square, of its colour; a king the words do not name («королю некуда
    деться») only when it is in check — then it is the one the words are about."""
    if ref is not None and ref.sq:
        s = chess.parse_square(ref.sq)
        p = board.piece_at(s)
        return s if p is not None and p.piece_type == chess.KING else None
    color = _side(ref, board, ctx) if ref is not None else None
    if color is None:
        return board.king(board.turn) if board.is_check() else None
    return board.king(color)


def _flights(board: chess.Board, k: int) -> list:
    color = board.color_at(k)
    b = _to_move(board, color)
    if b is None:
        return []
    return [m.to_square for m in b.legal_moves if m.from_square == k and not b.is_castling(m)]


def judge_no_flight(claim: Claim, board: chess.Board, ctx) -> Verdict:
    if claim.kind == "blocker":
        o = claim.objs[0] if claim.objs else None
        if o is None or not o.piece:
            return UNDECIDED
        pt = PIECE_TYPE[o.piece]
        colors = [o.side] if o.side is not None else [chess.WHITE, chess.BLACK]
        blockers = [s for c in colors for s in board.pieces(pt, c)]
        if not blockers:
            return UNDECIDED  # the piece is gone (taken): this is not the board the words are about
        for s in blockers:
            kc = board.color_at(s) if (claim.subj and claim.subj.owner == "own") else (
                claim.subj.side if claim.subj and claim.subj.side is not None else None)
            kings = [board.king(kc)] if kc is not None else [board.king(chess.WHITE), board.king(chess.BLACK)]
            if any(k is not None and chess.square_distance(k, s) == 1 for k in kings):
                return Verdict("true")
        s = blockers[0]
        kc = board.color_at(s) if (claim.subj and claim.subj.owner == "own") else None
        k = board.king(kc) if kc is not None else None
        tail = f" — it is not next to {_who(board, k)} and takes none of its squares" if k is not None else \
            " — it stands next to no king"
        return Verdict("false", "", f"{_who(board, s)}{tail}")
    k = _king_sq(claim.subj, board, ctx)
    if k is None:
        return UNDECIDED
    color = board.color_at(k)
    if board.turn != color and not board.is_check():
        # The opponent moves first: the words may be about after its move — but «у короля нет выхода» of a king on
        # its edge in the back-rank sense is false when it has a legal step off that edge (an air hole on h7)
        edge = chess.square_rank(k) in (0, 7)
        if claim.neg or claim.kind or not edge:
            return UNDECIDED
        off = [s for s in _flights(board, k) if chess.square_rank(s) != chess.square_rank(k)]
        if off:
            return Verdict("false", "", f"{_who(board, k)} has a way out: " + _join([chess.square_name(s) for s in off], "or"))
        return UNDECIDED
    fl = _flights(board, k)
    has_none = not fl
    if has_none != claim.neg:
        return Verdict("true")
    if claim.neg:
        return Verdict("false", "", f"{_who(board, k)} has no legal move")
    return Verdict("false", "", f"{_who(board, k)} can go to " + _join([chess.square_name(s) for s in fl], "or"))


def _zone(claim: Claim, k: int) -> Optional[Callable[[int], bool]]:
    n = claim.count
    r, f = chess.square_rank(k), chess.square_file(k)
    if claim.kind == "ranks" and n:
        if r >= 4:
            return lambda s: chess.square_rank(s) >= 8 - n
        return lambda s: chess.square_rank(s) < n
    if claim.kind == "files" and n:
        if f >= 4:
            return lambda s: chess.square_file(s) >= 8 - n
        return lambda s: chess.square_file(s) < n
    if claim.kind == "cut_rank" and n:
        line = n - 1
        if r == line:
            return None
        return (lambda s: chess.square_rank(s) > line) if r > line else (lambda s: chess.square_rank(s) < line)
    if claim.kind == "cut_file" and n:
        line = n - 1
        if f == line:
            return None
        return (lambda s: chess.square_file(s) > line) if f > line else (lambda s: chess.square_file(s) < line)
    return None


def judge_confined(claim: Claim, board: chess.Board, ctx) -> Verdict:
    k = _king_sq(claim.subj, board, ctx)
    if k is None:
        return UNDECIDED
    color = board.color_at(k)
    if board.turn != color:
        return UNDECIDED
    inside = _zone(claim, k)
    if inside is None or not inside(k):
        return UNDECIDED
    # the squares the king may walk on with the board standing: not its own pieces', not attacked by the other side
    # (the king itself taken off, so a slider's line goes through where it stood)
    empty = board.copy(stack=False)
    empty.remove_piece_at(k)
    seen, frontier, path = {k}, [k], {k: []}
    for _ in range(3):
        nxt = []
        for s in frontier:
            for t in chess.SquareSet(chess.BB_KING_ATTACKS[s]):
                if t in seen:
                    continue
                if board.color_at(t) == color or empty.is_attacked_by(not color, t):
                    continue
                seen.add(t)
                path[t] = path[s] + [t]
                if not inside(t):
                    walk = " and then ".join("K" + chess.square_name(x) for x in path[t])
                    return Verdict("false", "", f"{_who(board, k)} is not shut in: {walk}")
                nxt.append(t)
        frontier = nxt
    return Verdict("true")


def _geometric(claim: Claim) -> bool:
    """A checks_along claim judged on geometry alone (C2a): the king the checks are aimed at stands where the words
    put it, off the line, and the words say whose king it is."""
    return _king_placed(claim) and claim.to.side is not None


def _king_placed(claim: Claim) -> bool:
    """A checks_along claim whose checked king the words put on a square (C2a): judged on geometry, with whose king
    it is read from the words or, when they do not say, from the board (judge_checks_geometry)."""
    return claim.rel == "checks_along" and claim.to is not None and claim.to.piece == "K" and bool(claim.to.sq)


def _nearer_king(board: Optional[chess.Board], sq: str, want: bool) -> bool:
    """On *board* the king of *want* is the one the words put on *sq*: it stands there, or it is nearer to it than the
    other king (as near: its side is to move — the plan told is its own)."""
    if board is None:
        return False
    t = chess.parse_square(sq)
    mine, other = board.king(want), board.king(not want)
    if mine is None:
        return False
    if mine == t or other is None:
        return True
    if other == t:
        return False
    dm, do = chess.square_distance(mine, t), chess.square_distance(other, t)
    return dm < do or (dm == do and board.turn == want)


def judge_checks_geometry(claim: Claim, board: Optional[chess.Board], ctx) -> Verdict:
    """«(Kc7) … когда чёрная ладья начнёт шаховать по вертикали d»: the king the checks are aimed at stands where the
    words put it; off the line, no check along the line reaches it — on any board. Whose king it is: the words (its
    colour, the side that answers the checks, «шахует его», «закрыть короля от шахов»), else the other side from the
    checker when the board makes that king the one that can be there; else undecided."""
    kind, _, x = _line_of(claim.kind).partition(":")
    if kind not in ("file", "rank") or not x:
        return UNDECIDED
    k = chess.parse_square(claim.to.sq)
    if _on_line(claim.kind, k):
        return UNDECIDED
    aimed = "|aimed" in claim.kind
    subj = claim.subj
    checker = subj.side if subj is not None else None
    if checker is None and subj is not None and (subj.sq or subj.owner) and board is not None:
        checker = _side(subj, board, ctx)
    king = claim.to.side
    if king is None and claim.move is not None and claim.move.side is not None:
        king = claim.move.side
    if king is not None and checker is not None and king == checker:
        return UNDECIDED  # the checker's own king: the checks are aimed at the other one
    if king is None:
        if checker is not None:
            if not _nearer_king(board, claim.to.sq, not checker):
                return UNDECIDED  # the checker's own king may be the one told
            king = not checker
        else:
            cand = [c for c in (chess.WHITE, chess.BLACK) if _nearer_king(board, claim.to.sq, c)]
            if len(cand) == 1:
                king = cand[0]
            elif not aimed:
                return UNDECIDED
    if checker is None and king is not None:
        checker = not king
    pt = PIECE_TYPE.get(subj.piece) if subj is not None and subj.piece else None
    diagonal = pt in (chess.QUEEN, chess.BISHOP) or (pt is None and (board is None or checker is None or bool(
        board.pieces(chess.QUEEN, checker) | board.pieces(chess.BISHOP, checker))))
    if diagonal and claim.move is None:
        # «Король на e4 зажат: ферзь ставит шах по линии f» — a piece that also checks along a diagonal may stand on
        # that line and check from it (Qf3+): with the king's square only described, not walked to, it is not judged
        return UNDECIDED
    line = f"the {x}-file" if kind == "file" else f"rank {x}"
    what = _NAME[pt] if pt else "piece"
    ways = [f"the {chess.FILE_NAMES[chess.square_file(k)]}-file", f"rank {chess.square_rank(k) + 1}"]
    if pt in (chess.QUEEN, None):
        ways.append("a diagonal")
    elif pt == chess.BISHOP:
        ways = ["a diagonal"]
    who = f"{_colour(king)}'s king" if king is not None else "the king"
    by = f"{_colour(checker)}'s {what}" if checker is not None else f"a {what}"
    if claim.move is not None and (claim.move.san or claim.move.to):
        head = f"after {claim.move.san or 'K' + claim.to.sq} {who} stands on {claim.to.sq}"
    else:
        head = f"{who} stands on {claim.to.sq}"
    return Verdict("false", "", f"{head}, off {line}: {by} cannot check it along {line} — its checks can only come "
                   "along " + _join(ways, "or"))


def judge_checks_along(claim: Claim, board: chess.Board, ctx) -> Verdict:
    if _king_placed(claim):
        return judge_checks_geometry(claim, board, ctx)
    kind, _, x = _line_of(claim.kind).partition(":")
    if kind not in ("file", "rank") or not x:
        return UNDECIDED
    side = _side(claim.subj, board, ctx)
    if side is None:
        return UNDECIDED
    b = _to_move(board, side)
    if b is None:
        return UNDECIDED
    k = b.king(not side)
    if k is None:
        return UNDECIDED
    on_line = (lambda s: chess.square_file(s) == "abcdefgh".index(x)) if kind == "file" else \
        (lambda s: chess.square_rank(s) == int(x) - 1)
    pt = PIECE_TYPE.get(claim.subj.piece) if claim.subj and claim.subj.piece else None
    checks = []
    for m in b.legal_moves:
        if pt is not None and b.piece_type_at(m.from_square) != pt:
            continue
        if not b.gives_check(m):
            continue
        a = b.copy(stack=False)
        a.push(m)
        checks.append(b.san(m))
        for c in a.checkers():
            if a.piece_type_at(c) in (chess.ROOK, chess.QUEEN) and on_line(c) and on_line(k):
                return Verdict("true")
    line = f"the {x}-file" if kind == "file" else f"rank {x}"
    what = _NAME[pt] if pt else "piece"
    tail = f" (its checks: {_join(checks)})" if checks else ""
    return Verdict("false", "", f"{_colour(side)}'s {what} has no check along {line}: {_who(b, k)} is not on it{tail}")


def _blocks(board: chess.Board) -> list:
    """The legal moves that put a piece between the checking piece and the king."""
    k = board.king(board.turn)
    checkers = list(board.checkers())
    if k is None or len(checkers) != 1:
        return []
    between = chess.SquareSet(chess.between(checkers[0], k))
    return [m for m in board.legal_moves if m.from_square != k and m.to_square in between]


def judge_only_move(claim: Claim, board: chess.Board, ctx) -> Verdict:
    side = "White" if board.turn else "Black"
    mv = None
    if claim.move is not None:
        san = claim.move.san
        try:
            if san:
                mv = board.parse_san(san.rstrip("!?"))
            else:
                cands = [m for m in board.legal_moves if chess.square_name(m.to_square) == claim.move.to
                         and board.piece_type_at(m.from_square) == PIECE_TYPE[claim.move.piece or "P"]
                         and (claim.move.side is None or board.turn == claim.move.side)]
                mv = cands[0] if len(cands) == 1 else None
        except ValueError:
            mv = None
        if mv is not None and claim.move.capture and not board.is_capture(mv):
            mv = None
        if mv is None:
            return UNDECIDED  # the move is not this board's: not the position the words are about
    pt = PIECE_TYPE.get(claim.subj.piece) if claim.subj is not None and claim.subj.piece else None
    if claim.subj is not None and claim.subj.side is not None and claim.subj.side != board.turn:
        return UNDECIDED
    if claim.kind == "check_reply":
        # F13 «Ход Kf8 единственный», «у короля единственный ход Ke7»: the only legal reply to the check
        if mv is None or not board.is_check():
            return UNDECIDED  # off a check «единственный ход» is the only good move: not a rule of the board
        pool = list(board.legal_moves)
        if pt == chess.KING:
            k = board.king(board.turn)
            if mv.from_square != k:
                return UNDECIDED
            pool = [m for m in pool if m.from_square == k]
        # a reply after which the checking side mates at once is no reply in the coach's sense («Qa6+ — и у чёрных
        # только один ответ — bxa6», where 1...Ba7+ allows 2.Qxa7#): only the replies that survive the next move count
        others = sorted(board.san(m) for m in pool if m != mv and not _mated_next(board, m))
        if not others:
            return Verdict("true")
        who = f"{side}'s king" if pt == chess.KING else side
        return Verdict("false", "", f"{who} has other legal replies to the check besides {board.san(mv)}: "
                       + _join(others[:4]) + (f" and {len(others) - 4} more" if len(others) > 4 else ""))
    if claim.kind == "piece":
        # «Король может пойти только на f8»: every legal move of that piece goes to that square
        if mv is None or pt is None or board.piece_type_at(mv.from_square) != pt:
            return UNDECIDED
        dest = sorted({m.to_square for m in board.legal_moves if m.from_square == mv.from_square})
        if dest == [mv.to_square]:
            return Verdict("true")
        return Verdict("false", "", f"{_who(board, mv.from_square)} can also go to "
                       + _join([chess.square_name(x) for x in dest if x != mv.to_square], "or"))
    if claim.kind in ("block", "parry"):
        if not board.is_check():
            return UNDECIDED
        pool = _blocks(board) if claim.kind == "block" else list(board.legal_moves)
        if mv is not None:
            if mv not in pool:
                return UNDECIDED
            if len(pool) == 1:
                return Verdict("true")
            return Verdict("false", "", f"{side} has {len(pool)} legal {'blocks' if claim.kind == 'block' else 'moves'}: "
                           + _join(sorted(board.san(m) for m in pool), "and") + f" — {board.san(mv)} is not the only one")
        if pt is None:
            return UNDECIDED
        if pool and all(board.piece_type_at(m.from_square) == pt for m in pool):
            return Verdict("true")
        other = [board.san(m) for m in pool if board.piece_type_at(m.from_square) != pt]
        if not pool:
            return Verdict("false", "", f"{side} has no legal block of the check")
        return Verdict("false", "", f"not only the {_NAME[pt]}: " + _join(other) + " too")
    if mv is None:
        return UNDECIDED
    legal = list(board.legal_moves)
    if legal == [mv]:
        return Verdict("true")
    others = sorted(board.san(m) for m in legal if m != mv)
    return Verdict("false", "", f"{side} had other legal moves besides {board.san(mv)}: " + _join(others[:4])
                   + (f" and {len(others) - 4} more" if len(others) > 4 else ""))


def _mated_next(board: chess.Board, move: chess.Move) -> bool:
    """After *move* the other side has a mate in one."""
    a = board.copy(stack=False)
    a.push(move)
    for m in a.legal_moves:
        if a.gives_check(m):
            a.push(m)
            mate = a.is_checkmate()
            a.pop()
            if mate:
                return True
    return False


def _guards(board: chess.Board, sq: int, color: bool, skip: Optional[int] = None) -> str:
    """«the pawn on c6 and the queen on d8»: *color*'s pieces that defend *sq* on *board*."""
    names = [f"the {_NAME[board.piece_type_at(s)]} on {chess.square_name(s)}"
             for s in sorted(board.attackers(color, sq), key=lambda s: _VALUE[board.piece_type_at(s)]) if s != skip]
    return _join(names)


def _safety(board: chess.Board, sq: int) -> str:
    """Why the piece on *sq* is safe there: nothing attacks it, or what defends it."""
    p = board.piece_at(sq)
    if p is None or not board.attackers(not p.color, sq):
        return f"nothing attacks {chess.square_name(sq)}"
    guards = _guards(board, sq, p.color, skip=sq)
    return f"{chess.square_name(sq)} is defended by {guards}" if guards else f"nothing wins it on {chess.square_name(sq)}"


# ── a forcing line: what the side to move wins by captures and checks (fix 01.11) ────────────────────────────────
# «Ход Qh5, не давая чёрным спокойно выдвинуть коня на f6: на это Qxf7#» — a stopped move is stopped by a tactic as
# well as by a capture on its square. A small search of captures, promotions and (on the first two moves of the side
# to move) checks, with every reply to a check, finds what the static exchange cannot: a mate, a fork that wins a
# piece, a capture elsewhere. It stops at a node budget; then nothing is known (None) and the judge stays undecided.
_MATE_SCORE = 1000
_FORCE_NODES = 2500
_FORCE_PLIES = 8


class _Budget(Exception):
    pass


def _material(board: chess.Board, color: bool) -> int:
    return sum(v * (len(board.pieces(pt, color)) - len(board.pieces(pt, not color)))
               for pt, v in ((chess.PAWN, 1), (chess.KNIGHT, 3), (chess.BISHOP, 3), (chess.ROOK, 5), (chess.QUEEN, 9)))


def _forcing_order(board: chess.Board, moves: list) -> list:
    def key(m):
        victim = board.piece_type_at(m.to_square)
        return -(_VALUE.get(victim, 1 if board.is_en_passant(m) else 0) * 10 - _VALUE[board.piece_type_at(m.from_square)] // 10)
    return sorted(moves, key=key)


def _qsearch(board: chess.Board, alpha: int, beta: int, ply: int, nodes: list) -> int:
    nodes[0] += 1
    if nodes[0] > _FORCE_NODES:
        raise _Budget
    legal = list(board.legal_moves)
    if board.is_check():
        if not legal:
            return -_MATE_SCORE + ply
        if ply >= _FORCE_PLIES + 2:
            return _material(board, board.turn)
        best = -2 * _MATE_SCORE
        for m in _forcing_order(board, legal):
            board.push(m)
            v = -_qsearch(board, -beta, -alpha, ply + 1, nodes)
            board.pop()
            best = max(best, v)
            alpha = max(alpha, v)
            if alpha >= beta:
                break
        return best
    if not legal:
        return 0  # stalemate
    stand = _material(board, board.turn)
    if stand >= beta:
        return stand
    alpha = max(alpha, stand)
    if ply >= _FORCE_PLIES:
        return stand
    cands = [m for m in legal if board.is_capture(m) or m.promotion or (ply in (0, 2) and board.gives_check(m))]
    for m in _forcing_order(board, cands):
        board.push(m)
        v = -_qsearch(board, -beta, -alpha, ply + 1, nodes)
        board.pop()
        if v >= beta:
            return v
        alpha = max(alpha, v)
    return alpha


def forcing_gain(board: chess.Board) -> Optional[int]:
    """What the side to move on *board* wins in material (pawns) by a forcing line of captures and checks, against
    standing still (≥ 0; ≥ _MATE_SCORE / 2 for a mate); None when the search ran out of its budget."""
    b = board.copy(stack=False)
    try:
        v = _qsearch(b, -2 * _MATE_SCORE, 2 * _MATE_SCORE, 0, [0])
    except _Budget:
        return None
    return max(0, v - _material(board, board.turn))


def _loses_by_force(after: chess.Board) -> Optional[bool]:
    """After a move (the other side to move on *after*): the other side wins a pawn or more by force, or mates."""
    g = forcing_gain(after)
    return None if g is None else g >= 1


def _stop_loss(before: chess.Board, move: chess.Move) -> Optional[int]:
    """What *move* loses for the side making it (pawns, what it takes counted for it): by static exchange on its
    square, or by a forcing line anywhere (a mate, a fork, a capture elsewhere). None when the line search ran out."""
    from src.board_math import captured_value, move_loss

    if move_loss(before, move) > 0:
        return move_loss(before, move)
    after = before.copy(stack=False)
    after.push(move)
    if after.is_checkmate():
        return 0
    g = forcing_gain(after)
    if g is None:
        return None
    return max(0, g - captured_value(before, move))


def _retreat_parts(claim: Claim) -> tuple:
    """(chase tokens, flags) of a retreat_cover claim's kind: «chase:b3,c4|free|forced|wing=O-O»."""
    parts = (claim.kind or "").split("|")
    tokens = [t for t in parts[0].partition(":")[2].split(",") if t] if parts and parts[0].startswith("chase:") else []
    return tokens, set(parts[1:])


def _named_chases(board: chess.Board, frm: int, tokens: list) -> tuple:
    """The boards after a chase move the sentence writes that attacks the piece on *frm* (its owner to move), and the
    SAN; or the board itself when the move is played already (its piece stands there and attacks it). ([], '') else."""
    from src.answer_check_rules import _parse_lowered

    owner = board.color_at(frm)
    chaser = board.copy(stack=False)
    chaser.turn = not owner
    chaser.ep_square = None
    found = []
    for w in tokens:
        try:
            move = _parse_lowered(chaser, w)
        except Exception:  # noqa: BLE001
            move = None
        if move is None:
            continue
        b = chaser.copy(stack=False)
        b.push(move)
        if b.color_at(frm) == owner and b.is_attacked_by(not owner, frm) and not b.is_check():
            found.append((b, chaser.san(move)))
    if found:
        return [b for b, _ in found], (found[0][1] if len(found) == 1 else "")
    for w in tokens:
        sq = re.search(r"[a-h][1-8]$", w)
        if sq is None:
            continue
        s = chess.parse_square(sq.group(0))
        if board.color_at(s) == (not owner) and frm in board.attacks(s) and board.turn == owner:
            return [board], ""  # «8.b3 — и слон …» told on the board after it
    return [], ""


def judge_retreat_cover(claim: Claim, board: chess.Board, ctx) -> Verdict:
    """C5 «нападают на слона, и он вынужден уйти туда, откуда f1 уже не прикрывает»: false when, after the chase, the
    piece has a safe retreat (static exchange, board_math.safe_squares, and no forcing line that wins it) from which it
    still covers the square — after every chase the sentence may mean — or need not move at all. With a retreat named
    and no forcing word («слон отступит на e6, и f1 свободно») only that retreat is judged. «свободно» is judged only on
    an empty square (it may mean «empty»); a castling said to become possible covers the king's path squares."""
    from src.answer_check_rules import _chase_boards
    from src.board_math import safe_squares, see

    subj = claim.subj
    if subj is None or not subj.piece or subj.piece in ("P", "K"):
        return UNDECIDED
    tokens, flags = _retreat_parts(claim)
    pt = PIECE_TYPE[subj.piece]
    colors = [subj.side] if subj.side is not None else [chess.WHITE, chess.BLACK]
    castle = "castle" in flags
    if castle:
        wing = next((f.partition("=")[2] for f in flags if f.startswith("wing=")), "")
        wings = [wing] if wing else ["O-O", "O-O-O"]

        def path(color):  # the squares the king crosses (and lands on) when *color* castles
            rank = 0 if color == chess.WHITE else 7
            files = []
            for w in wings:
                files += [5, 6] if w == "O-O" else [3, 2]
            return [chess.square(f, rank) for f in files]

        zs_of = {c: path(not c) for c in (chess.WHITE, chess.BLACK)}
    else:
        zs = [chess.parse_square(o.sq) for o in claim.objs if o is not None and o.sq]
        if not zs:
            return UNDECIDED
        zs_of = {c: zs for c in (chess.WHITE, chess.BLACK)}
    cands = [(s, c) for c in colors for s in board.pieces(pt, c) if any(z in board.attacks(s) for z in zs_of[c])]
    if subj.sq:
        cands = [x for x in cands if x[0] == chess.parse_square(subj.sq)]
    if len(cands) != 1:
        return UNDECIDED  # «уже не прикрывает»: the piece covers the square now — one piece of that kind, or not ours
    frm, owner = cands[0]
    xs = [z for z in zs_of[owner] if z in board.attacks(frm)]
    if "free" in flags and any(board.piece_at(z) is not None for z in xs):
        return UNDECIDED  # «поле f1 свободно» with a piece on f1: it may mean the square is empty
    if flags:
        chases, chase_san = _named_chases(board, frm, tokens)
    else:
        chases, chase_san = _chase_boards(board, frm, tokens, [])
    if not chases:
        return UNDECIDED  # nothing chases it: «вынужден уйти» is about another position
    named = chess.parse_square(claim.move.to) if claim.move is not None and claim.move.to else None
    only_named = "line_named" in flags and named is not None

    def covers(b: chess.Board, t: int) -> bool:
        return any(z in b.attacks(t) or (z == t and "line" in flags) for z in xs)

    found = None
    for b in chases:
        if b.turn != owner:
            return UNDECIDED
        keep = []
        if not flags:
            # the reading of plan 31.10 («вынужден уйти туда, откуда …»), as it was: safe by static exchange
            for t in ([named] if named is not None else []) + safe_squares(b, frm):
                mv = chess.Move(frm, t)
                if mv in b.legal_moves:
                    a = b.copy(stack=False)
                    a.push(mv)
                    if covers(a, t):
                        keep.append((t, b.san(mv), a))
        elif only_named:
            mv = chess.Move(frm, named)
            if mv in b.legal_moves:
                a = b.copy(stack=False)
                a.push(mv)
                if covers(a, named):
                    keep.append((named, b.san(mv), a))
        else:
            # every way to meet the chase (stay when nothing wins the piece there, or a safe retreat), with what the
            # chaser then wins by force: a way that keeps the cover counts when it is no worse than the best way
            # (a loss elsewhere that every way suffers is not the retreat's)
            ways = []
            chaser = _to_move(b, not owner)
            if chaser is not None:
                attackers = [mv for mv in chaser.legal_moves if mv.to_square == frm]
                if attackers and all(see(chaser, mv) <= 0 for mv in attackers):
                    ways.append((frm, "", b, chaser))
            for t in safe_squares(b, frm):
                mv = chess.Move(frm, t)
                if mv in b.legal_moves:
                    a = b.copy(stack=False)
                    a.push(mv)
                    ways.append((t, b.san(mv), a, a))
            gains = [forcing_gain(w[3]) for w in ways]
            known = [g for g in gains if g is not None]
            best = min(known) if known else None
            for (t, san, a, _w), g in zip(ways, gains):
                if g is not None and best is not None and g <= best and covers(a, t):
                    keep.append((t, san, a))
        if not keep:
            return Verdict("true")  # after this chase every safe way gives the square up: the words hold here
        found = found or keep[0]
    t, san, a = found
    head = f"after {chase_san} " if chase_san else ""
    zname = _join([chess.square_name(z) for z in xs]) if not castle else _join([chess.square_name(z) for z in xs])
    tail = " — castling stays illegal" if castle else ""
    if not san:
        return Verdict("false", "", f"{head}{_colour(owner)}'s {_NAME[pt]} on {chess.square_name(frm)} need not move: "
                       f"nothing wins it there ({_safety(a, frm)}), and it still covers {zname}{tail}")
    if named is not None and t == named:
        return Verdict("false", "", f"{head}{_colour(owner)}'s {_NAME[pt]} on {chess.square_name(t)} still covers "
                       f"{zname}: {san} does not give it up{tail}")
    return Verdict("false", "", f"{head}{_colour(owner)}'s {_NAME[pt]} on {chess.square_name(frm)} is not forced off "
                   f"{zname}: {san} — it is safe there ({_safety(a, t)}) and still covers {zname}{tail}")


def judge_prevents(claim: Claim, board: chess.Board, ctx) -> Verdict:
    """C6 «d4, не давая чёрным спокойно поставить пешку на d5»: false when, after the move, the other side's move to
    that square is legal and loses nothing — by static exchange on the square, nor by a forcing line anywhere (a mate,
    a fork, a capture elsewhere: «Qh5, не давая … Nf6: на это Qxf7#»). The move must be the side to move's on this
    board; a castling target is judged by its legality and the same loss."""
    if claim.move is None or not (claim.move.san or claim.move.castle) or claim.to is None:
        return UNDECIDED
    castle = claim.kind.startswith("castle:")
    if not castle and not claim.to.sq:
        return UNDECIDED
    after = _playable(board, claim.move, strict=True)
    if after is None:
        return UNDECIDED  # the move is not this board's (for the side to move)
    mover = not after.turn
    subj = claim.subj
    if subj is not None and subj.owner == "their":
        stopped = not mover
    elif subj is not None and (subj.side is not None or subj.owner == "you"):
        stopped = _side(subj, board, ctx)
    else:
        stopped = not mover
    if stopped is None or stopped == mover:
        return UNDECIDED
    if castle:
        wing = claim.kind.partition(":")[2]
        cands = [m for m in after.legal_moves if after.is_castling(m)
                 and (not wing or (wing == "O-O") == after.is_kingside_castling(m))]
    else:
        t = chess.parse_square(claim.to.sq)
        pt = PIECE_TYPE.get(claim.to.piece) if claim.to.piece else None
        there = after.piece_at(t)
        if there is not None and there.color == stopped:
            return UNDECIDED  # its piece stands there already: the words are about a board before that move
        frm = claim.kind.partition(":")[2] if claim.kind.startswith("from:") else None
        cands = [m for m in after.legal_moves if m.to_square == t and (pt is None or after.piece_type_at(m.from_square) == pt)
                 and not after.is_castling(m) and (frm is None or chess.square_name(m.from_square) == frm)]
    if not cands:
        return Verdict("true")
    free = []
    for m in cands:
        loss = _stop_loss(after, m)
        if loss is None:
            return UNDECIDED  # the forcing line could not be searched out: no verdict
        if loss == 0:
            free.append(m)
    if not free:
        return Verdict("true")  # every such move loses material: «не давая спокойно …» holds
    m = free[0]
    played = after.san(m)
    a = after.copy(stack=False)
    a.push(m)
    why = _safety(a, m.to_square) if not castle else "nothing attacks the king's path"
    return Verdict("false", "", f"after {claim.move.san.rstrip('!?') if claim.move.san else 'the move'} {_colour(stopped)} "
                   f"can still play {played}: it is legal and loses nothing ({why})")


def _playable(board: chess.Board, m: MoveRef, *, strict: bool = False) -> Optional[chess.Board]:
    """*board* after *m* — for the side to move, or (not *strict*) for the other one after a pass; None when it is not
    a move here (or its written side is not the one to move)."""
    for b in (board,) if strict else (board, _to_move(board, not board.turn)):
        if b is None:
            continue
        if strict and m.side is not None and m.side != b.turn:
            continue
        try:
            if m.castle:
                mv = b.parse_san("O-O" if m.castle == "short" else "O-O-O")
            elif m.san:
                mv = b.parse_san(m.san.rstrip("!?"))
            else:
                continue
        except ValueError:
            continue
        if m.capture and not b.is_capture(mv):
            continue  # «Kxh5» with nothing on h5: not this board's move (python-chess reads it as Kh5)
        a = b.copy(stack=False)
        a.push(mv)
        return a
    return None


def _shown_boards(ctx) -> list:
    """The positions given to the turn as positions (the board shown after a tool), not the start position the
    context always holds."""
    try:
        keys = set(ctx.state_keys) - set(ctx.line_keys) - set(getattr(ctx, "other_board_keys", ()) or ())
        start = ctx._key(chess.Board())
        cur = ctx._key(ctx.current) if getattr(ctx, "current", None) is not None else None
        keys.discard(start if cur != start else None)
        return [b for b in ctx.boards if ctx._key(b) in keys]
    except Exception:  # noqa: BLE001 — a context without these fields: only the board itself
        return []


def _not_this_board(claim: Claim, board: chess.Board, ctx) -> bool:
    """The sentence does not describe *board*: a piece it places on a square is not there («чёрный конь забрался на
    h5» on another position), or the move it writes after the claim cannot be played from it («поле h5 занято
    твоей пешкой, и король вынужден её взять — Kxh5» before the move that put the pawn there)."""
    st = getattr(ctx, "relation_state", None) or {}
    placed = st.get("rules_placed") or ()
    if placed:
        # where the sentence may place them: this board, the board now, a board the turn shows, the positions of the
        # line the sentence writes («Qxd7# — ферзь бьёт слона на d7»: the bishop stood there before the capture)
        cur = getattr(ctx, "current", None)
        boards = [board] + ([cur] if cur is not None else []) + _shown_boards(ctx) \
            + [b for _, b, _ in (getattr(ctx, "scene_trail", None) or [])]
        for piece, sq in placed:
            s, pt = chess.parse_square(sq), PIECE_TYPE[piece]
            if not any(b.piece_type_at(s) == pt for b in boards):
                return True
    later = next((m for s, m in st.get("rules_moves") or () if s >= claim.span[1]), None)
    if later is not None and _playable(board, later) is None:
        own = _playable(board, claim.move) if claim.move is not None and claim.move.san else None
        if own is None or _playable(own, later) is None:
            return True
    return False


def detector_of(claim: Claim) -> Optional[str]:
    """The plan 31.10 detector (src/config.py DETECTOR_DEFAULTS) a claim of this file belongs to, or None for the
    board rules of WP-D, which follow COACH_RELATION_CHECK alone."""
    if _king_placed(claim):
        return "checks_geometry"
    if claim.rel in ("retreat_cover", "prevents"):
        return claim.rel
    if claim.rel == "only_move" and claim.kind == "check_reply":
        return "only_move_orders"
    return None


def _shadowed(name: str, claim: Claim, verdict: Verdict, ctx) -> None:
    """A detector in shadow: its false verdict is recorded with the relation shadow records (logged, never shown)."""
    try:
        seen = getattr(ctx, "_p3d_shadow", None)
        if seen is None:
            seen = set()
            ctx._p3d_shadow = seen
        st = getattr(ctx, "relation_state", None) or {}
        key = (name, st.get("rules_text", ""), verdict.truth)
        if key in seen:
            return
        seen.add(key)
        ctx.relation_shadow.append((st.get("rules_text", ""), [f"[{name}] {verdict.truth}"]))
        # counted as a flag, so the turn's relation_check event carries it, and recorded with every other shadow
        # detector's (the detector_shadow event; review-wiring 01.11)
        stats = getattr(ctx, "relation_stats", None)
        if isinstance(stats, dict):
            stats["flags"] = stats.get("flags", 0) + 1
        from src.answer_check import record_shadow

        record_shadow(ctx, name, [verdict.truth], st.get("rules_text") or None)
    except Exception:  # noqa: BLE001 — a context without the shadow list: nothing to record
        pass


def _guarded(judge: Callable[[Claim, chess.Board, Any], Verdict]) -> Callable[[Claim, chess.Board, Any], Verdict]:
    def run(claim: Claim, board: chess.Board, ctx) -> Verdict:
        name = detector_of(claim)
        mode = detector_mode(name, ctx) if name else "on"
        if mode == "off":
            return UNDECIDED
        if mode == "shadow":
            from src.answer_check_relations import mode as relation_mode

            if relation_mode(ctx) == "shadow":
                mode = "on"  # the whole relation check records it already, in its own words (SHADOW == ON)
        # a claim judged on geometry alone does not depend on the board, so the board guards do not apply to it
        if board is None or (ctx is not None and not _king_placed(claim) and _not_this_board(claim, board, ctx)):
            return UNDECIDED
        verdict = judge(claim, board, ctx)
        if mode == "shadow" and verdict.status == "false":
            _shadowed(name, claim, verdict, ctx)
            return UNDECIDED
        return verdict

    run.__name__ = judge.__name__
    run.__doc__ = judge.__doc__
    return run


RULE_JUDGES.update({rel: _guarded(fn) for rel, fn in (
    ("only_move", judge_only_move),
    ("no_flight", judge_no_flight),
    ("confined", judge_confined),
    ("can_capture", judge_can_capture),
    ("can_exchange", judge_can_exchange),
    ("occupied", judge_occupied),
    ("checks_along", judge_checks_along),
    ("retreat_cover", judge_retreat_cover),
    ("prevents", judge_prevents),
)})
