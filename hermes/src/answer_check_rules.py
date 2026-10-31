"""Claims about the rules of the position, checked on the board (2026-10-06).

The production check of 2026-10-06 (eval/bench/2026-10-06-blind-spots) found
claims the answer check let through because it read none of them:

  * castling — "Yes — you can castle here, it's perfectly legal" with f1
    attacked by the bishop on c4 (in Russian, English and Kazakh);
  * the result — «Да, это выигрыш» in a wrong-bishop ending, a tablebase draw;
  * mate and stalemate — «Чёрные получили мат» on a stalemate;
  * mate in N — «здесь мат в два хода» where there is none;
  * files and passed pawns — «линия d полуоткрыта для белых» with a white
    pawn on d5;
  * en passant — «взять на проходе нельзя» when exd6 is legal.

Each claim is judged only when it is about the board in front of the student:
a rule stated in general («рок[иеі]роваться можно, даже если ладья под боем») or a
hypothetical («если ты сыграешь…») is left alone.
"""

from __future__ import annotations

import re
from typing import Optional

import chess

from src.board_rules import castling_status, en_passant_moves, file_kind, is_passed

_W = r"(?<![а-яa-zәғқңөұүһі])"
_E = r"(?![а-яa-zәғқңөұүһі])"

# The claim is about this board, or a rule in general / a condition / a consequence; a denial before the
# claim. One source for the whole checker: src/claim_scope.py (2026-10-15).
from src.claim_scope import CONDITIONAL as _GENERAL, NOW as _NOW, YES_NO as _YES_NO  # noqa: E402
from src.claim_scope import about_now as _about_now, denied_before as _denied_before  # noqa: E402

# «тогда», «получится»: the consequence of the move just named, not the board as it is.
_THEN = re.compile(_W + r"(?:тогда|получится|получается|будет|выйдет|окажется|then|would\s+be|that\s+gives|"
                   r"сонда|болады)" + _E, re.IGNORECASE)


def _about_board(text: str) -> bool:
    return _about_now(text, strict=True)


def _negated_before(text: str, start: int) -> bool:
    return _denied_before(text, start, window=18)


# ── Castling ────────────────────────────────────────────────────────────────

_CASTLE_WORD = r"(?:рок[иеі]р\w*|castl\w*|O-O(?:-O)?|0-0(?:-0)?)"
_CAN_CASTLE = [
    re.compile(_W + r"(?:можешь|можете|можно|получится|сможешь|сможете|разрешена|возможна|доступна|легальна|"
               r"допустима|имеешь\s+право)\s+(?:[а-яё]+\s+){0,3}?" + r"(?:сделать\s+)?(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]р\w*",
               re.IGNORECASE),
    re.compile(_W + r"рок[иеі]ровк\w*\s+(?:в\s+\w+\s+(?:сторону\s+)?)?(?:[а-яё]+\s+){0,2}?(?:возможна|разрешена|доступна|"
               r"легальна|допустима|законна)" + _E, re.IGNORECASE),
    re.compile(r"\b(?:you|white|black)\s+(?:can|may|are\s+allowed\s+to)\s+(?:still\s+|now\s+)?castle\b"
               r"|\bcastling\s+(?:kingside\s+|queenside\s+|short\s+|long\s+)?is\s+(?:perfectly\s+|fully\s+|totally\s+|"
               r"completely\s+|still\s+)?(?:legal|possible|allowed|available)\b|\byes,?\s+(?:you\s+)?can\s+castle\b",
               re.IGNORECASE),
    re.compile(r"рок[иеі]ровка\s+жасай\s+ала(?:сың|сыз|ды)|рок[иеі]ровка\s+жасауға\s+болады|рок[иеі]ровка\s+жасауыңа\s+болады",
               re.IGNORECASE),
    # «O-O-O тоже возможна», «0-0 сейчас доступна» (09.10: the notation is the name of the castling too)
    re.compile(r"(?<![a-z0-9-])(?:o-o-o|0-0-0|o-o|0-0)(?![a-z0-9-])\s+(?:тоже\s+|сейчас\s+|уже\s+|здесь\s+|тут\s+|вполне\s+)*"
               r"(?:возможн[аы]|доступн[аы]|разрешен[аы]|легальн[аы]|допустим[аы])" + _E, re.IGNORECASE),
    # «Длинная рокировка у тебя есть всегда, она возможна» (09.10 with c1 and d1 taken): the castling named, then
    # «она возможна» in the same clause. («рокировка у тебя есть» alone is the right to castle: _castle_right_issues.)
    re.compile(_W + r"рок[иеі]ровк\w*[^.;!?]{0,40}?,\s*(?:и\s+)?(?:она|it)\s+(?:тоже\s+|сейчас\s+|уже\s+|вполне\s+|is\s+)?"
               r"(?:возможна|доступна|разрешена|легальна|possible|legal|available)" + _E, re.IGNORECASE),
    # «рок[иеі]роваться сейчас можно», «рок[иеі]ровку делать можно»
    re.compile(_W + r"рок[иеі]р\w*\s+(?:(?!не\s)[а-яё]+\s+){0,2}?(?:можно|можешь|можете|получится|разрешено|разрешается)" + _E,
               re.IGNORECASE),
]
_CANNOT_CASTLE = [
    re.compile(_W + r"(?:нельзя|не\s+можешь|не\s+можете|не\s+получится|не\s+сможешь|невозможн\w*|запрещен\w*|"
               r"не\s+разрешена|не\s+имеешь\s+права)\s+(?:[а-яё]+\s+){0,3}?(?:сделать\s+)?(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]р\w*",
               re.IGNORECASE),
    re.compile(_W + r"рок[иеі]ровк\w*\s+(?:в\s+\w+\s+(?:сторону\s+)?)?(?:[а-яё]+\s+){0,2}?(?:невозможна|запрещена|нельзя|"
               r"не\s+разрешена|недоступна|нелегальна)" + _E, re.IGNORECASE),
    re.compile(r"\b(?:you|white|black)?\s*(?:can'?t|cannot|can\s+not|may\s+not|are\s+not\s+allowed\s+to)\s+castle\b"
               r"|\bcastling\s+(?:kingside\s+|queenside\s+|short\s+|long\s+)?is\s+(?:not\s+(?:legal|possible|allowed|available)|"
               r"illegal|impossible)\b", re.IGNORECASE),
    re.compile(r"рок[иеі]ровка\s+жасай\s+алмай\w*|рок[иеі]ровка\s+жасауға\s+болмайды", re.IGNORECASE),
    re.compile(_W + r"рок[иеі]р\w*\s+(?:[а-яё]+\s+){0,2}?(?:нельзя|не\s+можешь|не\s+можете|не\s+получится|не\s+разрешено|"
               r"невозможно|запрещено)" + _E, re.IGNORECASE),
]


def _wing(text: str) -> Optional[str]:
    if re.search(r"длинн\w*|ферзев\w*|queenside|long|O-O-O|0-0-0|ұзын", text, re.IGNORECASE):
        return "O-O-O"
    if re.search(r"коротк\w*|королевск\w*|kingside|short|(?<![-0O])O-O(?!-O)|(?<![-0])0-0(?!-0)|қысқа", text, re.IGNORECASE):
        return "O-O"
    return None


def _named_side(text: str) -> Optional[bool]:
    m = re.search(_W + r"(бел\w*|ч[её]рн\w*|white|black|ақтар\w*|қаралар\w*)" + _E, text, re.IGNORECASE)
    if not m:
        return None
    w = m.group(1).lower()
    return chess.WHITE if w.startswith(("бел", "white", "ақ")) else chess.BLACK


def _castling_issues(text: str, ctx) -> list[str]:
    board = ctx.current
    if board is None or not re.search(_CASTLE_WORD, text, re.IGNORECASE):
        return []
    claims = []
    for rx in _CANNOT_CASTLE:
        for m in rx.finditer(text):
            claims.append((m.start(), False, m.end()))
    for rx in _CAN_CASTLE:
        for m in rx.finditer(text):
            if _negated_before(text, m.start()):
                continue
            if any(abs(m.start() - s) < 4 and not can for s, can, _ in claims):
                continue
            claims.append((m.start(), True, m.end()))
    if not claims:
        return []
    claims.sort()
    if _AFTER_MOVE.search(text[:claims[0][0]]):
        return []  # «сначала b3 — и ты сможешь рокироваться»: after the move, _castle_after_move_issues judges it
    question = getattr(ctx, "question", "") or ""
    question_about_castling = bool(re.search(_CASTLE_WORD, question, re.IGNORECASE))
    qm = re.search(_CASTLE_WORD, question, re.IGNORECASE)
    if qm and _GENERAL.search(question[qm.end():]):
        return []  # «можно ли рокироваться, если ладья под боем?» — a rule, not this board (voice, 2026-10-06)
    if _GENERAL.search(question) and not _NOW.search(text):
        return []
    if not (_about_board(text) or (question_about_castling and not _GENERAL.search(text))):
        return []
    # The side named next to the claim («белые не могут рокироваться»), not anywhere
    # in the sentence («…нельзя, потому что слон чёрных на c4…» is about White).
    first = claims[0]
    color = _named_side(text[max(0, first[0] - 25):first[2]])
    if color is None:
        color = ctx.student_color if ctx.student_color is not None else board.turn
    st = castling_status(board, color)
    wing = _wing(text) or _wing(getattr(ctx, "question", "") or "")
    wings = [wing] if wing else ["O-O", "O-O-O"]
    side = "White" if color == chess.WHITE else "Black"
    issues = []
    for _, can, _end in claims[:1]:
        legal = [w for w in wings if st[w][0]]
        if can and not legal:
            why = "; ".join(f"{w}: {st[w][1]}" for w in wings)
            issues.append(f"{side} cannot castle here — {why}")
        elif not can and wing and st[wing][0]:
            issues.append(f"{side} can castle {wing} here — it is legal on this board")
        elif not can and not wing and len(legal) == 2:
            issues.append(f"{side} can castle here (both ways are legal on this board)")
    return issues


# «Рокировка у тебя ещё есть: король и ладьи не ходили», «Право на рокировку у тебя есть, но сейчас рокироваться
# нельзя» — the RIGHT to castle, not castling legal now (review 30.10: castling_status cut both with «pieces stand
# between the king and the rook»). Judged only by what the board shows for sure: the king off its square, or the
# rook of the wing gone from its corner; the rights of a FEN (a set-up position often has «-» or «KQkq») are not.
_CASTLE_RIGHT = re.compile(
    _W + r"(?:право\s+на\s+)?(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]ровк\w*\s+(?:у\s+(?:тебя|вас|белых|ч[её]рных)\s+)?"
    r"(?:всегда\s+|сейчас\s+|уже\s+|ещ[её]\s+|по-прежнему\s+|пока\s+)*(?:есть|сохраняется|сохранилось|осталось|остается)"
    r"(?!\s+(?:смысл|резон|ли|причин))" + _E, re.IGNORECASE)


def _castle_right_issues(text: str, ctx) -> list[str]:
    board = ctx.current
    m = _CASTLE_RIGHT.search(text) if board is not None else None
    if m is None or _negated_before(text, m.start()):
        return []
    question = getattr(ctx, "question", "") or ""
    if _GENERAL.search(question) and not _NOW.search(text):
        return []
    if not (_about_board(text) or (re.search(_CASTLE_WORD, question, re.IGNORECASE) and not _GENERAL.search(text))):
        return []
    color = _named_side(text[max(0, m.start() - 25):m.end()])
    if color is None:
        color = ctx.student_color if ctx.student_color is not None else board.turn
    side = "White" if color == chess.WHITE else "Black"
    rank = 0 if color == chess.WHITE else 7
    king = chess.square(4, rank)
    if board.piece_at(king) != chess.Piece(chess.KING, color):
        return [f"{side} has no right to castle any more: the king has left {chess.square_name(king)}"]
    wing = _wing(text) or _wing(question)
    corners = {"O-O": chess.square(7, rank), "O-O-O": chess.square(0, rank)}
    gone = [w for w in ([wing] if wing else ["O-O", "O-O-O"]) if board.piece_at(corners[w]) != chess.Piece(chess.ROOK, color)]
    if gone and len(gone) == (1 if wing else 2):
        return [f"{side} has no right to castle {' or '.join(gone)} any more: the rook has left "
                + " and ".join(chess.square_name(corners[w]) for w in gone)]
    return []


# ── The result: win / draw ──────────────────────────────────────────────────

_RESULT = re.compile(
    _W + r"(?:это|позиция|здесь|тут|такое\s+окончание|окончание|эндшпиль|this|it|that|the\s+position|the\s+ending)"
    r"(?:\s+is|'s|\s+—|\s+-)?\s+(?:[а-яёa-z]+\s+){0,2}?"
    r"(?P<r>выигрыш\w*|выигран\w*|ничь[яеию]\w*|ничейн\w+|проигрыш\w*|проигран\w*|"
    r"(?:a\s+)?win(?:ning)?|won|(?:a\s+)?draw(?:n)?|lost|losing)" + _E, re.IGNORECASE)


def _result_issues(text: str, ctx) -> list[str]:
    ev = getattr(ctx, "engine_eval", None)
    tb = getattr(ctx, "tablebase", None)
    if ev is None and tb is None:
        return []
    issues = []
    for m in _RESULT.finditer(text):
        if _negated_before(text, m.start("r")) or re.search(r"\bnot\s+(?:a\s+)?$", text[max(0, m.start("r") - 8):m.start("r")]):
            continue
        before = text[:m.start()]
        if _GENERAL.search(before) and not _NOW.search(text):
            continue
        r = m.group("r").lower()
        # «ферзь на b6 — тогда пат, и это ничья»: the position after the student's
        # move, not this board (production voice, 2026-10-07: the check called the
        # true «Qb6 — пат» wrong and the coach «corrected» itself into a falsehood).
        after = [b for dest, b in _question_after_boards(ctx) if chess.square_name(dest) in before.lower()]
        if not after and _THEN.search(before):
            after = [b for _, b in _question_after_boards(ctx)]
        if not after:
            # The square was in the sentence before («Постой, ферзь b6 — это пат! У чёрного короля нет
            # ходов, а шаха нет, так что это сразу ничья.» — production voice 2026-10-07): a draw that the
            # student's own move makes is not judged against the board as it stands.
            draws = [b for _, b in _question_after_boards(ctx) if b.is_stalemate() or b.is_insufficient_material()]
            mates = [b for _, b in _question_after_boards(ctx) if b.is_checkmate()]
            if (draws and r.startswith(("ничь", "ничейн", "draw"))) or (mates and r.startswith(("выигр", "win", "won"))):
                break
        if after:
            if all(b.is_stalemate() or b.is_insufficient_material() for b in after) and r.startswith(("выигр", "win", "won")):
                issues.append("after the student's move the position is a draw (stalemate or no mating material), not a win")
            elif all(b.is_checkmate() for b in after) and r.startswith(("ничь", "ничейн", "draw")):
                issues.append("after the student's move it is checkmate, not a draw")
            break
        if r.startswith(("выигр", "win", "won")):
            if tb == "draw":
                issues.append("the endgame tablebase says this position is a draw with best play, not a win")
            elif tb is None and ev is not None and abs(ev) < 1.0:
                issues.append(f"the engine evaluates the position at {ev:+.1f} for White — nobody is winning")
        elif r.startswith(("ничь", "ничейн", "draw")):
            if tb and tb != "draw":
                issues.append(f"the endgame tablebase says {tb} — not a draw")
            elif tb is None and ev is not None and abs(ev) >= 3.0:
                issues.append(f"the engine evaluates the position at {ev:+.1f} for White — not a draw")
        break
    return issues


# ── Mate and stalemate on the board ─────────────────────────────────────────

_SAN_OR_SQ = re.compile(r"(?<![A-Za-z])(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8]|[a-h][1-8]|O-O)")
_MATE_CLAIM = re.compile(
    r"(?:(?:это|уже|получил\w*|поставил\w*|объявил\w*|ты\s+дал\w*|is|it'?s|that'?s|you(?:'ve)?\s+(?:given|delivered))\s+"
    r"(?:\w+\s+)?)(?P<w>мат|checkmate|mate)(?!\s+(?:в|in|через|за)\s)" + _E
    + r"|(?P<w2>чёрн\w+|черн\w+|бел\w+|black|white|ты)\s+(?:получил\w*\s+|поставлен\s+|is\s+|got\s+)?(?:мат|checkmated|mated)" + _E,
    re.IGNORECASE)
_STALEMATE_CLAIM = re.compile(_W + r"(?:это|уже|получил\w*|is|it'?s|that'?s)\s+(?:\w+\s+)?(?:пат|stalemate)" + _E, re.IGNORECASE)


def _mate_state_issues(text: str, ctx) -> list[str]:
    board = ctx.current
    if board is None or _SAN_OR_SQ.search(text):
        return []  # a line of moves: the written-move check judges «Qxg7 — мат»
    if not (board.is_checkmate() or board.is_stalemate()):
        # The board may have changed during the turn (a line loaded by a tool),
        # and «что это за мат» is a name: only a finished game is certain.
        return []
    issues = []
    mate = None
    for m in _MATE_CLAIM.finditer(text):
        if _negated_before(text, m.start()) or re.search(r"(?:не|not|no)\s+(?:\w+\s+)?$", text[max(0, m.start("w" if m.group("w") else "w2") - 12):m.start("w" if m.group("w") else "w2")]):
            continue
        mate = True
        break
    stalemate = None
    for m in _STALEMATE_CLAIM.finditer(text):
        if _negated_before(text, m.start()):
            continue
        stalemate = True
        break
    if mate and not board.is_checkmate() and _about_board(text + " сейчас" if _YES_NO.search(text) or board.is_stalemate() else text):
        if board.is_stalemate():
            issues.append("this is stalemate (no legal move, no check) — a draw, not mate")
        elif not _GENERAL.search(text):
            issues.append("the position on the board is not checkmate")
    if stalemate and not board.is_stalemate() and not _GENERAL.search(text):
        if board.is_checkmate():
            issues.append("this is checkmate, not stalemate (the king is in check)")
        elif _NOW.search(text) or _YES_NO.search(text):
            issues.append("the position on the board is not stalemate — there are legal moves")
    return issues


# ── Mate in N ───────────────────────────────────────────────────────────────

_NUM = {"один": 1, "одного": 1, "два": 2, "двух": 2, "три": 3, "трёх": 3, "трех": 3, "четыре": 4, "четырёх": 4,
        "пять": 5, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_MATE_IN = re.compile(r"(?P<neg>нет\s+|no\s+|не\s+видно\s+)?(?:форсированн\w+\s+|forced\s+)?(?:мат\w*|mate)\s+(?:в|in)\s+"
                      r"(?P<n>\d|один|одного|два|двух|три|тр[её]х|четыре|четыр[её]х|пять|one|two|three|four|five)"
                      r"(?P<after>[^.!?]{0,30})", re.IGNORECASE)


_MATE_AGAINST = re.compile(
    _W + r"(?:пропуска\w*|пропуст\w*|получа\w*|получи\w*|получишь|позволя\w*|позвол\w*|допуска\w*|допуст\w*|нарв\w*|"
    r"подставля\w*|себе|allow\w*|walk\w*\s+into|get\s+mated|after)" + _E, re.IGNORECASE)


def _mate_in_issues(text: str, ctx) -> list[str]:
    if getattr(ctx, "engine_eval", None) is None or ctx.current is None:
        return []  # no engine look at this board this turn
    mate = getattr(ctx, "engine_mate", None)
    for m in _MATE_IN.finditer(text):
        n = int(m["n"]) if m["n"].isdigit() else _NUM.get(m["n"].lower().replace("ё", "е"), _NUM.get(m["n"].lower()))
        if not n:
            continue
        neg = bool(m["neg"]) or bool(re.search(r"(?:нет|не\s+\w+|no|isn'?t|is\s+not|there'?s\s+no)\s*$",
                                               text[max(0, m.start() - 25):m.start()], re.IGNORECASE)) \
            or bool(re.match(r"\s*(?:ход\w*\s+)?(?:—\s*)?(?:здесь\s+|тут\s+|сейчас\s+|пока\s+)?(?:нет|не\s+\w+)",
                             m["after"] or "", re.IGNORECASE))  # «мат в два тут не форсируется» (2026-10-13)
        before = text[:m.start()]
        if _GENERAL.search(before) and not _NOW.search(text):
            continue
        if _named_side(text) is not None and _named_side(text) != ctx.current.turn:
            continue  # about the side not to move — the engine line is not
        if _MATE_AGAINST.search(text) or (getattr(ctx, "quoted", None) and not _NOW.search(text)):
            # «ты сам пропускаешь мат в один ход» after the student's idea: the mate after that move,
            # not this board's (the lesson tutor's true sentence was cut, 2026-10-08).
            continue
        has = mate is not None and 0 < mate <= n
        if neg and has:
            return [f"there IS a forced mate in {mate} here (engine)"]
        if not neg and not has and (mate is None or mate <= 0) and n <= 3:
            return [f"there is no forced mate in {n} here (engine)"]
        if not neg and mate is not None and mate > n:
            return [f"the shortest forced mate here takes {mate} moves, not {n} (engine)"]
        return []
    return []


# ── Files and passed pawns ──────────────────────────────────────────────────

_FILE_CLAIMS = [
    re.compile(_W + r"(?:вертикал\w*|лини\w*)\s+[\*'\"«]*(?P<f>[a-h])[\*'\"»]*[\s,]+"
               r"(?:(?!лини|вертикал|открыт|полуоткрыт|закрыт|file)[а-яёa-h0-9()*]+[\s,]+){0,9}?(?:—\s+|-\s+)?"
               r"(?:(?:это\s+)?(?:сейчас\s+|уже\s+|полностью\s+)?)(?P<k>полуоткрыт\w*|наполовину\s+(?:свободн|открыт)\w*|открыт\w*|закрыт\w*)", re.IGNORECASE),
    re.compile(_W + r"(?P<k>полуоткрыт\w*|открыт\w*)\s+(?:вертикал\w*|лини\w*)\s+\**(?P<f>[a-h])\**" + _E, re.IGNORECASE),
    re.compile(r"\b(?:the\s+)?\**(?P<f>[a-h])\**-file\s+(?:is\s+)?(?:now\s+|fully\s+|still\s+)?(?P<k>half-open|semi-open|open|closed)\b",
               re.IGNORECASE),
    re.compile(r"\b(?P<k>half-open|semi-open|open)\s+\**(?P<f>[a-h])\**-file\b", re.IGNORECASE),
]
_FOR_SIDE = re.compile(r"^[^.;]{0,25}?(?:для|у|for)\s+(?P<s>бел\w*|ч[её]рн\w*|white|black|тебя|меня|you)", re.IGNORECASE)


def _asked_about(ctx, pattern: str) -> bool:
    return bool(re.search(pattern, getattr(ctx, "question", "") or "", re.IGNORECASE))


def _file_issues(text: str, ctx) -> list[str]:
    board = ctx.current
    if board is None:
        return []
    if not (_asked_about(ctx, r"вертикал|лини[июя]|file|открыт|сызық|тік") or _NOW.search(text)):
        return []  # «игра по полуоткрытой линии c» in an opening's theory is not about this board
    issues = []
    for rx in _FILE_CLAIMS:
        for m in rx.finditer(text):
            if _negated_before(text, m.start("k")):
                continue
            if _GENERAL.search(text[:m.start()]) and not _NOW.search(text):
                continue
            f = "abcdefgh".index(m["f"].lower())
            k = m["k"].lower()
            actual = file_kind(board, f)
            name = m["f"].lower()
            if k.startswith(("полуоткрыт", "наполовину", "half", "semi")):
                if actual in ("open", "closed"):
                    issues.append(f"the {name}-file is {actual}, not half-open")
                    continue
                side = _FOR_SIDE.match(text[m.end():]) or re.search(
                    r"(?:для|у|for)\s+(?P<s>бел\w*|ч[её]рн\w*|white|black|тебя|меня|you)", m.group(0), re.IGNORECASE)
                if side:
                    s = side["s"].lower()
                    if s in ("тебя", "меня", "you"):
                        color = ctx.student_color if ctx.student_color is not None else board.turn
                    else:
                        color = chess.WHITE if s.startswith(("бел", "white")) else chess.BLACK
                    want = "half-open for White" if color == chess.WHITE else "half-open for Black"
                    if actual != want:
                        issues.append(f"the {name}-file is {actual} (a half-open file has no pawn of that side)")
            elif k.startswith(("открыт", "open")):
                if actual != "open":
                    issues.append(f"the {name}-file is {actual}, not open — pawns stand on it")
            elif k.startswith(("закрыт", "closed")):
                if actual != "closed":
                    issues.append(f"the {name}-file is {actual}, not closed")
    # «открытая только вертикаль e», «открыта лишь линия e», "only the e-file is open" (production
    # 2026-10-07: the c-file was open too)
    for m in re.finditer(r"(?:открыт\w*\s+(?:здесь\s+|тут\s+|сейчас\s+)?(?:только|лишь|одна)\s+(?:одна\s+)?(?:вертикал\w*|лини\w*)\s+\**(?P<f>[a-h])\**"
                         r"|(?:только|лишь)\s+(?:вертикал\w*|лини\w*)\s+\**(?P<f2>[a-h])\**\s+(?:[а-яё]+\s+){0,2}?открыт\w*"
                         r"|only\s+the\s+(?P<f3>[a-h])-?file\s+is\s+open)" + _E, text, re.IGNORECASE):
        if _negated_before(text, m.start()):
            continue
        named = (m["f"] or m["f2"] or m["f3"]).lower()
        opened = [chess.FILE_NAMES[f] for f in range(8) if file_kind(board, f) == "open"]
        if opened != [named]:
            issues.append(f"the open files here are {', '.join(opened) or 'none'}, not only the {named}-file")
    # «Открытых вертикалей здесь нет», "there are no open files"
    if re.search(r"(?:полностью\s+)?открыт\w*\s+(?:вертикал|лини)\w*\s+(?:здесь\s+|тут\s+|сейчас\s+)?нет|нет\s+(?:ни\s+одной\s+)?"
                 r"(?:полностью\s+)?открыт\w*\s+(?:вертикал|лини)|no\s+(?:fully\s+)?open\s+files|there\s+are\s+no\s+open\s+files",
                 text, re.IGNORECASE):
        opened = [chess.FILE_NAMES[f] for f in range(8) if file_kind(board, f) == "open"]
        if opened:
            issues.append(f"there are open files here: {', '.join(opened)} (no pawns on them)")
    # «У белых нет пешки на линии d»
    for m in re.finditer(_W + r"у\s+(?P<s>бел\w+|ч[её]рн\w+)\s+нет\s+пешк\w*\s+на\s+(?:лини\w+|вертикал\w+)\s+\**(?P<f>[a-h])\**",
                         text, re.IGNORECASE):
        color = chess.WHITE if m["s"].lower().startswith("бел") else chess.BLACK
        f = "abcdefgh".index(m["f"].lower())
        if any(chess.square_file(s) == f for s in board.pieces(chess.PAWN, color)):
            issues.append(f"{'White' if color else 'Black'} has a pawn on the {m['f'].lower()}-file")
    return list(dict.fromkeys(issues))


_PASSED_CLAIMS = [
    re.compile(_W + r"проходн\w*\s+(?:пешк\w+\s+)?(?:на\s+)?\**(?P<sq>[a-h][1-8])\**", re.IGNORECASE),
    re.compile(_W + r"пешк\w+\s+\**(?P<sq>[a-h][1-8])\**\s+(?:—\s+|-\s+)?(?:это\s+|уже\s+|теперь\s+|сейчас\s+)?(?:[а-яё]+\s+){0,1}?проходн\w*",
               re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])\**(?P<sq>[a-h][1-8])\**\s+(?:—\s+|-\s+)(?:это\s+)?проходн\w*", re.IGNORECASE),
    re.compile(r"\bpassed\s+pawn\s+on\s+\**(?P<sq>[a-h][1-8])\**|\b(?:the\s+)?\**(?P<sq2>[a-h][1-8])\**[- ]pawn\s+is\s+(?:a\s+)?passed",
               re.IGNORECASE),
]


def _passed_issues(text: str, ctx) -> list[str]:
    board = ctx.current
    if board is None:
        return []
    if not (_asked_about(ctx, r"проходн|passed|өтпелі") or _NOW.search(text)):
        return []
    issues = []
    for rx in _PASSED_CLAIMS:
        for m in rx.finditer(text):
            name = m.groupdict().get("sq") or m.groupdict().get("sq2")
            if not name:
                continue
            if _negated_before(text, m.start()) or re.search(r"(?:не|not)\s+(?:a\s+)?$", text[max(0, m.end() - 20):m.end() - len(name)]):
                continue
            if _GENERAL.search(text[:m.start()]) and not _NOW.search(text):
                continue
            sq = chess.parse_square(name.lower())
            p = board.piece_at(sq)
            if p is None or p.piece_type != chess.PAWN:
                continue  # whose pawn and where: the presence checks judge that
            if not is_passed(board, sq):
                issues.append(f"the pawn on {name.lower()} is not passed — an enemy pawn on its file or a neighbouring "
                              "file can stop it")
    return list(dict.fromkeys(issues))


# ── En passant ──────────────────────────────────────────────────────────────

_EP_NO = re.compile(_W + r"(?:нельзя|не\s+можешь|не\s+получится|невозможно|не\s+выйдет)\s+(?:[а-яё]+\s+){0,3}?на\s+проходе"
                    r"|на\s+проходе\s+(?:[а-яё]+\s+){0,2}?(?:нельзя|невозможно|не\s+получится)"
                    r"|\b(?:can'?t|cannot)\s+(?:take|capture)\s+en\s+passant|\ben\s+passant\s+is\s+not\s+(?:possible|available|legal)",
                    re.IGNORECASE)
_EP_YES = re.compile(_W + r"(?:можешь|можно|получится)\s+(?:[а-яё]+\s+){0,3}?на\s+проходе"
                     r"|\b(?:you\s+)?can\s+(?:take|capture)\s+(?:\w+\s+){0,2}en\s+passant|\ben\s+passant\s+is\s+(?:possible|available|legal)",
                     re.IGNORECASE)


def _en_passant_issues(text: str, ctx) -> list[str]:
    board = ctx.current
    if board is None or not re.search(r"на\s+проходе|en\s+passant", text, re.IGNORECASE):
        return []
    if _GENERAL.search(text) and not _NOW.search(text):
        return []
    available = en_passant_moves(board)
    m = _EP_NO.search(text)
    if m and available and not _negated_before(text, m.start()):
        return [f"en passant is available right now: {', '.join(board.san(x) for x in available)}"]
    m = _EP_YES.search(text)
    if m and not available and not _negated_before(text, m.start()) and (_NOW.search(text) or _YES_NO.search(text)):
        return ["there is no en passant capture on this board now (the last move was not a two-square pawn move "
                "next to one of your pawns)"]
    return []


# ── The king: where it can go, whether it is in check ──────────────────────

_KING_GOES = re.compile(
    _W + r"корол\w*\s+(?:[а-яё]+\s+){0,2}?(?:может\s+|сможет\s+)?(?:просто\s+|спокойно\s+|сразу\s+)?"
    r"(?:пойти|уйти|отойти|сходить|шагнуть|убежать|спрятаться|ходит|пойд[её]т|уйд[её]т|отойд[её]т|убежит|встать)\s+на\s+"
    r"(?:поле\s+)?(?P<sq>[a-h][1-8])(?![0-9])"
    r"|\bking\s+(?:can|could|will|would)?\s*(?:just\s+|simply\s+)?(?:go|goes|escape|escapes|step|steps|run|runs|move|moves)\s+"
    r"(?:to|on)\s+(?P<sq2>[a-h][1-8])\b", re.IGNORECASE)
_IN_CHECK = re.compile(
    _W + r"(?:(?P<side>бел\w+|ч[её]рн\w+|тво\w+|ваш\w+)\s+)?корол\w*\s+(?:сейчас\s+|уже\s+)?(?:находится\s+|стоит\s+)?"
    r"под\s+(?:шахом|ударом|атакой)"
    r"|\b(?:the\s+)?(?P<side2>white|black|your)?\s*king\s+is\s+(?:now\s+)?(?:in\s+check|under\s+attack)"
    r"|\byou\s+are\s+in\s+check", re.IGNORECASE)


def _question_after_boards(ctx) -> list:
    """Positions after the moves the student named (on the board in front of them)."""
    cached = getattr(ctx, "_question_after", None)
    if cached is not None:
        return cached
    out = []
    try:
        from src.prompt_builder import question_moves

        if ctx.current is not None and getattr(ctx, "question_raw", ""):
            for q in question_moves(ctx.question_raw, ctx.current.fen()):
                if q.get("after_fen"):
                    out.append((q["move"].to_square, chess.Board(q["after_fen"])))
    except Exception:  # noqa: BLE001
        out = []
    try:
        ctx._question_after = out
    except Exception:  # noqa: BLE001
        pass
    return out


def _king_can_go(board: chess.Board, sq: int) -> Optional[bool]:
    """Can a king next to *sq* step there on its move? None when no king is next to it."""
    verdicts = []
    for color in (chess.WHITE, chess.BLACK):
        k = board.king(color)
        if k is None or chess.square_distance(k, sq) != 1:
            continue
        b = board.copy(stack=False)
        b.turn = color
        b.ep_square = None
        verdicts.append(chess.Move(k, sq) in b.legal_moves)
    return any(verdicts) if verdicts else None


def _king_issues(text: str, ctx) -> list[str]:
    board = ctx.current
    if board is None:
        return []
    issues = []
    for m in _KING_GOES.finditer(text):
        if _negated_before(text, m.start()) or re.search(r"(?:не|not|can'?t|cannot)\s+(?:\w+\s+)?$",
                                                         text[max(0, m.start("sq") if m.group("sq") else m.start("sq2")) - 30:
                                                              m.start("sq") if m.group("sq") else m.start("sq2")]):
            continue
        name = (m.group("sq") or m.group("sq2")).lower()
        sq = chess.parse_square(name)
        # After the student's move when the sentence is about it («если ферзь на b6, король пойдёт на a7»).
        boards = [b for dest, b in _question_after_boards(ctx) if chess.square_name(dest) in text[:m.start()]]
        if not boards:
            if _GENERAL.search(text[:m.start()]):
                continue  # a hypothetical about some other move
            boards = [board]
        verdicts = [v for v in (_king_can_go(b, sq) for b in boards) if v is not None]
        if verdicts and not any(verdicts):
            issues.append(f"the king cannot go to {name} there — the square is attacked or taken"
                          + (" (the position after the student's move is stalemate)" if any(b.is_stalemate() for b in boards) else ""))
    for m in _IN_CHECK.finditer(text):
        before = text[:m.start()]
        if _GENERAL.search(before) or _negated_before(text, m.start()):
            continue  # «рок[иеі]ровка невозможна, если король под шахом» — a rule
        side = (m.group("side") or m.group("side2") or "").lower()
        if side.startswith(("бел", "white")):
            color = chess.WHITE
        elif side.startswith(("черн", "чёрн", "black")):
            color = chess.BLACK
        else:
            color = ctx.student_color if ctx.student_color is not None else board.turn
        b = board.copy(stack=False)
        b.turn = color
        if not b.is_check():
            issues.append(f"the {'white' if color else 'black'} king is not in check on this board")
    return issues


# ── Square colours ──────────────────────────────────────────────────────────

# Forms that describe a square («поле h8 белое», «чёрного цвета»), not a side («белые хотят»).
_LIGHT_WORDS = r"бел(?:ое|ая|ого\s+цвета)|светл(?:ое|ая|ого\s+цвета)|light|white"
_DARK_WORDS = r"ч[её]рн(?:ое|ая|ого\s+цвета)|т[её]мн(?:ое|ая|ого\s+цвета)|dark|black"
_SQ_COLOUR = re.compile(
    _W + r"(?:поле|клетка|квадрат)\s+(?:превращения\s+)?(?:на\s+)?(?P<sq>[a-h][1-8])\s+(?:—\s+|-\s+)?(?:это\s+|у\s+нас\s+)?"
    rf"(?P<c>{_LIGHT_WORDS}|{_DARK_WORDS})(?![а-яa-z])"
    rf"|\b(?P<sq2>[a-h][1-8])\s+is\s+an?\s+(?P<c2>light|dark|white|black)\s+square", re.IGNORECASE)
_BISHOP_COLOUR = re.compile(
    _W + r"слон\w*\s+(?:на\s+)?(?P<sq>[a-h][1-8])\s+(?:—\s+|-\s+)?(?:это\s+|у\s+тебя\s+)?(?P<c>белопольн\w*|чернопольн\w*|ч[её]рнопольн\w*)"
    r"|(?P<c2>белопольн\w*|чернопольн\w*|ч[её]рнопольн\w*)\s+слон\w*\s+(?:[а-яё]+\s+){0,2}?(?:на\s+|с\s+)?(?P<sq2>[a-h][1-8])"
    r"|\b(?:the\s+)?bishop\s+on\s+(?P<sq3>[a-h][1-8])\s+is\s+(?:a\s+)?(?P<c3>light|dark)[- ]squared", re.IGNORECASE)


def _is_light(sq: int) -> bool:
    return (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1


def _colour_issues(text: str) -> list[str]:
    """«поле h8 белое», «слон на e2 чернопольный» — the colour of a square is a fact of the board itself."""
    issues = []
    for m in _SQ_COLOUR.finditer(text):
        name = (m.group("sq") or m.group("sq2")).lower()
        said_light = bool(re.match(_LIGHT_WORDS, (m.group("c") or m.group("c2")), re.IGNORECASE))
        if _negated_before(text, m.start("c") if m.group("c") else m.start("c2")):
            continue
        if said_light != _is_light(chess.parse_square(name)):
            issues.append(f"{name} is a {'light' if _is_light(chess.parse_square(name)) else 'dark'} square")
    for m in _BISHOP_COLOUR.finditer(text):
        name = (m.group("sq") or m.group("sq2") or m.group("sq3")).lower()
        word = (m.group("c") or m.group("c2") or m.group("c3")).lower()
        said_light = word.startswith(("бел", "light"))
        if said_light != _is_light(chess.parse_square(name)):
            issues.append(f"a bishop on {name} is {'light' if _is_light(chess.parse_square(name)) else 'dark'}-squared")
    return issues


# ── The castling rule itself ────────────────────────────────────────────────

_ROOK_ATTACKED = (r"(?:ладь\w*\s+(?:[а-яё]+\s+){0,2}?(?:под\s+бо\w+|под\s+удар\w*|атакован\w*)"
                  r"|(?:атакованн\w*|атакуем\w*)\s+ладь\w*)")
# «ладья не должна быть под боем (в момент рокировки)», "the rook must not be attacked" (production 2026-10-07)
# …and «ладья не должна быть атакована» (09.10: the rule missed «атакована»)
_ROOK_MUST_NOT = (r"ладь\w*\s+не\s+(?:должн\w*|может|могут|обязан\w*)\s+(?:быть|находиться|стоять|оказаться)\s+"
                  r"(?:под\s+(?:бо\w+|удар\w*)|атакован\w*)|rook\s+(?:must|should|may|can)\s*(?:not|n'?t)\s+be\s+(?:attacked|under\s+attack)")

# The rule told to be denied: a myth, what many think, «нет такого правила», «это не так» — the reported speech
# of a wrong belief, not the coach's own claim.
_DEBUNK = re.compile(
    r"(?<![а-яё])(?:миф\w*|будто|якобы|многие\s+(?:думают|считают|полагают)|часто\s+(?:думают|считают)|"
    r"нет\s+такого\s+правила|такого\s+правила\s+нет|это\s+не\s+так(?!\s+(?:просто|важно|страшно|сложно|уж|часто))|"
    r"неправда|не\s+правда|в\s+правилах\s+(?:этого|такого)\s+нет|заблуждени\w*|ошибочно)(?![а-яё])"
    r"|\b(?:myths?|misconceptions?|there\s+is\s+no\s+such\s+rule|not\s+true)\b", re.IGNORECASE)


def _castling_rule_issues(text: str, question: str = "") -> list[str]:
    """«Нельзя рокироваться, если ладья под боем» — a false rule: only the king's squares matter
    (the voice coach said it on 2026-10-06). The castling may be named in the question only:
    «Можно рокироваться, если ладья под боем?» — «Можно, если только ладья не под боем»."""
    q = (question or "").lower().replace("ё", "е")
    # «Можно ли рокироваться, если моя ладья под боем?» — «Нет, нельзя — …» (the newest code,
    # 2026-10-08, with the right rule two sentences later): the general rule, answered no.
    if (re.search(_CASTLE_WORD, q, re.IGNORECASE) and re.search(_ROOK_ATTACKED, q, re.IGNORECASE)
            and re.search(r"(?<![а-яё])(?:если|когда)(?![а-яё])|\b(?:if|when)\b", q)
            and re.search(r"^\W*(?:(?:нет|no|жоқ)[\s,—–-]+(?:нельзя|не\s+можешь|не\s+можете|не\s+получится|you\s+can'?t|"
                          r"cannot)|нельзя)(?![а-яё])", text, re.IGNORECASE)):
        return ["castling is allowed when the rook is attacked: only the king may not be in check, pass "
                "through or land on an attacked square — the answer to the question is yes"]
    if not re.search(_CASTLE_WORD, text + " " + q, re.IGNORECASE) or not re.search(
            _ROOK_ATTACKED + r"|" + _ROOK_MUST_NOT + r"|rook\s+is\s+(?:not\s+)?(?:attacked|under\s+attack)", text, re.IGNORECASE):
        return []
    forbids = re.search(
        r"(?:нельзя|невозможн\w*|не\s+можешь|не\s+может|не\s+получится|запрещ\w*|can'?t|cannot|not\s+allowed)"
        r"[^.;!?]{0,60}?(?:если|когда|if|when)[^.;!?]{0,20}?(?:тво\w+\s+|ваш\w+\s+|мо\w+\s+)?" + _ROOK_ATTACKED +
        r"|" + _ROOK_ATTACKED + r"[^.;!?]{0,30}?(?:нельзя|невозможн|не\s+можешь|не\s+получится|запрещ)"
        r"|при\s+" + _ROOK_ATTACKED + r"[^.;!?]{0,30}?(?:нельзя|невозможн|запрещ)"
        r"|если\s+(?:только\s+)?(?:тво\w+\s+|ваш\w+\s+)?ладь\w*\s+(?:[а-яё]+\s+)?не\s+(?:находится\s+|стоит\s+)?"
        r"(?:под\s+(?:бо|удар)|атакован|никем\s+не\s+атакован)"  # «только если ладья не атакована» (09.10)
        r"|ладь\w*\s+(?:[а-яё]+\s+)?не\s+(?:атакован\w*|под\s+(?:бо\w+|удар\w*))[^.;!?]{0,30}?(?:можно|разрешен\w*)\s+рок[иеі]р"
        r"|only\s+if\s+(?:your\s+|the\s+)?rook\s+is\s+not\s+(?:attacked|under\s+attack)"
        r"|" + _ROOK_MUST_NOT,
        text, re.IGNORECASE)
    if forbids and _DEBUNK.search(text):
        return []  # «Есть миф, будто ладья не должна быть атакована, но в правилах этого нет» (review 30.10)
    if forbids and not re.search(r"(?<![а-яё])даже(?![а-яё])|\beven\s+if", text, re.IGNORECASE):
        return ["castling is allowed when the rook is attacked: only the king may not be in check, pass "
                "through or land on an attacked square"]
    return []


# «Be3 ставит слона прямо под удар пешки» when the bishop on e3 is hit by a bishop (the client's
# game, 2026-10-07): who attacks the piece the student's move put on its square.
_PIECE_ACC = {"слон": chess.BISHOP, "кон": chess.KNIGHT, "лад": chess.ROOK, "ферз": chess.QUEEN, "пешк": chess.PAWN,
              "корол": chess.KING}
_UNDER_ATTACK_BY = re.compile(
    r"(?:(?P<p1>слон|конь|ладья|ферзь|пешка)\s+(?:[а-яё]+\s+){0,2}?(?:вста[её]т|встанет|оказывается|окажется|попада[её]т|"
    r"попад[её]т)|(?:став\w*|подставля\w*|поставит)\s+(?:(?:сво\w+|тво\w+)\s+)?(?P<p2>слона|коня|ладью|ферзя|пешку|фигуру))"
    r"\s+(?:прямо\s+|сразу\s+)?под\s+(?:удар|бой)\s+(?:ч[её]рн\w+\s+|бел\w+\s+)?(?P<a>пешки|коня|слона|ладьи|ферзя|короля)" + _E)


def _attacked_by_issues(text: str, ctx) -> list[str]:
    issues = []
    for m in _UNDER_ATTACK_BY.finditer(text):
        if _negated_before(text, m.start()):
            continue
        said = next((t for k, t in _PIECE_ACC.items() if m["a"].startswith(k)), None)
        piece_word = m["p1"] or m["p2"] or ""
        named = next((t for k, t in _PIECE_ACC.items() if piece_word.startswith(k)), None)
        for dest, board in _question_after_boards(ctx):
            piece = board.piece_at(dest)
            if piece is None or (named is not None and named != piece.piece_type):
                continue
            attackers = board.attackers(not piece.color, dest)
            types = {board.piece_type_at(a) for a in attackers}
            if said in types:
                continue
            who = ", ".join(f"the {chess.piece_name(board.piece_type_at(a))} on {chess.square_name(a)}" for a in attackers)
            issues.append(f"the {chess.piece_name(piece.piece_type)} on {chess.square_name(dest)} is attacked by "
                          f"{who or 'nothing'}, not by a {chess.piece_name(said)}")
            break
    return issues


# «На b3 пешка пойти не может» with b2–b3 legal, «конь b1 не может пойти на c3» (the voice coach,
# 2026-10-06): a legal move of the board in front of the student denied. A condition or a later
# position («если…», «после…», «пока…») is not about this board and is left alone.
_GO_PIECE = r"(?P<piece>пешк\w*|кон[ьяеюё]\w*|слон\w*|ладь\w*|ферз\w*|корол\w*|pawn|knight|bishop|rook|queen|king)"
_GO_VERB = (r"(?:пойти|ходить|сходить|встать|отступить|уйти|прыгнуть|шагнуть|двинуться|переместиться|попасть|"
            r"go|move|retreat|step|jump)")
_CANNOT_GO = [
    re.compile(_W + _GO_PIECE + r"(?:\s+(?:с\s+|on\s+|from\s+)?(?P<frm>[a-h][1-8]))?\s+(?:сейчас\s+|никак\s+|уже\s+)?"
               r"(?:не\s+может|не\s+сможет|не\s+могут|can'?t|cannot|can\s+not)\s+(?:\w+\s+)?" + _GO_VERB
               + r"\s+(?:на|в|to|on)\s+(?P<to>[a-h][1-8])" + _E, re.IGNORECASE),
    re.compile(_W + r"(?:на|в)\s+(?P<to>[a-h][1-8])\s+" + _GO_PIECE + r"(?:\s+(?P<frm>[a-h][1-8]))?\s+(?:сейчас\s+|никак\s+)?"
               + _GO_VERB + r"\s+не\s+(?:может|сможет|могут)" + _E, re.IGNORECASE),
]
_GO_TYPES = {"пешк": chess.PAWN, "pawn": chess.PAWN, "кон": chess.KNIGHT, "knight": chess.KNIGHT, "слон": chess.BISHOP,
             "bishop": chess.BISHOP, "лад": chess.ROOK, "rook": chess.ROOK, "ферз": chess.QUEEN, "queen": chess.QUEEN,
             "корол": chess.KING, "king": chess.KING}


# «не может пойти на f7, там пешка под защитой» means it would be lost, not that the rules forbid it.
_GO_SAFETY = re.compile(r"защищ|защит|под\s+удар|под\s+бо|потер|отда|зев|бесплатн|без\s+потер|размен|"
                        r"defend|protect|lose|hang|attacked|safe", re.IGNORECASE)


def _reaches(board: chess.Board, sq: int, to: int) -> bool:
    """The piece on *sq* could go to *to* by its way of moving, ignoring checks and blockers on its own square."""
    piece = board.piece_at(sq)
    if piece.piece_type != chess.PAWN:
        return bool(board.attacks_mask(sq) & chess.BB_SQUARES[to])
    step = 8 if piece.color == chess.WHITE else -8
    return to in (sq + step, sq + 2 * step)  # the square is empty: a pawn goes there only straight ahead


def _cannot_go_issues(text: str, ctx) -> list[str]:
    board = getattr(ctx, "current", None)
    if board is None or (_GENERAL.search(text) and not _NOW.search(text)) or _GO_SAFETY.search(text):
        return []
    for rx in _CANNOT_GO:
        for m in rx.finditer(text):
            ptype = next(t for k, t in _GO_TYPES.items() if m.group("piece").lower().startswith(k))
            to = chess.parse_square(m.group("to"))
            frm = chess.parse_square(m.group("frm")) if m.group("frm") else None
            if board.piece_at(to) is not None:
                continue  # a capture: «can't go» there is about what it costs
            # The pieces the sentence may mean: the one on the named square, else every piece of the type
            # that moves that way to the square; all of them must be able to go.
            cands = [frm] if frm is not None else [sq for sq in board.pieces(ptype, chess.WHITE) | board.pieces(ptype, chess.BLACK)
                                                  if _reaches(board, sq, to)]
            if not cands or any(board.piece_type_at(sq) != ptype for sq in cands):
                continue
            legal = []
            for sq in cands:
                b = board.copy(stack=False)
                b.turn = board.color_at(sq)
                if b.turn != board.turn and (b.is_check() or not b.is_valid()):
                    break  # the side not to move: only when its moves are well defined
                mv = next((mv for mv in b.legal_moves if mv.from_square == sq and mv.to_square == to), None)
                if mv is None:
                    break
                legal.append((b, mv))
            else:
                b, mv = legal[0]
                return [f"{b.san(mv)} is legal here: the {chess.piece_name(ptype)} on "
                        f"{chess.square_name(mv.from_square)} can go to {chess.square_name(to)}"]
    return []


# «Король обязан отойти» right after «Первый ход — Rxh6+», where the only legal reply is gxh6; «вынуждены
# взять» where nothing can take. Production lesson answers, 07.10: the sacrifice nobody took, the king
# that «had to move» and could not. Judged on the scene — the position after the move the answer named
# in this sentence or the one before — and only when the claim cannot be true at all there.
_FORCED_KING = re.compile(
    _W + r"(?:(?:корол\w*|king)\s+(?:[а-яёa-z]+\s+){0,3}?(?:обязан\w*|вынужден\w*|должен|придётся|придется|has\s+to|must)"
         r"\s+(?:[а-яёa-z]+\s+)?(?:уйти|отойти|отступить|уходить|отходить|бежать|убегать|move|retreat|run|step)"
         # «чёрные обязаны ответить королём на e7» (the Opera Game told on the stand, 2026-10-08)
         r"|(?:обязан\w*|вынужден\w*|должн\w*|придётся|придется|has\s+to|must)\s+(?:[а-яёa-z]+\s+)?"
         r"(?:ответить|отвечать|уйти|отойти|сыграть|пойти|играть|reply|answer|move)\s+(?:[а-яёa-z]+\s+)?(?:корол[её]м|with\s+the\s+king))"
    + _E, re.IGNORECASE)
_FORCED_TAKE = re.compile(
    _W + r"(?:обязан\w*|вынужден\w*|должн\w*|приходится|придётся|придется|has\s+to|have\s+to|must)\s+"
         r"(?:[а-яёa-z]+\s+)?(?:взять|бить|побить|забрать|брать|съесть|take|capture)" + _E, re.IGNORECASE)


_WRITTEN_MOVE = re.compile(r"(?<![a-zа-я0-9])(?:[kqrbnкрфлс][a-h]?[1-8]?[x:×]?[a-h][1-8]|[a-h][x:×][a-h][1-8]|o-o(?:-o)?)[+#]?",
                           re.IGNORECASE)


def _norm_san(san: str) -> str:
    s = san.rstrip("+#!?").replace(":", "x").replace("×", "x").lower()
    for ru, en in (("кр", "k"), ("ф", "q"), ("л", "r"), ("с", "b"), ("к", "n")):
        if s.startswith(ru):
            return en + s[len(ru):]
    return s


def _scene_at(text: str, at: int, ctx):
    """(board, san) the claim at *at* is about: after the last move written before it in this sentence,
    else after the last move of the sentences before (if the explanation is still about it)."""
    if _NOW.search(text[:at]):
        return getattr(ctx, "current", None), "the move on the board"  # «сейчас король нападает…»: the board as it is
    before = [_norm_san(m.group(0)) for m in _WRITTEN_MOVE.finditer(text[:at])]
    trail = getattr(ctx, "scene_trail", []) or []
    if before and trail:
        last = before[-1]
        for san, board, _move in trail:  # the first move of the sentence written as the last one before the claim
            if _norm_san(san) == last:
                return board, san
        for san, board, _move in trail:
            if _norm_san(san)[-2:] == last[-2:]:
                return board, san
        return None, ""
    if before:
        return None, ""
    prev = getattr(ctx, "scene_before", None)
    if prev and prev[2] <= 3:
        return prev[0], prev[1]
    return None, ""


def _forced_reply_issues(text: str, ctx) -> list[str]:
    if getattr(ctx, "current", None) is None:
        return []  # no position of the turn: a line read from the starting board means nothing
    m_king, m_take = _FORCED_KING.search(text), _FORCED_TAKE.search(text)
    m0 = m_king or m_take
    if m0 is None:
        return []
    board, san = _scene_at(text, m0.start(), ctx)
    if board is None or board.is_game_over():
        return []
    if _GENERAL.search(text) and not _NOW.search(text) and not re.search(r"(?<![а-яё])после(?![а-яё])", text):
        return []
    side = "White" if board.turn == chess.WHITE else "Black"
    replies = list(board.legal_moves)
    named = _named_side(text)
    if named is not None and named != board.turn:
        return []
    m = m_king
    if m and not _negated_before(text, m.start()) and not any(board.piece_type_at(r.from_square) == chess.KING for r in replies):
        only = ", ".join(board.san(r) for r in replies[:3])
        return [f"after {san} the {side.lower()} king cannot move at all: the only replies are {only}"]
    m = m_take
    if m and not _negated_before(text, m.start()) and not any(board.is_capture(r) for r in replies):
        only = ", ".join(board.san(r) for r in replies[:3])
        return [f"after {san} {side} cannot take anything: the replies are {only}"]
    return []


# «после Nxe5 чёрные обязаны ответить dxe5» (prod 29.10, trap-legal): 5...Be6 holds about as well (+2.9 against
# +2.6 at depth 24), so dxe5 is the best reply, not a forced one; «Qxd5+. Король вынужден уйти с e6» (prod 29.10,
# mate2-no) where Qxd5 takes the queen back. The rules above judge forcedness only when the claim cannot be true at
# all; whether a reply that is legal is also forced is the engine's word. The claim is found here — the board it is
# about, the reply it names or the kind of reply (a king move, a capture) — and judged in the async engine stage
# (src/hypothetical.verify_forced_reply; src/server.py, text and voice).
_FORCED_WORDS = (r"обязан\w*|вынужден\w*|приходится|придётся|придется|(?:has|have|had)\s+to|must|"
                 r"(?:is|are|was|were)\s+forced\s+to")
# «должны ответить» is «should» as often as «must»: the best reply is claimed, not the only one.
_SHOULD_WORDS = r"должн\w*|должен"
_REPLY_VERBS = (r"ответить|отвечать|сыграть|играть|пойти|идти|взять|бить|побить|забрать|брать|съесть|отступить|уйти|"
                r"отойти|закрыться|перекрыться|reply|answer|play|take|capture|recapture|retreat|block")
_FORCED_MOVE = re.compile(
    _W + r"(?P<word>" + _FORCED_WORDS + "|" + _SHOULD_WORDS + r")\s+(?:[а-яёa-z]+\s+){0,2}?(?:" + _REPLY_VERBS + r")"
    # «ответить dxe5», «взять: Kxh7», «ответить ходом 5...dxe5», «взять пешкой dxe5»
    r"(?:\s*:\s*|\s+(?:(?:сразу|только|ходом|пешкой|кон[её]м|слоном|ладь[её]й|ферз[её]м|корол[её]м|на\s+это|with|by)(?:\s*:\s*|\s+)){0,2})"
    r"[*_«\"]*(?:\d{1,3}\s?\.{1,3}\s?)?(?=[kqrbnкрфлс]?[a-h]?[1-8]?[x:×]?[a-h][1-8]|o-o)", re.IGNORECASE)
_ONLY_WORDS = (r"единственн\w+\s+(?:законн\w+\s+)?(?:ход|ответ|защита|спасение)|"
               r"(?:только|ровно|всего|лишь)\s+один\s+(?:законн\w+\s+)?(?:ход|ответ)|другого\s+(?:хода\s+|ответа\s+)?нет|"
               r"нет\s+(?:другого\s+)?выбора|the\s+only\s+(?:move|reply|defen[cs]e)|only\s+move|no\s+(?:other\s+)?choice")
# «единственный ход — Kd6», «нет выбора: dxe5»; «dxe5 — единственный ход», «Kxb3! — единственный ход».
_ONLY_THEN_MOVE = re.compile(_W + r"(?:" + _ONLY_WORDS + r")" + _E + r"\s*(?:[—–:-]|это|is)?\s*[*_«\"]*(?:\d{1,3}\s?\.{1,3}\s?)?"
                             r"(?=[kqrbnкрфлс]?[a-h]?[1-8]?[x:×]?[a-h][1-8]|o-o)", re.IGNORECASE)
_MOVE_THEN_ONLY = re.compile(r"(?<![a-zа-я0-9])(?P<mv>(?:[kqrbnкрфлс][a-h]?[1-8]?[x:×]?[a-h][1-8]|[a-h][x:×][a-h][1-8]|o-o(?:-o)?)[+#]?)"
                             r"[!?*_»\"]*\s*(?:[—–:-]|это|is)\s*(?:здесь\s+|тут\s+|here\s+)?(?:" + _ONLY_WORDS + r")" + _E,
                             re.IGNORECASE)
# The piece the claim is about, right before it: «пешка g7 обязана взять», «конь с c6 обязан взять ферзя».
_SUBJECT = re.compile(_W + r"(?P<p>пешка|конь|слон|ладья|ферзь|король|pawn|knight|bishop|rook|queen|king)"
                      r"(?:\s+(?:с|на|from|on))?(?:\s+(?P<sq>[a-h][1-8]))?\s*$", re.IGNORECASE)
_SUBJECT_TYPES = {"пеш": chess.PAWN, "кон": chess.KNIGHT, "сло": chess.BISHOP, "лад": chess.ROOK, "фер": chess.QUEEN,
                  "кор": chess.KING, "paw": chess.PAWN, "kni": chess.KNIGHT, "bis": chess.BISHOP, "roo": chess.ROOK,
                  "que": chess.QUEEN, "kin": chess.KING}
# The claim is someone else's or not made: «ты думаешь, что чёрные обязаны…», «если бы чёрные были вынуждены…».
_NOT_A_CLAIM = re.compile(_W + r"(?:бы|думаешь|думал\w*|считаешь|кажется|казалось|пишешь|говоришь|спрашиваешь|думают|"
                          r"think|thought|seems?|you\s+say|wonder)" + _E, re.IGNORECASE)
# …or the sentence disowns it, wherever it stands: «Неверно, что сейчас белые обязаны сыграть Qe3», «Это не значит,
# что ферзь обязан отступить», «Многие считают, что…», «…dxe5 — это заблуждение», "it is not true that…" (review
# 30.10: each of these states the truth the engine would state, and was cut). A sentence that reports or denies a
# claim is the coach correcting it, not making it.
_DISOWNED = re.compile(
    _W + r"(?:неверн\w*|неправд\w*|ошибочн\w*|заблужд\w*|миф\w*|вовсе\s+не|не\s+значит|не\s+означает|не\s+совсем|"
    r"не\s+обязательно|не\s+факт|(?:сказать|говорить|утвержда\w+|счита\w+|дума\w+|пиш\w+|писать|говорят|верят|"
    r"полага\w+|увер\w+|принято)\s*,?\s*(?:что|будто)|not\s+true|untrue|myths?|misconception\w*|wrong\s+to|"
    r"mistake\s+to|(?:does\s+not|doesn'?t|do\s+not|don'?t)\s+mean|not\s+necessarily|(?:say|says|said|think|thinks|"
    r"believe|believes|claim|claims|written)\s+that)" + _E, re.IGNORECASE)
# Replies listed as a choice — «dxe5 или Be6», «Qe3 или Qa4 — выбирай любой», "Qe3 or Qa4": what is claimed is a
# set of replies or the kind of move, not one forced reply (review 30.10: «придётся отступить: Qe3 или Qa4» was cut
# with Qa4 «about as good»).
_OR_MOVE = r"(?:[kqrbnкрфлс]?[a-h]?[1-8]?[x:×]?[a-h][1-8]|o-o(?:-o)?)"
# «dxe5 или Be6», «Qe3, Qa4 или Qc4» after the named reply (a comma alone may go on with the line: «Kxf7, Ng5+»).
_OR_NEXT = re.compile(r"(?:[+#]?[!?*_»\"]*\s*,\s*[*_«\"]*" + _OR_MOVE + r")*[+#]?[!?*_»\"]*\s*(?:или|либо|or|/)\s*[*_«\"]*"
                      r"(?:\d{1,3}\s?\.{1,3}\s?)?(?=" + _OR_MOVE + ")", re.IGNORECASE)
_OR_BEFORE = re.compile(_OR_MOVE + r"[+#]?[!?*_»\"]*\s*(?:или|либо|or|/)\s*[*_«\"]*$", re.IGNORECASE)
# A move away is the claim («ферзю придётся отступить: Qe3», «король вынужден уйти: Ke7»): the move written after
# it is an example — every move of that piece is the reply claimed.
_AWAY_VERBS = re.compile(_W + r"(?:отступить|уйти|отойти|уходить|отходить|убежать|убегать|бежать|retreat|move\s+away|"
                         r"step\s+away|run)" + _E, re.IGNORECASE)
# «ты обязан», «вам придётся», "you must": the student's side (the side to move when unknown), whatever side the
# clause before named («после Ke5 белые играют a6, и ты обязан идти Kd6» is about Black; review 30.10).
_YOU = re.compile(_W + r"(?:ты|вы|тебе|вам|тебя|вас|you)" + _E, re.IGNORECASE)
# «уйти с e8», «отступить с d4»: the square the piece leaves — the side to move must have it there.
_FROM_SQUARE = re.compile(r"\s*(?:[а-яёa-z]+\s+){0,2}?(?:с|from|off)\s+(?P<sq>[a-h][1-8])(?![0-9])", re.IGNORECASE)
# «белые играют a6», «чёрные отвечают h6»: a pawn move told with a verb is a move of the line, not a square.
_PLAY_VERB = re.compile(_W + r"(?:игра\w*|сыгра\w*|отвеча\w*|ответ\w*|ход\w*|пойд\w*|plays?|played|replies|answers)"
                        r"\s*:?\s*$", re.IGNORECASE)


# The reply written right after the claim: SAN, or a bare pawn move — after «обязаны ответить» «h6» is a move.
_REPLY_TOKEN = re.compile(_WRITTEN_MOVE.pattern + r"|(?<![a-zа-я0-9])[a-h][1-8](?:=?[qrbn])?[+#]?(?![a-zа-я0-9])", re.IGNORECASE)


def _reply_named(board: chess.Board, token: str) -> Optional[chess.Move]:
    """The legal move of *board* the written *token* names («dxe5», «Кd6», «5...dxe5»); None when none or two do."""
    want = _norm_san(token)
    found = [mv for mv in board.legal_moves if _norm_san(board.san(mv)) == want]
    return found[0] if len(found) == 1 else None  # «bxc5»: the b-pawn and a bishop may both take


def _line_tokens(text: str, upto: int) -> tuple:
    """(the moves written before *upto* in *text* as SAN, whether the line opens with move 1)."""
    from src.answer_check import _MOVE, _to_san

    converted, _ = _to_san(text[:upto])
    toks, last_end = [], -1
    for m in _MOVE.finditer(converted):
        san = m["san"]
        follows = last_end >= 0 and re.fullmatch(r"[\s,]*", converted[last_end:m.start()]) is not None
        told = bool(toks) and _PLAY_VERB.search(converted[max(0, m.start() - 30):m.start()]) is not None
        if not (m["num"] or m["bdots"] or san[0] in "KQRBNO" or "x" in san or follows or told):
            continue  # «e4» without a number is a square
        toks.append(san + (m["check"] or ""))
        last_end = m.end()
    first = _MOVE.search(converted)
    from_one = bool(first and re.match(r"\s*1\s?\.", converted[first.start():]))
    return toks, from_one


def _play(root: chess.Board, toks: list):
    """(board, SAN of the last move) after *toks* played from *root*; None when one of them is not legal."""
    b, last = root.copy(stack=False), ""
    try:
        for tok in toks:
            mv = b.parse_san(tok)
            last = b.san(mv)
            b.push(mv)
    except ValueError:
        return None
    return b, last


def _line_scene(text: str, upto: int, ctx):
    """(board, SAN of its last move) after the moves written before *upto* in *text*, played as one line from a
    position given to the turn (the board on the screen first) — the start position only when it is the board, or
    the line opens with move 1. («после Nxe5 …» is the student's own idea, quoted: the other checks pass over it,
    here it is the line.) (None, "") when no such line holds; (False, "") when no move is written there."""
    toks, from_one = _line_tokens(text, upto)
    if not toks:
        return False, ""
    current = ctx.current
    roots = [current] + [b for b in getattr(ctx, "boards", []) if b is not current and ctx.is_given(b)]
    for root in roots:
        if root.board_fen() == chess.STARTING_BOARD_FEN and current.board_fen() != chess.STARTING_BOARD_FEN and not from_one:
            continue
        played = _play(root, toks)
        if played:
            return played
    return None, ""


def line_end(text: str, ctx):
    """(board, last move) at the end of the line *text* writes, as _line_scene reads it; None when it writes none."""
    board, last = _line_scene(text, len(text), ctx)
    return (board, last) if board else None


def _clause(lowered: str, at: int) -> str:
    """The clause of the claim at *at*: from the last comma, dash or «и / а / но» before it, and 25 characters on."""
    return re.split(r"[,;:—–]|\sи\s|\sа\s|\sно\s", lowered[max(0, at - 30): at])[-1] + lowered[at: at + 25]


def _readings(text: str, lowered: str, at: int, upto: int, named_at, ctx) -> tuple:
    """The boards the claim may be about: ([(board, after)] that may condemn it, [(board, after)] that only clear it).

    The moves written before the claim are a line from a position given to the turn — or, as often, the next
    moves of the line the sentences before built («Первый ход — Bxb5+. … axb5. Дальше Nc7+ — чёрные обязаны
    ответить Rxc7», prod programme 23.10: Nc7+ is legal on the screen board too, where Kd7 is the better reply;
    in the line Rxc7 is the only one; review 30.10). A line of the answer is a derived board, which never
    condemns by itself — it only clears: the claim is wrong when it is wrong in every reading."""
    board, after = _line_scene(text, upto, ctx)
    prev = getattr(ctx, "scene_before", None)
    # The lines the sentences before ended with: the scene, and the line read with the student's quoted moves.
    ends = [p[0] for p in (prev, getattr(ctx, "forced_line", None)) if p and p[2] <= 3]
    condemn, clear = [], []
    if board is not False:
        if board is not None:
            condemn.append((board, after))
        toks, _ = _line_tokens(text, upto)
        for end in ends:
            played = _play(end, toks)
            if played:
                clear.append(played)
        return condemn, clear
    # No move written before the claim: the board as it is («сейчас»), a move of it named first («Kxb3! —
    # единственный ход»), or the scene of the sentence before («Rxh6+. Король обязан отойти…») — one move from
    # the board on the screen; a longer line there only clears. «Здесь» after a move told in the sentence before
    # may mean either board (review 30.10: «Rh8+. Здесь король вынужден уйти с e8» was judged with White to move).
    student = getattr(ctx, "student_color", None)
    if _NOW.search(lowered[:upto]) or (_YOU.search(_clause(lowered, at)) and student in (None, ctx.current.turn)):
        condemn.append((ctx.current, ""))  # «а ты обязан ответить dxe5»: the student's move now
    elif named_at and _reply_named(ctx.current, named_at[1]) is not None and named_at[3] == named_at[0]:
        condemn.append((ctx.current, ""))
    if prev and prev[2] <= 2:
        b = ctx.current.copy(stack=False)
        try:
            b.push_san(prev[1])
        except ValueError:
            b = None
        if b is not None and b.board_fen() == prev[0].board_fen() and b.turn == prev[0].turn:
            condemn.append((b, prev[1]))
        else:
            clear.append((prev[0], prev[1]))
    line = getattr(ctx, "forced_line", None)
    if line and line[2] <= 2:
        clear.append((line[0], line[1]))
    return condemn, clear


def _claim_on(board, after: str, lowered: str, at: int, named_at, kind_m, ctx, anchored: bool) -> Optional[dict]:
    """The claim read on *board* (None when it cannot be about it). *anchored*: a move written before the claim
    leads there (a line, the scene of the sentence before), not the board as it is."""
    if board is None or board.is_game_over() or not board.is_valid():
        return None
    # The side named in the claim's own clause, else the last one named before it («у чёрных … — конь обязан
    # взять»): a board where the other side moves is another moment of the line. «ты / вы» is the student.
    clause = _clause(lowered, at)
    named_side = _named_side(clause)
    if named_side is None and _YOU.search(clause):
        student = getattr(ctx, "student_color", None)
        named_side = student if student is not None else board.turn
    if named_side is None:
        sides = re.findall(_W + r"(бел\w*|ч[её]рн\w*|white|black)" + _E, lowered[max(0, at - 60): at])
        named_side = _named_side(sides[-1]) if sides else None
    if named_side is not None and named_side != board.turn:
        return None
    # The piece the claim is about («слон обязан взять ладью» on a board where that side has no bishop is a claim
    # about the move just written — Сxa2 — not about the next one).
    subj = _SUBJECT.search(lowered[max(0, at - 30): at]) if (named_at or kind_m.re is _FORCED_TAKE) else None
    ptype = _SUBJECT_TYPES[subj["p"].lower()[:3]] if subj else None
    origin = chess.parse_square(subj["sq"]) if subj and subj["sq"] else None
    if ptype is not None and not any(board.piece_type_at(mv.from_square) == ptype and origin in (None, mv.from_square)
                                     for mv in board.legal_moves):
        return None
    if named_at:
        move = _reply_named(board, named_at[1])
        if move is None or (ptype is not None and board.piece_type_at(move.from_square) != ptype):
            return None
        verb = lowered[at:named_at[3]]
        if _AWAY_VERBS.search(verb):
            # «придётся отступить: Qe3» claims that the queen must move; Qe3 is one way.
            piece = board.piece_type_at(move.from_square)
            moves = [mv for mv in board.legal_moves if mv.from_square == move.from_square]
            return {"board": board.copy(stack=False), "after": after, "moves": moves, "named": None,
                    "kind": f"a {chess.piece_name(piece)} move", "strict": named_at[2]}
        return {"board": board.copy(stack=False), "after": after, "moves": [move], "named": board.san(move),
                "strict": named_at[2]}
    is_king = kind_m.re is _FORCED_KING
    if is_king:
        square = _FROM_SQUARE.match(lowered, kind_m.end())
        king = board.king(board.turn)
        if square and king != chess.parse_square(square["sq"]):
            return None  # «уйти с e8»: that king is not the side to move's
        if not anchored and not board.is_check():
            return None  # «король вынужден уйти» of a king not in check: a moment told before, not this board
    moves = [mv for mv in board.legal_moves
             if (board.piece_type_at(mv.from_square) == chess.KING if is_king else
                 board.is_capture(mv) and (ptype is None or board.piece_type_at(mv.from_square) == ptype)
                 and origin in (None, mv.from_square))]
    if not moves:
        return None  # the rules' own check says so (_forced_reply_issues)
    strict = not re.search(r"должн|должен", kind_m.group(0))
    return {"board": board.copy(stack=False), "after": after, "moves": moves, "named": None,
            "kind": "a king move" if is_king else "a capture", "strict": strict}


def forced_reply_claim(text: str, ctx) -> Optional[dict]:
    """A claim that a reply is forced («обязаны ответить dxe5», «король вынужден уйти», «единственный ход — Kd6»)
    for the engine to judge: {board, after (the move it follows), moves (the replies claimed), named (the SAN, or
    None for a kind of reply), strict (forced, not merely best), also (the same claim on the other boards the
    sentence may be about, see _readings)}; None when there is none or its board is unsure.
    *text*: the sentence as check_sentence reads it (ё → е, files in Latin letters)."""
    if getattr(ctx, "current", None) is None or not text or text.rstrip().endswith("?"):
        return None  # a question claims nothing («почему ферзь обязан был встать на c1?»)
    lowered = text.lower()
    if _DISOWNED.search(lowered):
        return None
    named_at = None  # (claim position, token, strict, token position)
    for m in _FORCED_MOVE.finditer(lowered):
        tok = _REPLY_TOKEN.match(lowered, m.end())
        if tok and not _negated_before(lowered, m.start()):
            named_at = (m.start(), tok.group(0), not m.group("word").startswith("долж"), tok.start(), tok.end())
            break
    if named_at is None:
        m = _ONLY_THEN_MOVE.search(lowered)
        tok = _REPLY_TOKEN.match(lowered, m.end()) if m else None
        if tok and not _negated_before(lowered, m.start()):
            named_at = (m.start(), tok.group(0), True, tok.start(), tok.end())
    if named_at is None:
        m = _MOVE_THEN_ONLY.search(lowered)
        if m and not _negated_before(lowered, m.end("mv") + 4):
            named_at = (m.start(), m.group("mv"), True, m.start(), m.end("mv"))
    if named_at and (_OR_NEXT.match(lowered, named_at[4]) or _OR_BEFORE.search(lowered[:named_at[3]])):
        return None  # a choice of replies, not a forced one
    kind_m = None
    if named_at is None:
        kind_m = _FORCED_KING.search(lowered) or _FORCED_TAKE.search(lowered)
        if kind_m is None or _negated_before(lowered, kind_m.start()):
            return None
    at = named_at[0] if named_at else kind_m.start()
    if _NOT_A_CLAIM.search(lowered[:at + 40]):
        return None
    if _GENERAL.search(lowered) and not _NOW.search(lowered) and not re.search(r"(?<![а-яё])после(?![а-яё])|\bafter\b", lowered):
        return None  # a rule in general («обычно приходится брать…»), as _forced_reply_issues reads it
    # The board the claim is about: before the named move when it stands first («Kxb3! — единственный ход»),
    # else after the moves written before the claim — see _readings.
    upto = named_at[3] if named_at else at
    condemn, clear = _readings(text, lowered, at, upto, named_at, ctx)
    claims, also = [], []
    for i, (board, after) in enumerate(condemn + clear):
        if board is ctx.current:
            after = ""
        claim = _claim_on(board, after, lowered, at, named_at, kind_m, ctx, anchored=bool(after))
        if claim is None or any(c["board"].fen() == claim["board"].fen() for c in claims + also):
            continue
        (claims if i < len(condemn) else also).append(claim)
    if not claims:
        return None
    claim = claims[0]
    claim["also"] = claims[1:] + also
    return claim


# «При длинной проверяй d1, c1, b1» (production 08.10): the king goes e1–d1–c1; b1 only has to be empty — the
# rook passes it, and it may be attacked.
_LONG_CASTLE = re.compile(_W + r"(?:длинн\w*|ферзев\w*|o-o-o|0-0-0|long|queen-?side)" + _E, re.IGNORECASE)


def _castling_b1_issues(text: str) -> list[str]:
    if not _LONG_CASTLE.search(text) or not re.search(r"(?<![a-z0-9])b[18](?![0-9])", text):
        return []
    if re.search(r"пуст|свобод|не\s+важн|может\s+быть\s+под|empty|free|may\s+be\s+attacked|doesn'?t\s+matter", text):
        return []
    listed = re.search(r"(?<![a-z0-9])[d][18][^.;]{0,12}(?<![a-z0-9])c[18][^.;]{0,12}(?<![a-z0-9])b[18](?![0-9])", text)
    attacked = re.search(r"(?<![a-z0-9])b[18](?![0-9])[^.;]{0,40}(?:под\s+бо|под\s+удар|атаков|бит\w*|attacked|under\s+attack)"
                         r"|(?:под\s+бо|под\s+удар|атаков|бит\w*|attacked)[^.;]{0,40}(?<![a-z0-9])b[18](?![0-9])", text)
    if listed or attacked:
        return ["for long castling the king passes d1 and lands on c1 (d8, c8 for Black): only those and the king's "
                "own square must be safe; b1 (b8) must just be empty — it may be attacked"]
    return []


# «если позиция повторилась трижды — ничья объявляется автоматически» (production 08.10): threefold repetition and
# the 50-move rule give a draw when a player claims it; only fivefold repetition and 75 moves end the game by themselves.
def _automatic_draw_issues(text: str) -> list[str]:
    if not re.search(r"автоматич\w*|сама\s+собой|сам\s+собой|automatic\w*|by\s+itself", text):
        return []
    if re.search(r"пят\w*\s*крат|пять\s+раз|fivefold|five\s+times|75|семьдесят\s+пят", text):
        return []
    if re.search(r"трижды|тр[её]х?кратн\w*|три\s+раза|threefold|three\s+times|50\s+ход|пятидесят|50[- ]move|fifty", text):
        return ["a threefold repetition or 50 moves without a capture or a pawn move give a draw only when a player "
                "claims it; the game ends by itself only after a fivefold repetition or 75 such moves"]
    return []


# «Если слон c4 уйдёт на a6, рокировка станет доступна» (production 08.10) with the bishop still hitting f1 from a6:
# the piece is moved on the board as said and castling judged there.
_CASTLE_AFTER = re.compile(
    _W + r"(?:если|когда|после\s+того\s+как)\s+(?:[а-яё]+\s+){0,2}?(?P<piece>слон|конь|ладья|ферзь|пешка)\s+"
    r"(?:с\s+)?(?P<frm>[a-h][1-8])?\s*(?:[а-яё-]+\s+){0,2}?(?:уйд[её]т|уйдет|отойд[её]т|отойдет|уходит|отходит|пойд[её]т|"
    r"переместится|встанет)\s+на\s+(?P<to>[a-h][1-8])"
    r"[^.;]{0,60}?рок[иеі]р\w*\s+(?:станет|будет|окажется|снова\s+будет)\s+(?:доступн|возможн|разреш|можно|легальн)",
    re.IGNORECASE)


def _castle_after_issues(text: str, ctx) -> list[str]:
    board = getattr(ctx, "current", None)
    m = _CASTLE_AFTER.search(text)
    if board is None or m is None:
        return []
    ptype = {"слон": chess.BISHOP, "конь": chess.KNIGHT, "ладья": chess.ROOK, "ферзь": chess.QUEEN, "пешка": chess.PAWN}[m["piece"].lower()]
    to = chess.parse_square(m["to"])
    froms = [chess.parse_square(m["frm"])] if m["frm"] else [sq for sq in board.pieces(ptype, chess.WHITE) | board.pieces(ptype, chess.BLACK)]
    student = ctx.student_color if getattr(ctx, "student_color", None) is not None else board.turn
    wing = "O-O-O" if _LONG_CASTLE.search(text) else "O-O"
    for frm in froms:
        pc = board.piece_at(frm)
        if pc is None or pc.piece_type != ptype or pc.color == student:
            continue
        b = board.copy(stack=False)
        b.remove_piece_at(frm)
        b.set_piece_at(to, pc)
        legal, why = castling_status(b, student).get(wing, (True, ""))
        if not legal:
            return [f"even with the {chess.piece_name(ptype)} on {chess.square_name(to)} {wing} stays impossible: {why}"]
        return []
    return []


# ── Castling after a move, and where a chased piece retreats (prod 09.10, 29.10) ──────────────────────────

# What a piece is worth when it is taken: a capture by something cheaper, or of an undefended piece, loses it.
_WORTH = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


def _taken_on(board: chess.Board, sq: int) -> Optional[str]:
    """The capture (SAN) that simply wins the piece on *sq*: by a cheaper piece, or of a piece nothing defends."""
    pc = board.piece_at(sq)
    if pc is None or pc.piece_type == chess.KING:
        return None
    b = board.copy(stack=False)
    b.turn = not pc.color
    b.ep_square = None
    caps = [m for m in b.legal_moves if m.to_square == sq]
    if not caps:
        return None
    cheapest = min(caps, key=lambda m: _WORTH[b.piece_type_at(m.from_square)])
    if _WORTH[b.piece_type_at(cheapest.from_square)] < _WORTH[pc.piece_type] or not board.attackers(pc.color, sq):
        return b.san(cheapest)
    return None


def _path_squares(color: bool, wing: str) -> list:
    rank = 0 if color == chess.WHITE else 7
    files = (4, 5, 6) if wing == "O-O" else (4, 3, 2)
    return [chess.square(f, rank) for f in files]


def _castling_kept_out(after: chess.Board, student: bool, wings: list) -> Optional[str]:
    """After the student's move (*after*, the opponent to move): a reply that keeps every castling of *wings*
    illegal — '' when nothing has to be done (the reason is the student's own pieces, the rights, or a piece the
    move did not touch), the reply in SAN, or None when every reply of the forbidding piece gives castling up."""
    def legal_any(b: chess.Board) -> bool:
        st = castling_status(b, student)
        return any(st[w][0] for w in wings)

    if legal_any(after):
        return None  # castling is there at once: the opponent has to do something about it
    if after.is_check() or after.is_game_over():
        return None
    guards = set()
    for w in wings:
        for sq in _path_squares(student, w):
            guards |= set(after.attackers(not student, sq))
    if not guards:
        return ""  # nothing of the opponent's forbids it — the student's own pieces or rights do
    hit = {g for g in guards if _taken_on(after, g) is not None}
    rest = after.copy(stack=False)
    for g in hit:
        rest.remove_piece_at(g)
    if not legal_any(rest):
        return ""  # what the move does not hit (a piece of the opponent's, the student's own pieces) still forbids it
    for move in after.legal_moves:
        if move.from_square not in hit:
            continue
        b = after.copy(stack=False)
        b.push(move)
        if not legal_any(b) and _taken_on(b, move.to_square) is None and not b.is_check():
            return after.san(move)
    return None


# «Да, после b3 короткая рокировка станет возможна» — the bishop on c4 retreats to a6 and still covers f1 (prod
# 09.10, the same position 29.10). A castling promised after a written move of the student's is judged after the
# opponent's reply: the forbidding piece stays put when the move does not hit it, or steps to a safe square from
# which it still forbids castling.
_CASTLE_WILL = re.compile(
    _W + r"(?:(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]ровк\w*\s+(?:(?!не\s)[а-яё]+\s+){0,2}?"
    r"(?:станет|будет|окажется|сразу\s+будет|уже\s+будет|снова\s+будет)\s+(?:сразу\s+|уже\s+|снова\s+|тебе\s+)?"
    r"(?:возможн|доступн|разреш|легальн)\w*"
    r"|(?:можно\s+будет|сможешь|сможете|успеешь)\s+(?:сразу\s+|уже\s+|спокойно\s+|наконец\s+)?(?:сделать\s+)?"
    r"(?:коротк\w+\s+|длинн\w+\s+)?рок[иеі]р\w*"
    r"|(?:you(?:'ll|\s+will)?\s+be\s+able\s+to|you\s+can\s+then)\s+castle|castling\s+(?:becomes|will\s+be)\s+"
    r"(?:possible|legal|available))" + _E, re.IGNORECASE)
_YES_WILL = re.compile(r"^\W*(?:да|yes|иә)\W+(?:(?!не\s)[а-яё]+\s+){0,2}?(?:станет|будет)\s+(?:сразу\s+|уже\s+)?"
                       r"(?:возможн|доступн|разреш|легальн)\w*" + _E, re.IGNORECASE)
_CASTLE_NOW_AFTER = re.compile(  # «после b3 можно рокироваться» — present tense after the move
    _W + r"(?:можно|можешь|можете)\s+(?:сразу\s+|уже\s+|спокойно\s+)?(?:сделать\s+)?(?:коротк\w+\s+|длинн\w+\s+)?"
    r"рок[иеі]р\w*" + _E, re.IGNORECASE)
# A move written in the lowered sentence, pawn pushes too («b3», «bxc4», «nf3», «кf3», «o-o»).
_MOVE_LOW = re.compile(r"(?<![a-zа-я0-9])(?:[kqrbnкрфлс][a-h]?[1-8]?[x:×]?[a-h][1-8]|[a-h](?:[x:×][a-h])?[1-8](?:=[qrbn])?|"
                       r"o-o(?:-o)?|0-0(?:-0)?)[+#!?]*(?![a-zа-я0-9])", re.IGNORECASE)
_AFTER_MOVE = re.compile(r"(?<![а-яёa-z])(?:после|after|сначала|first)\s+(?:хода\s+|move\s+)?(?:\d{1,3}\s?\.\s?)?"
                         r"(?P<m>" + _MOVE_LOW.pattern + r")", re.IGNORECASE)
# Something between the move and the claim that makes it a condition on the reply: «после b3, если чёрные
# ответят Be6, рокировка станет возможна» is true; it is the reply that decides, and it is named.
_ON_REPLY = re.compile(r"(?<![а-яё])(?:если|когда|как\s+только|в\s+случае|при\s+условии|только|уйд|отступ|отойд|"
                       r"ответ|прогон|прогнав|прогнать|убер|уберёшь|разменя|if|when|once|unless|only|retreat|answer)",
                       re.IGNORECASE)

# The claim names a later condition or a further step itself (review 30.10): «…, но сначала нужно вывести слона»,
# «лишь тогда, когда слон уйдёт», «после того, как уберёшь слона», «через пару ходов», «осталось вывести слона» —
# not a promise of castling right after the move; nor «после Nf3 и вывода слона …», a plan of several steps.
_LATER = re.compile(r"(?<![а-яёa-z])(?:если|когда|как\s+только|только|лишь|после\s+того|после\s+этого|сначала|прежде|"
                    r"перед\s+этим|через\s+(?:[а-яё]+\s+)?(?:ход|хода|ходов|пару|несколько)|осталось|останется|"
                    r"(?:нужно|надо)\s+(?:ещ[её]\s+|сначала\s+|будет\s+)|потом|позже|затем|в\s+будущем|"
                    r"if|when|once|only|after|first|later|eventually)(?![а-яёa-z])", re.IGNORECASE)
_STEP = re.compile(r"(?<![а-яёa-z])(?:и|а\s+также|плюс|затем|потом|and|then)\s+"
                   r"(?!(?:ты|вы|тогда|уже|сразу|you|then)(?![а-яёa-z]))[а-яёa-z]", re.IGNORECASE)
# Whose castling the claim is about, when it names a side: «у черных рокировка станет возможна» after the
# student's Bxe5 is the opponent's castling (review 30.10: it was judged for the student's king).
_CASTLE_SIDE = re.compile(_W + r"(?:(?P<w>бел\w*|white)|(?P<b>ч[её]рн\w*|black)|(?P<o>соперник\w*|противник\w*|opponent\w*))"
                          + _E, re.IGNORECASE)


def _parse_lowered(board: chess.Board, written: str) -> Optional[chess.Move]:
    """A move written in the lowered sentence («b3», «bxc4», «nf3», «кf3») on *board*: «bc4» may be the bishop."""
    s = _norm_san(written).replace("0-0-0", "o-o-o").replace("0-0", "o-o").replace("o-o-o", "O-O-O").replace("o-o", "O-O")
    pawn = bool(re.fullmatch(r"[a-h](?:x[a-h])?[1-8](?:=[qrbn])?[+#!?]*", s))  # «b3», «bxc4» — a pawn first
    for cand in ([s.upper() if s[:1] == "o" else s] if pawn or s[0] not in "kqrbn" else []) + \
            ([s[0].upper() + s[1:]] if s[0] in "kqrbn" and not s.startswith("o") else []):
        try:
            return board.parse_san(cand)
        except ValueError:
            continue
    return None


def _castle_after_move_issues(text: str, ctx) -> list[str]:
    board = getattr(ctx, "current", None)
    if board is None or not re.search(_CASTLE_WORD, text + " " + (getattr(ctx, "question", "") or ""), re.IGNORECASE):
        return []
    student = ctx.student_color if getattr(ctx, "student_color", None) is not None else board.turn
    if board.turn != student:
        return []
    claim = _CASTLE_WILL.search(text)
    if claim is None and re.search(_CASTLE_WORD, getattr(ctx, "question", "") or "", re.IGNORECASE):
        claim = _YES_WILL.search(text)  # «А если сначала b3, потом рокировка будет?» — «Да, станет возможна.»
    move_txt = None
    if claim is not None:
        moves = [m for m in _AFTER_MOVE.finditer(text[:claim.start()])]
        if moves:
            move_txt = moves[-1]["m"]
            between = text[moves[-1].end():claim.start()]
            if _MOVE_LOW.search(between) or _ON_REPLY.search(between) or _STEP.search(between):
                return []  # a line of moves, the reply or another step named: not this claim
        elif text.lstrip(" *_«\"").lower().startswith(("да", "yes", "иә")):
            # «А если сначала сыграть b3, потом рокировка будет?» — «Да, после этого рокировка станет возможна».
            qm = [m.group(0) for m in _MOVE_LOW.finditer(getattr(ctx, "question", "") or "")]
            move_txt = qm[-1] if len(qm) == 1 else None
    else:
        now = _CASTLE_NOW_AFTER.search(text)
        moves = [m for m in _AFTER_MOVE.finditer(text[:now.start()])] if now else []
        if now is None or not moves or not text[:moves[-1].start()].strip(" *_—–-").lower() in ("", "да", "да,", "yes", "yes,"):
            return []  # present tense only right after «после b3»: «после b3 можно рокироваться»
        claim, move_txt = now, moves[-1]["m"]
        between = text[moves[-1].end():claim.start()]
        if _MOVE_LOW.search(between) or _ON_REPLY.search(between) or _STEP.search(between):
            return []
    if not move_txt or _negated_before(text, claim.start()):
        return []
    if _LATER.search(text[claim.end():]):
        return []  # «…станет возможна, когда слон уйдёт», «…, но сначала убери слона» — the condition is named
    move = _parse_lowered(board, move_txt)
    if move is None or board.is_castling(move):
        return []
    wing = _wing(text) or _wing(getattr(ctx, "question", "") or "")
    wings = [wing] if wing else ["O-O", "O-O-O"]
    after = board.copy(stack=False)
    san = board.san(move)
    after.push(move)
    named = {("w" if s["w"] else "b" if s["b"] else "o") for s in _CASTLE_SIDE.finditer(text[max(0, claim.start() - 30):claim.end()])}
    if len(named) > 1:
        return []
    if named:
        owner = {"w": chess.WHITE, "b": chess.BLACK, "o": not student}[named.pop()]
        if owner != student:
            # The opponent's castling after the student's move: it is theirs to play at once, or the claim is false.
            st = castling_status(after, owner)
            if any(st[w][0] for w in wings):
                return []
            why = "; ".join(f"{w}: {st[w][1]}" for w in wings if st[w][1])
            other = "White" if owner == chess.WHITE else "Black"
            return [f"after {san} {other} still cannot castle ({' or '.join(wings)}) — {why}"]
    reply = _castling_kept_out(after, student, wings)
    if reply is None:
        return []
    side = "White" if student == chess.WHITE else "Black"
    names = " or ".join(wings)
    if reply == "":
        st = castling_status(after, student)
        why = "; ".join(f"{w}: {st[w][1]}" for w in wings if st[w][1])
        return [f"after {san} {side} still cannot castle ({names}) — {why}; the move does not change that"]
    b = after.copy(stack=False)
    b.push(after.parse_san(reply))
    st = castling_status(b, student)
    why = "; ".join(f"{w}: {st[w][1]}" for w in wings if st[w][1])
    return [f"after {san} the opponent answers {reply} and {side} still cannot castle ({names}) — {why}; "
            f"castling after {san} depends on the reply, it is not guaranteed"]


# «Прогнать слона не выйдет — он отступит на a6, b5, d3 или e2 и всё равно будет бить f1» (prod 29.10, four answers
# on r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w): on b5, d3 and e2 the bishop is simply taken (Nxb5,
# cxd3, Nxe2). The squares a chased piece is said to retreat to are checked: a square where it is lost is no retreat.
_RETREAT_PIECE = {"слон": chess.BISHOP, "кон": chess.KNIGHT, "лад": chess.ROOK, "ферз": chess.QUEEN,
                  "піл": chess.BISHOP, "тура": chess.ROOK, "уәзір": chess.QUEEN,
                  "bishop": chess.BISHOP, "knight": chess.KNIGHT, "rook": chess.ROOK, "queen": chess.QUEEN}
_RETREAT_NOUN = re.compile(_W + r"(?P<n>слон\w*|кон[ьяюеё]\w*|ладь\w*|ферз\w*|піл\w*|тура\w*|уәзір\w*|bishop|knight|rook|queen)" + _E,
                           re.IGNORECASE)
_SQ_LIST = r"[a-h][1-8](?:\s*(?:,|или|либо|и|or|and|,\s*or)\s*[a-h][1-8])*"
# A retreat verb says it by itself; «уйдёт», «уходит» only when the piece is chased in the sentence («прогнать слона
# мало — он уйдёт на…»): «после Qa5 конь уходит на b7» is a move of a line, not a retreat from an attack.
_GO_AWAY = r"уйд[её]т|уйдя|уйти|уходит|спрячется|спрятаться|убежит|убежать"
_CHASED = re.compile(r"прогна|прогон|отогна|отгоня|выгна|гонишь|гнать|нападаешь|нападает\s+на|атакуешь|вынужден|"
                     r"chase|kick|қуып|қуу", re.IGNORECASE)
_RETREAT = re.compile(
    _W + r"(?:отступ(?:ит|ят|ив|ая|ать|ает|ить)|отойд[её]т|отойдя|отойти|отходит|(?P<go>" + _GO_AWAY + r"))"
    r"\s+(?:(?!не\s)[а-яё]+\s+){0,2}?на\s+(?:пол[яе]\s+)?(?P<sqs>" + _SQ_LIST + r")(?![0-9])"
    r"|(?P<kk>" + _SQ_LIST + r")\s*-?\s*(?:ге|ке|қа|ға)\s+(?:шегін\w*|қаш\w*|кет\w*)"
    r"|\bretreat(?:s|ing)?\s+to\s+(?P<en>" + _SQ_LIST + r")\b", re.IGNORECASE)
# The sentence says the piece is lost there itself: «на b5 его заберёт конь», "Nxb5 wins it".
_LOSS_WORDS = re.compile(r"возьм|взят|забер|забира|съе[сдл]|выигр|потер|теря|зевн|подстав|отда[её]|погиб|ловушк|попад[её]т|"
                         r"(?:окаж|оказ|встан|встаёт|попад|будет)\w*\s+под\s+(?:бой|бо[ея]м|удар\w*|взятие)|без\s+защит|незащищ|captur|taken|lost|loses|wins\s+it|trapped|hang",
                         re.IGNORECASE)


def _chase_boards(board: chess.Board, frm: int, named: list, asked: list) -> tuple:
    """The boards where the piece on *frm* is chased, its owner to move, and the chasing move (SAN, or ''): after
    the chasing move written in the sentence, else in the question («Ход e5 прогоняет коня», «Что будет, если я
    сыграю e5?»); the board itself when the piece is attacked already; else after each move of the opponent's that
    attacks it — a square is lost only when it is lost after all of them. ([], '') when nothing chases it."""
    owner = board.color_at(frm)
    chaser = board.copy(stack=False)
    chaser.turn = not owner
    chaser.ep_square = None

    def chased(move: chess.Move) -> Optional[chess.Board]:
        b = chaser.copy(stack=False)
        b.push(move)
        return b if b.color_at(frm) == owner and b.is_attacked_by(not owner, frm) and not b.is_check() else None

    for written in (named, asked):
        found = []
        for w in written:
            move = _parse_lowered(chaser, w)
            b = chased(move) if move is not None else None
            if b is not None:
                found.append((b, chaser.san(move)))
        if found:
            return [b for b, _ in found], (found[0][1] if len(found) == 1 else "")
    if board.is_attacked_by(not owner, frm):
        b = board.copy(stack=False)
        b.turn = owner
        b.ep_square = None
        return [b], ""
    boards = [b for b in (chased(mv) for mv in chaser.legal_moves) if b is not None]
    return boards, ""


def _retreat_square_issues(text: str, ctx) -> list[str]:
    board = getattr(ctx, "current", None)
    m = _RETREAT.search(text) if board is not None else None
    if m is None or _negated_before(text, m.start()) or _LOSS_WORDS.search(text):
        return []
    if m["go"] and not _CHASED.search(text):
        return []
    clause = re.split(r"[,;:—–]", text[:m.start()])[-1]
    if re.search(r"(?<![а-яё])(?:если|когда|пусть|допустим)(?![а-яё])|\b(?:if|when|suppose)\b", clause):
        return []  # «Если слон c4 уйдёт на d5, рокировка станет доступна» — the move assumed, not offered as a retreat
    sq_txt = m["sqs"] or m["kk"] or m["en"]
    squares = [chess.parse_square(s) for s in re.findall(r"[a-h][1-8]", sq_txt)]
    nouns = list(_RETREAT_NOUN.finditer(text[:m.start()]))
    if not nouns or not squares:
        return []
    word = nouns[-1]["n"].lower()
    ptype = next((t for k, t in _RETREAT_PIECE.items() if word.startswith(k)), None)
    if ptype is None:
        return []
    written = {_norm_san(x.group(0))[-2:] for x in _WRITTEN_MOVE.finditer(text) if re.search(r"[x:×]", x.group(0))}
    if any(chess.square_name(s) in written for s in squares):
        return []  # «…на b5, но там Nxb5»: the capture is in the sentence
    # The piece: the only one of its kind that reaches every square named (a bishop on c4 for a6, b5, d3, e2).
    cands = []
    for sq in board.pieces(ptype, chess.WHITE) | board.pieces(ptype, chess.BLACK):
        color = board.color_at(sq)
        b = board.copy(stack=False)
        b.turn = color
        b.ep_square = None
        if all(chess.Move(sq, t) in b.legal_moves for t in squares):
            cands.append((sq, b))
    if len(cands) != 1:
        return []
    frm = cands[0][0]
    # The retreat is judged where the piece is chased (review 30.10: «Ход e5 прогоняет коня — он отступит на d5»
    # was judged with the pawn still on e4, and the main line of the Alekhine, 2.e5 Nd5, was «lost»).
    span = (m.start(), m.end())
    named = [x.group(0) for x in _MOVE_LOW.finditer(text) if not (span[0] <= x.start() < span[1])]
    chases, chase_san = _chase_boards(board, frm, named, [x.group(0) for x in _MOVE_LOW.finditer(getattr(ctx, "question", "") or "")])
    if not chases:
        return []
    # The chase the sentence means is one after which every square it names is a retreat (prod 29.10, d1-why: after
    # b3 or Nd2 the bishop can go to a6, b5, d3 and e2 and is lost on three of them; after d3 two of the squares are
    # no retreat at all, and judging on every chase at once named only b5). When no chase leaves them all open, every
    # chase is judged as before.
    def opens_all(b: chess.Board) -> bool:
        return all(chess.Move(frm, t) in b.legal_moves and b.piece_at(t) is None for t in squares)

    # With the relation checker off this is not applied either: off is the whole rollback to the checks of 6eb7b972
    # (review 30.10, wiring).
    from src.answer_check_relations import mode as relation_mode

    main = [b for b in chases if opens_all(b)] if relation_mode(ctx) != "off" else []
    if main:
        chases = main
    lost, safe = [], []
    for t in squares:
        caps = []
        for b in chases:
            mv = chess.Move(frm, t)
            if mv not in b.legal_moves or b.piece_at(t) is not None:
                caps.append(None)  # not a retreat there (or a capture): nothing to say
                continue
            after = b.copy(stack=False)
            after.push(mv)
            caps.append(_taken_on(after, t) or "")
        if all(caps):
            lost.append((chess.square_name(t), caps[0]))
        elif all(c == "" for c in caps):
            safe.append(chess.square_name(t))
    if not lost:
        return []
    name = chess.piece_name(ptype)
    return [(f"after {chase_san} " if chase_san else "")
            + f"the {name} on {chess.square_name(frm)} has no retreat to " + ", ".join(s for s, _ in lost)
            + " — there it is simply lost (" + ", ".join(c for _, c in lost) + ")"
            + (f"; {'of the squares named only ' if len(safe) + len(lost) == len(squares) else ''}{', '.join(safe)} "
               f"{'is a real retreat' if len(safe) == 1 else 'are real retreats'}" if safe else "")]


# «На доске ход чёрных» with White to move (production 09.10, a lesson puzzle): the side to move named for the board.
_TURN_CLAIM = re.compile(
    _W + r"(?:(?:сейчас|здесь|тут|на\s+доске|в\s+этой\s+позиции)\s+(?:[а-яё]+\s+)?ход\s+(?:у\s+)?(?P<a>белых|ч[её]рных)"
    r"|ход\s+(?:у\s+)?(?P<b>белых|ч[её]рных)\s+(?:сейчас|здесь|тут|на\s+доске)"
    r"|^\W*ход\s+(?:у\s+)?(?P<c>белых|ч[её]рных)(?=[\s,.!—–:-]))" + _E, re.IGNORECASE)


def _turn_claim_issues(text: str, ctx) -> list[str]:
    board = getattr(ctx, "current", None)
    m = _TURN_CLAIM.search(text)
    if board is None or m is None or getattr(ctx, "scene_trail", None):
        return []  # a move written in this sentence: the turn may be the one after it
    if board.board_fen() == chess.STARTING_BOARD_FEN:
        return []  # no position of the student's: the board may show a line a tool has just put there
    if re.search(r"(?<![а-яё])(?:после|если|когда|тогда|в\s+партии|в\s+примере|в\s+уроке)(?![а-яё])", text[:m.start()]):
        return []
    said = chess.WHITE if (m["a"] or m["b"] or m["c"]).lower().startswith("бел") else chess.BLACK
    if said != board.turn:
        return [f"on the board it is {'White' if board.turn else 'Black'} to move, not {'White' if said else 'Black'}"]
    return []


def _outcome_issues(lowered: str, ctx) -> list[str]:
    """«Нет, не догонит», «пешка проходит», «ничью не удержать» in an ending of ≤ 7 pieces against the tablebase
    (src/endgame_claims.py; prod 29.10, the square: the coach said the pawn queens in a tablebase draw)."""
    from src.endgame_claims import outcome_issues

    return outcome_issues(lowered, ctx)


_EMPHASIS = re.compile(r"\*{1,3}|(?<![a-zа-яё0-9])_{1,2}|_{1,2}(?![a-zа-яё0-9])")


def rules_issues(lowered: str, ctx) -> list[str]:
    """All the claims above in one sentence (*lowered*: lower case, ё → е)."""
    # Markdown emphasis is gone already (answer_check.check_sentence): «нельзя рокироваться, если **ладья** под боем»
    # (09.10 — the bold hid the claim); a caller with the raw sentence gets the same reading.
    lowered = _EMPHASIS.sub("", lowered or "")
    try:
        return (_castling_issues(lowered, ctx) + _result_issues(lowered, ctx) + _mate_state_issues(lowered, ctx)
                + _attacked_by_issues(lowered, ctx)
                + _mate_in_issues(lowered, ctx) + _file_issues(lowered, ctx) + _passed_issues(lowered, ctx)
                + _en_passant_issues(lowered, ctx) + _king_issues(lowered, ctx) + _colour_issues(lowered)
                + _castling_rule_issues(lowered, getattr(ctx, "question", "")) + _cannot_go_issues(lowered, ctx)
                + _forced_reply_issues(lowered, ctx) + _castling_b1_issues(lowered) + _automatic_draw_issues(lowered)
                + _castle_after_issues(lowered, ctx) + _turn_claim_issues(lowered, ctx) + _outcome_issues(lowered, ctx)
                + _castle_after_move_issues(lowered, ctx) + _retreat_square_issues(lowered, ctx)
                + _castle_right_issues(lowered, ctx))
    except Exception:  # noqa: BLE001 — a broken pattern must never block an answer
        return []
