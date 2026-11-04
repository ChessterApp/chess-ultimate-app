"""The Laws of Chess a rules question is about, said to the model as facts (2026-10-13).

Rules questions are answered from the model's head, and the same question went both ways on one day:
«У меня кончилось время, а у соперника остался только король. Кто победил?» — «ничья» in one run,
«победил соперник» in the next; «Позиция повторилась три раза, но не подряд» — «Нет, не ничья». The
rule each question is about is matched by its words and given as it stands in the FIDE Laws.
"""

from __future__ import annotations

import re
from typing import Optional

import chess

_W = r"(?<![\w-])"

# (words that mean the question is about this rule, the rule as the FIDE Laws state it)
RULES = (
    (re.compile(_W + r"(?:врем\w*|флаг\w*|time|clock|flag\w*|уақыт\w*)", re.IGNORECASE),
     re.compile(_W + r"(?:кончил\w*|вышл\w*|упал\w*|истекл\w*|просроч\w*|ran\s+out|runs?\s+out|lost\s+on\s+time|flag\w*|бітті|таусыл\w*)",
                re.IGNORECASE),
     "Time: a player whose time runs out loses — UNLESS the opponent cannot checkmate by any series of legal "
     "moves (a lone king, king and bishop, king and knight): then the game is a DRAW (FIDE Laws 6.9)."),
    (re.compile(_W + r"(?:тр[её]хкрат\w*|повторени\w*|повтор\w*\s+(?:\w+\s+)?(?:три|3|трижды)|repetition|repeated\s+(?:three|3)|"
                     r"қайтал\w*)", re.IGNORECASE), None,
     "Repetition: the same position (same side to move, same castling and en passant rights) occurring three "
     "times — not necessarily in a row — lets the player to move claim a draw; five times ends the game as a "
     "draw automatically (FIDE 9.2, 9.6.1)."),
    (re.compile(r"(?:правил\w*\s+)?(?<![\d])50\s*(?:-?\s*ти\s+)?ход\w*|fifty[-\s]move|50[-\s]move|75\s*ход\w*", re.IGNORECASE), None,
     "Fifty moves: 50 moves by each side with no capture and no pawn move let a player claim a draw; after 75 "
     "such moves the game is drawn automatically (FIDE 9.3, 9.6.2)."),
    (re.compile(_W + r"(?:рок[иеі]р\w*|castl\w*)", re.IGNORECASE),
     re.compile(_W + r"(?:если|когда|раньше|после|под\s+бо\w*|под\s+удар\w*|шах\w*|атак\w*|бь[её]т|бьют|бит\w+|if|when|after|attacked|check|ever)",
                re.IGNORECASE),
     "Castling is illegal only if the king or that rook has already moved, a piece stands between them, the "
     "king is in check now, or the king would pass through or land on an attacked square. It IS legal when the "
     "rook is attacked or passes an attacked square (b1/b8 in long castling), and when the king was checked "
     "earlier but never moved (FIDE 3.8.2)."),
    (re.compile(_W + r"(?:на\s+проходе|en\s+passant|өтпелі\s+алу)", re.IGNORECASE), None,
     "En passant: only a pawn may take a pawn that has just advanced two squares past it, as if it had moved one, "
     "and only on the very next move — never later, never with another piece (FIDE 3.7.4)."),
    (re.compile(_W + r"(?:превра\w*|promot\w*|второго\s+ферз\w*|two\s+queens|айналд\w*)", re.IGNORECASE), None,
     "Promotion: a pawn reaching the last rank becomes a queen, rook, bishop or knight of its colour, whatever "
     "is already on the board (several queens are fine) — never a king or a pawn (FIDE 3.7.5)."),
    (re.compile(_W + r"(?:пат(?:а|у|ом|е|ов\w*)?|stalemate\w*)(?![\w-])", re.IGNORECASE), None,
     "Stalemate: the side to move has no legal move and is not in check — the game is drawn at once (FIDE 5.2.1)."),
    (re.compile(_W + r"(?:тронул\w*|коснул\w*|дотронул\w*|touch(?:ed)?[-\s]move|touched)", re.IGNORECASE), None,
     "Touch-move: a player who deliberately touches their own piece must move it (and a touched opponent's piece "
     "must be taken) if that is legal; saying «поправляю» / «j'adoube» first allows adjusting (FIDE 4.2–4.3)."),
    (re.compile(_W + r"(?:недостат\w*\s+материал\w*|insufficient\s+material|голый\s+корол\w*|одинок\w+\s+корол\w*|только\s+корол\w*)",
                re.IGNORECASE), None,
     "Insufficient material: with no series of legal moves able to mate (king vs king, king and bishop vs king, "
     "king and knight vs king, bishops all on one colour) the game is drawn (FIDE 5.2.2)."),
)

# How each piece moves (FIDE Laws 3.2–3.8), for a question about a piece's moves («Может ли пешка ходить назад?»,
# "Can a pawn move backwards?", «Пешка артқа жүре ала ма?» — r-pawn-back, prod 29.10: «пешка так и остаётся на
# своей линии до конца партии», when every capture moves it to the next file). Plan 31.10 P6 D; COACH_TURN_FACTS.
_MOVE_WORDS = (r"(?:ходит|ходят|ходить|ходил\w*|сходить|пойти|ид[её]т|двига\w*|передвига\w*|перемеща\w*|"
               r"назад|обратно|вбок|в\s+сторону|наискос\w*|по\s+диагонал\w*|по\s+вертикал\w*|по\s+горизонтал\w*|"
               r"перепрыг\w*|прыга\w*|прыгн\w*|бь[её]т|бьют|бить|берет|берёт|брать|взять|"
               r"moves?|moving|go(?:es)?|backwards?|sideways|diagonally|jumps?|jumping|captures?|capturing|"
               r"жүре\w*|жүр\w*|артқа|алға|секір\w*|қиғаш\w*|ұра\w*)")


def _piece_words(stem: str) -> re.Pattern:
    return re.compile(_W + r"(?:" + stem + r")(?![\w-])[\s\S]{0,60}?" + _W + _MOVE_WORDS + r"(?![\w-])|"
                      + _W + _MOVE_WORDS + r"(?![\w-])[\s\S]{0,40}?" + _W + r"(?:" + stem + r")(?![\w-])", re.IGNORECASE)


MOVE_RULES = (
    (_piece_words(r"пешк\w*|пешек|pawns?|сарбаз\w*"),
     "Pawn: it moves straight forward only — one square, or two from its starting square — never backwards or "
     "sideways. It captures one square diagonally forward, so every capture moves it to the next file: a pawn does "
     "not stay on its file for the whole game (exd5 takes it from e to d). En passant and promotion are its other two "
     "moves (FIDE 3.7)."),
    (_piece_words(r"конь|коня|коню|кон[её]м|коне|кони|коней|коням|конями|knights?|ат|атпен|атты"),
     "Knight: it moves in an L — two squares along a file or rank and one to the side — and is the only piece that "
     "jumps over others; it always lands on a square of the other colour (FIDE 3.6)."),
    (_piece_words(r"слон\w*|bishops?|піл\w*"),
     "Bishop: any number of squares along a diagonal, never over a piece, so it stays on squares of one colour for "
     "the whole game (FIDE 3.2)."),
    (_piece_words(r"ладь\w*|ладей|rooks?|тура\w*|зеңбірек\w*"),
     "Rook: any number of squares along a file or a rank, never over a piece (FIDE 3.3)."),
    (_piece_words(r"ферз\w*|queens?|уәзір\w*"),
     "Queen: any number of squares along a file, a rank or a diagonal, never over a piece (FIDE 3.4)."),
    (_piece_words(r"корол(?:ь|я|ю|ем|ём|е|и|ей|ям|ями|ях)|kings?|патша\w*"),
     "King: one square in any direction, never onto a square an opponent's piece attacks, plus castling (FIDE 3.8)."),
)

# A rules question names no move and asks «можно ли», «что будет», «кто победил», «ничья ли»…
_ASKS_A_RULE = re.compile(
    _W + r"(?:можно\s+ли|можно|разрешено|нельзя|правил\w*|кто\s+(?:победил|выиграл)|ничья|засчита\w*|что\s+будет|"
    r"is\s+it|can\s+i|can\s+a|allowed|legal|rule\w*|who\s+wins|draw|бола\s+ма|ереже\w*)", re.IGNORECASE)
# …and a question about how a piece moves (plan 31.10 P6 D): «может ли», «умеет», «как ходит», "can the/a pawn",
# "move backwards", «жүре ала ма», «ала ма».
_ASKS_A_MOVE_RULE = re.compile(
    _W + r"(?:может\s+ли|могут\s+ли|умеет|умеют|как\s+(?:ходит|ходят|ходить|двига\w+|бь[её]т|бьют|прыга\w+)|"
    r"куда\s+(?:ходит|ходят)|правд\w*\s+ли|разве|"
    r"can\s+(?:a|an|the|it|my|your|pawns?|knights?|bishops?|rooks?|queens?|kings?)|"
    r"how\s+(?:does|do|can)\s+(?:a|an|the)|move\s+backwards?|"
    r"ала\s+ма|бола\s+ма|жүре\s+ме)", re.IGNORECASE)


def _facts_on() -> bool:
    """COACH_TURN_FACTS (src/config.py, plan 31.10): off leaves the rules as they were before 31.10."""
    import os

    raw = os.environ.get("COACH_TURN_FACTS")
    if raw is not None:
        return raw.strip().lower() not in ("0", "false", "no", "off")
    try:
        from src import config

        return bool(getattr(config, "COACH_TURN_FACTS", True))
    except Exception:  # noqa: BLE001
        return True


# A square or a written move: the question is about a position, not about how a piece moves in general.
_NAMES_A_SQUARE = re.compile(r"(?<![\w-])(?:[KQRBNКФЛСо]?x?[a-hа-х][1-8]|O-O(?:-O)?|0-0(?:-0)?)(?![\w-])", re.IGNORECASE)


def _question_rules(text: str) -> list:
    """The rules the question's words are about (RULES, and with COACH_TURN_FACTS the movement rules)."""
    found = []
    if _ASKS_A_RULE.search(text):
        for words, also, rule in RULES:
            if words.search(text) and (also is None or also.search(text)) and rule not in found:
                found.append(rule)
    # How the pieces move — when no Law above is what the question is about («взять на проходе слоном» is en passant,
    # not how a bishop moves) and it names no square or move (then it is about a position).
    if not found and _facts_on() and (_ASKS_A_RULE.search(text) or _ASKS_A_MOVE_RULE.search(text)) \
            and not _NAMES_A_SQUARE.search(text):
        for words, rule in MOVE_RULES:
            if words.search(text) and rule not in found:
                found.append(rule)
    return found


_RULE_STALEMATE = next(r for _, _, r in RULES if r.startswith("Stalemate"))
_RULE_CASTLING = next(r for _, _, r in RULES if r.startswith("Castling"))
_RULE_MATERIAL = next(r for _, _, r in RULES if r.startswith("Insufficient material"))
_STALEMATE_HOW = ("To avoid stalemate the defending king needs just ONE legal move; a check is not required (a check "
                  "the king cannot escape is mate, not a way out of stalemate).")
_RULE_MATE = ("Checkmate: the king is in check and no legal move gets it out of check — the game ends at once (FIDE "
              "5.1.1); with no check and no legal move it is stalemate, a draw.")
_CASTLE_WORDS = re.compile(_W + r"(?:рок[иеі]р\w*|castl\w*|o-o(?:-o)?|0-0(?:-0)?)", re.IGNORECASE)


def _side(color: bool) -> str:
    return "White" if color == chess.WHITE else "Black"


def _after_fact(board: "chess.Board", san: str) -> Optional[str]:
    """«after Qd7 Black is not in check and has 2 legal moves (Kb8, Ka7)» — for a move from *board*."""
    try:
        move = board.parse_san(san)
    except ValueError:
        return None
    after = board.copy(stack=False)
    after.push(move)
    side = _side(after.turn)
    legal = [after.san(m) for m in after.legal_moves]
    if after.is_checkmate():
        return f"after {san} {side} is in check and has no legal move: mate"
    if not legal:
        return f"after {san} {side} is not in check and has no legal move: stalemate, a draw"
    check = "is in check" if after.is_check() else "is not in check"
    shown = ", ".join(legal[:6]) + (", …" if len(legal) > 6 else "")
    return f"after {san} {side} {check} and has {len(legal)} legal move{'s' if len(legal) != 1 else ''} ({shown})"


def _line_ends(board: "chess.Board", moves: list) -> Optional["chess.Board"]:
    b = board.copy(stack=False)
    for san in moves or []:
        try:
            b.push_san(str(san))
        except ValueError:
            return None
    return b


def _verdict_rules(message: str, verdicts: dict) -> str:
    """D′ (plan 31.10, P6): the rules the board shows this turn, with the facts of the recommended move.

    stalemate-hyp (prod 29.10): «Хочу сыграть Qb6, чтобы запереть короля» — the idea move was stalemate (the server
    knew it, src/hypothetical.py), and the answer taught «запирать короля надо так, чтобы он был под шахом». The rule
    and the facts of the engine's move («after Qd7 Black is not in check and has 2 legal moves») go in."""
    fen = verdicts.get("fen")
    if not fen:
        return ""
    try:
        board = chess.Board(fen)
    except ValueError:
        return ""
    ideas = [i for i in (verdicts.get("ideas") or []) if isinstance(i, dict) and i.get("san")]
    lines = [ln for ln in (verdicts.get("engine_lines") or []) if isinstance(ln, dict)]
    best_line = None
    for ln in lines[:1]:
        moves = ln.get("moves") or []
        if moves and _line_ends(board, moves[:1]) is not None:
            best_line = moves
    rules, facts = [], []
    stalemate_ideas, mate_ideas, material_ideas = [], [], []
    for item in ideas:
        try:
            move = board.parse_san(item["san"])
        except ValueError:
            continue
        after = board.copy(stack=False)
        after.push(move)
        if after.is_stalemate():
            stalemate_ideas.append(item["san"])
        elif after.is_checkmate():
            mate_ideas.append(item["san"])
        elif after.is_insufficient_material():
            material_ideas.append(item["san"])
    line_end = _line_ends(board, best_line) if best_line else None
    if stalemate_ideas or (line_end is not None and line_end.is_stalemate()):
        rules.append(_RULE_STALEMATE + " " + _STALEMATE_HOW)
        for san in stalemate_ideas:
            fact = _after_fact(board, san)
            if fact:
                facts.append(fact)
        told = set(stalemate_ideas)
        others = ([best_line[0]] if best_line else []) + [i["san"] for i in ideas if i["san"] not in told]
        for san in others:
            if san in told:
                continue
            told.add(san)
            fact = _after_fact(board, san)
            if fact:
                facts.append(fact + (" — the engine's move" if best_line and san == best_line[0] else ""))
            if len(told) >= len(stalemate_ideas) + 3:
                break
    if mate_ideas:
        rules.append(_RULE_MATE)
        for san in mate_ideas:
            fact = _after_fact(board, san)
            if fact:
                facts.append(fact)
    if material_ideas:
        rules.append(_RULE_MATERIAL)
    # Castling asked about («Можно мне сейчас рокироваться?») where the board forbids it: the Law (the board facts
    # already say why on this board, so they are not repeated here). A bare «0-0» in a game is a move, not a question.
    if _CASTLE_WORDS.search(message or "") and ("?" in (message or "") or _ASKS_A_RULE.search(message or "")):
        try:
            from src.board_rules import castling_status

            st = castling_status(board, board.turn)
            if not all(legal for legal, _ in st.values()):
                rules.append(_RULE_CASTLING)
        except Exception:  # noqa: BLE001 — the castling rule is a bonus
            pass
    asked = set(_question_rules(message or ""))
    kept = [r for r in rules if not any(r.startswith(a) or a.startswith(r) for a in asked)]
    if any(r.startswith(_RULE_STALEMATE) for r in rules) and not any(r.startswith(_RULE_STALEMATE) for r in kept):
        kept.append(_STALEMATE_HOW)  # the question's stalemate rule is there already; how to avoid it is not
    rules = kept
    if not rules and not facts:
        return ""
    out = "## The rules the board shows this turn (FIDE Laws of Chess, verified on the board)"
    if rules:
        out += "\n" + "\n".join(f"- {r}" for r in rules)
    if facts:
        out += "\nOn this board (" + _side(board.turn) + " to move): " + "; ".join(facts) + "."
    return out + "\nTeach by these rules and facts; never state a rule of technique that contradicts them."


def rules_block(message: str, *, board_verdicts: Optional[dict] = None) -> str:
    """The rules a rules question is about, as a turn-context block; "" for anything else.

    *board_verdicts* (plan 31.10, P6 D′): what the engine and the board found this turn — {"fen": the position the
    ideas were played from, "ideas": the idea moves' items (src/hypothetical.hypothetical_notes: {"san", "mate"/
    "draw"/"headline", …}), "idea_fens": the positions after them, "engine_lines": the engine line's lines ({"moves":
    [SAN…], "eval"})}. Called with them (src/server.py, once the idea moves are judged) it returns only the rules those
    verdicts show — a stalemate an idea move (or the engine's line) makes, a mate, no material left, castling that is
    not possible when the message asks about it (the Law only: the board facts give the reason) — with the facts of the engine's move and the other idea moves, never
    the question's rules again; "" when there are none, or with COACH_TURN_FACTS off. Without them it is the
    question's rules: the Laws the words are about and (D, with COACH_TURN_FACTS) how the pieces named move."""
    if board_verdicts is not None:
        if not _facts_on():
            return ""
        try:
            return _verdict_rules(message or "", board_verdicts)
        except Exception:  # noqa: BLE001 — never block a turn on the rules
            return ""
    text = message or ""
    found = _question_rules(text)
    if not found:
        return ""
    return ("## The rules this question is about (FIDE Laws of Chess, verified)\n"
            + "\n".join(f"- {r}" for r in found)
            + "\nAnswer by these rules — the first word is the verdict they give. They answer the rule asked about; "
              "do not apply them to the board on the screen unless the question is about that position "
              "(«в начальной позиции рокировка доступна» is false: pieces stand between).")
