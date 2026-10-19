"""The position a theory question is about — built on a hidden board, not the student's (2026-10-20).

Asan's rule (16.10): a theory question («расскажи про шотландскую», «ферзь против ладьи — это
выигрыш?», «что такое вилка») is answered from a second board the student does not see: the
position the question is about is built there, Stockfish and the tablebase look at it, and the
model gets verified facts. The board in front of the student changes only when it is nobody's
(the start position, an empty board), when the coach itself put the last position up (an earlier
example, an opening line — the student is browsing), or when the student asks to see it
(«покажи», «поставь на доску»). Before, an opening named in a question replaced the student's own
position from move one (a tester's complaint, 01.10, fixed then for «из этой позиции» only), a
topic's example replaced it for every «что такое …», and an endgame named by its material was
not built at all — the answer came from the model's head.

Three readers here:
  * who owns the board — ``student_owns`` / ``show_on_board``;
  * the endgame a question names by material — ``endgame_theory`` («ладья и слон против ладьи»,
    «мат двумя слонами», "queen vs rook"): a verified position of that material, the textbook
    verdict and the method, for the engine and the tablebase to confirm;
  * the turn-context blocks for a hidden analysis — ``hidden_note_block``, ``endgame_block``.
"""

from __future__ import annotations

import re
from typing import Optional

import chess

# «покажи», «поставь на доску», «расставь», «загрузи», "show me", "set it up", "put it on the board".
_WANTS_SHOWN = re.compile(
    r"(?<![\w-])(?:покажи\w*|показать|поставь\w*|поставить|расставь\w*|расставить|загрузи\w*|загрузить|"
    r"выведи|на\s+доск[еу]|show(?:\s+me)?|put\s+(?:it\s+|this\s+)?(?:up|on\s+the\s+board)|set\s+(?:it\s+)?up|"
    r"load|display|көрсет\w*|тақтаға)(?![\w-])", re.IGNORECASE)
_DEFAULT_BOARDS = frozenset({chess.STARTING_BOARD_FEN, "8/8/8/8/8/8/8/8"})


def wants_shown(text: str) -> bool:
    """The student asks to see it on the board."""
    return bool(_WANTS_SHOWN.search(text or ""))


def is_default_board(fen: Optional[str]) -> bool:
    """The start position or an empty board: nobody's to keep."""
    return not fen or fen.split()[0] in _DEFAULT_BOARDS


def by_coach(board) -> bool:
    """The last position on *board* was put there by the coach (an example, a line, a puzzle)."""
    source = getattr(board, "source", None) or {}
    return bool(isinstance(source, dict) and source.get("coach"))


def student_owns(board) -> bool:
    """The position on *board* is the student's own: they set it, played it or loaded it — not the
    start position, not what the coach last put up."""
    if board is None:
        return False
    fen = getattr(board, "fen", None)
    return not is_default_board(fen) and not by_coach(board)


def show_on_board(message: str, board) -> bool:
    """Whether a position the question is about may go on the student's board this turn."""
    return not student_owns(board) or wants_shown(message)


# ── Endgames named by their material ────────────────────────────────────────

_PIECE_RE = (
    r"(?P<n>дв[аеу]х?|двумя|две|2|тр[иёе]х?|тремя|3|two|three)?\s*"
    r"(?P<p>ферз(?:ь|я|ю|ем|ём|и|ей|ям|ями)|лад(?:ья|ьи|ье|ью|ьей|ьёй|ьям|ьями|ей)|"
    r"слон(?:а|у|ом|ы|ов|ам|ами|е)?|кон(?:ь|я|ю|ем|ём|и|ей|ям|ями)|пеш(?:ка|ки|ке|ку|кой|ек|кам|ками)|"
    r"queens?|rooks?|bishops?|knights?|pawns?|уәзір\w*|тура\w*|піл\w*|ат(?:тар)?|пешка\w*)(?![\w-])"
)
_PIECE = re.compile(r"(?<![\w-])" + _PIECE_RE, re.IGNORECASE)
_SPLIT = re.compile(r"\s+(?:против|vs\.?|versus|v\.|қарсы)\s+", re.IGNORECASE)
_LONE_KING = re.compile(r"(?<![\w-])(?:корол\w*|king|корол|патша\w*)(?![\w-])", re.IGNORECASE)
_MATE_WITH = re.compile(r"(?<![\w-])(?:мат\w*|заматовать|checkmate|mate|мат\s+қою)(?![\w-])", re.IGNORECASE)
_LETTER = {"ферз": "Q", "лад": "R", "слон": "B", "кон": "N", "пеш": "P", "queen": "Q", "rook": "R", "bishop": "B",
           "knight": "N", "pawn": "P", "уәзір": "Q", "тура": "R", "піл": "B", "ат": "N"}
_COUNT = {"дв": 2, "two": 2, "2": 2, "тр": 3, "three": 3, "3": 3}
_VALUE = {"Q": 9, "R": 5, "B": 3, "N": 3, "P": 1}
_RU = {"Q": ("ферзь", "два ферзя"), "R": ("ладья", "две ладьи"), "B": ("слон", "два слона"),
       "N": ("конь", "два коня"), "P": ("пешка", "две пешки")}
_RU_GEN = {"Q": ("ферзя", "двух ферзей"), "R": ("ладьи", "двух ладей"), "B": ("слона", "двух слонов"),
           "N": ("коня", "двух коней"), "P": ("пешки", "двух пешек")}


def _side_pieces(text: str) -> Optional[str]:
    """'QR' (sorted by value) for the pieces *text* names; '' for a lone king; None for no pieces."""
    letters = []
    for m in _PIECE.finditer(text):
        word = m.group("p").lower()
        letter = next((v for k, v in _LETTER.items() if word.startswith(k)), None)
        if not letter:
            continue
        n = m.group("n")
        count = 1
        if n:
            count = next((v for k, v in _COUNT.items() if n.lower().startswith(k)), 1)
        letters += [letter] * count
    if not letters:
        return "" if _LONE_KING.search(text) else None
    return _sorted(letters)


def _sorted(letters) -> str:
    return "".join(sorted(letters, key="QRBNP".index))


def board_material(fen: Optional[str]) -> Optional[tuple[str, str]]:
    """The material on *fen* as ``material_in`` writes it — ('R', 'P') for a rook against a pawn — or None
    (no board, more than 7 pieces: not a textbook ending)."""
    if not fen:
        return None
    try:
        board = chess.Board(fen)
    except ValueError:
        return None
    if len(board.piece_map()) > 7:
        return None
    sides = {chess.WHITE: [], chess.BLACK: []}
    for piece in board.piece_map().values():
        if piece.piece_type != chess.KING:
            sides[piece.color].append(piece.symbol().upper())
    a, b = _sorted(sides[chess.WHITE]), _sorted(sides[chess.BLACK])
    if sum(_VALUE[x] for x in b) > sum(_VALUE[x] for x in a):
        a, b = b, a
    return a, b


def material_in(text: str) -> Optional[tuple[str, str]]:
    """The two sides' pieces a question names, strongest side first — ('QR', '') for «ферзь и ладья
    против короля», ('Q', 'R') for «ладья против ферзя», ('BB', '') for «мат двумя слонами»; None
    when the question names no such pairing."""
    t = (text or "").replace("ё", "е")
    parts = _SPLIT.split(t, maxsplit=1)
    if len(parts) == 2:
        a, b = _side_pieces(parts[0]), _side_pieces(parts[1])
        if a is None or b is None or (a == "" and b == ""):
            return None
    elif _MATE_WITH.search(t):
        a = _side_pieces(t)
        # «мат конём», «мат слоном», «мат пешкой» are tactics (the piece delivers the mate — the site's own
        # sets), not the endgame of a lone minor piece or pawn against the king.
        if not a or a in ("B", "N", "P"):
            return None
        b = ""
    else:
        return None
    if sum(_VALUE[x] for x in b) > sum(_VALUE[x] for x in a):
        a, b = b, a
    return a, b


def _ru_side(pieces: str, genitive: bool = False) -> str:
    """«ладья и слон» / «ладьи и слона» (after «против»); «король» for a lone king."""
    if not pieces:
        return "короля" if genitive else "король"
    forms = _RU_GEN if genitive else _RU
    groups = []
    for letter in "QRBNP":
        n = pieces.count(letter)
        if n == 1:
            groups.append(forms[letter][0])
        elif n == 2:
            groups.append(forms[letter][1])
        elif n > 2:
            groups.append(f"{n} {forms[letter][0]}")
    return " и ".join(groups)


# The textbook endgames, one verified position each (checked legal and quiet — no piece hangs, no
# check — by tests/unit/test_hidden_board_2026_10_20.py; the engine and the tablebase judge the
# position itself at run time). ``result`` is the textbook verdict for the material in general.
ENDGAMES: dict[str, dict] = {
    "Q|": {"fen": "8/8/8/4k3/8/8/8/3QK3 w - - 0 1", "result": "win", "kb": "basic-checkmates",
           "method": "the queen takes squares a knight's move away from the king and drives it to the edge "
                     "without checking; the own king comes up; mate on the edge; watch for stalemate. "
                     "About 10 moves from anywhere."},
    "R|": {"fen": "8/8/8/4k3/8/8/8/R3K3 w - - 0 1", "result": "win", "kb": "basic-checkmates",
           "method": "the rook cuts the king off along a rank or a file, the own king takes the opposition, a "
                     "rook check pushes the king back one line at a time; mate on the edge. Up to 16 moves."},
    "QR|": {"fen": "8/8/8/4k3/8/8/8/R2QK3 w - - 0 1", "result": "win",
            "method": "queen and rook mate easily: the staircase with checks on neighbouring ranks, or the queen "
                      "alone drives the king to the edge while the rook cuts it off; watch for stalemate."},
    "RR|": {"fen": "8/8/8/4k3/8/8/8/R3K2R w - - 0 1", "result": "win",
            "method": "the «staircase» (ladder) mate: the rooks check on neighbouring ranks in turn, each one "
                      "driving the king one rank towards the edge; the own king is not needed."},
    "BB|": {"fen": "8/8/8/4k3/8/8/8/2B1KB2 w - - 0 1", "result": "win",
            "method": "the two bishops side by side build a wall of diagonals, the king is driven to the edge "
                      "and then into a corner; the own king supports; mate in a corner. Up to 19 moves."},
    "BN|": {"fen": "8/8/8/4k3/8/8/8/2B1K1N1 w - - 0 1", "result": "win",
            "method": "mate is possible only in a corner of the bishop's colour; the king is driven to the "
                      "edge, then along it to the right corner (the «W» manoeuvre of the knight). Up to 33 "
                      "moves — the hardest elementary mate; the 50-move rule is a real danger."},
    "NN|": {"fen": "8/8/8/4k3/8/8/8/1N2K1N1 w - - 0 1", "result": "draw",
            "method": "two knights cannot force mate against a lone king: the mating position exists, but the "
                      "last move before it is always stalemate unless the defender walks into it. (With a "
                      "defending pawn the Troitsky line decides — a special case.)"},
    "B|": {"fen": "8/8/8/4k3/8/8/8/2B1K3 w - - 0 1", "result": "draw",
           "method": "a single bishop cannot mate: insufficient material, the game is drawn at once."},
    "N|": {"fen": "8/8/8/4k3/8/8/8/4K1N1 w - - 0 1", "result": "draw",
           "method": "a single knight cannot mate: insufficient material, the game is drawn at once."},
    "P|": {"fen": "8/8/4k3/8/4K3/4P3/8/8 b - - 0 1", "result": "depends", "kb": "opposition-and-key-squares",
           "method": "king and pawn against king is decided by the opposition and the key squares: the king "
                     "in front of its pawn on a key square wins regardless of the move; the defender who holds "
                     "the opposition in front of the pawn draws. A rook pawn draws whenever the defender's king "
                     "reaches the corner (or the attacker's king is locked in front of its own pawn). In the "
                     "position here it is Black to move and White wins; with White to move the same position "
                     "is a draw."},
    "Q|R": {"fen": "8/r7/3k4/8/8/8/8/2Q1K3 w - - 0 1", "result": "win",
            "method": "queen against rook is a win, but a long one (up to 31 moves): the defender keeps the "
                      "rook next to the king (the third-rank / Philidor defence); the attacker drives the king "
                      "to the edge and wins the rook by zugzwang or a fork of king and rook. Checks must be "
                      "aimed at separating king and rook."},
    "Q|B": {"fen": "8/8/3kb3/8/8/8/8/2Q1K3 w - - 0 1", "result": "win",
            "method": "queen against bishop is a straightforward win: the king is driven to the edge, the "
                      "bishop is won by a fork or the king is mated with the queen and king."},
    "Q|N": {"fen": "8/8/3k4/4n3/8/8/8/2Q1K3 w - - 0 1", "result": "win",
            "method": "queen against knight is a win: separate the knight from its king, then it is lost to a "
                      "fork, or the king is mated on the edge."},
    "Q|P": {"fen": "8/7Q/8/8/8/2k5/3p4/7K w - - 0 1", "result": "depends",
            "method": "queen against a pawn on the seventh rank: a centre pawn (d or e) or a knight pawn (b or "
                      "g) loses — the queen forces the king in front of the pawn with checks, winning a tempo "
                      "each time for the own king to approach. A bishop pawn (c or f) or a rook pawn (a or h) "
                      "with the attacking king far away is a DRAW: the defender gets stalemate when the king "
                      "steps into the corner (bishop pawn) or in front of the pawn (rook pawn). The position "
                      "here is the winning case (d-pawn)."},
    "R|B": {"fen": "8/8/3kb3/8/8/8/8/R3K3 w - - 0 1", "result": "draw",
            "method": "rook against bishop (no pawns) is a draw with correct defence: the defender keeps the "
                      "king in the SAFE corner — the corner of the opposite colour to the bishop — and the "
                      "bishop nearby; in the wrong corner (the bishop's colour) the position is lost."},
    "R|N": {"fen": "8/8/3kn3/8/8/8/8/R3K3 w - - 0 1", "result": "draw",
            "method": "rook against knight (no pawns) is a draw: the knight stays next to its king in the "
                      "centre; the defender loses only when the knight is separated from the king or the king "
                      "is driven into a corner."},
    "R|P": {"fen": "8/8/8/8/3k4/3p4/8/R3K3 w - - 0 1", "result": "depends",
            "method": "rook against pawn: the rook wins when its king gets in front of the pawn or the pawn "
                      "can be cut off and won; a far-advanced pawn supported by its king, with the rook's "
                      "king far away, draws (and in rare cases queens). The rule: count whether the rook's "
                      "king reaches the queening square in time — the rook alone cannot stop a supported "
                      "pawn on the seventh."},
    "RB|R": {"fen": "3r4/8/3k4/8/8/8/8/2R1KB2 w - - 0 1", "result": "draw",
             "method": "rook and bishop against rook is a draw with correct defence, but hard: the defender "
                       "keeps the king away from the edge, or uses the second-rank (Cochrane) defence; "
                       "the Philidor position (defending king on the edge, kings facing) is lost. The "
                       "attacker tries to win within 50 moves."},
    "RN|R": {"fen": "3r4/8/3k4/8/8/8/8/2R1K1N1 w - - 0 1", "result": "draw",
             "method": "rook and knight against rook is a draw: the defender keeps the king in the centre and "
                       "the rook active, giving checks from a distance; lost only with the king trapped on the "
                       "edge."},
    "RP|R": {"fen": "1K6/1P1k4/8/8/8/8/r7/2R5 w - - 0 1", "result": "depends", "kb": "lucena-position",
             "method": "rook and pawn against rook depends on the kings: with the attacking king in front of "
                       "the pawn on the seventh the Lucena position wins («building a bridge» — the rook on "
                       "the fourth rank shelters the king from checks); with the defending king in front of "
                       "the pawn the Philidor position draws (the rook on the third rank until the pawn "
                       "advances, then checks from behind). A rook pawn is usually a draw. The position here "
                       "is Lucena, a win for White."},
    "Q|Q": {"fen": "3q4/8/3k4/8/8/8/8/2Q1K3 w - - 0 1", "result": "draw",
            "method": "queen against queen without pawns is a draw: perpetual check. With a far-advanced "
                      "passed pawn the stronger side often wins by hiding the king from checks behind the "
                      "pawn or forcing a queen trade with check."},
    "R|R": {"fen": "3r4/8/3k4/8/8/8/8/2R1K3 w - - 0 1", "result": "draw",
            "method": "rook against rook without pawns is a draw. With pawns, rook endings are the most common "
                      "endgame: the rook belongs behind the passed pawn, the king goes to the centre, and an "
                      "extra pawn is often not enough («all rook endings are drawn» — a joke with truth in it)."},
    "B|B": {"fen": "8/8/3kb3/8/8/8/8/2B1K3 w - - 0 1", "result": "draw",
            "method": "bishop against bishop without pawns is a draw. With pawns: bishops of the SAME colour "
                      "give the extra pawn normal winning chances; bishops of OPPOSITE colours are the most "
                      "drawish ending — even two pawns up is often a draw, because the defender blocks the "
                      "pawns on squares the attacking bishop cannot attack."},
    "B|N": {"fen": "8/8/3kn3/8/8/8/8/2B1K3 w - - 0 1", "result": "draw", "kb": "bishop-vs-knight",
            "method": "bishop against knight without pawns is a draw. With pawns, the bishop is stronger with "
                      "pawns on both wings and open play; the knight is stronger in closed positions, with "
                      "pawns on one wing and with an outpost."},
    "N|N": {"fen": "8/8/3kn3/8/8/8/8/4K1N1 w - - 0 1", "result": "draw",
            "method": "knight against knight without pawns is a draw (no mating material)."},
    "RR|Q": {"fen": "3q4/8/3k4/8/8/8/8/R3K2R w - - 0 1", "result": "draw",
             "method": "queen against two rooks without pawns is a draw in general (the rooks protect each "
                       "other and give checks; the queen cannot win one of them); with pawns the two rooks "
                       "are often the better side, the queen's chances come from forks and a weak king."},
    "Q|BB": {"fen": "8/8/3k4/3bb3/8/8/8/2Q1K3 w - - 0 1", "result": "win",
             "method": "queen against two bishops is a win in general but a long one; a few fortress "
                       "positions (bishops and king huddled together) hold the draw."},
    "Q|BN": {"fen": "8/8/3k4/3bn3/8/8/8/2Q1K3 w - - 0 1", "result": "win",
             "method": "queen against bishop and knight is a win in general, with a few fortresses; the "
                       "method is to separate the minor pieces from the king and win one by a fork."},
    "Q|NN": {"fen": "8/8/3k4/3nn3/8/8/8/2Q1K3 w - - 0 1", "result": "win",
             "method": "queen against two knights is a win in general but one of the hardest; the knights "
                       "next to their king in the centre can hold for a long time."},
    "BB|N": {"fen": "8/8/3kn3/8/8/8/8/2B1KB2 w - - 0 1", "result": "win",
             "method": "two bishops against a knight is a win in general (up to 66 moves — the 50-move rule "
                       "can rescue the defender); the knight must be driven away from its king."},
    "BP|": {"fen": "7k/8/8/6KP/8/3B4/8/8 w - - 0 1", "result": "depends", "kb": "wrong-bishop",
            "method": "bishop and pawn against king wins — except the «wrong bishop»: a rook pawn whose "
                      "queening square is not of the bishop's colour, with the defending king in (or reaching) "
                      "that corner, is a draw: the king cannot be driven out of the corner without stalemate. "
                      "The position here is that drawn case."},
}


def endgame_theory(message: str) -> Optional[dict]:
    """The textbook endgame *message* names by its material, or None: {"key", "title", "sides", "fen",
    "result", "method", "kb"} — «ладья против слона», «как поставить мат конём и слоном», "queen vs rook"."""
    sides = material_in(message)
    if not sides:
        return None
    key = f"{sides[0]}|{sides[1]}"
    entry = ENDGAMES.get(key)
    if entry is None:
        return None
    strong, weak = sides
    head = "Король и пешка" if strong == "P" else _ru_side(strong).capitalize()
    title = f"{head} против {'короля' if not weak else _ru_side(weak, genitive=True)}"
    return {"key": key, "title": title, "sides": (strong, weak), "fen": entry["fen"], "result": entry["result"],
            "method": entry["method"], "kb": entry.get("kb")}


_RESULT_WORDS = {"win": "a WIN for the stronger side with correct play",
                 "draw": "a DRAW with correct defence",
                 "depends": "DEPENDS on the position — see the method"}


def endgame_block(theory: dict, note: Optional[str], shown: bool) -> str:
    """The turn-context block for an endgame named by its material: the textbook verdict and method, the
    verified position (on the student's board or on the hidden one), and the engine's look at it."""
    strong, weak = theory["sides"]
    lines = [
        f"## The endgame the student asked about — {theory['title']} (textbook, verified position)",
        f"Material: King + {' + '.join(chess.piece_name(chess.Piece.from_symbol(c).piece_type) for c in strong)} "
        f"against King" + (f" + {' + '.join(chess.piece_name(chess.Piece.from_symbol(c).piece_type) for c in weak)}" if weak else " alone")
        + f". Textbook result: {_RESULT_WORDS[theory['result']]}.",
        f"Method: {theory['method']}",
        f"A typical position of this material: {theory['fen']}" + (
            " — the server has ALREADY put it on the student's board (do not set it again; you may draw arrows on it)."
            if shown else
            " — on a HIDDEN board, not on the student's: the student's own position stays in front of them. "
            "Explain in words; do not describe this position as «the board», draw no arrows for it, and end by "
            "offering to put it on the board — a short «покажи» from the student will do it."),
    ]
    if note:
        lines.append(f"Engine and tablebase on that position: {note}")
    lines.append(
        "Answer the theory question from this block: the result, WHY (the method), and the key idea the student "
        "should remember. Any move you name must be legal in the position above or in the engine line; never "
        "invent a position, a square or a line. If the student's question is about THEIR position on the board "
        "rather than the theory, answer about their board instead."
    )
    return "\n".join(lines)


def hidden_note_block(note: str, what: str) -> str:
    """The engine's look at a position on the hidden board (an opening line's final position, a famous game's
    end), as a turn-context block."""
    return (
        f"## Engine analysis on a hidden board — {what}\n"
        f"{note}\n"
        "Stockfish analysed this position on a second board the student does NOT see; their own position stays "
        "in front of them. Use the facts in your own coaching words — what the last move threatens, what the "
        "best reply is — without calling it «the board» and without arrows; the student can say «покажи» to see it."
    )
