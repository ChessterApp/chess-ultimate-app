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

# The claim is about this board: a now/here word, or an answer that opens with yes/no.
_NOW = re.compile(_W + r"(?:сейчас|здесь|тут|в\s+этой\s+позиции|на\s+доске|уже|now|here|right\s+now|at\s+the\s+moment|"
                  r"in\s+this\s+position|on\s+the\s+board|қазір|осы\s+жерде|бұл\s+позицияда)" + _E)
_YES_NO = re.compile(r"^\W*(?:да|нет|конечно|увы|yes|no|nope|sure|unfortunately|иә|жоқ)" + _E)
# A rule in general, a condition, a future or a hypothetical: not about the board as it is.
_GENERAL = re.compile(_W + r"(?:если|когда|пока|даже|в\s+общем|по\s+правилам|обычно|всегда|никогда|после|"
                      r"if|when|unless|even|in\s+general|always|never|usually|after|once|"
                      r"егер|кезде)" + _E)


def _about_board(text: str) -> bool:
    if _GENERAL.search(text) and not _NOW.search(text):
        return False
    return bool(_NOW.search(text) or _YES_NO.search(text))


def _negated_before(text: str, start: int) -> bool:
    return bool(re.search(r"(?:^|\s)(?:не|ни|not|никак)\s+(?:\w+\s+)?$", text[max(0, start - 18):start]))


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
    question = getattr(ctx, "question", "") or ""
    question_about_castling = bool(re.search(_CASTLE_WORD, question, re.IGNORECASE))
    if _GENERAL.search(question) and not _NOW.search(text):
        return []  # «можно ли рок[иеі]роваться, если ладья под боем?» — a rule, answered in general
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
            or bool(re.match(r"\s*(?:ход\w*\s+)?(?:—\s*)?(?:здесь\s+|тут\s+)?нет", m["after"] or "", re.IGNORECASE))
        before = text[:m.start()]
        if _GENERAL.search(before) and not _NOW.search(text):
            continue
        if _named_side(text) is not None and _named_side(text) != ctx.current.turn:
            continue  # about the side not to move — the engine line is not
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


def rules_issues(lowered: str, ctx) -> list[str]:
    """All the claims above in one sentence (*lowered*: lower case, ё → е)."""
    try:
        return (_castling_issues(lowered, ctx) + _result_issues(lowered, ctx) + _mate_state_issues(lowered, ctx)
                + _mate_in_issues(lowered, ctx) + _file_issues(lowered, ctx) + _passed_issues(lowered, ctx)
                + _en_passant_issues(lowered, ctx) + _king_issues(lowered, ctx) + _colour_issues(lowered))
    except Exception:  # noqa: BLE001 — a broken pattern must never block an answer
        return []
