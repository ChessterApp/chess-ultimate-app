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
def _pos(moves: list, at: int, low: str, state: Optional[dict] = None) -> Pos:
    """The position the words before *at* point at: after the moves written before it, «затем …» going on from the
    line before; else the board now — or a position of the line the sentence before wrote («Ra2+ … Bxa2. Королю
    некуда шагнуть: a2 занят собственным слоном»), each of which is an alternative."""
    before = tuple(m for s, _, m in moves if s < at)
    if _THEN.search(low):
        return Pos(at="then", moves=before)  # «Тогда …», «Затем … (Kc7)»: on from where the sentence before ended
    if before:
        return Pos(at="after", moves=before)
    last = state.get("rules_last") if isinstance(state, dict) else None
    if isinstance(last, tuple) and last:
        story = state.get("rules_story") or last
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


def _claim(rel, subj, objs=(), *, pos=Pos(), span=(0, 0), move=None, kind="", neg=False, count=None):
    return Claim(rel=rel, subj=subj, objs=tuple(objs), pos=pos, span=span, source="rules", move=move, kind=kind,
                 neg=neg, count=count)


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
                       r"(?:\s+(?P<own>свои\w*|собственн\w*|сво\w+\s+же))?(?:\s+(?:же\s+)?(?P<pw>[а-я]+))?" + _E)
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
        objs = tuple(Ref(sq=s, piece=piece if not neg else None) for s in sqs)
        out.append(_claim("occupied", None, objs, pos=_pos(moves, m.start(), low, state), span=(m.start(), m.end()), neg=neg))
    return out


# checks_along ─────────────────────────────────────────────────────────────────────────────────────────────────
_CHECKS = re.compile(_W + r"(?<!от\s)(?:шахи|шаховать|шахует|шахуют|шахами|давать\s+шахи|дает\s+шахи|начн\w+\s+шаховать)\s+"
                     r"(?:[а-я]+\s+)?по\s+(?P<kind>вертикали|линии|горизонтали)\s+(?:«)?(?P<x>[a-h1-8])(?![a-z0-9])")


def _checks_along(conv, low, moves, state):
    out = []
    for m in _CHECKS.finditer(low):
        if re.search(r"от\s+(?:[а-я]+\s+)?$", low[max(0, m.start() - 12):m.start()]):
            continue
        moves_before = any(s < m.start() for s, _, _ in moves)
        head = low[:m.start()]
        if _HYPO.search(low) or _IF.search(head) or not moves_before:
            continue  # a check «when» something happens is about the board after the moves told before it
        x = m.group("x")
        kind = ("file:" + x) if x.isalpha() else ("rank:" + x)
        if (m.group("kind") == "вертикали") != x.isalpha():
            continue
        pm = None
        for p in _PIECE.finditer(low, max(0, m.start() - 40), m.start()):
            pm = p
        if pm is None:
            continue
        side = _side_word(low, max(0, pm.start() - 20), pm.start())
        subj = Ref(piece=_piece_at(low, pm), side=side, text=pm.group(0))
        out.append(_claim("checks_along", subj, pos=_pos(moves, m.start(), low, state), span=(pm.start(), m.end()), kind=kind))
    return out


_CUE = re.compile(r"тольк|единствен|выбор|ходов|обязан|вынужден|должн|некуда|нет\s|заперт|отрезан|прижат|зажат|загород|"
                  r"закрыл|занял|отнял|перекрыл|забрал|закрывает|занимает|загораживает|забирает|отбирает|отнимает|перекрывает|"
                  r"мож|могу|смож|занят|свободн|пуст|шах")


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
        for part in (_only_move, _no_flight, _can_capture, _occupied, _checks_along):
            claims += part(conv, low, moves, st)
    if isinstance(state, dict):
        state["rules_placed"] = _placed(low) if claims else ()
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


def see(board: chess.Board, move: chess.Move) -> int:
    """The static exchange count of the capture *move* (in pawns): what its side wins on that square when both sides
    keep taking there with their cheapest piece while it pays."""
    t = move.to_square
    if board.is_en_passant(move):
        first = 1
    else:
        v = board.piece_at(t)
        first = _VALUE[v.piece_type] if v else 0
    b = board.copy(stack=False)
    mover = b.piece_at(move.from_square)
    gains = [first]
    on_square = _VALUE[mover.piece_type]
    b.push(move)
    side = b.turn
    while True:
        attackers = [s for s in b.attackers(side, t)
                     if chess.Move(s, t) in b.legal_moves or (b.piece_type_at(s) == chess.PAWN and chess.square_rank(t) in (0, 7))]
        if not attackers:
            break
        s = min(attackers, key=lambda x: _VALUE[b.piece_type_at(x)])
        gains.append(on_square - gains[-1])
        on_square = _VALUE[b.piece_type_at(s)]
        mv = next((m for m in b.legal_moves if m.from_square == s and m.to_square == t), None)
        if mv is None:
            break
        b.push(mv)
        side = b.turn
    for i in range(len(gains) - 1, 0, -1):
        gains[i - 1] = -max(-gains[i - 1], gains[i])
    return gains[0]


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


def judge_checks_along(claim: Claim, board: chess.Board, ctx) -> Verdict:
    kind, _, x = claim.kind.partition(":")
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


def _playable(board: chess.Board, m: MoveRef) -> Optional[chess.Board]:
    """*board* after *m* — for the side to move, or for the other one after a pass; None when it is not a move here."""
    for b in (board, _to_move(board, not board.turn)):
        if b is None:
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


def _guarded(judge: Callable[[Claim, chess.Board, Any], Verdict]) -> Callable[[Claim, chess.Board, Any], Verdict]:
    def run(claim: Claim, board: chess.Board, ctx) -> Verdict:
        if board is None or (ctx is not None and _not_this_board(claim, board, ctx)):
            return UNDECIDED
        return judge(claim, board, ctx)

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
)})
