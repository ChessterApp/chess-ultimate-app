"""An opening asked about by name: the book line on the board and in the turn.

On production (2026-09-30) a student asked «как играть против жареной печени».
The coach took the quiet Italian that stood on the board for it, called the
Fried Liver «the Italian reversed», and explained the fork with a knight
jumping f3-d5. The ECO book has the line (C57) and every defence against it,
but the Russian slang name reached neither the book nor the model's tools.

When the student's message names an opening (src/openings_book.named_opening),
the server now does before the model is called:

  * finds the line in the book (named lines: exact name; families: the root);
  * puts it on the student's board — unless the board already stands in that
    opening — so the answer and the board talk about the same position;
  * gives the model the line, where the book lets either side deviate from it
    (the defences: 5...Na5, 4...Bc5, …) and plain facts of its final position
    (the knight f7 attacks the queen d8 and the rook h8).

COACH_OPENING_PRESTEP=0 turns it off (config.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import chess

from src.openings_book import RU_FAMILY, _split_moves, get_book, named_opening

# Messages that search the games database name openings too («партии Карлсена
# в сицилианской») — the games tool answers those; the board is left alone.
_SEARCH_RE = re.compile(r"(?<![а-яёa-z])(найд|найт|поищ|поиск|find|search)", re.IGNORECASE)

# Russian names of named lines, for the block (the model answers in Russian and
# otherwise translates «Fried Liver» on its own).
RU_NAMED = {
    "Italian Game: Two Knights Defense, Fried Liver Attack": "атака «жареная печень» (Fegatello)",
    "Italian Game: Two Knights Defense, Traxler Counterattack": "контратака Траксля (Уилкс-Барре)",
    "Italian Game: Two Knights Defense, Polerio Defense": "защита Полерио (5...Na5)",
    "Italian Game: Two Knights Defense": "защита двух коней",
    "Italian Game: Giuoco Piano": "джуоко пиано (тихая итальянская)",
    "Italian Game: Giuoco Pianissimo": "джуоко пианиссимо",
    "Scholar's Mate": "детский мат",
    "Barnes Opening: Fool's Mate": "дурацкий мат",
    "Légal Trap": "мат Легаля",
    "Blackburne Shilling Trap": "ловушка Блэкберна (гамбит Блэкберна–Костича)",
    "Queen's Pawn Game: London System": "лондонская система",
}


@dataclass
class OpeningPlan:
    name: str
    eco: str
    pgn: str
    final_fen: str
    load: bool                    # the server puts the line on the board
    block: str                    # the turn-context block for the model
    branches: list = field(default_factory=list)
    relative: bool = False        # the question is about the board, the opening is a reference
    hidden: bool = False          # the student's own position stays; the line is analysed on a hidden board


def _move_label(ply: int, san: str) -> str:
    """Ply 8, 'Na5' → '5...Na5'; ply 9, 'd4' → '5. d4' (ply 0 = White's first)."""
    number = ply // 2 + 1
    return f"{number}. {san}" if ply % 2 == 0 else f"{number}...{san}"


def _short_name(name: str) -> str:
    """'Italian Game: Two Knights Defense, Polerio Defense' → 'Two Knights Defense, Polerio Defense'."""
    return name.split(":", 1)[1].strip() if ":" in name else name


def _board_after(pgn: str) -> chess.Board:
    board = chess.Board()
    for san in _split_moves(pgn):
        board.push_san(san)
    return board


def _key(board: chess.Board) -> str:
    """Placement + side to move."""
    return " ".join(board.fen().split()[:2])


def _board_in_opening(line_pgn: str, board_fen: Optional[str], board_pgn: Optional[str]) -> bool:
    """The student's board already shows this opening: a game that follows the
    line (the student may be stepping through it), the line's final position,
    or a book position deeper in it. The start position and 1.e4 e5 are on the
    way to every opening — they are not «in» one."""
    line = _split_moves(line_pgn)
    if board_pgn:
        game = _split_moves(board_pgn)
        if len(game) >= len(line) and game[: len(line)] == line:
            return True
    if not board_fen:
        return False
    try:
        key = _key(chess.Board(board_fen))
    except ValueError:
        return False
    if key == _key(_board_after(line_pgn)):
        return True
    found = get_book().by_position(board_fen)
    if found:
        deeper = _split_moves(found["book_line"])
        return len(deeper) >= len(line) and deeper[: len(line)] == line
    return False


def _facts(board: chess.Board) -> list[str]:
    from src.position_facts import static_facts

    if board.is_checkmate():
        loser = "White" if board.turn == chess.WHITE else "Black"
        return [f"{loser} is checkmated."]
    facts = static_facts(board)
    if board.is_check():
        facts.insert(0, f"{'White' if board.turn == chess.WHITE else 'Black'} is in check.")
    return facts


# «как играть против…», «как защищаться», «how to avoid»: the student meets the line.
_AGAINST_RE = re.compile(r"против|защит|избеж|отвеча|against|avoid|defen|meet|counter", re.IGNORECASE)

# The question is about the position on the board, with the opening as a
# destination or a comparison — «как из этой позиции перейти в защиту двух
# коней», «хочу перевести игру в лондонскую», «похоже на дракона?». A tester
# (01.10) played a few moves and asked to steer into another opening: the
# server put that opening's line on the board from move one and his position
# was gone. The board is left alone for these; the model gets the line and
# how it compares with what was played.
_RELATIVE_RE = re.compile(
    r"из\s+(?:этой|текущей|моей|данной|такой)\s+позици|с\s+этой\s+позици|отсюда|перейти|перевести|перевод|"
    r"транспо|транспониро|в\s+эту\s+позици|текущ\w*\s+позици|сейчас\s+на\s+доске|на\s+доске\s+сейчас|"
    r"похож[аеио]?\s+(?:ли\s+)?(?:это\s+)?на|это\s+(?:уже\s+)?(?:он[аи]?|тот|та)\b|получилась|получается|"
    r"from\s+(?:this|the\s+current|my)\s+position|transpos|steer\s+(?:into|to|towards)|get\s+(?:into|to)\s+(?:the|a)\s|"
    r"is\s+this\s+(?:the|a)\b|does\s+this\s+look\s+like",
    re.IGNORECASE)


def asks_about_the_board(message: str) -> bool:
    return bool(_RELATIVE_RE.search((message or "").replace("ё", "е")))


def _compare_with_line(line_pgn: str, board_pgn: Optional[str], board_fen: Optional[str]) -> str:
    """How the board relates to the line, in words the model can rely on."""
    line = _split_moves(line_pgn)
    if board_pgn:
        game = _split_moves(board_pgn)
        k = 0
        while k < len(line) and k < len(game) and line[k].rstrip("+#") == game[k].rstrip("+#"):
            k += 1
        played = " ".join(_move_label(i, m) for i, m in enumerate(game)) or "(no moves)"
        if k == len(line):
            return (f"Moves on the board: {played}. The line was played in full; the board is {len(game) - k} "
                    f"plies beyond it.")
        if k == len(game):
            return (f"Moves on the board: {played}. They follow the line so far; the line continues "
                    f"{_move_label(k, line[k])}.")
        return (f"Moves on the board: {played}. The board left the line at {_move_label(k, game[k])} "
                f"(the line has {_move_label(k, line[k])} there). Moves already played cannot be taken back: "
                f"say whether the line's structure is still reachable from the board, and how, or that it is not.")
    if board_fen:
        try:
            board = chess.Board(board_fen)
        except ValueError:
            return ""
        if board.fullmove_number <= 1 and board.turn == chess.WHITE:
            return "The board shows the starting position."
        return (f"The board (no move list): {board_fen}. Compare the pieces with the line's final position and "
                f"say what differs and whether the line's structure is still reachable.")
    return ""


def build_block(name: str, eco: str, pgn: str, branches: list, loaded: bool, facts: list[str],
                message: str = "", relative: Optional[str] = None, hidden: bool = False) -> str:
    ru = RU_NAMED.get(name) or RU_FAMILY.get(name.split(":")[0].strip())
    title = f"{eco} {name}" + (f" — по-русски: {ru}" if ru else "")
    lines = [
        "## The opening the student asked about (ECO book, verified — not from memory)",
        title,
        f"Book line: {pgn}",
    ]
    if loaded:
        lines.append("The server has ALREADY put this line on the student's board (the final position is "
                     "shown; the student can step through the moves). Do not load or set it again.")
    elif hidden:
        lines.append("The student's OWN position stays on the board (they did not ask to change it): the line "
                     "was played on a HIDDEN board and analysed there — do not load it, do not call it «the "
                     "board», draw no arrows for it. Explain the opening in words from this block, and end by "
                     "offering to put the line on the board: a short «покажи» from the student will do it.")
    elif relative:
        lines.append("The student asks about the position ON THE BOARD in relation to this opening (how to "
                     "get there from it, whether it is the same, what differs). The board was LEFT AS IT IS — "
                     "do not load the line and do not replace the position; the line below is a reference. "
                     + (relative or ""))
    else:
        lines.append("The student's board already stands in this opening; it was left as it is.")
    if facts:
        lines.append("Facts of the final position of the line (checked on the board): "
                     + "; ".join(f.rstrip(".") for f in facts) + ".")
    # The side whose move ends the line is the one playing it; the other meets it.
    player = chess.WHITE if len(_split_moves(pgn)) % 2 == 1 else chess.BLACK
    meets = "Black" if player == chess.WHITE else "White"
    plays = "White" if player == chess.WHITE else "Black"
    length = len(_split_moves(pgn))
    goes_on = [b for b in branches if b["ply"] >= length]
    earlier = [b for b in branches if b["ply"] < length]
    # How much book follows a choice is how much it is played: the main defence
    # (5...Na5 against the Fried Liver) has far more lines than 4...Nxe4.
    all_moves = [_split_moves(e[2]) for e in get_book().entries]
    for b in branches:
        prefix = _split_moves(b["line"])[: b["ply"] + 1]
        b["book_lines"] = sum(1 for m in all_moves if m[: len(prefix)] == prefix)
    defences = sorted((b for b in earlier if (b["ply"] % 2 == 1) == (player == chess.WHITE)),
                      key=lambda b: -b["book_lines"])
    tries = [b for b in earlier if b not in defences]
    if defences:
        lines.append(f"Book choices for {meets} (the side that meets this line — its defences and ways to "
                     f"avoid it), the most played first (by the number of book lines after it):")
        for b in defences:
            lines.append(f"- {_move_label(b['ply'], b['move'])} — {_short_name(b['name'])} ({b['eco']}, "
                         f"{b['book_lines']} book lines): {b['line']}")
    if tries:
        lines.append(f"Other book tries for {plays}:")
        for b in tries:
            lines.append(f"- {_move_label(b['ply'], b['move'])} — {_short_name(b['name'])} ({b['eco']}): {b['line']}")
    if goes_on:
        lines.append("How the line goes on in the book:")
        for b in goes_on:
            lines.append(f"- {_move_label(b['ply'], b['move'])} — {_short_name(b['name'])} ({b['eco']}): {b['line']}")
    if defences and _AGAINST_RE.search(message or ""):
        lines.append(f"The student asks how to meet it: recommend {meets}'s main book choice above (the "
                     f"first one), say at which move it comes and why it works, and name one more; do "
                     f"not advise walking into the line itself.")
    lines.append(
        "Answer about THIS opening from this block: what it is, the idea of each side, the trap or "
        "the main threat, and — when the student asks how to play against it — which alternative "
        "to choose and why. Any move you name must come from these lines, the engine block or a "
        "tool result; do not invent moves, squares or attacks. Say which side the student plays "
        "if the question says it («чёрными», «против …» means the other side's opening). "
        + ("Answer from the board as it stands: which moves of the line are still possible, which are "
           "not, and what the student can do from here."
           if relative else
           "The position the board showed before is not what the student asked about.")
    )
    return "\n".join(lines)


# «как называется дебют …», «что за дебют», "what opening is …", «қандай дебют»: the name is asked for.
_ASKS_THE_NAME = re.compile(
    r"как\s+(?:он\s+|это\s+)?называ|что\s+(?:это\s+)?за\s+(?:дебют|защит|вариант|систем|начал)|какой\s+(?:это\s+)?дебют"
    r"|какая\s+(?:это\s+)?(?:защита|система)|какой\s+(?:это\s+)?вариант|назван\w*\s+(?:дебют|защит|вариант)"
    r"|what\s+(?:opening|defen[cs]e|variation)|which\s+opening|name\s+of\s+(?:the|this)\s+(?:opening|line)"
    r"|қандай\s+дебют|дебют\w*\s+ат", re.IGNORECASE)
_PIECE_BEFORE = {"кон": "N", "слон": "B", "лад": "R", "ферз": "Q", "корол": "K", "knight": "N", "bishop": "B",
                 "rook": "R", "queen": "Q", "king": "K"}
_LINE_TOKEN = re.compile(r"(?<![\w-])(?:O-O(?:-O)?|[KQRBNКФЛСКр]{0,2}[a-h]?[1-8]?[x:х×]?[a-h][1-8](?:=[QRBN])?)(?![\w-])")


def line_named(message: str) -> list[str]:
    """The moves *message* lists from the start, in order — «е4 … е6», «1.e4 c5 2.Кf3», «конь f3» — as SAN; a token
    that is no legal move of the line so far is passed over."""
    from src.move_text import normalize
    from src.notation import russian_to_san

    # «e2-e4 e7-e5»: each from-to move joined first, or normalize() pairs «e4 e7» across the space
    text = normalize(re.sub(r"(?<![\w-])([a-h][1-8])\s*[-–—]\s*([a-h][1-8])(?![\w-])", r"\1\2", message or ""))
    board, sans = chess.Board(), []

    def play(token: str, piece: Optional[str]) -> bool:
        for cand in ([piece + token] if piece and token[0] in "abcdefgh" else []) + [token]:
            try:
                move = board.parse_san(cand)
            except ValueError:
                continue
            sans.append(board.san(move))
            board.push(move)
            return True
        return False

    for m in _LINE_TOKEN.finditer(text):
        token = russian_to_san(m.group(0))
        before = text[max(0, m.start() - 14):m.start()].lower()
        piece = next((p for w, p in _PIECE_BEFORE.items() if re.search(w + r"\w*\s+(?:на\s+|to\s+)?$", before)), None)
        if re.fullmatch(r"[a-h][1-8][a-h][1-8]", token):
            # normalize() joins «e4 c5» into «e4c5» (a move said square to square): a move from-to if it is one,
            # else the two moves of the line
            move = chess.Move.from_uci(token)
            if move in board.legal_moves:
                sans.append(board.san(move))
                board.push(move)
            else:
                play(token[:2], piece)
                play(token[2:], None)
        else:
            play(token, piece)
        if len(sans) >= 30:
            break
    return sans


def _numbered(sans: list[str]) -> str:
    return " ".join((f"{i // 2 + 1}." if i % 2 == 0 else "") + san for i, san in enumerate(sans))


def plan_opening(message: str, board_fen: Optional[str] = None,
                 board_pgn: Optional[str] = None, show: Optional[bool] = None) -> Optional[OpeningPlan]:
    """The opening *message* names, ready for the turn — or None.

    *show* False: the board is the student's own and they did not ask to see the line — it is not
    loaded; the plan says ``hidden`` and the caller analyses ``final_fen`` on a hidden board
    (src/question_position, 2026-10-20). None keeps the old rule (load unless the board is in the opening).
    """
    if not message or _SEARCH_RE.search(message):
        return None
    name = named_opening(message)
    named_line: list[str] = []
    if not name:
        # «Как называется дебют, где белые играют е4, а чёрные отвечают е6?» — no name in the words, the moves are:
        # the book names them (stand run 28.10: the voice coach got «found: false» and said it could not tell).
        named_line = line_named(message) if _ASKS_THE_NAME.search(message) else []
        identified = get_book().identify(named_line) if len(named_line) >= 2 else None
        name = (identified or {}).get("name")
    if not name:
        return None
    book = get_book()
    entry = book.exact(name) or next(iter(book.by_name(name)), None)
    if entry is None:
        return None
    eco, full_name, pgn = entry
    try:
        final = _board_after(pgn)
    except ValueError:
        return None
    in_opening = _board_in_opening(pgn, board_fen, board_pgn)
    relative = None
    if not in_opening and asks_about_the_board(message) and not _is_start(board_fen):
        relative = _compare_with_line(pgn, board_pgn, board_fen)
    load = not in_opening and relative is None
    hidden = load and show is False
    load = load and not hidden
    branches = book.branches(full_name, pgn)
    block = build_block(full_name, eco, pgn, branches, load, _facts(final), message, relative, hidden)
    if named_line:
        block = (f"The moves the student named — {_numbered(named_line)} — are the opening below (the ECO book, by those "
                 "moves): say its name.\n" + block)
    return OpeningPlan(
        name=full_name, eco=eco, pgn=pgn, final_fen=final.fen(), load=load,
        block=block, branches=branches, relative=relative is not None, hidden=hidden,
    )


def _is_start(fen: Optional[str]) -> bool:
    if not fen:
        return True
    try:
        return _key(chess.Board(fen)) == _key(chess.Board())
    except ValueError:
        return True


def mentions_opening(message: str) -> bool:
    """The message names an opening (for the tool subset: keep the opening tools)."""
    return named_opening(message or "") is not None
