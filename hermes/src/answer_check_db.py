"""What the coach says about the games database and about a game it loaded (review 03.11).

Two classes the live run of 03.11 caught after the coach could load any database game:

  * a claim about the database that no tool of the turn made — «поиск по базе ничего не вернул», «база не отдала
    партию», «у меня нет доступа к базе партий», «в базе только данные о встречах, а не сами ходы» — said on turns
    where search_master_games / get_game_pgn did not run or found the game. Such a sentence is allowed only after
    a database tool of the turn came back empty or failed (``db_claim_issues``). The claim and the database are
    read in one clause, and only the games database counts — not the web, the engine's search, the tablebase, an
    account or a link, nor the student's own games; a search of an earlier turn is judged against what the
    database said then, and «этой партии нет, но есть другие» against a search that found other games
    (verification 04.11);
  * a move of the loaded game told wrong — «33.d8=Q+» for 33.d8=R+, «на 4-м ходу белые взяли пешку на e4» for
    4...Nxe4, «на 25-й ход чёрная пешка пошла на f5» for 25.f5. A numbered move, or a move number with who moved,
    which piece, what it took and where, is read against the game's main line (``loaded_game_issues``) — when the
    sentence tells that game (its players, «в партии», told as played) or the line it writes follows the game
    first; an opening's moves, a puzzle, a what-if, the student's game are other lines (verification 04.11).

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
    if tool_name == "search_master_games" and status == "found":
        # which games came back: «партии 2019 года в базе нет» after a search that found only 2026 ones is true
        games = data.get("games") if isinstance(data, dict) else data
        found = ctx.__dict__.setdefault("db_found_games", [])
        found += [g for g in (games or []) if isinstance(g, dict)][:50]
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
# The games database by name. Not «поиск / search» alone: the engine's search, a web search, «в поисках контригры»
# are no database (verification 04.11: 18 of 200 true sentences cut).
_DB_WORD = re.compile(_B + r"(?:баз\w*|database\w*|db|twic|базада\w*|базасы\w*|дерекқор\w*)" + _E, re.IGNORECASE)
# …unless the base is another one — the tablebase, the puzzles, the opening book, the topics («база знаний»): the
# check is about the games database only.
_OTHER_BASE = re.compile(
    _B + r"(?:эндшпильн\w*|таблиц\w*|налимов\w*|syzygy|tablebase\w*|задач\w*|пазл\w*|puzzle\w*|упражнени\w*|"
    r"дебютн\w*|книг\w*|знани\w*|opening\s+(?:book|explorer)|endgame)" + _E, re.IGNORECASE)
_GAMES_BASE = re.compile(r"баз\w*\s+(?:партий|данных\s+партий)|партий\s+мастеров|games?\s+database|database\s+of\s+games|"
                         r"twic", re.IGNORECASE)
# A source that is not the games database, named in the claim: the web, the engine, an account, a link, a rating list,
# a broadcast, the microphone — «нет доступа к рейтинг-листу», «поиск в интернете ничего не дал».
_OTHER_SOURCE = re.compile(
    _B + r"(?:интернет\w*|сет(?:и|ь)|web|google|гугл\w*|онлайн\w*|online|новост\w*|news|движ(?:ок|ка|ку|ком|ке)|"
    r"engine\w*|stockfish|стокфиш\w*|lichess\w*|личес\w*|chess\.com|чесском\w*|аккаунт\w*|account\w*|профил\w*|"
    r"profile\w*|ссылк\w*|link\w*|url|рейтинг\w*|rating\w*|fide|фиде|трансляци\w*|broadcast\w*|микрофон\w*|"
    r"microphone|камер\w*|camera)" + _E, re.IGNORECASE)
_NOTHING = re.compile(
    r"ничего\s+не\s+(?:дал|дала|дало|вернул\w*|наш\w*|наход\w*|выда\w*|показ\w*)|не\s+(?:отдал\w*|отда[её]т|вернул\w*|"
    r"нашл\w*|наш[её]л|нашлось|наход\w*|выдал\w*|выда[её]т|содерж\w*|хран\w*|смог\w*\s+найти|удалось\s+найти)|"
    r"(?:пуст\w*|пусто)" + _E + r"|нет\s+(?:такой\s+|этой\s+|нужной\s+)?(?:парти\w*|игр\w*|ход\w*|данных|доступа)|"
    r"(?:такой|этой|нужной)\s+парти\w*\s+(?:у\s+меня\s+)?(?:в\s+базе\s+)?нет|отсутству\w*|"
    r"в\s+базе\s+(?:[\w«»-]+\s+){0,3}?нет(?![\w-])|нет\s+в\s+базе|"
    r"returned\s+nothing|found\s+nothing|(?:couldn'?t|could\s+not|can'?t|cannot|didn'?t|did\s+not)\s+(?:find|get|load|"
    r"access|open)|(?:is|was)\s+not\s+in|isn'?t\s+in|wasn'?t\s+in|no\s+(?:such\s+)?(?:game|games|results?|moves|"
    r"access)|empty|жоқ|табылмады|таба\s+алмадым",
    re.IGNORECASE)
# «нет доступа к базе», «не могу загрузить конкретную партию … из базы» — said of the database, in the same clause
# (verification 04.11: «нет доступа к рейтинг-листу», «не могу открыть эту партию — ссылка…» were cut).
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
# The student's own games (the «Мои партии» section, get_user_games, an import), not the master database: «В базе
# «Мои партии» у тебя пока пусто», «нет доступа к твоим партиям».
_OWN_GAMES = re.compile(r"мо(?:и|их|ими|ю|ей)\s+(?:\w+\s+)?парти\w*|тво(?:и|их|ими|ю|ей|я|ем|им)\s+(?:\w+\s+)?"
                        r"(?:парти\w*|игр\w*)|сохран[её]нн\w*|импорт\w*|your\s+(?:\w+\s+)?games?|my\s+games|"
                        r"менің\s+ойындарым", re.IGNORECASE)
# A plan or an offer, not a report: «если в базе нет — поищу ещё», «давай посмотрим, нет ли…», «пока не найду её в
# базе».
_NOT_A_REPORT = re.compile(_B + r"(?:если|ли|может|возможно|вдруг|if|whether|maybe|perhaps|might|until|"
                           r"пока\s+не\s+(?:найду|поищу|загружу|проверю|посмотрю))" + _E, re.IGNORECASE)
# A search of an earlier turn: judged against what the database said then (the session's recent results).
_EARLIER = re.compile(_B + r"(?:в\s+прошлый\s+раз|раньше|ранее|до\s+этого|прежде|в\s+прошл\w+\s+(?:ход\w*|"
                      r"сообщени\w*|ответ\w*)|тот\s+(?:поиск|раз)|прошл\w+\s+поиск\w*|earlier|last\s+time|"
                      r"previously|before)" + _E, re.IGNORECASE)
# The asked game is missing, but the search found others: «Именно этой партии в базе нет, но есть три других».
_FOUND_OTHER = re.compile(
    _B + r"(?:(?:но|зато|однако|but|though|although)\s+(?:\w+\s+){0,3}?(?:есть|нашл\w*|наш[её]л\w*|наход\w*|"
    r"нашлась|found|got|there\s+(?:are|is|were))|други[хеим]\s+(?:\w+\s+){0,2}?(?:парти\w*|игр\w*)|"
    r"other\s+games?|another\s+game|(?:нашл\w*|наш[её]л\w*|есть)\s+только|only\s+found|found\s+only)" + _E,
    re.IGNORECASE)
# Clauses: a claim and its database are read in one («у меня в этом сеансе нет ссылки на неё, а поиск по базе ничего
# не вернул» — the link is one clause, the database another).
_CLAUSE = re.compile(r"[;:()\[\]—–]|\s-\s|,\s*(?=(?:а|но|однако|зато|but|while|whereas|and)" + _E + r")", re.IGNORECASE)

DB_NOT_RUN_ISSUE = ("the games database was not searched this turn (search_master_games / get_game_pgn did not run): "
                    "never say what it holds, lacks or returned, nor that you have no access to it — the database "
                    "holds the full moves of its games; offer to look the game up instead")
DB_FOUND_ISSUE = ("the database tools of this turn found what was asked (see their results): the claim that the "
                  "database gave nothing, has no such game or no moves is false — tell what was found")
DB_EARLIER_FOUND_ISSUE = ("the earlier database searches of this conversation found games (none came back empty): "
                          "never say an earlier search gave nothing")


def _claims(text: str) -> list:
    """The clauses of *text* that state something about the games database: (kind set, clause)."""
    out = []
    for clause in _CLAUSE.split(text or ""):
        low = clause.lower().replace("ё", "е")
        if not _DB_WORD.search(low):
            continue
        if (_OTHER_BASE.search(low) and not _GAMES_BASE.search(low)) or _OTHER_SOURCE.search(low) \
                or _NOT_A_REPORT.search(low) or _OWN_GAMES.search(low):
            continue
        kinds = {k for k, rx in (("access", _NO_ACCESS), ("moves", _NO_MOVES), ("nothing", _NOTHING)) if rx.search(low)}
        if kinds:
            out.append((kinds, clause))
    return out


def _like(pattern: str) -> "re.Pattern":
    return re.compile(re.escape(pattern.lower()).replace("%", ".*").replace("_", "."))


def _asked_not_returned(clause: str, ctx) -> bool:
    """The clause names a year or a player none of the games the search returned has: the search found other games,
    not the one the sentence says is missing."""
    games = getattr(ctx, "db_found_games", None) or []
    if not games:
        return False
    years = {str(g.get("date") or "")[:4] for g in games}
    if any(y not in years for y in re.findall(r"(?<!\d)(?:1[5-9]\d\d|20\d\d)(?!\d)", clause)):
        return True
    from src.player_names import _NAME_TOKEN, known_player, name_patterns

    names = [f"{g.get('white_name') or g.get('White') or ''}|{g.get('black_name') or g.get('Black') or ''}".lower()
             for g in games]
    for i, tok in enumerate(_NAME_TOKEN.findall(clause)):
        if len(tok) < 4 or not (known_player(tok) or (i and tok[0].isupper())):
            continue
        pats = [_like(p) for p in name_patterns(tok)]
        if pats and not any(p.search(n) for p in pats for n in names):
            return True
    return False


def db_claim_issues(lowered: str, ctx, original: Optional[str] = None) -> list[str]:
    """«База ничего не вернула» / «нет доступа к базе» / «в базе нет ходов» against the database's results."""
    if ctx is None or not getattr(ctx, "db_tracked", False):
        return []
    claims = _claims(original if original is not None else lowered)
    if not claims:
        return []
    results = getattr(ctx, "db_results", None) or []
    whole = (original if original is not None else lowered) or ""
    for kinds, clause in claims:
        about_position = bool(_POSITION_WORD.search(clause))
        if _EARLIER.search(clause):
            # «в прошлый раз поиск ничего не нашёл»: what the database said on the conversation's earlier turns
            earlier = getattr(ctx, "db_results_earlier", None) or []
            if not earlier or any(s != "found" for t, s in earlier + results):
                continue
            return [DB_EARLIER_FOUND_ISSUE]
        if kinds == {"moves"}:
            allowed = any(t == "get_game_pgn" and s != "found" for t, s in results)
        else:
            allowed = any(s != "found" and (t != "find_games_by_position" or about_position) for t, s in results)
            if not allowed and "nothing" in kinds and any(t == "search_master_games" and s == "found"
                                                          for t, s in results):
                # the search found games, but not the one asked: «этой партии нет, но есть три других»
                allowed = bool(_FOUND_OTHER.search(whole)) or _asked_not_returned(clause, ctx)
        if not allowed:
            return [DB_FOUND_ISSUE if results else DB_NOT_RUN_ISSUE]
    return []


# ── the moves of the loaded game ────────────────────────────────────────────────────────────────────────────────

_SAN = r"(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)"
# A move of a written line: numbered («20.Qc2», «20...Bxg2») or not («d5» right after «1.d4»).
_LINE_MOVE = re.compile(r"(?<![\w.])(?:(?P<num>\d{1,3})\s?(?P<dots>\.\.\.|…|\.)\s?)?(?P<san>" + _SAN +
                        r")(?P<chk>[+#])?(?![\w])")
# Alternatives, conditions, threats, other games: not what was played.
_ALTERNATIVE = re.compile(
    _B + r"(?:вместо|лучше|сильнее|точнее|стоило|следовало|можно|надо\s+было|нужно\s+было|мог\w*|если|бы|угрож\w*|"
    r"грозил\w*|грозит|грозя|вариант\w*|альтернатив\w*|ошибк\w*|напрашивал\w*|предлага\w*|"
    r"instead|better|stronger|could|should|would|if|threat\w*|alternative|missed|possible)" + _E, re.IGNORECASE)
_NOT = re.compile(_B + r"(?:не|нет|ни|not|never|n'?t)" + _E, re.IGNORECASE)
_YEAR = re.compile(r"(?<!\d)(?:1[5-9]\d\d|20\d\d)(?!\d)")
# The sentence is about the game on the board: it is «в партии / в этой партии / in the game», or tells it as played
# («сыграли», «пошла», «взял», "played") — not a line of theory, a puzzle, a what-if («На 20.Qc2 чёрные ответят…»,
# «Итальянская партия начинается 1.e4 e5») — verification 04.11: 19 of 30 such sentences were cut.
_IN_THE_GAME = re.compile(
    _B + r"(?:(?:в|из)\s+(?:(?:этой|той|их|самой|всей|данной)\s+)?(?:парти[ия]|игре)|в\s+ней|всю\s+партию|"
    r"парти[яю]\s+(?:пошла|продолжил\w*|началась|закончил\w*|шла)|in\s+(?:the|this|that)\s+game|the\s+game\s+"
    r"(?:went|continued|began|ended))" + _E, re.IGNORECASE)
_PLAYED = re.compile(
    _B + r"(?:взял\w*|взяли|забрал\w*|побил\w*|съел\w*|сбил\w*|пош[её]л|пошла|пошли|сыграл\w*|сходил\w*|ответил\w*|"
    r"двинул\w*|перев[её]л\w*|провел\w*|провёл\w*|отош[её]л\w*|отступил\w*|встал\w*|последовал\w*|был\w*\s+сыгран\w*|"
    r"начал(?:и|а|ось)?|жертвовал\w*|пожертвовал\w*|took|captured|played|went|moved|answered|replied|followed|"
    r"sacrificed|pushed|promoted)" + _E, re.IGNORECASE)
# …and not the student's own game, a puzzle, an exercise: «В твоей прошлой партии на 12-м ходу ты взял…».
_NOT_THIS_GAME = re.compile(
    _B + r"(?:тво(?:ей|ю|я|ем|их|и)\s+(?:\w+\s+)?(?:парти\w*|игр\w*)|сво(?:ей|ю)\s+(?:\w+\s+)?парти\w*|"
    r"(?:прошл|предыдущ|друг|следующ)\w+\s+парти\w*|ты\s+(?:\w+\s+){0,2}?(?:взял|сыграл|пош[её]л|ходил|сходил|"
    r"двинул|побил|забрал|ответил|отдал|пожертвовал)\w*|your\s+(?:\w+\s+)?game|you\s+(?:\w+\s+)?(?:played|took|"
    r"moved|captured)|задач\w*|этюд\w*|упражнени\w*|puzzle\w*|exercise\w*|study)" + _E, re.IGNORECASE)
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
# Two plies of the game written in a row before the wrong one tie a line to the game («20.Qa2 Bxg2 21.Kxg1»).
_TIED_PLIES = 2


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


def _side_names(game: dict) -> str:
    return f"{game.get('White') or ''}|{game.get('Black') or ''}".lower()


def _names_other_player(text: str, game: dict) -> bool:
    """*text* names a known player who is neither side of the game on the board."""
    from src.player_names import _NAME_TOKEN, known_player

    sides = _side_names(game).replace("|", " ")
    if not sides.strip():
        return False
    for tok in _NAME_TOKEN.findall(text.lower()):
        pats = known_player(tok) if len(tok) >= 4 else None
        if pats and not any(p.strip("%").lower().replace("_", "") in sides for p in pats):
            return True
    return False


def _names_a_side(text: str, game: dict) -> bool:
    """*text* names White or Black of the game on the board, in any script («Абдусатторов», «Nakamura»)."""
    from src.player_names import _NAME_TOKEN, name_patterns

    sides = _side_names(game)
    if not sides.strip("|"):
        return False
    surnames = [s.split(",")[0].strip() for s in sides.split("|") if s.strip()]
    for i, tok in enumerate(_NAME_TOKEN.findall(text or "")):
        if len(tok) < 4 or not tok[0].isupper():
            continue
        low = tok.lower().replace("ё", "е")
        if any(len(s) >= 4 and (low.startswith(s) or s.startswith(low)) for s in surnames):
            return True
        if any(_like(p).search(sides) for p in name_patterns(tok)):
            return True
    return False


def _other_opening(text: str, line: list) -> bool:
    """*text* names an opening the game on the board did not reach («Итальянская партия начинается…» beside a
    Catalan): its moves are that opening's, not the game's. By position, so a transposition is the game's own."""
    try:
        from src.openings_book import _split_moves, get_book, named_openings

        names = named_openings(text)
        if not names:
            return False
        reached = {(b.board_fen(), b.turn) for b, _ in line[:40]}
        if line[:40]:
            last, move = line[:40][-1]
            after = last.copy(stack=False)
            after.push(move)
            reached.add((after.board_fen(), after.turn))
        book = get_book()
        for name, _ in names:
            for entry in book.by_name(name, limit=3) or []:
                board = chess.Board()
                try:
                    for san in _split_moves(entry[2]):
                        board.push_san(san)
                except ValueError:
                    continue
                if (board.board_fen(), board.turn) in reached:
                    return False  # the game's own opening («Испанская партия, и на 4-м ходу…»)
        return True
    except Exception:  # noqa: BLE001 — without the book an opening named is another line
        return True


def _about_the_game(original: str, low: str, game: dict, line: list) -> Optional[bool]:
    """True: the sentence tells the game on the board; False: another game, a line of theory, a puzzle, the
    student's game; None: it does not say (a numbered move alone is then a line of its own)."""
    if _names_a_side(original, game):
        return True
    if _NOT_THIS_GAME.search(low) or _other_opening(original, line):
        return False
    if _IN_THE_GAME.search(low) or _PLAYED.search(low):
        return True
    return None


def _numbered_issue(text: str, line: list, about: Optional[bool]) -> Optional[str]:
    """(a) «33.d8=Q+» for 33.d8=R+: the first move of a written line that leaves the game, judged when the sentence
    tells the game or two plies of the game came right before it. Otherwise the line that leaves the game is another
    line («1.d4 d5 2.c4» beside 1.d4 Nf6: a Queen's Gambit, not the game) and so is the rest of the sentence."""
    at = None  # index into *line* of the next ply the written line reaches
    tied = 0
    last_end = -1
    for m in _LINE_MOVE.finditer(text):
        contiguous = last_end >= 0 and not text[last_end:m.start()].strip(" ,")
        last_end = m.end()
        num = m["num"]
        if num is None:
            if not contiguous or at is None:
                at = None
                continue  # «пешку на e5»: a square, or a move of a line not followed
            if at >= len(line):
                return None
            board, move = line[at]
            same = _same(board, m["san"], move)
            if same is True:
                at, tied = at + 1, tied + 1
                continue
            if same is False and (about is True or (about is None and tied >= _TIED_PLIES)):
                return (f"{_label(board, board.parse_san(m['san']))} was not played in the game on the board: at "
                        f"that move it went {_label(board, move)} (tell the game's moves only from its move list)")
            return None  # the line left the game at a move without a number: another line
        white = m["dots"] == "."
        idx = next((i for i, (b, _) in enumerate(line)
                    if b.fullmove_number == int(num) and (b.turn == chess.WHITE) == white), None)
        if idx is None:
            at = None
            continue
        if not (contiguous and at == idx):
            tied = 0  # a new line starts here
        board, move = line[idx]
        same = _same(board, m["san"], move)
        if same is True:
            at, tied = idx + 1, tied + 1
            continue
        if same is None:
            return None  # not a move of the game's position there: src/answer_check.py judges it
        if about is True or (about is None and tied >= _TIED_PLIES):
            return (f"{num}{m['dots']}{m['san']} was not played in the game on the board: at that move it went "
                    f"{_label(board, move)} (tell the game's moves only from its move list)")
        return None  # another line: theory, a what-if, a puzzle — and the rest of the sentence goes on with it
    return None


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
    about = _about_the_game(original or "", low, game, line)
    if about is False:
        return []
    issue = _numbered_issue(text, line, about)
    if issue:
        return [issue]
    if about is not True:
        return []  # «На 12-м ходу белые берут пешку» with nothing tying it to the game: not judged
    out: list[str] = []
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


def forget_board_game(ctx) -> None:
    """The database game left the board (a puzzle, a position, another game put up): nothing is judged against it,
    and the rewrite no longer hears of it (mirrors src/boards.Board._forget_db_game; verification 04.11)."""
    if ctx is None:
        return
    for name in ("loaded_game", "master_game", "loaded_game_text"):
        if getattr(ctx, name, None) is not None:
            setattr(ctx, name, None)


def game_db_issues(lowered: str, original: str, ctx) -> list[str]:
    """Both checks above; never raises."""
    out: list[str] = []
    for check, args in ((db_claim_issues, (lowered, ctx, original)), (loaded_game_issues, (original, ctx))):
        try:
            out += check(*args)
        except Exception:  # noqa: BLE001 — the check must never break a turn
            logger.debug("%s failed", check.__name__, exc_info=True)
    return out
