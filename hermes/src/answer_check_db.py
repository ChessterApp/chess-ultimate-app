"""What the coach says about the games database and about a game it loaded (review 03.11).

Two classes the live run of 03.11 caught after the coach could load any database game:

  * a claim about the database that no tool of the turn made — «поиск по базе ничего не вернул», «база не отдала
    партию», «у меня нет доступа к базе партий», «в базе только данные о встречах, а не сами ходы» — said on turns
    where search_master_games / get_game_pgn did not run or found the game. Such a sentence is allowed only after
    a database tool of the turn came back empty or failed (``db_claim_issues``);
  * a move of the loaded game told wrong — «33.d8=Q+» for 33.d8=R+, «на 4-м ходу белые взяли пешку на e4» for
    4...Nxe4, «на 25-й ход чёрная пешка пошла на f5» for 25.f5. A numbered move, or a move number with who moved,
    which piece, what it took and where, is read against the game's main line (``loaded_game_issues``).

The server records the turn's database results and the game it loaded (``note_tool_result``,
``note_board_game``); with nothing recorded nothing is judged (the voice check, the lesson tutor). Conditions,
alternatives, negations and other games are never read as claims: a right sentence cut is worse than a wrong one
let through.
"""

from __future__ import annotations

import io
import json
import logging
import re
from typing import Optional

import chess
import chess.pgn

logger = logging.getLogger(__name__)

DB_TOOLS = ("search_master_games", "get_game_pgn", "find_games_by_position")


# ── what the turn's database tools said ─────────────────────────────────────────────────────────────────────────

def _status(tool: str, data) -> Optional[str]:
    """'found' / 'empty' / 'error' for one database tool's result."""
    if isinstance(data, dict):
        if data.get("error"):
            return "error"
        if tool == "get_game_pgn":
            return "found" if data.get("pgn") else "empty"
        games = data.get("games") if "games" in data else data.get("results")
        if isinstance(games, list):
            return "found" if games else "empty"
        return "found" if data else "empty"
    if isinstance(data, list):
        return "found" if data else "empty"
    return None


def note_tool_result(ctx, tool_name: str, result, shown: bool = True) -> None:
    """Record a database tool's outcome on the check context, and the game get_game_pgn put on the board."""
    if ctx is None or tool_name not in DB_TOOLS:
        return
    try:
        data = json.loads(result) if isinstance(result, str) else result
    except (TypeError, ValueError):
        data = None
    status = _status(tool_name, data) or "error"
    ctx.__dict__.setdefault("db_results", []).append((tool_name, status))
    if tool_name == "get_game_pgn" and shown and isinstance(data, dict) and data.get("board_actions"):
        for action in data["board_actions"]:
            if isinstance(action, dict) and action.get("type") == "load_pgn" and action.get("pgn"):
                note_board_game(ctx, action["pgn"], data.get("headers") or {}, data.get("moves") or [])


def note_board_game(ctx, pgn: str, headers: Optional[dict] = None, moves: Optional[list] = None) -> None:
    """The database game on the board (loaded this turn, or there from an earlier one): its main line, headers and
    the move list the rewrite of a wrong sentence is given."""
    if ctx is None or not pgn:
        return
    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except Exception:  # noqa: BLE001
        game = None
    if game is None:
        return
    board = game.board()
    line = []
    for move in game.mainline_moves():
        if move not in board.legal_moves:
            break
        line.append((board.copy(stack=False), move))
        board.push(move)
    if not line:
        return
    heads = dict(headers or {}) or dict(game.headers)
    ctx.loaded_game = line
    ctx.master_game = {k: heads.get(k, "") for k in ("White", "Black", "Event", "Date", "Result")}
    if not moves:
        from src.tools.twic_search import move_list

        moves = move_list(pgn)
    ctx.loaded_game_text = (
        f"White {heads.get('White', '?')}, Black {heads.get('Black', '?')}, {heads.get('Event', '')} "
        f"{heads.get('Date', '')}, result {heads.get('Result', '')}.\n" + "\n".join(moves))


def turn_tools_note(ctx) -> str:
    """For the rewrite of a wrong sentence: what the database tools of the turn did, and the game on the board."""
    parts = []
    results = getattr(ctx, "db_results", None) or []
    if results:
        said = ", ".join(f"{t} — {s}" for t, s in results)
        parts.append(f"## Database tools of this turn\n{said}. Say about the database only what these results say.")
    game = getattr(ctx, "loaded_game_text", None)
    if game:
        parts.append("## The database game on the board (a master game the coach loaded; it is not the student's "
                     "game — no «ты/you» for its sides). Tell it only from this list:\n" + game)
    return "\n\n".join(parts)


def master_game_side_note(ctx) -> str:
    """Whose side «ты» is when the board holds a master game the coach loaded: nobody's."""
    game = getattr(ctx, "master_game", None)
    if not game:
        return ""
    return (f"The board shows a master game the coach loaded (White {game.get('White') or '?'}, Black "
            f"{game.get('Black') or '?'}): neither side is the student — never «ты», «твой», \"you\" for a side of "
            "it; name the players or the colours.")


# ── claims about the database ───────────────────────────────────────────────────────────────────────────────────

_B = r"(?<![\w-])"
_E = r"(?![\w-])"
# The database, a search of it, a game of it.
_DB_WORD = re.compile(_B + r"(?:баз\w*|поиск\w*|database|db|search\w*|базада\w*|базасы\w*|дерекқор\w*)" + _E, re.IGNORECASE)
_NOTHING = re.compile(
    r"ничего\s+не\s+(?:дал|дала|дало|вернул\w*|наш\w*|наход\w*|выда\w*|показ\w*)|не\s+(?:отдал\w*|отда[её]т|вернул\w*|"
    r"нашл\w*|наш[её]л|нашлось|наход\w*|выдал\w*|выда[её]т|содерж\w*|хран\w*|смог\w*\s+найти|удалось\s+найти)|"
    r"(?:пуст\w*|пусто)" + _E + r"|нет\s+(?:такой\s+|этой\s+|нужной\s+)?(?:парти\w*|игр\w*|ход\w*|данных|доступа)|"
    r"(?:такой|этой|нужной)\s+парти\w*\s+(?:у\s+меня\s+)?(?:в\s+базе\s+)?нет|отсутству\w*|"
    r"returned\s+nothing|found\s+nothing|(?:couldn'?t|could\s+not|can'?t|cannot|didn'?t|did\s+not)\s+(?:find|get|load|"
    r"access|open)|(?:is|was)\s+not\s+in|isn'?t\s+in|wasn'?t\s+in|no\s+(?:such\s+)?(?:game|games|results?|moves|"
    r"access)|empty|жоқ|табылмады|таба\s+алмадым",
    re.IGNORECASE)
# «нет доступа к базе», «не могу загрузить конкретную партию», «база не хранит ходов», «только данные о встречах».
_NO_ACCESS = re.compile(
    r"нет\s+доступа|не\s+(?:могу|можу|получится|удастся)\s+(?:её\s+|ее\s+|эту\s+)?(?:загрузить|открыть|показать|найти|"
    r"достать|поставить)\s+(?:\w+\s+){0,2}?(?:парти\w*|игр\w*)|no\s+access|(?:can'?t|cannot)\s+(?:load|open|show|"
    r"access)\s+(?:\w+\s+){0,2}?(?:game|database)",
    re.IGNORECASE)
_NO_MOVES = re.compile(
    r"(?:а\s+не|без|нет)\s+(?:сами[хм]?\s+)?ход\w*|только\s+(?:данные|сведения|информаци\w*|результат\w*|заголовк\w*)|"
    r"without\s+(?:the\s+)?moves|no\s+moves|only\s+(?:the\s+)?(?:headers|results|metadata)|not\s+the\s+moves",
    re.IGNORECASE)
_POSITION_WORD = re.compile(r"позици\w*|position\w*", re.IGNORECASE)
# The student's own games (the «Мои партии» section, get_user_games), not the master database: «В базе «Мои партии» у
# тебя пока пусто» is that tool's word.
_OWN_GAMES = re.compile(r"мо(?:и|их|ими)\s+парти\w*|тво(?:и|их|ими)\s+(?:сохран\w+\s+)?парти\w*|сохран[её]нн\w*|"
                        r"your\s+(?:saved\s+)?games|my\s+games|менің\s+ойындарым", re.IGNORECASE)
# A plan or an offer, not a report: «если в базе нет — поищу ещё», «давай посмотрим, нет ли…».
_NOT_A_REPORT = re.compile(_B + r"(?:если|ли|может|возможно|вдруг|if|whether|maybe|perhaps|might)" + _E, re.IGNORECASE)

DB_NOT_RUN_ISSUE = ("the games database was not searched this turn (search_master_games / get_game_pgn did not run): "
                    "never say what it holds, lacks or returned, nor that you have no access to it — the database "
                    "holds the full moves of its games; offer to look the game up instead")
DB_FOUND_ISSUE = ("the database tools of this turn found what was asked (see their results): the claim that the "
                  "database gave nothing, has no such game or no moves is false — tell what was found")


def db_claim_issues(lowered: str, ctx) -> list[str]:
    """«База ничего не вернула» / «нет доступа к базе» / «в базе нет ходов» against the turn's database results."""
    if ctx is None or not getattr(ctx, "db_tracked", False):
        return []
    text = lowered or ""
    db = bool(_DB_WORD.search(text))
    access = bool(_NO_ACCESS.search(text))
    moves = db and bool(_NO_MOVES.search(text))
    nothing = db and bool(_NOTHING.search(text))
    if not (access or moves or nothing) or _NOT_A_REPORT.search(text) or _OWN_GAMES.search(text):
        return []
    results = getattr(ctx, "db_results", None) or []
    about_position = bool(_POSITION_WORD.search(text))
    if moves and not (access or nothing):
        allowed = any(t == "get_game_pgn" and s != "found" for t, s in results)
    else:
        allowed = any(s != "found" and (t != "find_games_by_position" or about_position) for t, s in results)
    if allowed:
        return []
    return [DB_FOUND_ISSUE if results else DB_NOT_RUN_ISSUE]


# ── the moves of the loaded game ────────────────────────────────────────────────────────────────────────────────

_SAN = r"(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?)"
_NUMBERED = re.compile(r"(?<![\w.])(?P<num>\d{1,3})\s?(?P<dots>\.\.\.|…|\.)\s?(?P<san>" + _SAN + r")(?P<chk>[+#])?(?![\w])")
# Alternatives, conditions, threats, other games: not what was played.
_ALTERNATIVE = re.compile(
    _B + r"(?:вместо|лучше|сильнее|точнее|стоило|следовало|можно|надо\s+было|нужно\s+было|мог\w*|если|бы|угрож\w*|"
    r"грозил\w*|грозит|грозя|вариант\w*|альтернатив\w*|ошибк\w*|напрашивал\w*|предлага\w*|"
    r"instead|better|stronger|could|should|would|if|threat\w*|alternative|missed|possible)" + _E, re.IGNORECASE)
_NOT = re.compile(_B + r"(?:не|нет|ни|not|never|n'?t)" + _E, re.IGNORECASE)
_YEAR = re.compile(r"(?<!\d)(?:1[5-9]\d\d|20\d\d)(?!\d)")
_ORDINAL = re.compile(
    r"(?:на|в|с)\s+(?P<a>\d{1,3})(?:-?(?:м|ом|ем|й|ом))?\s+ход\w*|(?P<b>\d{1,3})-?(?:й|ой|ый|ом|м|ым)\s+ход\w*|"
    r"ход\w*\s+(?:номер\s+)?(?P<c>\d{1,3})(?![\d.])|(?:on|at|by)\s+move\s+(?P<d>\d{1,3})|move\s+(?P<e>\d{1,3})(?![\d.])",
    re.IGNORECASE)
_SIDE_NOM = re.compile(_B + r"(?P<s>белые|ч[её]рные|white|black)" + _E, re.IGNORECASE)
_PIECE_NOM = {"пешка": chess.PAWN, "конь": chess.KNIGHT, "слон": chess.BISHOP, "ладья": chess.ROOK,
              "ферзь": chess.QUEEN, "король": chess.KING}
_PIECE_ACC = {"пешку": chess.PAWN, "коня": chess.KNIGHT, "слона": chess.BISHOP, "ладью": chess.ROOK,
              "ферзя": chess.QUEEN, "короля": chess.KING}
_PIECE_EN = {"pawn": chess.PAWN, "knight": chess.KNIGHT, "bishop": chess.BISHOP, "rook": chess.ROOK,
             "queen": chess.QUEEN, "king": chess.KING}
_ADJ_SIDE = re.compile(_B + r"(?P<s>бел(?:ая|ый)|ч[её]рн(?:ая|ый))\s+(?P<p>пешка|конь|слон|ладья|ферзь|король)" + _E,
                       re.IGNORECASE)
_CAPTURE = re.compile(_B + r"(?:взял\w*|взяли|взять|забрал\w*|забира\w*|побил\w*|съел\w*|сбил\w*|бь[её]т|бьют|"
                      r"took|takes|captur\w*)" + _E, re.IGNORECASE)
_MOVED = re.compile(_B + r"(?:пош[её]л|пошла|пошли|сыграл\w*|сходил\w*|ответил\w*|двинул\w*|перев[её]л\w*|"
                    r"отош[её]л\w*|отступил\w*|встал\w*|play\w*|went|moved|answered|replied)" + _E, re.IGNORECASE)
_SQUARE = re.compile(r"(?<![a-z0-9])[a-h][1-8](?![0-9])")


def _same(board: chess.Board, san: str, move: chess.Move) -> Optional[bool]:
    try:
        return board.parse_san(san) == move
    except ValueError:
        return None  # not a move there: src/answer_check.py says it is impossible


def _label(board: chess.Board, move: chess.Move) -> str:
    return f"{board.fullmove_number}{'.' if board.turn == chess.WHITE else '...'}{board.san(move)}"


def _plies(line: list, num: int) -> list:
    return [(b, m) for b, m in line if b.fullmove_number == num]


def _fits(board: chess.Board, move: chess.Move, want: dict) -> bool:
    if want.get("sq") is not None and move.to_square != want["sq"]:
        return False
    piece = board.piece_at(move.from_square)
    if want.get("mover") is not None and (piece is None or piece.piece_type != want["mover"]):
        return False
    if want.get("capture") and not board.is_capture(move):
        return False
    if want.get("victim") is not None:
        victim = board.piece_at(move.to_square) if not board.is_en_passant(move) else chess.Piece(chess.PAWN, not board.turn)
        if victim is None or victim.piece_type != want["victim"]:
            return False
    if want.get("san"):
        if _same(board, want["san"], move) is not True:
            return False
    return True


def _window(text: str, start: int, end: int) -> str:
    """The clause around a move number: back to the clause's start, on to the end of what follows it."""
    left = max(text.rfind(c, 0, start) for c in ".;:—–!?,(") + 1
    nxt = [i for i in (text.find(c, end) for c in ".;—–!?") if i >= 0]
    right = min(nxt) if nxt else len(text)
    return text[left:min(right, end + 90)]


def _names_other_player(text: str, game: dict) -> bool:
    """*text* names a known player who is neither side of the game on the board."""
    from src.player_names import _NAME_TOKEN, known_player

    sides = f"{game.get('White') or ''} {game.get('Black') or ''}".lower()
    if not sides.strip():
        return False
    for tok in _NAME_TOKEN.findall(text.lower()):
        pats = known_player(tok) if len(tok) >= 4 else None
        if pats and not any(p.strip("%").lower().replace("_", "") in sides for p in pats):
            return True
    return False


def loaded_game_issues(original: str, ctx) -> list[str]:
    """The moves told of the database game on the board, against its main line."""
    line = getattr(ctx, "loaded_game", None) if ctx is not None else None
    if not line:
        return []
    from src.answer_check import _to_san

    text, _ = _to_san(original or "")
    low = text.lower().replace("ё", "е")
    if _ALTERNATIVE.search(low):
        return []
    game = getattr(ctx, "master_game", None) or {}
    year = str(game.get("Date") or "")[:4]
    if any(y != year for y in _YEAR.findall(low)):
        return []  # another game named by its year
    if _names_other_player(original or "", game):
        return []  # «в партии Карлсен — Каруана на 20-м ходу…» while Nakamura's game is on the board
    out: list[str] = []
    # (a) «33.d8=Q+»: a numbered move is the game's move at that number
    for m in _NUMBERED.finditer(text):
        num, white = int(m["num"]), m["dots"] == "."
        at = [(b, mv) for b, mv in _plies(line, num) if (b.turn == chess.WHITE) == white]
        if not at:
            continue
        board, move = at[0]
        if _same(board, m["san"], move) is False:
            out.append(f"{num}{m['dots']}{m['san']} was not played in the game on the board: at that move it went "
                       f"{_label(board, move)} (tell the game's moves only from its move list)")
            break  # the rest of the line follows from the wrong move
    if out:
        return out
    # (b) «на 4-м ходу белые взяли пешку на e4», «25-й ход: чёрная пешка пошла на f5», «на 11-м ходу пошли Nd3+»
    for m in _ORDINAL.finditer(low):
        num = int(next(g for g in m.groups() if g))
        window = _window(low, m.start(), m.end())
        if _NOT.search(window):
            continue
        orig_window = _window(text, m.start(), m.end())
        want: dict = {}
        side = None
        adj = _ADJ_SIDE.search(window)
        if adj:
            side = chess.WHITE if adj["s"].startswith("бел") else chess.BLACK
            want["mover"] = _PIECE_NOM[adj["p"]]
        s = _SIDE_NOM.search(window)
        if s and side is None:
            side = chess.WHITE if s["s"].startswith(("бел", "white")) else chess.BLACK
        verb = _CAPTURE.search(window) or _MOVED.search(window)
        if not verb:
            continue
        want["capture"] = bool(_CAPTURE.search(window))
        before, after = window[:verb.start()], window[verb.end():]
        if "mover" not in want:
            nom = re.search(_B + r"(пешка|конь|слон|ладья|ферзь|король)" + _E, window)
            if nom:
                want["mover"] = _PIECE_NOM[nom.group(1)]
            else:
                en = re.search(_B + r"(pawn|knight|bishop|rook|queen|king)" + _E, before)
                if en:
                    want["mover"] = _PIECE_EN[en.group(1)]
        if want["capture"]:
            acc = re.search(_B + r"(пешку|коня|слона|ладью|ферзя|короля|pawn|knight|bishop|rook|queen|king)" + _E, after)
            if acc:
                want["victim"] = _PIECE_ACC.get(acc.group(1)) or _PIECE_EN.get(acc.group(1))
        sq = _SQUARE.search(after)
        if sq:
            want["sq"] = chess.parse_square(sq.group(0))
        san = re.search(r"(?<![\w])" + _SAN + r"(?![\w])", orig_window[orig_window.lower().find(verb.group(0)):]
                        if verb.group(0) in orig_window.lower() else "")
        if san and san.group(0)[0] in "KQRBN" or (san and "x" in san.group(0)):
            want["san"] = san.group(0)
        if not any(want.get(k) is not None for k in ("sq", "mover", "victim", "san")) and not want["capture"]:
            continue
        at = _plies(line, num)
        if not at:
            continue
        mine = [(b, mv) for b, mv in at if side is None or b.turn == side]
        if any(_fits(b, mv, want) for b, mv in mine):
            continue
        played = " ".join(_label(b, mv) for b, mv in at)
        other = [(b, mv) for b, mv in at if side is not None and b.turn != side and _fits(b, mv, want)]
        claim = orig_window.strip()
        if other:
            who = "White" if other[0][0].turn == chess.WHITE else "Black"
            out.append(f"«{claim}» is wrong: at move {num} it was {who} — {played} in the game on the board")
        else:
            out.append(f"«{claim}» does not match the game on the board: at move {num} it went {played}")
        break
    return out


def game_db_issues(lowered: str, original: str, ctx) -> list[str]:
    """Both checks above; never raises."""
    out: list[str] = []
    for check, args in ((db_claim_issues, (lowered, ctx)), (loaded_game_issues, (original, ctx))):
        try:
            out += check(*args)
        except Exception:  # noqa: BLE001 — the check must never break a turn
            logger.debug("%s failed", check.__name__, exc_info=True)
    return out
