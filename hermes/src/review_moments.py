"""A game review as guided «Моменты» (coach redesign P3b): the ``review_moments`` summary.

The critical-moments scan (``find_critical_moments``; ``review_game`` and the server's review
pre-step run it too) already holds, for every turning point, the position before the move, the
move played, the engine's better move and the evaluations. This module turns that into at most
``MAX_MOMENTS`` steps the student replays on the board: the position with the mover to move, a
question, the move to find (SAN + UCI), a motif and a short explanation.

Everything is deterministic: the moves are checked against the position with python-chess (a
moment whose played or best move does not fit is dropped), the motif comes from the board
(src/motifs.py), the question and explanation from templates. ``build_review_moments`` never
raises; it returns ``None`` when no moment survives.

The card and the coach's words are one fact (18.11). Tester's report of 17.11: the text said the game had three key
moments, all around move 30, over a card titled «Разбор партии · 6 моментов» whose first moment was move 5. Both
were made from the same scan, apart: the card lists every moment with a better move to find, the text was the
model's own pick of «the turning points that matter most» with the model's own count, and nothing told it the card
was there. The card is now built first and the words follow it: ``moments_line`` is the server's own first line of
the answer (the card's count and its moves), ``card_note`` tells the model the same list, which of the moments to
explain in words (``main_moments`` — the biggest swings, picked here) and that the others are on the card.
"""

from __future__ import annotations

import io
import logging
from typing import Any, Optional

import chess
import chess.pgn

logger = logging.getLogger(__name__)

MAX_MOMENTS = 10
MAX_NAME = 80
MAX_TEXT = 240
# critical_moments reports a forced mate as ±10000 pawns; centipawns are clamped to this.
MAX_CP = 10000

# How many of the card's moments the answer explains in words — the prompt's «a game review: the 2–3 turning
# points» (src/prompt_builder.BRIEF_ANSWER_LAYER): the biggest swings of the card, the others stay on it.
MAIN_MOMENTS = 3

# Short motif slugs the client translates; a moment the board does not explain has none.
MOTIFS = ("mate", "fork", "discovered_attack", "pin", "skewer", "hanging_piece")

_TEXT = {
    "ru": {
        "question_mate": "{side} могут поставить мат. Найдите ход!",
        "question": "В партии было {played}. Найдите ход сильнее за {side_gen}.",
        "white": "Белые", "black": "Чёрные", "white_gen": "белых", "black_gen": "чёрных",
        "better": "Сильнее {best}",
        "swing": "После {played} оценка изменилась: {before} → {after}.",
        "mate": "мат",
        "motif": {
            "mate": "ведёт к мату", "fork": "вилка", "discovered_attack": "вскрытое нападение",
            "pin": "связка", "skewer": "линейный удар", "hanging_piece": "фигура без защиты",
        },
    },
    "en": {
        "question_mate": "{side} can force mate here. Find the move!",
        "question": "The game went {played}. Find a stronger move for {side_gen}.",
        "white": "White", "black": "Black", "white_gen": "White", "black_gen": "Black",
        "better": "Better was {best}",
        "swing": "After {played} the evaluation went {before} → {after}.",
        "mate": "mate",
        "motif": {
            "mate": "leads to mate", "fork": "a fork", "discovered_attack": "a discovered attack",
            "pin": "a pin", "skewer": "a skewer", "hanging_piece": "an undefended piece",
        },
    },
}


def build_review_moments(
    data: Any,
    *,
    pgn: Optional[str] = None,
    side: Optional[str] = None,
    language: Optional[str] = None,
    game_id: Any = None,
) -> Optional[dict]:
    """The ``review_moments`` summary of a critical-moments result, or None.

    *data* is ``find_critical_moments``' result (``critical_moments``) or ``review_game``'s
    (``moments``). *pgn* gives the players and the result; *side* ("white"/"black") keeps only
    that side's moments; *language* picks the templates (English for "en", Russian otherwise).
    """
    try:
        return _build(data, pgn=pgn, side=side, language=language, game_id=game_id)
    except Exception:  # noqa: BLE001 — a summary must never break a turn
        logger.debug("review_moments build failed", exc_info=True)
        return None


def _build(data: Any, *, pgn, side, language, game_id) -> Optional[dict]:
    if not isinstance(data, dict):
        return None
    rows = data.get("critical_moments") if "critical_moments" in data else data.get("moments")
    if not isinstance(rows, list):
        return None
    text = _TEXT["en" if (language or "").lower().startswith("en") else "ru"]
    want = side.lower() if isinstance(side, str) and side.lower() in ("white", "black") else None
    moments = []
    for row in rows:
        moment = _moment(row, text, want)
        if moment:
            moments.append(moment)
    if not moments:
        return None
    moments.sort(key=lambda m: m["ply"])
    return {"kind": "review_moments", "game": _game(pgn, game_id), "moments": moments[:MAX_MOMENTS]}


def _clip(value: Any, limit: int = MAX_NAME) -> Optional[str]:
    if value is None:
        return None
    out = str(value).strip()
    return out[:limit] if out else None


def _game(pgn: Optional[str], game_id: Any) -> dict:
    headers: dict = {}
    if isinstance(pgn, str) and pgn.strip():
        try:
            game = chess.pgn.read_headers(io.StringIO(pgn))
            headers = dict(game) if game is not None else {}
        except Exception:  # noqa: BLE001 — the players are cosmetic
            headers = {}
    game = {"white": _clip(headers.get("White")) or "?", "black": _clip(headers.get("Black")) or "?"}
    result = _clip(headers.get("Result"))
    if result and result != "*":
        game["result"] = result
    if isinstance(game_id, (int, str)) and not isinstance(game_id, bool) and str(game_id):
        game["id"] = game_id
    return game


def _cp(pawns: Any) -> Optional[int]:
    if isinstance(pawns, bool) or not isinstance(pawns, (int, float)):
        return None
    return max(-MAX_CP, min(MAX_CP, int(round(pawns * 100))))


def _parse(board: chess.Board, token: Any) -> Optional[chess.Move]:
    """A legal move of *board* from SAN (or UCI), else None."""
    if not isinstance(token, str) or not token.strip():
        return None
    token = token.strip()
    try:
        return board.parse_san(token)
    except ValueError:
        pass
    try:
        move = chess.Move.from_uci(token)
    except ValueError:
        return None
    return move if move in board.legal_moves else None


def _numbered(board: chess.Board, san: str) -> str:
    dots = "." if board.turn == chess.WHITE else "..."
    return f"{board.fullmove_number}{dots}{san}"


def _moment(row: Any, text: dict, want: Optional[str]) -> Optional[dict]:
    if not isinstance(row, dict):
        return None
    try:
        board = chess.Board(row.get("fen_before"))
    except (TypeError, ValueError):
        return None
    if not board.is_valid():
        return None
    mover = "white" if board.turn == chess.WHITE else "black"
    if row.get("side") in ("white", "black") and row["side"] != mover:
        return None  # the row and its position disagree on who moved
    if want and mover != want:
        return None
    played, best = _parse(board, row.get("move")), _parse(board, row.get("best_move"))
    if played is None or best is None or played == best:
        return None
    played_san, best_san = board.san(played), board.san(best)
    motif = _motif(board, best, played, row.get("type"))
    moment: dict = {
        "ply": (board.fullmove_number - 1) * 2 + (1 if board.turn == chess.WHITE else 2),
        "fen": board.fen(),
        "played": played_san,
        "best": best_san,
        "best_uci": best.uci(),
    }
    if motif:
        moment["motif"] = motif
    before, after = _cp(row.get("eval_before")), _cp(row.get("eval_after"))
    moment["question"] = _question(board, played_san, motif, text)
    moment["explanation"] = _explanation(board, played_san, best_san, motif, before, after, text)
    if before is not None:
        moment["eval_before"] = before
    if after is not None:
        moment["eval_after"] = after
    return moment


def _question(board: chess.Board, played_san: str, motif: Optional[str], text: dict) -> str:
    white = board.turn == chess.WHITE
    if motif == "mate":
        return text["question_mate"].format(side=text["white" if white else "black"])
    return text["question"].format(
        played=_numbered(board, played_san), side_gen=text["white_gen" if white else "black_gen"])


def _score(cp: int, text: dict) -> str:
    if abs(cp) >= MAX_CP:
        return f"{'+' if cp > 0 else '−'}{text['mate']}"
    pawns = cp / 100
    return f"{'+' if pawns >= 0 else '−'}{abs(pawns):.1f}"


def _explanation(board, played_san, best_san, motif, before, after, text) -> str:
    out = text["better"].format(best=_numbered(board, best_san))
    out += f" — {text['motif'][motif]}." if motif else "."
    if before is not None and after is not None:
        out += " " + text["swing"].format(
            played=_numbered(board, played_san), before=_score(before, text), after=_score(after, text))
    return out[:MAX_TEXT]


# ── motif ────────────────────────────────────────────────────────────────────


def _undefended(board: chess.Board, square: int) -> bool:
    """The piece on *square* can be taken for free: attacked and not defended."""
    piece = board.piece_at(square)
    if piece is None or piece.piece_type == chess.KING:
        return False
    return board.is_attacked_by(not piece.color, square) and not board.is_attacked_by(piece.color, square)


def _motif(board: chess.Board, best: chess.Move, played: chess.Move, kind: Any) -> Optional[str]:
    """What the better move does (or what the played one gave away), when the board shows it."""
    from src.motifs import _discovers, _forks, _pins, _skewers

    us = board.turn
    after = board.copy(stack=False)
    after.push(best)
    if after.is_checkmate() or kind == "missed_mate":
        return "mate"
    if _forks(after, best.to_square):
        return "fork"
    if _discovers(board, best):
        return "discovered_attack"
    if _pins(after, us) and not _pins(board, us):
        return "pin"
    if _skewers(after, us) and not _skewers(board, us):
        return "skewer"
    victim = board.piece_at(best.to_square)
    if victim is not None and victim.piece_type != chess.PAWN and _undefended(board, best.to_square):
        return "hanging_piece"  # the better move took a piece left without defence
    played_after = board.copy(stack=False)
    played_after.push(played)
    moved = played_after.piece_at(played.to_square)
    if moved is not None and moved.piece_type != chess.PAWN and _undefended(played_after, played.to_square):
        return "hanging_piece"  # the move played left the piece en prise
    return None


# ── the card and the words about it ──────────────────────────────────────────

_LINE = {
    "ru": ("В разборе партии {n} {noun}: {moves}.", "В разборе партии {n} {noun}."),
    "en": ("The review of the game has {n} {noun}: {moves}.", "The review of the game has {n} {noun}."),
    "kk": ("Партия талдауында {n} сәт бар: {moves}.", "Партия талдауында {n} сәт бар."),
}


def _noun(n: int, language: str) -> str:
    if language == "en":
        return "moment" if n == 1 else "moments"
    if n % 10 == 1 and n % 100 != 11:
        return "момент"
    return "момента" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "моментов"


def played_label(moment: dict) -> str:
    """«5.Nxe5» / «12...Qd7»: the move of a card's moment with its number, as the card's own texts write it."""
    ply = int(moment.get("ply") or 0)
    return f"{(ply + 1) // 2}{'.' if ply % 2 else '...'}{moment.get('played')}"


def card_moments(card: Any) -> list:
    """The moments of a ``review_moments`` summary; [] for anything else (no card is shown then)."""
    if not isinstance(card, dict) or card.get("kind") != "review_moments":
        return []
    return [m for m in card.get("moments") or [] if isinstance(m, dict) and m.get("ply") and m.get("played")]


def _loss(moment: dict) -> int:
    """What the move of *moment* cost its mover, in centipawns (the card's evaluations are from White's side)."""
    before, after = moment.get("eval_before"), moment.get("eval_after")
    if not isinstance(before, int) or not isinstance(after, int):
        return 0
    return before - after if int(moment.get("ply") or 0) % 2 else after - before


def main_moments(card: Any, count: int = MAIN_MOMENTS) -> list:
    """The *count* moments of the card with the biggest swings, in the game's order — the ones the answer explains
    in words. All of them when the card has no more than that."""
    moments = card_moments(card)
    if len(moments) <= count:
        return moments
    top = sorted(range(len(moments)), key=lambda i: (-_loss(moments[i]), i))[:count]
    return [moments[i] for i in sorted(top)]


def moments_line(card: Any, language: Optional[str] = None, spoken: bool = False) -> str:
    """The server's own first line of a review's answer: how many moments the card under it has, and their moves —
    «В разборе партии 6 моментов: 5.Nxe5, 12...Qd7, …». *spoken*: the count alone (a list of moves is not read
    aloud). "" when there is no card."""
    moments = card_moments(card)
    if not moments:
        return ""
    code = (language or "ru").lower()[:2]
    code = "kk" if code in ("kk", "kz") else code if code in _LINE else "ru"
    with_moves, alone = _LINE[code]
    if spoken:
        return alone.format(n=len(moments), noun=_noun(len(moments), code))
    return with_moves.format(n=len(moments), noun=_noun(len(moments), code),
                             moves=", ".join(played_label(m) for m in moments))


def card_note(card: Any, told: bool = False, found: Optional[int] = None) -> str:
    """What the model is told about the card of the review (English): its moments are the review's moments — the
    same count, the same moves. *told*: the server has written ``moments_line`` at the head of the answer (the text
    turn's review step); otherwise the model says the count itself (its own tool call, the voice coach). *found*:
    how many swings the scan found in all, when it kept only the biggest. "" when there is no card."""
    moments = card_moments(card)
    if not moments:
        return ""
    n = len(moments)
    labels = [played_label(m) for m in moments]
    main = main_moments(card)
    main_labels = [played_label(m) for m in main]
    rest = [label for label in labels if label not in main_labels]
    lines = [
        "## The review card — the same moments, one count",
        "With your answer the student gets the review's card («Разбор партии» / \"Game review\" / «Партияны талдау») "
        f"with exactly {n} moment{'s' if n != 1 else ''} "
        f"to go through on the board, in this order: {', '.join(labels)}. The count is the system's: never give "
        "another number of moments, mistakes or turning points, never recount them, and never present a part of "
        "them as all there is («три ключевых момента» over a card of six).",
    ]
    if told:
        lines.append(f"The system has ALREADY written the first line of your answer for the student — that the "
                     f"review has {n} moment{'s' if n != 1 else ''} (in a written answer with the list above, read "
                     "aloud the count alone). Do not give the count or the whole list again: go on from that line.")
    else:
        lines.append(f"Say first that the review has {n} moment{'s' if n != 1 else ''} — this number, the one the "
                     "card shows.")
    if rest:
        lines.append(f"Explain in words only the {len(main)} biggest swings — {', '.join(main_labels)} (picked by the "
                     f"size of the engine's swing, not by you) — one or two sentences each, and say that the other "
                     f"{len(rest)} ({', '.join(rest)}) are on the card to go through on the board.")
    else:
        lines.append("Explain each of them, one or two sentences each.")
    if isinstance(found, int) and found > n:
        lines.append(f"The engine found {found} swings of this size in the game; the review keeps the biggest — "
                     f"never say the game had only {n} mistakes.")
    return "\n".join(lines)
