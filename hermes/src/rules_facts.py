"""The Laws of Chess a rules question is about, said to the model as facts (2026-10-13).

Rules questions are answered from the model's head, and the same question went both ways on one day:
«У меня кончилось время, а у соперника остался только король. Кто победил?» — «ничья» in one run,
«победил соперник» in the next; «Позиция повторилась три раза, но не подряд» — «Нет, не ничья». The
rule each question is about is matched by its words and given as it stands in the FIDE Laws.
"""

from __future__ import annotations

import re

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

# A rules question names no move and asks «можно ли», «что будет», «кто победил», «ничья ли»…
_ASKS_A_RULE = re.compile(
    _W + r"(?:можно\s+ли|можно|разрешено|нельзя|правил\w*|кто\s+(?:победил|выиграл)|ничья|засчита\w*|что\s+будет|"
    r"is\s+it|can\s+i|can\s+a|allowed|legal|rule\w*|who\s+wins|draw|бола\s+ма|ереже\w*)", re.IGNORECASE)


def rules_block(message: str) -> str:
    """The rules a rules question is about, as a turn-context block; "" for anything else."""
    text = message or ""
    if not _ASKS_A_RULE.search(text):
        return ""
    found = []
    for words, also, rule in RULES:
        if words.search(text) and (also is None or also.search(text)) and rule not in found:
            found.append(rule)
    if not found:
        return ""
    return ("## The rules this question is about (FIDE Laws of Chess, verified)\n"
            + "\n".join(f"- {r}" for r in found)
            + "\nAnswer by these rules — the first word is the verdict they give.")
