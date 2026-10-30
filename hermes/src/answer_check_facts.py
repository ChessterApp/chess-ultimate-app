"""Claims the board and the game's record decide exactly (prod check 29.10, from 30.10).

Four classes the answer check (src/answer_check.py) did not read, each caught on the live run of 29.10:

  * advice in words to make a move the piece cannot make — «надо увести ферзя с d8 — например, на c7 или на b6»
    with the c7 pawn on c7 and the d8–b6 diagonal shut by it (the queen's only move was Qxe7);
  * «что под ударом» answered with only a part: «под ударом только X», «больше ничего не висит», «остальное
    защищено» are read against the board's list of pieces that are attacked and not safe
    (src/position_facts.exposed_pieces — the same list the coach's facts give it);
  * a move told as played on this board that was not: «Это … система, где белые пошли 6.Сс4» on the board after
    5...a6, the bishop still on f1;
  * the history of exchanges: «Чёрные вывели ферзя на d5 после размена на e4» after 1.e4 d5 2.exd5 Qxd5 — the
    capture was on d5.

What was played is known from the record that leads to the board: the game, a line the turn has (the board's PGN,
the question's moves), or else the ECO book's lines through the position — only when their length is the
position's own move count. With no record nothing is judged. Plans, conditions, questions, quotes, denials and
other games are never read as claims about this board: a right sentence cut is worse than a wrong one let through.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import chess

from src.answer_check import (SQ, _MOVE, _NAMES, _NEGATION, _NOT_TOLD, _geometry_move, _is_hypothetical,
                              _just_played, _to_san)
from src.claim_scope import FUTURE_VERB

logger = logging.getLogger(__name__)

_B = r"(?<![а-яёa-z])"
_E = r"(?![а-яёa-z])"
_COLOR = {chess.WHITE: "white", chess.BLACK: "black"}
_TYPE_BY_STEM = (("ферз", chess.QUEEN), ("ладь", chess.ROOK), ("слон", chess.BISHOP), ("кон", chess.KNIGHT),
                 ("корол", chess.KING), ("пешк", chess.PAWN), ("queen", chess.QUEEN), ("rook", chess.ROOK),
                 ("bishop", chess.BISHOP), ("knight", chess.KNIGHT), ("king", chess.KING), ("pawn", chess.PAWN))


def _ptype(word: str) -> Optional[int]:
    word = (word or "").lower().replace("ё", "е")
    return next((t for stem, t in _TYPE_BY_STEM if word.startswith(stem)), None)


def _key(board: chess.Board) -> str:
    return board.board_fen() + (" w" if board.turn else " b")


def _ply(board: chess.Board) -> int:
    return (board.fullmove_number - 1) * 2 + (0 if board.turn == chess.WHITE else 1)


def _label(board: chess.Board, san: str) -> str:
    return f"{board.fullmove_number}{'.' if board.turn == chess.WHITE else '...'}{san}"


def _quoted(text: str, at: int) -> bool:
    before = text[:at]
    return before.count("«") > before.count("»") or before.count('"') % 2 == 1 or before.count("“") > before.count("”")


# ── the record: how the game on the board went ────────────────────────────────────────────────────────────────

_BOOK_THROUGH: Optional[dict] = None


def _book_index() -> dict:
    """Position (placement, side, castling, en passant) → every ECO book line through it, as (entry, plies)."""
    global _BOOK_THROUGH
    if _BOOK_THROUGH is None:
        from src.openings_book import _position_key, _split_moves, get_book

        index: dict = {}
        for i, entry in enumerate(get_book().entries):
            board = chess.Board()
            try:
                for n, san in enumerate(_split_moves(entry[2]), 1):
                    board.push_san(san)
                    index.setdefault(_position_key(board), []).append((i, n))
            except ValueError:
                continue
        _BOOK_THROUGH = index
    return _BOOK_THROUGH


def histories(ctx) -> list[tuple[list, bool]]:
    """The known ways the game reached the board: [(steps, complete)], each step (board before, move, SAN);
    *complete* when the record starts at the initial position (no moves before it are unknown). Empty when the
    board's history is not known — then nothing about it is judged."""
    cur = getattr(ctx, "current", None)
    if cur is None:
        return []
    target = _key(cur)
    sources = list(getattr(ctx, "line_records", None) or [])
    if getattr(ctx, "game_moves", None):
        sources.append((chess.Board(), list(ctx.game_moves)))
    if getattr(ctx, "game_moves", None):
        game, keys = chess.Board(), {_key(chess.Board())}
        for san in ctx.game_moves:
            try:
                game.push_san(san)
            except ValueError:
                break
            keys.add(_key(game))
        if target not in keys:
            return []  # a game is on, and the board judged is another (the hidden board of theory): which game is told is not known
    out, seen = [], set()
    for start, sans in sources:
        board = start.copy(stack=False)
        complete = board.board_fen() == chess.STARTING_BOARD_FEN and board.turn == chess.WHITE \
            and board.fullmove_number == 1
        steps: list = []
        found = complete and _key(board) == target
        for san in sans:
            if found:
                break
            try:
                move = board.parse_san(san)
            except ValueError:
                break
            steps.append((board.copy(stack=False), move, board.san(move)))
            board.push(move)
            found = _key(board) == target
        if found:
            sig = (start.fen(), tuple(s[2] for s in steps))
            if sig not in seen:
                seen.add(sig)
                out.append((steps, complete))
    if out:
        return out
    # No game and no line reaches the board: the book's lines through it, when they are the position's own length
    # (a FEN's move counter agrees with them) — the Najdorf after 5...a6, the Scandinavian after 2...Qxd5.
    try:
        from src.openings_book import _position_key, _split_moves, get_book

        hits = _book_index().get(_position_key(cur)) or []
        entries = get_book().entries
    except Exception:  # noqa: BLE001 — the book is a bonus on top of the record
        logger.debug("book history lookup failed", exc_info=True)
        return []
    for i, plies in hits:
        if plies != _ply(cur):
            continue
        sans = _split_moves(entries[i][2])[:plies]
        sig = ("book", sans)
        if sig in seen:
            continue
        seen.add(sig)
        board, steps = chess.Board(), []
        for san in sans:
            move = board.parse_san(san)
            steps.append((board.copy(stack=False), move, board.san(move)))
            board.push(move)
        out.append((steps, True))
    return out


def _unrelated_boards(ctx, found: list) -> list:
    """Positions of the turn that are neither the board, nor on the way to it, nor a line going on from it: a
    tool's position («Белые только что сыграли Qxf7#» about the mate a tool just showed), another board. A claim
    about the board's own game cannot be told apart from one about these."""
    related = {_key(ctx.current)}
    for steps, _ in found:
        related.update(_key(b) for b, _, _ in steps)
    for start, sans in list(getattr(ctx, "line_records", None) or []) + (
            [(chess.Board(), list(ctx.game_moves))] if getattr(ctx, "game_moves", None) else []):
        board, keys = start.copy(stack=False), [_key(start)]
        for san in sans:
            try:
                board.push_san(san)
            except ValueError:
                break
            keys.append(_key(board))
        if _key(ctx.current) in keys:
            related.update(keys)  # the board's own line: its past and the moves that go on from it
    return [b for b in ctx.boards if ctx.is_given(b) and _key(b) not in related
            and not (b.board_fen() == chess.STARTING_BOARD_FEN and b.turn == chess.WHITE)]


def _last_move_fits(board: chess.Board, san: str, color: bool) -> bool:
    """*san* by *color* may be the move that led to *board*: its piece stands on its square, the other side to move."""
    sq = re.findall(SQ, san)
    if board.turn == color:
        return False
    if san.startswith("O-O"):
        king = board.king(color)
        return king is not None and chess.square_file(king) in (2, 6)
    if not sq:
        return False
    piece = board.piece_at(chess.parse_square(sq[-1]))
    want = {"K": chess.KING, "Q": chess.QUEEN, "R": chess.ROOK, "B": chess.BISHOP, "N": chess.KNIGHT}.get(san[0], chess.PAWN)
    if "=" in san:
        want = {"Q": chess.QUEEN, "R": chess.ROOK, "B": chess.BISHOP, "N": chess.KNIGHT}[san.split("=")[1][0]]
    return piece is not None and piece.color == color and piece.piece_type == want


def _record_text(steps: list) -> str:
    parts = []
    for before, _, san in steps:
        if before.turn == chess.WHITE:
            parts.append(f"{before.fullmove_number}.{san}")
        elif not parts:
            parts.append(f"{before.fullmove_number}...{san}")
        else:
            parts.append(san)
    return " ".join(parts)


# A sentence about the board's own game, and markers of another game or of theory in general.
_ABOUT_BOARD = re.compile(
    r"^\W*(?:это|здесь|тут|сейчас|теперь|на\s+доске|у\s+нас|в\s+этой\s+позиции|this\s+is|here|now)" + _E
    + r"|в\s+(?:этой|нашей|твоей|вашей|данной|текущей)\s+(?:партии|игре|позиции)|на\s+доске|" + _B
    + r"(?:здесь|тут)" + _E + r"|in\s+this\s+(?:game|position)|on\s+the\s+board|только\s+что|последним\s+ходом",
    re.IGNORECASE)
_OTHER_GAME = re.compile(
    r"в\s+партии\s+(?!(?:эт|наш|тво|ваш|данн|текущ))|в\s+матче|в\s+турнир\w*|в\s+\d{4}|когда-то|однажды|историческ\w*|"
    r"в\s+теори\w*|обычно|как\s+правило|часто|чаще|нередко|иногда|классическ\w*|знаменит\w*|in\s+the\s+game\s+(?!we|you)|"
    r"historically|usually|often|typically|in\s+\d{4}", re.IGNORECASE)
# The question asks about the board in front of the student («Как называется этот дебют?», «…здесь?»).
_QUESTION_ABOUT_BOARD = re.compile(
    _B + r"(?:эт(?:от|а|о|у|ой|ом)|здесь|тут|на\s+доске|сейчас|у\s+меня|мо(?:й|я|ю|ей|его|ем)|this|here|my)" + _E,
    re.IGNORECASE)


def _about_this_game(lowered: str, ctx, question_counts: bool) -> bool:
    if _OTHER_GAME.search(lowered) or _NOT_TOLD.search(lowered) or getattr(ctx, "board_moved", False):
        return False
    if _ABOUT_BOARD.search(lowered) or getattr(ctx, "game_moves", None):
        return True
    return question_counts and bool(_QUESTION_ABOUT_BOARD.search(getattr(ctx, "question", "") or ""))


def _recent_line(ctx) -> bool:
    """A line written in this or the previous sentence that leaves the board: what follows may be about it."""
    scene = getattr(ctx, "scene", None)
    return scene is not None and ctx.scene_age <= 1 and ctx.current is not None and _key(scene) != _key(ctx.current)


# ── (c) a move told as played on this board ─────────────────────────────────────────────────────────────────────

_SAN = r"[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?|O-O-O|O-O"
_PLAYED = re.compile(
    r"(?<![\w-])(?P<side>(?i:белые|ч[её]рные|ты|вы|соперник|противник|white|black|you|your\s+opponent))\s+"
    r"(?:(?i:уже|сразу|только\s+что|здесь|тут|в\s+ответ)\s+){0,2}"
    r"(?P<verb>(?i:сыграли|сыграл[аи]?|пошли|пош[её]л|пошла|ответили|ответил[аи]?|выбрали|выбрал[аи]?|предпочли|"
    r"избрали|сделали\s+ход|сделал[аи]?\s+ход|played|went\s+for|chose|opted\s+for|answered\s+with|replied\s+with))"
    r"\s+(?:(?i:ходом|ход|move)\s+)?[—–:-]?\s*"
    r"(?:(?P<num>\d{1,3})\s?(?P<dots>\.\.\.|…|\.)\s?)?(?P<san>" + _SAN + r")[+#]?(?![A-Za-z0-9])")


def _same(board: chess.Board, san: str, move: chess.Move) -> bool:
    try:
        return board.parse_san(san) == move
    except ValueError:
        return san.replace("x", "").rstrip("+#") == board.san(move).replace("x", "").rstrip("+#")


def played_move_issues(lowered: str, original: str, ctx) -> list[str]:
    """«здесь / в этой партии белые пошли 6.Сс4» must be a move of the board's record (prod 29.10, move-najdorf:
    the board was after 5...a6). A system named in general («в системе Созина белые идут 6.Bc4») is not told as
    played and is left alone."""
    if ctx.current is None:
        return []
    converted, _ = _to_san(original)
    hits = list(_PLAYED.finditer(converted))
    if not hits or not _about_this_game(lowered, ctx, question_counts=False):
        return []
    found = histories(ctx)
    if not found:
        return []
    out = []
    conv_low = converted.lower().replace("ё", "е")  # the offsets of *converted* («Кр» became «K»)
    for m in hits:
        if _is_hypothetical(conv_low, converted, m.start(), played=_just_played(ctx)) or _quoted(converted, m.start()) \
                or m["san"] in ctx.quoted or _NEGATION.search(conv_low[max(0, m.start("verb") - 24):m.start("verb")]):
            continue
        side = m["side"].lower()
        color = chess.WHITE if side.startswith(("бел", "white")) else chess.BLACK if side.startswith(("чер", "чёр", "black")) else None
        if color is None:
            if ctx.student_color is None:
                continue
            color = ctx.student_color if not side.startswith(("сопер", "против", "your op")) else not ctx.student_color
        dots = m["dots"]
        if dots:
            want = chess.WHITE if dots == "." else chess.BLACK
            if want != color:
                continue  # «белые пошли 6...Nf6»: the numbering does not fit the side — not this claim
        san = m["san"]
        if any(_last_move_fits(b, san, color) for b in _unrelated_boards(ctx, found)):
            continue  # it may be told of another position of the turn
        verdicts = []
        for steps, complete in found:
            if m["num"]:
                ply = (int(m["num"]) - 1) * 2 + (0 if color == chess.WHITE else 1)
                first = _ply(steps[0][0]) if steps else _ply(ctx.current)
                if ply < first:
                    verdicts.append(None)  # before the record begins: not known
                    continue
                if ply >= first + len(steps):
                    verdicts.append(("future", steps))
                    continue
                before, move, real = steps[ply - first]
                verdicts.append(None if _same(before, san, move) else ("other", steps, before, real))
            else:
                mine = [(b, mv) for b, mv, _ in steps if b.turn == color]
                if any(_same(b, san, mv) for b, mv in mine) or not complete:
                    verdicts.append(None)
                else:
                    verdicts.append(("never", steps))
        if not verdicts or any(v is None for v in verdicts):
            continue
        kind, steps = verdicts[0][0], verdicts[0][1]
        record = _record_text(steps)
        side_name = "White" if color == chess.WHITE else "Black"
        label = (m["num"] + m["dots"] if m["num"] else "") + san
        if kind == "future":
            to_move = "White" if ctx.current.turn == chess.WHITE else "Black"
            out.append(f"{label} has not been played on this board: the position is after {record or 'no moves'}, "
                       f"{to_move} to move at move {ctx.current.fullmove_number} — a move not yet made is only a "
                       "possible continuation, never what was played here")
        elif kind == "other":
            before, real = verdicts[0][2], verdicts[0][3]
            out.append(f"at {_label(before, real)} {side_name} played {real} here, not {san} "
                       f"(the moves that led to the board: {record})")
        else:
            out.append(f"{side_name} did not play {san} in the moves that led to this board ({record}): "
                       "never tell a move as played that the record does not have")
    return out


# ── (d) the history of exchanges ────────────────────────────────────────────────────────────────────────────────

_EXCHANGE_AFTER = re.compile(
    _B + r"(?:после|в\s+результате|вслед\s+за)\s+(?:(?:этого|раннего|быстрого|центрального|взаимного|первого)\s+)?"
    r"(?:размен\w*|обмен\w*|взяти\w*)(?:\s+(?:центральных\s+)?(?:пешек|пешки|пешками|фигур|фигурами|ферзей|ферзями|"
    r"коней|конями|слонов|слонами|ладей|ладьями))?\s+на\s+(?P<sq>" + SQ + r")(?![0-9])"
    r"|(?<![a-z])after\s+the\s+(?:exchange|trade|capture)s?\s+on\s+(?P<sq_en>" + SQ + r")(?![0-9])", re.IGNORECASE)
_EXCHANGE_DONE = re.compile(
    _B + r"(?:разменял\w*|обменял\w*|разменивал\w*|(?:был|произош[её]л|состоялся|случился)\s+(?:\w+\s+)?размен\w*|"
    r"размен\s+(?:уже\s+)?(?:был|произош[её]л|состоялся))(?:\s+(?!на\s)[^\s.,;!?]+){0,3}?\s+на\s+(?P<sq>" + SQ + r")(?![0-9])"
    r"|(?<![a-z])(?:exchanged|traded)\s+(?:[a-z]+\s+){0,2}?on\s+(?P<sq_en>" + SQ + r")(?![0-9])", re.IGNORECASE)
# The past told: «вывели», «разменялись», «пошёл» (the ending of a past verb, not a noun like «материал»).
_PAST = re.compile(r"(?<![а-яё])(?!(?:материал|потенциал|финал|сигнал|интервал|идеал|капитал|арсенал|журнал|генерал)"
                   r"(?![а-яё]))[а-яё]{2,}(?:[аеиоуыя]л(?:и|ись|а|ась|ся)?|ш[её]л)(?![а-яё])"
                   r"|(?<![a-z])(?:[a-z]{2,}ed|went|took|brought|got|came|gave|chose)(?![a-z])", re.IGNORECASE)
_PLAN = re.compile(_B + r"(?:можно|нужно|надо|стоит|следует|давай\w*|лучше|если|бы|когда|будет|будут|смож\w+|сыграй\w*|"
                   r"предлага\w*|план\w*|иде[яюи]|хоч\w+|хот(?:ят|ел\w*)|чтобы|готов\w*|собира\w+|стрем\w+|угрож\w+|"
                   r"could|would|will|should|can|if|plan|idea|want\w*|threat\w*)" + _E, re.IGNORECASE)


def exchange_history_issues(lowered: str, original: str, ctx) -> list[str]:
    """«после размена на e4 чёрные вывели ферзя» must match a capture on e4 in the record of the board's game (prod
    29.10, name-scandi: 2.exd5 Qxd5 — the capture was on d5). Only the past told about this game; «можно
    разменяться на e4», «после размена на e4 будет…» are plans."""
    if ctx.current is None or lowered.rstrip().endswith("?"):
        return []
    hits = [(m, "after") for m in _EXCHANGE_AFTER.finditer(lowered)] + [(m, "done") for m in _EXCHANGE_DONE.finditer(lowered)]
    if not hits or _PLAN.search(lowered) or FUTURE_VERB.search(lowered) or _recent_line(ctx) \
            or not _about_this_game(lowered, ctx, question_counts=True):
        return []
    found = histories(ctx)
    if not found or not all(complete for _, complete in found):
        return []  # a record that begins mid-game may miss the capture
    if _unrelated_boards(ctx, found) and not _ABOUT_BOARD.search(lowered):
        return []  # another position of the turn may be the one told
    captured: dict = {}
    for steps, _ in found:
        for before, move, san in steps:
            if before.is_capture(move) and _label(before, san) not in captured.get(move.to_square, []):
                captured.setdefault(move.to_square, []).append(_label(before, san))
    # A capture written in the sentence itself («после размена на d5 (2.exd5 Qxd5)»): its own line, read there.
    converted, _ = _to_san(original)
    written = {re.findall(SQ, x["san"])[-1] for x in _MOVE.finditer(converted) if "x" in x["san"]}
    out = []
    for m, kind in hits:
        sq = m["sq"] or m["sq_en"]
        if kind == "after":
            rest = lowered[:m.start()] + " " + lowered[m.end():]
            if not _PAST.search(rest):
                continue  # «после размена на e4 у белых лучше» — no past told
        if _NEGATION.search(lowered[max(0, m.start() - 24):m.start()]) or _quoted(lowered, m.start()) \
                or _is_hypothetical(lowered, original, m.start(), played=_just_played(ctx)):
            continue  # a condition, or moves written before it: a line, not this game
        if sq in written or chess.parse_square(sq) in captured:
            continue
        steps = found[0][0]
        caps = ", ".join(f"{' '.join(v)} (on {chess.square_name(k)})" for k, v in captured.items())
        out.append(f"no capture was made on {sq} in the moves that led to this board ({_record_text(steps)}): "
                   + (f"the captures were {caps}" if caps else "no piece has been captured yet")
                   + " — tell the exchanges of this game as its record has them")
    return out


# ── (a) a move advised in words that the piece cannot make ───────────────────────────────────────────────────────

# Saving a piece is a move now («увести ферзя», «отступить слоном»); placing one («поставить коня на d5») may be a
# plan of several moves, judged only with «сейчас», «сразу», «в первую очередь».
_RETREAT_IMP = (r"уведи(?:те)?|уводи(?:те)?|уводим|отведи(?:те)?|отводи(?:те)?|отводим|убери(?:те)?|убираем|спрячь(?:те)?|"
                r"прячем|отступи(?:те)?|отступаем|отойди(?:те)?|уйди(?:те)?|уходи(?:те)?|уведу|отведу|уберу|спрячу|отступлю|"
                r"отойду|уйду|retreat|withdraw|tuck")
_RETREAT_INF = r"увести|отвести|убрать|спрятать|отступить|отойти|уйти|уводить|отводить|отступать|уходить"
_PLACE_IMP = (r"поставь(?:те)?|ставь(?:те)?|ставим|поставлю|выведи(?:те)?|выводим|выведу|сыграй(?:те)?|пойди(?:те)?|"
              r"иди(?:те)?|ходи(?:те)?|сходи(?:те)?|переставь(?:те)?|переведи(?:те)?|двинь(?:те)?|продвинь(?:те)?|"
              r"move|put|place|bring|play")
_PLACE_INF = r"поставить|вывести|сыграть|пойти|сходить|переставить|перевести|двинуть|продвинуть"
_CUE = re.compile(_B + r"(?:надо|нужно|стоит|следует|можно|лучше|пора|важно|придется|придётся|должен|должна|должны|"
                  r"имеет\s+смысл|советую|рекомендую|предлагаю|хорошо\s+бы|попробуй(?:те)?|постарайся|давай(?:те)?|можешь|"
                  r"сможешь|остается|остаётся|правильно|разумно|логично|выгодно|требуется|успе\w+|"
                  r"should|must|need\s+to|have\s+to|can|could|better|try\s+to|time\s+to)" + _E, re.IGNORECASE)
_NOW = re.compile(_B + r"(?:сейчас|немедленно|срочно|в\s+первую\s+очередь|первым\s+делом|сразу|этим\s+ходом|следующим\s+ходом|"
                  r"на\s+этом\s+ходу|now|immediately|at\s+once|this\s+move|next\s+move)" + _E, re.IGNORECASE)
_LATER = re.compile(_B + r"(?:сначала|потом|затем|после|позже|позднее|далее|дальше|следом|в\s+будущем|со\s+временем|в\s+итоге|"
                    r"рокир\w*|first|then|later|eventually|afterwards|after)" + _E, re.IGNORECASE)
# Advice about a move already gone by: «правильно было отступить слоном на g3» (corpus 30.10) is about the position
# before the last moves, not the board.
_PAST_ADVICE = re.compile(_B + r"(?:было|был[аио]?|стоило|следовало|могл[аи]?|мог|could\s+have|should\s+have|would\s+have|"
                          r"had\s+to|needed\s+to|was\s+to)" + _E, re.IGNORECASE)
_STUDENT_IDEA = re.compile(_B + r"(?:предлага\w*|хочешь|хотел\w*|спрашива\w*|пишешь|говоришь|думаешь|собира\w*|планиру\w*|"
                           r"решил\w*|задумал\w*|you\s+(?:want|suggest|ask|think))" + _E, re.IGNORECASE)
_DENIED_AFTER = re.compile(r"нельзя|невозможн|не\s+(?:выйдет|получится|удастся|сможет|сможешь|может|можешь)|не\s+пройд|"
                           r"can'?t|cannot|impossible|not\s+possible|no\s+way", re.IGNORECASE)
_PIECE_ACC = r"ферзя|ладью|слона|коня|короля|пешку|ферз[её]м|ладь[её]й|слоном|кон[её]м|корол[её]м|пешкой|queen|rook|bishop|knight|king|pawn"
_POSS = r"(?P<poss>(?:сво|тво|мо|наш|ваш|бел|ч[её]рн|the|your|my|his|her|white'?s|black'?s)\w*\s+)?"
_FROM = rf"(?:\s+(?:с|со|from|on|off)\s+(?:пол[яе]\s+)?(?P<frm>{SQ})|\s+(?P<frm2>{SQ}))?(?![0-9])"
_GAP = (r"(?:\s+из-под\s+(?:удара|боя|атаки|шаха))?(?:\s*[—–,:]\s*|\s+)(?:(?:например|скажем|допустим|лучше(?:\s+всего)?|"
        r"хотя\s+бы|прямо|сразу|обратно|назад|подальше|back|over)\s*,?\s*)?")
_TARGETS = (rf"(?:на|в|to|onto|on)\s+(?:пол[ея]\s+)?(?P<t1>{SQ})(?![0-9])"
            rf"(?P<more>(?:\s*(?:,|или|либо|/|or)\s*(?:на\s+|в\s+|to\s+)?(?:пол[ея]\s+)?{SQ}(?![0-9]))*)")
_ADVICE = [
    # «увести ферзя с d8 — например, на c7 или на b6», «отступи слоном на e2», "retreat the queen to c7"
    re.compile(_B + rf"(?P<verb>{_RETREAT_IMP}|{_RETREAT_INF}|{_PLACE_IMP}|{_PLACE_INF})\s+"
               r"(?:(?:сейчас|сразу|скорее|быстрее|немедленно|срочно)\s+)?" + _POSS
               + rf"(?P<piece>{_PIECE_ACC})" + _E + _FROM + _GAP + _TARGETS, re.IGNORECASE),
    # «ферзя надо увести на c7», «ферзём лучше отступить на e7»
    re.compile(_B + _POSS + rf"(?P<piece>{_PIECE_ACC})" + _E + _FROM
               + r"\s+(?:(?:сейчас|сразу)\s+)?(?P<cue>надо|нужно|стоит|следует|лучше|пора|можно|придется|придётся)\s+(?:бы\s+)?"
               + rf"(?:(?:сейчас|сразу)\s+)?(?P<verb>{_RETREAT_INF}|{_PLACE_INF})" + _GAP + _TARGETS, re.IGNORECASE),
    # «ферзю надо уйти на c7»
    re.compile(_B + _POSS + r"(?P<piece>ферзю|ладье|слону|коню|королю|пешке)" + _E + _FROM
               + r"\s+(?:(?:сейчас|сразу)\s+)?(?P<cue>надо|нужно|стоит|следует|лучше|пора|придется|придётся)\s+(?:бы\s+)?"
               + r"(?P<verb>уйти|отступить|отойти|уходить|отступать|встать|перейти|спрятаться)" + _GAP + _TARGETS,
               re.IGNORECASE),
]
_IMPERATIVE = re.compile(rf"(?:{_RETREAT_IMP}|{_PLACE_IMP})$", re.IGNORECASE)
_RETREAT = re.compile(rf"(?:{_RETREAT_IMP}|{_RETREAT_INF})$", re.IGNORECASE)


def _owner(poss: str, ctx) -> Optional[bool]:
    """The colour a possessive names, or None when either side may be meant."""
    p = (poss or "").lower().replace("ё", "е")
    if p.startswith(("бел", "white")):
        return chess.WHITE
    if p.startswith(("черн", "black")):
        return chess.BLACK
    student = getattr(ctx, "student_color", None)
    if student is None:
        return None
    if p.startswith(("тво", "ваш", "сво", "your")):
        return student
    if p.startswith(("мо", "my")):
        return not student
    return None


def _candidate_boards(ctx) -> list:
    """The positions an advice may be about: the board, the end of each line and game, positions a tool gave —
    not the moves inside a line (the game's past) nor the initial position standing in for an unknown one."""
    inside = set()
    for start, sans in list(getattr(ctx, "line_records", None) or []) + (
            [(chess.Board(), list(ctx.game_moves))] if getattr(ctx, "game_moves", None) else []):
        board = start.copy(stack=False)
        keys = [_key(board)]
        for san in sans:
            try:
                board.push_san(san)
            except ValueError:
                break
            keys.append(_key(board))
        inside.update(keys[:-1])
    out = [ctx.current]
    for board in ctx.boards:
        key = _key(board)
        if board is ctx.current or not ctx.is_given(board) or key in inside:
            continue
        if board.board_fen() == chess.STARTING_BOARD_FEN and ctx.current.board_fen() != chess.STARTING_BOARD_FEN:
            continue
        out.append(board)
    if getattr(ctx, "scene", None) is not None and ctx.scene_age <= 1:
        out.append(ctx.scene)  # a line written just before: «…Nc3. Тогда надо увести ферзя» may be about its end
    return out


def _can_go(board: chess.Board, color: bool, ptype: int, froms: list, to: int) -> bool:
    """A piece of *ptype* on one of *froms* can move to *to* — now when *color* is to move, else after some reply."""
    def reaches(b: chess.Board) -> bool:
        return any(m.from_square in froms and m.to_square == to and b.piece_type_at(m.from_square) == ptype
                   for m in b.legal_moves)
    if board.turn == color:
        return reaches(board)
    replies = list(board.legal_moves)
    if not replies:
        return True  # the game is over: nothing to judge
    for reply in replies:
        after = board.copy(stack=False)
        after.push(reply)
        if reaches(after):
            return True
    return False


def _why_not(board: chess.Board, color: bool, ptype: int, a: int, to: int) -> str:
    there = board.piece_at(to)
    if there is not None and there.color == color:
        return f"a {_COLOR[color]} {chess.piece_name(there.piece_type)} stands on {chess.square_name(to)}"
    if ptype == chess.PAWN:
        return f"a pawn on {chess.square_name(a)} does not get there"
    if not _geometry_move(ptype, a, to):
        return f"a {_NAMES[ptype]} does not move from {chess.square_name(a)} to {chess.square_name(to)}"
    block = next((sq for sq in chess.SquareSet.between(a, to) if board.piece_at(sq) is not None), None)
    if block is not None:
        return f"the {chess.piece_name(board.piece_type_at(block))} on {chess.square_name(block)} is in the way"
    if board.turn != color:
        return "it cannot get there after any reply"
    return "it would leave its own king in check"


def advice_move_issues(lowered: str, original: str, ctx) -> list[str]:
    """«надо увести ферзя с d8 — например, на c7 или на b6» (prod game 29.10, st2): a move advised in words must be
    one the piece can make on the board the sentence is about. The student's piece or the coach's, whichever side
    is to move (the other side's piece: after some reply). A plan («сначала …, потом …»), a condition, a question,
    the student's idea quoted and a denial are not judged."""
    if ctx.current is None or lowered.rstrip().endswith("?"):
        return []
    from src.answer_check import _DENIES

    if _DENIES.search(lowered):
        return []  # «увести ферзя на c7 нельзя: там пешка» says the truth
    out = []
    for rx in _ADVICE:
        for m in rx.finditer(lowered):
            verb = m["verb"]
            ptype = _ptype(m["piece"])
            if ptype is None:
                continue
            before = lowered[:m.start()]
            clause = re.split(r"[.;!?]", before)[-1]
            imperative = bool(_IMPERATIVE.match(verb)) and not m.groupdict().get("cue")
            if not imperative and not m.groupdict().get("cue") and not _CUE.search(clause[-60:]):
                continue  # an infinitive with no «надо», «можно», «стоит»: a description, not advice
            frm = m["frm"] or m["frm2"]
            if not _RETREAT.match(verb) and not _NOW.search(clause + " " + m.group(0)):
                continue  # «поставить коня на d5» may be a plan of several moves
            if (ptype == chess.KING and not _NOW.search(clause + " " + m.group(0))) or (ptype == chess.PAWN and not frm):
                continue
            if _LATER.search(clause) or _LATER.search(m.group(0)) or _STUDENT_IDEA.search(clause) \
                    or _PAST_ADVICE.search(clause) or _PAST_ADVICE.search(m.group(0)) \
                    or _quoted(lowered, m.start()) or _NEGATION.search(clause[-30:]) \
                    or re.search(_B + r"(?:не|нельзя|незачем|never|don'?t|not)\s+(?:\w+\s+){0,2}$", clause) \
                    or _is_hypothetical(lowered, original, m.start(), played=_just_played(ctx)) \
                    or _DENIED_AFTER.search(lowered[m.end():m.end() + 40].split(",")[0]):
                continue
            targets = [m["t1"]] + re.findall(SQ, m["more"] or "")
            owner = _owner(m["poss"], ctx)
            if owner is None:  # «чёрным надо увести ферзя», «белые должны отвести слона»
                side = re.findall(_B + r"(бел(?:ым|ые|ых)|ч[её]рн(?:ым|ые|ых)|white|black)" + _E, clause[-60:])
                owner = (chess.WHITE if side[-1].startswith(("бел", "white")) else chess.BLACK) if side else None
            bad, primary = [], None
            for t in dict.fromkeys(targets):
                to = chess.parse_square(t)
                if any((pc := b.piece_at(to)) is not None and pc.piece_type == ptype for b in _candidate_boards(ctx)):
                    continue  # «убрать коня на f6»: the knight standing there (to be taken), not a move to f6
                had, possible = False, False
                for board in _candidate_boards(ctx):
                    for color in ([owner] if owner is not None else [board.turn, not board.turn]):
                        if frm:
                            pc = board.piece_at(chess.parse_square(frm))
                            if pc is None or pc.piece_type != ptype or pc.color != color:
                                continue
                            froms = [chess.parse_square(frm)]
                        else:
                            froms = list(board.pieces(ptype, color))
                        if not froms or to in froms:
                            continue
                        had = True
                        if primary is None:
                            primary = (board, color, froms)
                        if _can_go(board, color, ptype, froms, to):
                            possible = True
                            break
                    if possible:
                        break
                if had and not possible:
                    bad.append(to)
            if not bad or primary is None:
                continue
            board, color, froms = primary
            name = f"the {_COLOR[color]} {_NAMES[ptype]}" + (f" on {chess.square_name(froms[0])}" if len(froms) == 1 else "")

            def why(t: int) -> str:
                # of two bishops, the one whose line leads there: «the pawn on d5 is in the way» of the bishop c4
                a = next((sq for sq in froms if _geometry_move(ptype, sq, t)), froms[0])
                reason = _why_not(board, color, ptype, a, t)
                return reason if len(froms) == 1 else f"{reason}, for the one on {chess.square_name(a)}"
            reasons = " or ".join(f"{chess.square_name(t)} ({why(t)})" for t in bad)
            tail = ""
            if board.turn == color:
                legal = [board.san(mv) for mv in board.legal_moves if mv.from_square in froms]
                its = "its" if len(froms) == 1 else f"the {_NAMES[ptype]}s'"
                if len(legal) == 1:
                    tail = f"; {its} only legal move now is {legal[0]}"
                elif legal:
                    tail = f"; {its} legal moves now: {', '.join(legal[:12])}"
                else:
                    tail = "; it has no legal move now" if len(froms) == 1 else "; none of them has a legal move now"
            out.append(f"{name} cannot go to {reasons} on the board{tail} — advise only a move the piece can make")
    return list(dict.fromkeys(out))


# ── (b) «what is attacked» answered as if complete ───────────────────────────────────────────────────────────────

_UNDER = (r"(?:под\s+(?:ударом|боем|атакой)|в\s+опасности|висит|висят|висящ\w*|атакован\w*|hanging|under\s+attack|"
          r"attacked|en\s+prise|in\s+danger)")
_HOLDS = r"(?:защищ[её]н\w*|прикрыт\w*|в\s+безопасности|defended|protected|covered|safe)"
_SIDE_WORDS = (r"(?:у\s+(?:тебя|вас|меня|нас|белых|ч[её]рных|соперника|противника|него|них)|сейчас|здесь|тут|теперь|"
               r"is|are|now|right\s+now)")
_ONLY = [
    # «под ударом у тебя только слон c4», «hanging is only the bishop»
    re.compile(_UNDER + rf"\s+(?:{_SIDE_WORDS}\s+){{0,3}}(?P<only>только|лишь|only|just)\s+(?P<what>[^.,;:!?—–()]{{1,40}})",
               re.IGNORECASE),
    # «только слон c4 под ударом», "only the bishop is hanging"
    re.compile(rf"(?<![а-яa-z])(?P<only>только|лишь|only)\s+(?P<what>[^.,;:!?—–()]{{1,40}}?)\s+(?:{_SIDE_WORDS}\s+){{0,2}}"
               + _UNDER, re.IGNORECASE),
    # «единственная фигура под ударом — слон c4», "the only piece hanging is the bishop on c4"
    re.compile(r"(?P<only>единственн\w+|the\s+only)\s+(?:(?:фигур\w*|пешк\w*|piece|thing|target)\s+)?(?:(?:котор\w+|что|that|which)\s+)?"
               rf"(?:{_SIDE_WORDS}\s+){{0,2}}" + _UNDER + r"\s*(?:[—–:-]|это|is|,)?\s*(?P<what>[^.,;!?()]{1,40})", re.IGNORECASE),
]
_ELSE = [
    # «больше ничего не висит», «кроме него у тебя ничего не под ударом», "nothing else is hanging"
    re.compile(r"(?<![а-яa-z])(?:больше|кроме\s+[^,.;!?]{1,30}?)\s*,?\s*(?:у\s+\S+\s+)?(?:ничего|никто|ни\s+одна\s+(?:фигура|пешка))\s+"
               r"(?:у\s+\S+\s+)?(?:сейчас\s+|здесь\s+|тут\s+)?не\s+" + _UNDER, re.IGNORECASE),
    re.compile(r"(?<![a-z])nothing\s+else\s+(?:of\s+\w+\s+)?(?:is\s+)?" + _UNDER, re.IGNORECASE),
    # «остальное защищено», «все остальные фигуры в безопасности», "everything else is protected"
    re.compile(r"(?<![а-яa-z])(?:все\s+остальн\w+|вс[её]\s+остальное|остальн\w+|все\s+прочие|прочие|everything\s+else|"
               r"(?:all\s+)?the\s+rest)\s+(?:(?:тво\w+|мо\w+|бел\w+|ч[её]рн\w+|фигур\w*|пешк\w*|сейчас|здесь|тут|is|are|"
               rf"pieces)\s+){{0,3}}(?:надежно\s+|над[её]жно\s+|хорошо\s+|прочно\s+|well\s+)?(?P<holds>{_HOLDS})"
               r"|(?<![а-яa-z])(?:все\s+остальн\w+|вс[её]\s+остальное|остальн\w+)\s+(?:\S+\s+){0,2}?не\s+" + _UNDER,
               re.IGNORECASE),
]
_NOTHING = [
    # «у тебя ничего не висит», «ни одна фигура не под ударом», "nothing is hanging"
    re.compile(r"(?<![а-яa-z])(?:ничего|ни\s+одна\s+(?:фигура|пешка)|ни\s+одной\s+фигуры)\s+(?:у\s+\S+\s+)?"
               r"(?:сейчас\s+|здесь\s+|тут\s+|пока\s+)?не\s+" + _UNDER + r"(?P<qual>\s+без\s+защиты)?", re.IGNORECASE),
    re.compile(r"(?<![a-z])(?:nothing|no\s+(?:piece|pawn)s?)\s+(?:of\s+\w+\s+)?(?:is\s+|are\s+)?" + _UNDER, re.IGNORECASE),
]


def _side_of(sentence: str, ctx) -> Optional[bool]:
    s = sentence.lower().replace("ё", "е")
    student = getattr(ctx, "student_color", None)
    if student is None and ctx.current is not None:
        student = ctx.current.turn  # a study board: the student plays the side to move
    if re.search(_B + r"(?:белых|белые|белым|white)" + _E, s):
        return chess.WHITE
    if re.search(_B + r"(?:черных|черные|черным|black)" + _E, s):
        return chess.BLACK
    if re.search(_B + r"(?:соперник\w*|противник\w*|opponent)" + _E, s):
        return None if student is None else not student
    if re.search(_B + r"(?:у\s+тебя|у\s+вас|тво\w+|ваш\w+|your|you)" + _E, s):
        return student
    if re.search(_B + r"(?:у\s+меня|мо(?:й|я|е|и|их|им)|my|mine)" + _E, s) and getattr(ctx, "student_color", None) is not None:
        return not ctx.student_color
    return None


def _named(text: str) -> tuple[set, set]:
    squares = {chess.parse_square(s) for s in re.findall(rf"(?<![a-z0-9]){SQ}(?![0-9])", text)}
    types = set()
    for w in re.findall(r"[а-яёa-z]+", text):
        t = _ptype(w)
        if t is not None and (len(w) > 3 or w in ("конь", "коня", "king")):
            types.add(t)
    return squares, types


def _exposed_text(board: chess.Board, items: list) -> str:
    from src.position_facts import _piece, _pieces

    parts = []
    for sq, kind, attackers, defenders in items[:4]:
        if kind == "hanging":
            parts.append(f"{_piece(board, sq)} is attacked by {_pieces(board, attackers)} and not defended")
        elif kind == "cheaper":
            parts.append(f"{_piece(board, sq)} is attacked by a cheaper piece, {_pieces(board, attackers)}")
        else:
            parts.append(f"{_piece(board, sq)} is attacked by {_pieces(board, attackers)} and defended only by "
                         f"{_pieces(board, defenders)}, so the exchange on {chess.square_name(sq)} wins material")
    return "; ".join(parts)


def exhaustive_attack_issues(lowered: str, original: str, ctx, state: dict) -> list[str]:
    """«под ударом только X», «больше ничего не висит», «остальное защищено» against the board's own list of
    pieces that are attacked and not safe (prod 29.10, «Что у меня сейчас под ударом?»: the bishop c4 named, the
    d5 pawn — hit by Nf6 and Qd8, held only by that bishop — left out)."""
    board = ctx.current
    if board is None or lowered.rstrip().endswith("?") or getattr(ctx, "board_moved", False) or _recent_line(ctx):
        return []
    from src.position_facts import exchange_gain, exposed_pieces

    claims = []
    for rx in _ONLY:
        for m in rx.finditer(lowered):
            if re.search(r"(?:не|not)\s*$", lowered[:m.start("only")]):
                continue  # «под ударом не только слон» says the opposite
            claims.append((m, "only", m["what"]))
    for rx in _ELSE:
        for m in rx.finditer(lowered):
            hold = m.groupdict().get("holds")
            claims.append((m, "else_hold" if hold and not re.match(r"в\s+безопасности|safe", hold) else "else", ""))
    if not any(kind.startswith("else") for _, kind, _ in claims):
        for rx in _NOTHING:
            for m in rx.finditer(lowered):
                if re.search(r"(?:больше|кроме\s+[^,.;!?]{1,30}?)\s*,?\s*(?:у\s+\S+\s+)?$", lowered[:m.start()]):
                    continue
                claims.append((m, "none_hold" if m.groupdict().get("qual") else "none", ""))
    out = []
    for m, kind, what in claims:
        if _is_hypothetical(lowered, original, m.start(), played=_just_played(ctx)) or _quoted(lowered, m.start()) \
                or _STUDENT_IDEA.search(lowered[:m.start()]):
            continue
        named_sq, named_types = _named(lowered)
        side = _side_of(lowered, ctx)
        if kind == "only":
            what_sq, what_types = _named(what)
            if not what_sq and not what_types:
                continue
            owners = {board.piece_at(s).color for s in what_sq if board.piece_at(s) is not None}
            if len(owners) == 1 and (side is None or ctx.student_color is None):
                side = owners.pop()  # «только слон c4»: the side of the piece named, surer than a guess at «у тебя»
        elif kind.startswith("else"):
            if state["n"] == 0 and not named_sq and not named_types:
                continue  # «больше ничего» with nothing said before it here: what it excludes is not known
            named_sq |= state["squares"]
            named_types |= state["types"]
            side = side if side is not None else state.get("side")
        if side is None:
            q = (getattr(ctx, "question", "") or "")
            if re.search(_B + r"(?:у\s+меня|мо(?:й|я|е|и|их)|мне|my|i)" + _E, q):
                side = ctx.student_color if ctx.student_color is not None else board.turn
        if side is None:
            continue
        state["side"] = side
        items = [it for it in exposed_pieces(board, side) if (exchange_gain(board, it[0]) or 0) > 0]
        if kind.endswith("_hold"):
            items = [it for it in items if it[1] == "hanging"]  # «защищено»: a piece with a defender is defended
        items = [it for it in items if it[0] not in named_sq and board.piece_type_at(it[0]) not in named_types]
        if not items:
            continue
        who = "White" if side == chess.WHITE else "Black"
        claim = {"only": "it is not the only one", "else": "it is not true that nothing else is in danger",
                 "else_hold": "it is not true that the rest is defended", "none": "it is not true that nothing is in danger",
                 "none_hold": "it is not true that nothing is left undefended"}[kind]
        out.append(f"{claim} — {who} has more under attack on the board: {_exposed_text(board, items)}")
    return list(dict.fromkeys(out))


# ── one entry for src/answer_check.check_sentence ─────────────────────────────────────────────────────────────────

def record_fact_issues(lowered: str, original: str, ctx) -> list[str]:
    """The four checks above; never raises (the check must never break a turn)."""
    if ctx is None:
        return []
    state = ctx.__dict__.setdefault("_facts_state", {"n": 0, "squares": set(), "types": set(), "side": None})
    out: list[str] = []
    for check in (advice_move_issues, played_move_issues, exchange_history_issues):
        try:
            out += check(lowered, original, ctx)
        except Exception:  # noqa: BLE001
            logger.debug("%s failed", check.__name__, exc_info=True)
    try:
        out += exhaustive_attack_issues(lowered, original, ctx, state)
    except Exception:  # noqa: BLE001
        logger.debug("exhaustive_attack_issues failed", exc_info=True)
    if lowered.strip():
        squares, types = _named(lowered)
        state["n"] += 1
        state["squares"] |= squares
        state["types"] |= types
    return out
