"""Trades told about a recorded game, judged against its score (plan 31.10, P6; detector ``trades``).

«там был красивый размен, где белые отдали ферзя за ладью» about game 6 of Dubai 2021 (prod 29.10, x-wc2021-g6):
the score was in the turn (``ctx.line_records``), and 26.Qxc8 Rxc8 27.Rxc8 is the queen for TWO rooks; «Карлсен
впервые отдал ладью за коня» (sets_old) — Black had no knight left after 19...Bxd4. Every claim of the form

    <side or player> отдал(и) / пожертвовал(и) A за B        (A, B: units — «ферзя», «две ладьи», «пешку и слона»)
    <side or player> разменял(и) / обменял(и) / променял(и) A на B
    <side or player> gave (up) / sacrificed / traded / exchanged A for B

in the past tense, about a game whose whole score the turn has, is true only if some exchange of that game fits it
exactly, by count (src/game_record.exchanges: a maximal run of captures; neighbouring runs a move or two apart count
as one window, so a combination with a quiet check inside is one trade). Pawns count only when the sentence names
them («ладью за слона» is 80.Rxf7+ Kxf7 81.Rb7+ Kg6 82.Rxa7, the f7 pawn aside). Otherwise the issue names the
nearest real exchange — the one where the giver lost most of what the sentence says it gave, then where the other
side lost most of what it says came back: «26.Qxc8 Rxc8 27.Rxc8 — White gave the queen for two rooks».

The games judged: a famous game whose score is among the turn's records (src/famous_games.GAMES — its whole verified
score, even when the record is a part of it), and the game on the board (the live game's moves, or a loaded game of
at least 20 plies from the initial position that passes through the board now). A sentence that may mean several of
them is cut only when it is false in every one; a sentence naming a player of none of them, or another game («в
партии Таль — Ботвинник»), a hypothetical («если бы … отдали бы»), a negation or a non-unit («за атаку», «ни за что»)
is skipped, and so is a sentence about a line (a move written that the game never had — here or as the move the
answer just wrote). «получили двух слонов за коня» is not a trade claim (the bishop pair, an imbalance: test_prod_check
_2026_10_30_small), so «получил(и)/got/won A за B» is not read, and two bishops on either side are the bishop pair.
Kazakh is not parsed (no native review yet).
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any, Optional

import chess

logger = logging.getLogger(__name__)

DETECTOR = "trades"
_GAP = 4  # quiet plies allowed between two runs of one window
_MAX_RUNS = 4  # runs in one window
_MIN_LOADED = 20  # plies of a loaded record from the initial position that make it a game

_PIECES = (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
_NAME = {chess.QUEEN: ("queen", "queens"), chess.ROOK: ("rook", "rooks"), chess.BISHOP: ("bishop", "bishops"),
         chess.KNIGHT: ("knight", "knights"), chess.PAWN: ("pawn", "pawns")}
_NUM_EN = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}

# ── the words ─────────────────────────────────────────────────────────────────────────────────────────────────
_RU_VERB = (r"(?P<give>(?:по)?жертвовал[аи]?|отдал[аи]?|отдавал[аи]?)"
            r"|(?P<swap>разменял[аи]?|обменял[аи]?|променял[аи]?)")
_EN_VERB = r"(?P<egive>gave\s+up|gave|sacrificed|sacked|traded|exchanged|swapped)"
_VERB = re.compile(r"(?<![\w-])(?:" + _RU_VERB + "|" + _EN_VERB + r")(?![\w-])", re.IGNORECASE)
_FOR_RU = re.compile(r"(?<![\w-])за(?![\w-])", re.IGNORECASE)
_FOR_SWAP = re.compile(r"(?<![\w-])(?:на|за)(?![\w-])", re.IGNORECASE)
_FOR_EN = re.compile(r"(?<![\w-])for(?![\w-])", re.IGNORECASE)

# Not a claim about what happened: a hypothetical, a recommendation, a rule, a negation.
_NOT_TOLD = re.compile(
    r"(?<![\w-])(?:бы|если|когда|будто|словно|мог\w*|можно|нужно|надо|стоит|стоило|следует|следовало|пришлось|"
    r"придется|придётся|обычно|часто|иногда|никогда|если\s+бы|would|could|should|might|if|when|whenever|usually|"
    r"often|never|instead)(?![\w-])", re.IGNORECASE)
_NEG_BEFORE = re.compile(r"(?<![\w-])(?:не|ни|not|never|didn't|did\s+not)\s+(?:\S+\s+)?$", re.IGNORECASE)

_RU_NUM = {"один": 1, "одного": 1, "одну": 1, "одна": 1, "одной": 1, "два": 2, "две": 2, "двух": 2, "оба": 2,
           "обе": 2, "обоих": 2, "обеих": 2, "три": 3, "трех": 3, "четыре": 4, "четырех": 4, "пять": 5, "пяти": 5}
_EN_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "both": 2, "three": 3, "four": 4, "five": 5}
# Words inside a unit phrase that change nothing: determiners, colours, wings, «целого», squares.
_FILLER = re.compile(
    r"^(?:сво\w+|его|ее|её|их|этого|эту|этих|т[уо]т|ту|того|тех|целого|целую|целых|всего|лишь|только|сразу|"
    r"просто|фактически|бел\w+|черн\w+|чёрн\w+|темнопольн\w+|светлопольн\w+|чернопольн\w+|белопольн\w+|королевск\w+|"
    r"ферзев\w+|центральн\w+|проходн\w+|сдвоенн\w+|последн\w+|оставш\w+|лишн\w+|"
    r"the|his|her|their|its|whole|entire|just|only|white's|black's|own|light-squared|dark-squared|extra|passed|"
    r"kingside|queenside|remaining|last|[a-h][1-8]|на|on)$", re.IGNORECASE)
_AND = re.compile(r"^(?:и|а|плюс|также|ещ[её]|and|plus|&)$", re.IGNORECASE)
_MINOR_ADJ = re.compile(r"^(?:л[её]гк\w+|minor)$", re.IGNORECASE)


def _unit(word: str) -> Optional[str]:
    """The unit a word names: "Q", "R", "B", "N", "P", "piece" (any of Q R B N), "exchange" (R for a minor)."""
    w = word.lower().replace("ё", "е")
    if re.match(r"^ферз", w) or re.match(r"^queens?$", w):
        return "Q"
    if re.match(r"^(?:ладь|ладей|ладе)", w) or re.match(r"^rooks?$", w):
        return "R"
    if re.match(r"^слон", w) or re.match(r"^bishops?$", w):
        return "B"
    if w in ("конь", "коня", "коню", "конем", "коне", "кони", "коней", "коням", "конями") or re.match(r"^knights?$", w):
        return "N"
    if re.match(r"^(?:пешк|пешек)", w) or re.match(r"^pawns?$", w):
        return "P"
    if re.match(r"^фигур", w) or re.match(r"^pieces?$", w):
        return "piece"
    if re.match(r"^качеств", w) or w == "exchange":
        return "exchange"
    return None


def _units(span: str, strict: bool) -> Optional[list]:
    """The units *span* names, in order, as slots ("Q", "R", …, "minor", "piece"); "exchange" stays a slot of its own.
    *strict* (the giver's side, between the verb and «за»): any other word makes the span not a list of units — None.
    Not strict (after «за»): the list ends at the first other word. None when no unit is named."""
    words = re.findall(r"[\w'’-]+|[,;]", span)
    slots: list = []
    n, minor, pending_and = 1, False, False
    for w in words:
        lw = w.lower().replace("ё", "е")
        if lw in (",",):
            pending_and = True
            continue
        if _AND.match(lw):
            pending_and = True
            continue
        num = _RU_NUM.get(lw) or _EN_NUM.get(lw) or (int(lw) if lw.isdigit() and 0 < int(lw) < 9 else None)
        if num:
            n = num
            continue
        if _MINOR_ADJ.match(lw):
            minor = True
            continue
        u = _unit(lw)
        if u is not None:
            if slots and not pending_and:
                # two units with no «и» between them: not a list
                if strict:
                    return None
                break
            if u == "piece" and minor:
                u = "minor"
            if u == "P" and n == 1:
                u = "P+"  # «пешку», «пешки»: at least one; a number («две пешки») is counted exactly
            slots += [u] * n
            n, minor, pending_and = 1, False, False
            continue
        if _FILLER.match(lw):
            continue
        if strict:
            return None
        break
    return slots or None


# ── the games ─────────────────────────────────────────────────────────────────────────────────────────────────
_FAMOUS_SANS: Optional[list] = None


def _famous() -> list:
    """(game dict, its SAN moves without +/#, its moves) of src/famous_games.GAMES, computed once."""
    global _FAMOUS_SANS
    if _FAMOUS_SANS is None:
        out = []
        try:
            from src.famous_games import GAMES, _replay

            for g in GAMES:
                _, moves = _replay(g)
                b, sans = chess.Board(), []
                for mv in moves:
                    sans.append(b.san(mv).rstrip("+#"))
                    b.push(mv)
                out.append((g, sans, moves))
        except Exception:  # noqa: BLE001
            out = []
        _FAMOUS_SANS = out
    return _FAMOUS_SANS


def _is_start(board: chess.Board) -> bool:
    return board.board_fen() == chess.STARTING_BOARD_FEN and board.turn == chess.WHITE


def _key(board: chess.Board) -> str:
    return board.board_fen() + (" w" if board.turn else " b")


def _players(g: dict) -> list:
    """(name stem, colour) for the players of a famous game: the English names, the Russian ones (white_ru/black_ru)."""
    out = []
    for keys, colour in ((("white", "white_ru"), chess.WHITE), (("black", "black_ru"), chess.BLACK)):
        for k in keys:
            for part in re.findall(r"[A-Za-zА-Яа-яЁё]{4,}", g.get(k) or ""):
                if part.lower() in ("duke", "count", "karl", "and", "james", "robert", "isouard", "brunswick", "paul",
                                    "adolf", "lionel", "jean", "garry", "veselin", "donald", "magnus", "ian"):
                    continue
                out.append((part.lower().replace("ё", "е")[:5], colour))
    return out


def games_of(ctx: Any) -> list:
    """The games of the turn a trade may be told about: [{"name", "moves" (SAN), "players", "key"}]."""
    records = list(getattr(ctx, "line_records", None) or [])
    out, seen = [], set()
    for g, fam, _ in _famous():
        for start, sans in records:
            if not _is_start(start):
                continue
            rec = [str(x).rstrip("+#") for x in sans]
            n = min(len(rec), len(fam))
            if n >= min(8, len(fam)) and rec[:n] == fam[:n]:
                if g["key"] not in seen:
                    seen.add(g["key"])
                    out.append({"key": g["key"], "name": g["name"], "moves": list(fam), "players": _players(g)})
                break
    famous_records = [tuple(x["moves"]) for x in out]
    own = None
    if getattr(ctx, "game_moves", None):
        own = [str(m) for m in ctx.game_moves]
        name = "this game"
    else:
        cur = getattr(ctx, "current", None)
        best = None
        for start, sans in records:
            if not _is_start(start) or len(sans) < _MIN_LOADED:
                continue
            clean = tuple(str(x).rstrip("+#") for x in sans)
            if any(f[:len(clean)] == clean for f in famous_records):
                continue  # a famous game's record: judged by its whole score above
            if cur is not None:
                b, keys = chess.Board(), {_key(chess.Board())}
                for s in sans:
                    try:
                        b.push_san(s)
                    except ValueError:
                        break
                    keys.add(_key(b))
                if _key(cur) not in keys:
                    continue
            if best is None or len(sans) > len(best):
                best = list(sans)
        own, name = best, "the game on the board"
    if own:
        clean = [s.rstrip("+#") for s in own]
        if not any(f[:len(clean)] == tuple(clean) for f in famous_records):
            out.append({"key": "board", "name": name, "moves": own, "players": []})
    return out


_EXCH_CACHE: dict = {}


def _exchanges(moves: list) -> tuple:
    """(runs of src/game_record.exchanges, the board after the last move), cached per score."""
    key = tuple(moves)
    hit = _EXCH_CACHE.get(key)
    if hit is None:
        from src.game_record import exchanges

        runs = exchanges(list(moves))
        b = chess.Board()
        for s in moves:
            try:
                b.push_san(s)
            except ValueError:
                break
        hit = (runs, b)
        if len(_EXCH_CACHE) > 64:
            _EXCH_CACHE.clear()
        _EXCH_CACHE[key] = hit
    return hit


# ── the verdict ───────────────────────────────────────────────────────────────────────────────────────────────
def _expand(slots: list, other: list) -> tuple:
    """"exchange" on one side is a rook there and a minor piece on the other side."""
    mine = [s for s in slots if s != "exchange"]
    extra = []
    for s in slots:
        if s == "exchange":
            mine.append("R")
            extra.append("minor")
    return mine, extra


_LETTER = {"Q": chess.QUEEN, "R": chess.ROOK, "B": chess.BISHOP, "N": chess.KNIGHT, "P": chess.PAWN}


def _fits(lost: Counter, slots: list) -> bool:
    """*lost* (piece type → count) is exactly what *slots* name. Pawns count only when a slot names them: "P" slots
    (a number was said: «две пешки») exactly, a bare "P+" («пешку», «пешки») as at least one."""
    need = Counter(s for s in slots if s in _LETTER)
    some_pawns = "P+" in slots
    have = Counter({t: c for t, c in lost.items() if t not in (chess.KING, chess.PAWN)})
    pawns = lost.get(chess.PAWN, 0)
    if need["P"]:
        if pawns != need["P"]:
            return False
    elif some_pawns and pawns < 1:
        return False
    for letter, c in need.items():
        if letter == "P":
            continue
        t = _LETTER[letter]
        if have[t] < c:
            return False
        have[t] -= c
    rest = [t for t, c in have.items() for _ in range(c)]
    wild = [x for x in slots if x in ("minor", "piece")]
    if len(rest) != len(wild):
        return False
    minors = [t for t in rest if t in (chess.BISHOP, chess.KNIGHT)]
    return len(minors) >= wild.count("minor")


def _windows(runs: list) -> list:
    """Every window (i, j, lost) of up to _MAX_RUNS neighbouring runs, each at most _GAP quiet plies after the one
    before; *lost* is what each side lost in it."""
    out = []
    for i in range(len(runs)):
        lost = {chess.WHITE: Counter(), chess.BLACK: Counter()}
        for j in range(i, min(len(runs), i + _MAX_RUNS)):
            if j > i and runs[j].start_ply - runs[j - 1].end_ply - 1 > _GAP:
                break
            for c in (chess.WHITE, chess.BLACK):
                lost[c] = lost[c] + runs[j].lost.get(c, Counter())
            out.append((i, j, {c: Counter(lost[c]) for c in lost}))
    return out


def _phrase(lost: Counter) -> str:
    """«the queen», «a rook, a bishop and two pawns», «nothing»."""
    parts = []
    for t in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
        c = lost.get(t, 0)
        if c:
            one, many = _NAME[t]
            parts.append("the queen" if t == chess.QUEEN and c == 1 else f"{_NUM_EN.get(c, c)} {one if c == 1 else many}")
    if not parts:
        return "nothing"
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _slots_phrase(slots: list) -> str:
    c = Counter("P" if x == "P+" else x for x in slots)
    parts = []
    for x, (one, many) in (("Q", ("queen", "queens")), ("R", ("rook", "rooks")), ("B", ("bishop", "bishops")),
                           ("N", ("knight", "knights")), ("minor", ("minor piece", "minor pieces")),
                           ("piece", ("piece", "pieces")), ("P", ("pawn", "pawns"))):
        n = c.get(x, 0)
        if n:
            parts.append("the queen" if x == "Q" and n == 1 else f"{_NUM_EN.get(n, n)} {one if n == 1 else many}")
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _bare(slots: list) -> str:
    """«queen», «rook or knight» — the units, no article or number (for «lost no …»)."""
    names = {"Q": "queen", "R": "rook", "B": "bishop", "N": "knight", "P": "pawn", "P+": "pawn",
             "minor": "minor piece", "piece": "piece"}
    seen = []
    for x in slots:
        if names.get(x) and names[x] not in seen:
            seen.append(names[x])
    return " or ".join(seen)


def _plies(moves: list) -> list:
    """(board before, move, SAN) for each move of the score."""
    b, out = chess.Board(), []
    for s in moves:
        try:
            mv = b.parse_san(s)
        except ValueError:
            break
        out.append((b.copy(stack=False), mv, b.san(mv)))
        b.push(mv)
    return out


def _run_text(plies: list, start: int, end: int, side: bool) -> str:
    """Plies *start*..*end* (1-based) as numbered moves, from the quiet move that offered the giver's first piece
    taken (16.Qb8+ Nxb8), and with a mate that follows at once (17.Rd8#)."""
    if start >= 2:
        before, mv, _ = plies[start - 1]
        prev_board, prev_mv, _ = plies[start - 2]
        victim = before.piece_at(mv.to_square)
        if (victim is not None and victim.color == side and mv.to_square == prev_mv.to_square
                and not prev_board.is_capture(prev_mv)):
            start -= 1
    if end < len(plies):
        nxt = plies[end][0].copy(stack=False)
        nxt.push(plies[end][1])
        if nxt.is_checkmate():
            end += 1
    out = []
    for p in range(start, end + 1):
        san = plies[p - 1][2]
        if p % 2 == 1:
            out.append(f"{(p - 1) // 2 + 1}.{san}")
        elif p == start:
            out.append(f"{(p - 1) // 2 + 1}...{san}")
        else:
            out.append(san)
    return " ".join(out)


def _overlap(lost: Counter, slots: list) -> int:
    """How much of what *slots* name the side lost (the nearest-exchange score)."""
    need = Counter(_LETTER["P" if x == "P+" else x] for x in slots if x in _LETTER or x == "P+")
    hit = sum(min(lost.get(t, 0), c) for t, c in need.items())
    wild = sum(1 for x in slots if x in ("minor", "piece"))
    spare = sum(c for t, c in lost.items() if t in _PIECES) - sum(min(lost.get(t, 0), c) for t, c in need.items()
                                                                     if t in _PIECES)
    return hit + min(wild, max(0, spare))


def _excess(lost: Counter, matched: int) -> int:
    """Pieces (not pawns) the side lost beyond the *matched* ones the sentence names."""
    return max(0, sum(c for t, c in lost.items() if t in _PIECES) - matched)


def _verdict(game: dict, side: bool, give: list, get: list, move_no: Optional[int]) -> Optional[str]:
    """None when some window of *game* fits; else the issue naming the nearest real exchange: the window where the
    giver lost most of what it is said to give and least else, then where the other side lost most of what it is
    said to give back and least else, then the fewest runs (then the one nearest the move the sentence names, then
    the first). «белые отдали ферзя за коня» in the Opera game is 16.Qb8+ Nxb8 17.Rd8# — the queen for nothing,
    not the long run 13.Rxd7 … Nxb8 that has a knight in it."""
    runs, _ = _exchanges(game["moves"])
    windows = _windows(runs)
    for _, _, lost in windows:
        if _fits(lost[side], give) and _fits(lost[not side], get):
            return None
    who = "White" if side == chess.WHITE else "Black"
    claim = f"{who} never gave {_slots_phrase(give)} for {_slots_phrase(get)}"
    best, best_score = None, None
    for i, j, lost in windows:
        g = _overlap(lost[side], give)
        near = 0
        if move_no:
            mid = (runs[i].start_ply + runs[j].end_ply) // 2
            near = -abs((mid + 1) // 2 - move_no)
        o = _overlap(lost[not side], get)
        swapped = _overlap(lost[side], get) + _overlap(lost[not side], give)  # «коня за слона» when it was the other way
        if not g and not o and not swapped:
            continue
        score = (g, -_excess(lost[side], g), o, -_excess(lost[not side], o), swapped, -(j - i), near, -i)
        if best_score is None or score > best_score:
            best, best_score = (i, j, lost), score
    if game["key"] != "board":
        where = f"In {game['name']}, "
    else:
        where = "In this game, " if game["name"] == "this game" else "In the game on the board, "
    lost_none = ""
    if best is None or not best_score[0]:
        lost_none = f" ({who} lost no {_bare(give)} in it)"
    if best is None:
        return f"{where}{claim}{lost_none}."
    claim += lost_none
    i, j, lost = best
    text = _run_text(_plies(game["moves"]), runs[i].start_ply, runs[j].end_ply, side)
    back = _phrase(lost[not side])
    told = f"{who} gave {_phrase(lost[side])}"
    if back == "nothing":
        told += " and got nothing back for it" + (", and the mate followed" if text.endswith("#") else "")
    else:
        told += f" for {back}"
    return f"{where}{claim}: {text} — {told}."


# ── the claims of a sentence ──────────────────────────────────────────────────────────────────────────────────
_SUBJECT_NOM = re.compile(r"^(?:белые|черные|чёрные|white|black)$", re.IGNORECASE)
_NAMES_A_GAME = re.compile(r"(?<![\w-])(?:в\s+)?парти\w*\s+(?P<a>[А-ЯЁA-Z][\w-]+)(?:\s*[—–-]\s*(?P<b>[А-ЯЁA-Z][\w-]+))?")
_MOVE_NO = re.compile(r"(?<![\w-])(?:на\s+)?(\d{1,3})\s*-?\s*(?:м|ом|й)?\s+ход\w*|(?<![\w-])(?:on\s+)?move\s+(\d{1,3})",
                      re.IGNORECASE)


def _subject(ctx: Any, before: str, players: list) -> Optional[bool]:
    """The colour the subject before the verb names: the nearest of its last four words that is a player of the game,
    «белые»/«чёрные»/White/Black, or «ты»/«я» when the student's colour is known. None when none of them is there."""
    from src.game_record import side_words

    words = re.findall(r"[\w'’-]+", before)[-4:]
    for w in reversed(words):
        lw = w.lower().replace("ё", "е")
        for stem, colour in players:
            if lw.startswith(stem):
                return colour
        if _SUBJECT_NOM.match(lw) or lw in ("ты", "я", "you", "i"):
            return side_words(ctx, lw)
    return None


_SAN = re.compile(r"(?<![\w-])(?:\d+\.+\s*)?([KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)[+#!?]*(?![\w-])")


def _told_line(sentence: str, ctx: Any, game: dict) -> bool:
    """The sentence is about a line, not the game: it writes a move the game never had, or the move the answer just
    wrote (this sentence or the one before) is not one of the game's («…hxg5 — выходит, что ты отдал целого слона за
    одну пешку» after «а если бы ты взял на g5»)."""
    moves = {str(m).rstrip("+#") for m in game["moves"]}
    for m in _SAN.finditer(sentence or ""):
        if m.group(1) not in moves:
            return True
    scene = (getattr(ctx, "scene_san", "") or "").rstrip("+#")
    return bool(scene) and getattr(ctx, "scene_age", 9) <= 1 and scene not in moves


def claims(sentence: str) -> list:
    """[(verb match, A slots, B slots, reversed=False)] of the trade claims a sentence makes, its subject not yet read."""
    out = []
    text = sentence or ""
    for m in _VERB.finditer(text):
        rest = text[m.end():]
        clause = re.split(r"[.;!?:—–()]|,\s*(?:а|но|и|где|когда|после|чтобы|which|but|and|where|when)\s", rest)[0]
        if m.group("swap"):
            sep = _FOR_SWAP.search(clause)
        elif m.group("give"):
            sep = _FOR_RU.search(clause)
        else:
            sep = _FOR_EN.search(clause)
        if not sep:
            continue
        a_span, b_span = _MOVE_NO.sub(" ", clause[:sep.start()]), _MOVE_NO.sub(" ", clause[sep.end():])
        a = _units(a_span, strict=True)
        b = _units(b_span, strict=False)
        if not a or not b:
            continue
        aw, bw = re.findall(r"\w+", a_span.lower()), re.findall(r"\w+", b_span.lower())
        if len(aw) == 1 and bw and bw[0][:4] == aw[0][:4]:
            continue  # «фигуру за фигурой», «пешку за пешкой»: one after another, not a trade
        if sorted(a) == ["B", "B"] or sorted(b) == ["B", "B"]:
            continue  # «отдали коня за двух слонов», "for the two bishops": the bishop pair, not two bishops taken
        out.append((m, a, b, False))
    return out


def trade_issues(sentence: str, ctx: Any) -> list[str]:
    """The issues of *sentence* (the answer check's normalised text) about trades in a recorded game."""
    from src.config import detector_mode

    mode = detector_mode(DETECTOR, ctx)
    if mode == "off" or not sentence or not _VERB.search(sentence):
        return []
    found = claims(sentence)
    if not found:
        return []
    games = games_of(ctx)
    if not games:
        return []
    # a sentence about another game: a famous game the turn has no score of, or «в партии <name>» naming no player
    try:
        from src.famous_games import famous_game

        named = famous_game(sentence)
    except Exception:  # noqa: BLE001
        named = None
    if named is not None:
        games = [g for g in games if g["key"] == named["key"]]
        if not games:
            return []
    issues: list = []
    for m, a, b, rev in found:
        head = sentence[:m.start()]
        if _NOT_TOLD.search(sentence) or _NEG_BEFORE.search(head):
            continue
        gm = None
        for x in _NAMES_A_GAME.finditer(sentence):
            gm = x
        cands = games
        if gm:
            names = [n for n in (gm["a"], gm["b"]) if n]
            stems = [n.lower().replace("ё", "е")[:5] for n in names]
            cands = [g for g in games if any(s == st for s in stems for st, _ in g["players"])]
            if not cands:
                continue
        verdicts = []
        undecided = False
        for g in cands:
            side = _subject(ctx, head, g["players"])
            if side is None or _told_line(sentence, ctx, g):
                undecided = True
                break
            give, get = (b, a) if rev else (a, b)
            give_r, extra_get = _expand(give, get)
            get_r, extra_give = _expand(get, give)
            give_all, get_all = give_r + extra_give, get_r + extra_get
            mn = _MOVE_NO.search(sentence)
            move_no = int(mn.group(1) or mn.group(2)) if mn else None
            v = _verdict(g, side, give_all, get_all, move_no)
            if v is None:
                undecided = True
                break
            verdicts.append(v)
        if undecided or not verdicts:
            continue
        issue = verdicts[0]
        if mode == "shadow":
            logger.info("trades shadow: %s — %s", sentence[:200], issue)
            continue
        if issue not in issues:
            issues.append(issue)
    return issues
