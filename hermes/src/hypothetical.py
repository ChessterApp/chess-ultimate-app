"""The student's idea, played on the board and looked at by the engine.

«А если я поставлю ладью на g1?» used to be answered from the model's head: the
coach wrote that the rook attacks the queen on h4 (it does not, 2026-10-01) or
that a capture through its own pawn wins material. Now each move the student
names is played on the board the moment the message arrives, Stockfish looks
at the position after it for a few hundred milliseconds, and the model gets
the facts — the evaluation against the position before, the opponent's best
reply, what the moved piece really attacks and whether it is safe — before it
writes a word. The positions after the moves also join the boards the answer
is checked against.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import chess

from src.fen_repair import repair_fen
from src.position_facts import VALUES, static_facts
from src.tools.stockfish import analyze_cached, analyze_position, analyze_timed

logger = logging.getLogger(__name__)

MAX_MOVES = 3
MIN_DEPTH = 10
MATE_PAWNS = 100.0
# Thresholds in pawns, from the mover's side: how much the idea gives away
# against the position before it.
BLUNDER = 3.0
MISTAKE = 1.5
INACCURACY = 0.7
# A position won by this much for the side to move (a mate included) is decided: a move or a line that keeps the
# mover at least this far ahead is no mistake, however much bigger the number before it was. Out there a short
# search's scores are coarse — a mate in 11 is a mate at 300 ms before Rh8+ and +7.6 after it, while Rh8+ is the
# engine's own best move at depth 30 (replay 30.10, castle-long-b1: «about 92.4 pawns given away»).
DECIDED = 5.0


def _keeps_decided(before: float, after: float, mover: chess.Color) -> bool:
    """The mover was decisively winning before (White-side pawns *before*) and still is after (*after*)."""
    sign = 1 if mover == chess.WHITE else -1
    return before * sign >= DECIDED and after * sign >= DECIDED


def _given_away(before: float, loss: float) -> str:
    """'about 2.3 pawns given away', or the mate thrown away when the position before was a forced mate."""
    if abs(before) >= MATE_PAWNS - 0.5:
        return "the forced mate is gone"
    return f"about {loss:.1f} pawns given away"


def _white_pawns(line: Optional[dict], turn: chess.Color) -> Optional[float]:
    """A line's score in pawns from White's side; mates as ±MATE_PAWNS."""
    if not line:
        return None
    sign = 1 if turn == chess.WHITE else -1
    if line.get("mate_in") is not None:
        return MATE_PAWNS * sign * (1 if line["mate_in"] > 0 else -1)
    return float(line.get("score") or 0.0) * sign


def _fmt(pawns: Optional[float]) -> str:
    """'+1.2 for White', 'a forced mate for Black'."""
    if pawns is None:
        return "unknown"
    if abs(pawns) >= MATE_PAWNS - 0.5:
        return "a forced mate for " + ("White" if pawns > 0 else "Black")
    return f"{pawns:+.1f} for White"


def _san_line(board: chess.Board, pv: str, plies: int = 4) -> list[str]:
    b = board.copy(stack=False)
    out = []
    for uci in (pv or "").split()[:plies]:
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError:
            break
        if mv not in b.legal_moves:
            break
        out.append(b.san(mv))
        b.push(mv)
    return out


_PIECE_NAMES = {chess.PAWN: ("a pawn", "pawns"), chess.KNIGHT: ("a knight", "knights"), chess.BISHOP: ("a bishop", "bishops"),
                chess.ROOK: ("a rook", "rooks"), chess.QUEEN: ("the queen", "queens")}


def _numbered(board: chess.Board, sans: list[str]) -> str:
    """«6...Nxd5 7.Bxd8 Bb4+» — *sans* from *board*, with the move numbers of that position."""
    out, num, white = [], board.fullmove_number, board.turn == chess.WHITE
    for i, san in enumerate(sans):
        if white:
            out.append(f"{num}.{san}")
        else:
            out.append(f"{num}...{san}" if i == 0 else san)
            num += 1
        white = not white
    return " ".join(out)


def _losses(start: chess.Board, end: chess.Board) -> dict:
    """{color: {piece type: how many it lost}} from *start* to *end* (kings and promotions aside)."""
    out = {}
    for color in (chess.WHITE, chess.BLACK):
        out[color] = {t: max(0, len(start.pieces(t, color)) - len(end.pieces(t, color))) for t in _PIECE_NAMES}
    return out


def _listed(counts: dict) -> str:
    parts = []
    for t in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
        n = counts.get(t, 0)
        if n == 1:
            parts.append(_PIECE_NAMES[t][0])
        elif n > 1:
            parts.append(f"{n} {_PIECE_NAMES[t][1]}")
    return " and ".join(parts)


def _was_capture(board: chess.Board, move: chess.Move, reply_sans: list[str]) -> bool:
    """The line's last move takes something that can be taken back at once — a recapture the engine did not show
    («…Kxd8» ends an exchange; «…Nxd5» with a piece still hitting d5 does not)."""
    b = board.copy(stack=False)
    b.push(move)
    last = move
    for san in reply_sans:
        try:
            last = b.parse_san(san)
        except ValueError:
            break
        b.push(last)
    if not b.move_stack:
        return False
    before = b.copy(stack=True)
    before.pop()
    return before.is_capture(last) and b.is_attacked_by(b.turn, last.to_square)


def line_outcome(board: chess.Board, move: chess.Move, reply_sans: list[str], before: Optional[float] = None,
                 after: Optional[float] = None) -> Optional[str]:
    """Where the student's move and the engine's line lead, in words: «at the end of the line White has given a
    knight for a pawn». The coach got «Nxd5 (line Nxd5 Bxd8 Bb4+ Qd2)» cut after four plies and told the Elephant
    trap as «конь f6 бьёт d5, и ты отдаёшь коня» with the queen trick missing (stand run 28.10)."""
    end = board.copy(stack=False)
    mover = end.turn
    end.push(move)
    for san in reply_sans:
        try:
            end.push_san(san)
        except ValueError:
            break
    lost = _losses(board, end)
    side = "White" if mover == chess.WHITE else "Black"
    if not end.is_checkmate():
        # The line stops in the middle of the fight (a check or a capture last — the Blackburne line ended on 5.Bxf7+), or
        # the count says one thing and the engine another (a sacrifice for an attack): no count — the evaluation.
        unsettled = end.is_check() or _was_capture(board, move, reply_sans)
        gained = sum(VALUES[t] * (lost[not mover][t] - lost[mover][t]) for t in _PIECE_NAMES)
        sign = 1 if mover == chess.WHITE else -1
        moved = (after - before) * sign if before is not None and after is not None and abs(after) < MATE_PAWNS - 0.5 else None
        if unsettled or (moved is not None and abs(gained - moved) > 2.0 and (gained > 0) != (moved > 0)):
            return (f"The line is not settled after these moves (exchanges or an attack go on): judge it by the evaluation, "
                    f"not by counting material — {side} is " + ("better" if (after or 0) * sign > 0.3 else
                                                                "worse" if (after or 0) * sign < -0.3 else "about equal")
                    + " at the end.")
    for t in _PIECE_NAMES:  # an exchange cancels out: only the difference is the outcome
        both = min(lost[chess.WHITE][t], lost[chess.BLACK][t])
        lost[chess.WHITE][t] -= both
        lost[chess.BLACK][t] -= both
    mine, theirs = _listed(lost[mover]), _listed(lost[not mover])
    if end.is_checkmate():
        result = f"{'checkmate for ' + side if end.turn != mover else side + ' is checkmated'}"
    elif mine and theirs:
        result = f"{side} has given {mine} for {theirs}"
    elif mine:
        result = f"{side} has lost {mine} for nothing"
    elif theirs:
        result = f"{side} has won {theirs}"
    else:
        result = "the material is level again"
    tail = [f for f in static_facts(end) if "trapped" in f or "TRAPPED" in f][:1]
    return f"At the end of this line {result}" + (f"; {tail[0]}" if tail else "") + "."


def _piece(board: chess.Board, sq: int) -> str:
    p = board.piece_at(sq)
    return f"the {'white' if p.color else 'black'} {chess.piece_name(p.piece_type)} on {chess.square_name(sq)}"


def moved_piece_facts(board: chess.Board, after: chess.Board, move: chess.Move) -> list[str]:
    """What the moved piece attacks from its new square, and whether it is safe there."""
    mover = board.turn
    dest = move.to_square
    name = f"the {chess.piece_name(after.piece_type_at(dest))} on {chess.square_name(dest)}"
    facts = []
    if after.is_check():
        facts.append(f"{name} gives check")
    targets = [s for s in after.attacks(dest)
               if (p := after.piece_at(s)) is not None and p.color != mover and p.piece_type != chess.KING]
    if targets:
        facts.append(f"{name} attacks " + ", ".join(_piece(after, s) for s in sorted(targets, key=lambda s: -VALUES[after.piece_type_at(s)])))
    else:
        facts.append(f"{name} attacks nothing")
    attackers = after.attackers(not mover, dest)
    defenders = after.attackers(mover, dest)
    if attackers:
        who = ", ".join(_piece(after, s) for s in attackers)
        cheaper = min(VALUES[after.piece_type_at(a)] for a in attackers) < VALUES[after.piece_type_at(dest)]
        if not defenders:
            facts.append(f"{name} can be taken by {who} and nothing defends it")
        elif cheaper:
            facts.append(f"{name} can be taken by a cheaper piece: {who}")
        else:
            facts.append(f"{name} is attacked by {who} and defended by " + ", ".join(_piece(after, s) for s in defenders))
    else:
        facts.append(f"{name} is not attacked")
    # A capture that can be taken back is a trade, not a loss: «exd6 на проходе — и чёрные
    # заберут её ферзём, отдаёшь пешку» (production 2026-10-07; it takes the d5 pawn first).
    if board.is_capture(move):
        moved_type = after.piece_type_at(dest)
        if board.is_en_passant(move):
            captured_type = chess.PAWN
            taken = chess.square(chess.square_file(dest), chess.square_rank(move.from_square))
            facts.insert(0, f"this is an en passant capture: it takes the pawn on {chess.square_name(taken)}")
        else:
            captured_type = board.piece_type_at(dest)
        if attackers and captured_type and VALUES[captured_type] >= VALUES[moved_type]:
            level = "material stays level" if VALUES[captured_type] == VALUES[moved_type] else "the mover stays ahead"
            facts.append(f"if it is taken back, that is a trade — a {chess.piece_name(captured_type)} for a "
                         f"{chess.piece_name(moved_type)}, {level}; not a loss")
    return facts


def _verdict(loss: Optional[float], after_pawns: Optional[float], mover: chess.Color) -> str:
    if loss is None:
        return ""
    if after_pawns is not None and abs(after_pawns) >= MATE_PAWNS - 0.5:
        winner = chess.WHITE if after_pawns > 0 else chess.BLACK
        return "it walks into a forced mate" if winner != mover else "it keeps the forced win"
    if loss >= BLUNDER:
        return f"a blunder — it gives away about {loss:.1f} pawns' worth against the position before the move"
    if loss >= MISTAKE:
        return f"a serious mistake — about {loss:.1f} pawns worse than the position before the move"
    if loss >= INACCURACY:
        return f"an inaccuracy — about {loss:.1f} pawns worse than before; there is clearly better"
    return "a sound move — it keeps the evaluation"


def hypothetical_notes(fen: str, moves: list[dict], movetime_ms: int = 300,
                       reveal_best: bool = True) -> Optional[dict]:
    """Engine facts for the legal *moves* (items with a ``move``) from *fen*.

    Returns {"note": text for the turn context, "fens": positions after the
    moves, "items": per-move data} or None when nothing could be analysed.
    Never raises: a failed analysis leaves that move with board facts only.
    """
    fen = repair_fen(fen)
    try:
        board = chess.Board(fen)
    except ValueError:
        return None
    legal = [m for m in moves if m.get("move") is not None][:MAX_MOVES]
    if not legal or not board.is_valid():
        return None
    try:
        base = analyze_timed(fen, movetime_ms, multipv=1, min_depth=MIN_DEPTH)
        base_line = (base.get("lines") or [None])[0] if "error" not in base else None
    except Exception:  # noqa: BLE001 — the facts below do not need it
        logger.debug("hypothetical: base analysis failed", exc_info=True)
        base_line = None
    before = _white_pawns(base_line, board.turn)
    best_san = _san_line(board, base_line.get("pv", ""), 1) if base_line else []

    lines, fens, items = [], [], []
    mover = board.turn
    for item in legal:
        move = item["move"]
        if isinstance(move, str):
            try:
                move = chess.Move.from_uci(move)
            except ValueError:
                continue
        if move not in board.legal_moves:
            continue
        san = board.san(move)
        after = board.copy(stack=False)
        after.push(move)
        fens.append(after.fen())
        side = "White" if mover == chess.WHITE else "Black"
        words = f" («{item['words']}»)" if item.get("words") and item.get("source") == "prose" else ""
        if after.is_checkmate():
            lines.append(f"- {san}{words} ({side}): checkmate — the game ends.")
            items.append({"san": san, "mate": True})
            continue
        if after.is_stalemate():
            other = "Black" if mover == chess.WHITE else "White"
            lines.append(f"- {san}{words} ({side}): STALEMATE — {other} has no legal move and is not in check, so the "
                         f"game is drawn at once. It is not mate: the king cannot go anywhere, every square around it is "
                         f"covered. Tell the student plainly that this move throws the win away.")
            items.append({"san": san, "draw": True, "headline": f"{san} is stalemate — an immediate draw"})
            continue
        if after.is_insufficient_material():
            lines.append(f"- {san}{words} ({side}): the game is drawn at once (no material left to mate).")
            items.append({"san": san, "draw": True, "headline": f"{san} leaves no material to mate — a draw"})
            continue
        facts = moved_piece_facts(board, after, move)
        after_pawns, reply, reply_line = None, None, []
        try:
            res = analyze_timed(after.fen(), movetime_ms, multipv=1, min_depth=MIN_DEPTH)
            line = (res.get("lines") or [None])[0] if "error" not in res else None
            if line:
                after_pawns = _white_pawns(line, after.turn)
                reply_line = _san_line(after, line.get("pv", ""), 10)
                reply = reply_line[0] if reply_line else None
        except Exception:  # noqa: BLE001
            logger.debug("hypothetical: analysis after %s failed", san, exc_info=True)
        loss = None
        if before is not None and after_pawns is not None:
            loss = (before - after_pawns) if mover == chess.WHITE else (after_pawns - before)
        verdict = _verdict(loss, after_pawns, mover)
        parts = [f"- {san}{words} ({side}'s move)."]
        if after_pawns is not None:
            parts.append(f"Evaluation after it: {_fmt(after_pawns)} (before the move: {_fmt(before)}) — {verdict}.")
        why = None
        if reply:
            parts.append(f"The opponent's best reply: {reply}" + (f" (line {_numbered(after, reply_line)})" if len(reply_line) > 1 else "") + ".")
            why = _reply_point(after, reply)
            if why:
                parts.append(why)
            outcome = line_outcome(board, move, reply_line, before, after_pawns) if len(reply_line) > 1 else None
            if outcome:
                parts.append(outcome + " Explain the idea with this line; never invent another continuation.")
        hanging = [f for f in static_facts(after) if "not defended" in f or "cheaper" in f][:2]
        parts.append("Facts after the move: " + "; ".join(facts + hanging) + ".")
        if reveal_best and best_san and best_san[0] != san and loss is not None and loss >= INACCURACY:
            parts.append(f"The engine prefers {best_san[0]} instead.")
        lines.append(" ".join(parts))
        headline = None
        if loss is not None and loss >= INACCURACY or (verdict and "blunder" in verdict):
            headline = f"{san} is {verdict.split(' — ')[0] if verdict else 'a mistake'}"
            if why and "TRAPPED" in why:
                headline += " — " + why.split("; ")[-1].replace("Why: ", "").rstrip(".")
            elif reply:
                headline += f" — the reply {reply} punishes it"
        items.append({"san": san, "after": after.fen(), "before": before, "eval": after_pawns, "loss": loss,
                      "reply": reply, "facts": facts, "headline": headline})
    if not lines:
        return None
    return {"note": "\n".join(lines), "fens": fens, "items": items}


_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def _safe_squares(board: chess.Board, sq: chess.Square) -> list[str]:
    """Where the piece on *sq* (its side to move) can go without being lost."""
    piece = board.piece_at(sq)
    out = []
    for mv in board.legal_moves:
        if mv.from_square != sq:
            continue
        b = board.copy(stack=False)
        b.push(mv)
        attackers = b.attackers(not piece.color, mv.to_square)
        if not attackers:
            out.append(chess.square_name(mv.to_square))
            continue
        cheapest = min(_VALUE[b.piece_type_at(a)] or 100 for a in attackers)
        defended = bool(b.attackers(piece.color, mv.to_square))
        if defended and cheapest >= _VALUE[piece.piece_type]:
            out.append(chess.square_name(mv.to_square))
    return out


def _reply_point(after: chess.Board, reply_san: str) -> Optional[str]:
    """What the opponent's best reply does, when it is concrete: a fork, an
    attack on a piece that has no safe square left (a trapped piece — 6.b3? b5
    and the bishop a4 cannot retreat, production 2026-10-06)."""
    try:
        move = after.parse_san(reply_san)
    except ValueError:
        return None
    from src.position_facts import describe_move

    described = describe_move(after, move)
    b = after.copy(stack=False)
    b.push(move)
    victim_side = b.turn
    trapped = []
    for sq in b.attacks(move.to_square):
        piece = b.piece_at(sq)
        if piece is None or piece.color != victim_side or piece.piece_type in (chess.PAWN, chess.KING):
            continue
        if _VALUE[piece.piece_type] <= _VALUE[b.piece_type_at(move.to_square)] and b.attackers(victim_side, sq):
            continue  # attacked by an equal or bigger piece and defended: not lost
        if not _safe_squares(b, sq):
            trapped.append(f"the {'white' if piece.color else 'black'} {chess.piece_name(piece.piece_type)} "
                           f"on {chess.square_name(sq)}")
    bits = []
    if " — " in described:
        bits.append(f"{reply_san} means {described.split(' — ', 1)[1]}")
    if trapped:
        bits.append(", ".join(trapped) + " is TRAPPED after it — no safe square to go to, so it is lost")
    return ("Why: " + "; ".join(bits) + ".") if bits else None


def verify_line(board: chess.Board, line: list[str], movetime_ms: int = 300, threshold_cp: int = 150) -> Optional[str]:
    """Why a written line («после Nf7 Kxf7 Qxc5 у тебя перевес») ends badly for
    the side that starts it: the evaluation at its end against the position
    before, by the engine. None when it holds, or the line cannot be played."""
    try:
        end = board.copy(stack=False)
        played = []
        for san in line:
            try:
                mv = end.parse_san(san)
            except ValueError:
                break
            played.append(end.san(mv))
            end.push(mv)
        if len(played) < 2 or end.is_game_over():
            return None
        base = analyze_timed(board.fen(), movetime_ms, multipv=1, min_depth=MIN_DEPTH)
        res = analyze_timed(end.fen(), movetime_ms, multipv=1, min_depth=MIN_DEPTH)
        b_line = (base.get("lines") or [None])[0] if "error" not in base else None
        e_line = (res.get("lines") or [None])[0] if "error" not in res else None
        if not b_line or not e_line:
            return None
        before = _white_pawns(b_line, board.turn)
        after = _white_pawns(e_line, end.turn)
        if before is None or after is None:
            return None
        loss = (before - after) if board.turn == chess.WHITE else (after - before)
        if loss * 100 < threshold_cp or _keeps_decided(before, after, board.turn):
            return None
        side = "White" if board.turn else "Black"
        worse = ("the forced mate is gone" if abs(before) >= MATE_PAWNS - 0.5
                 else f"about {loss:.1f} pawns worse for {side}")
        return f"the line {' '.join(played)} ends at {_fmt(after)} against {_fmt(before)} before it — {worse} (engine)"
    except Exception:  # noqa: BLE001
        logger.debug("verify_line failed", exc_info=True)
        return None


def live_game_note(fen: str, movetime_ms: int = 300) -> Optional[dict]:
    """The engine's look at a live game for the coach — the evaluation and the
    opponent's threat only, never the best move (the coach hints; production,
    2026-10-05: the queen on h5 hung to g6 and the coach proposed a knight fork)."""
    fen = repair_fen(fen)
    try:
        board = chess.Board(fen)
    except ValueError:
        return None
    if not board.is_valid() or board.is_game_over():
        return None
    # An ending of ≤ 7 pieces: the tablebase's result beside the engine's evaluation, asked during the search —
    # the voice coach's game note had none, and the check judged «не догонит» in a game without it (30.10).
    tb_future = None
    if len(board.piece_map()) <= 7:
        try:
            from src.voice_engine_note import _tablebase_result, _threat_pool

            tb_future = _threat_pool.submit(_tablebase_result, board.copy(stack=False))
        except Exception:  # noqa: BLE001 — a bonus on top of the engine
            tb_future = None
    try:
        from src.position_facts import THREAT_MOVETIME_MS, _score, _threat

        res = analyze_timed(fen, movetime_ms, multipv=1, min_depth=MIN_DEPTH)
        line = (res.get("lines") or [None])[0] if "error" not in res else None
        if not line:
            return None
        white = _white_pawns(line, board.turn)
        threat = _threat(board, _score(line), lambda f: analyze_timed(f, THREAT_MOVETIME_MS, multipv=1, min_depth=10))
        side, other = ("White", "Black") if board.turn else ("Black", "White")
        parts = [f"- Evaluation: {_fmt(white)}."]
        if threat:
            parts.append(f"- {other} threatens {threat} if {side} ignores it.")
        tb = None
        if tb_future is not None:
            try:
                tb = tb_future.result(timeout=0.5)  # the lookup ran during the search; a slow one is left out
            except Exception:  # noqa: BLE001
                tb = None
        if tb:
            # The result only, no move: the coach hints in a game.
            parts.append(f"- Endgame tablebase (exact, perfect play): {tb.upper()} — whatever the evaluation shows.")
        return {"eval": white, "threat": threat, "note": "\n".join(parts), "tablebase": tb}
    except Exception:  # noqa: BLE001
        logger.debug("live_game_note failed", exc_info=True)
        return None


def verify_recommendation(board: chess.Board, move: chess.Move, san: str, movetime_ms: int = 300,
                          threshold_cp: int = 150, reveal_best: bool = True, line: Optional[list] = None) -> Optional[str]:
    """Why the move the coach recommends is wrong on *board*, by the engine.

    None when the move holds the evaluation (gives away less than
    *threshold_cp*), mates, or the engine cannot say. The text names the
    reply, the evaluation against the position before, and what the moved
    piece really does — the rewrite is written from it. *reveal_best* off (a
    live game) keeps the engine's own move out of it.
    """
    line_moves = list(line or [])
    try:
        if move not in board.legal_moves:
            return None
        base = analyze_timed(board.fen(), movetime_ms, multipv=1, min_depth=MIN_DEPTH)
        base_line = (base.get("lines") or [None])[0] if "error" not in base else None
        if not base_line:
            return None
        before = _white_pawns(base_line, board.turn)
        best = _san_line(board, base_line.get("pv", ""), 1)
        if best and best[0] == san:
            return verify_line(board, line_moves, movetime_ms, threshold_cp) if line_moves else None
        after = board.copy(stack=False)
        after.push(move)
        if after.is_game_over():
            return None
        res = analyze_timed(after.fen(), movetime_ms, multipv=1, min_depth=MIN_DEPTH)
        line = (res.get("lines") or [None])[0] if "error" not in res else None
        if not line:
            return None
        after_pawns = _white_pawns(line, after.turn)
        if before is None or after_pawns is None:
            return None
        loss = (before - after_pawns) if board.turn == chess.WHITE else (after_pawns - before)
        if loss * 100 < threshold_cp or _keeps_decided(before, after_pawns, board.turn):
            # The move itself holds; a written line after it may still end badly.
            return verify_line(board, line_moves, movetime_ms, threshold_cp) if line_moves else None
        reply = _san_line(after, line.get("pv", ""), 3)
        facts = moved_piece_facts(board, after, move)
        mated = abs(after_pawns) >= MATE_PAWNS - 0.5 and (after_pawns > 0) != (board.turn == chess.WHITE)
        if mated:
            why = f"{san} is a blunder on this board (engine): it walks into a forced mate — {san} {' '.join(reply)}"
        else:
            why = (f"{san} is a mistake on this board (engine): after {san} {' '.join(reply)} the evaluation is "
                   f"{_fmt(after_pawns)} against {_fmt(before)} before the move — {_given_away(before, loss)}")
        why += "; " + "; ".join(facts[:2])
        if reveal_best and best:
            why += f". The engine's move here is {best[0]}"
        return why
    except Exception:  # noqa: BLE001 — a failed check never blocks the answer
        logger.debug("verify_recommendation failed", exc_info=True)
        return None


def site_solution_note(fen: Optional[str], solution, movetime_ms: int = 250) -> Optional[str]:
    """Why the site's listed solution of a task cannot be taught, by the board and the engine, or None.

    A sweep of all 1896 tasks of the site's programme (2026-10-08) found 21 broken ones: the listed
    solution loses or misses the mate the set is about («Мат в 3 хода — Набор 27, №1»: Rxf5+ loses, Rd6+
    mates), is not a legal move, or the position itself is impossible. The coach and the lesson tutor
    were handed such a solution as the answer. Never raises.
    """
    from src.fen_repair import repair_fen

    first = (solution[0] if isinstance(solution, (list, tuple)) and solution else solution) or None
    if not fen or not first:
        return None
    try:
        board = chess.Board(repair_fen(fen))
    except ValueError:
        return "the lesson's position (FEN) cannot be read: do not analyse it, explain the lesson's idea in words."
    if not board.is_valid():
        return ("the lesson's position is not a legal chess position (a data error of the site): do not analyse it "
                "or name moves in it; explain the lesson's idea in words.")
    move = None
    try:
        move = board.parse_san(str(first))
    except ValueError:
        try:
            cand = chess.Move.from_uci(str(first))
            move = cand if cand in board.legal_moves else None
        except ValueError:
            move = None
    try:
        base = analyze_timed(board.fen(), movetime_ms, multipv=1, min_depth=MIN_DEPTH)
        best = _san_line(board, (base.get("lines") or [{}])[0].get("pv", ""), 1) if "error" not in base else []
    except Exception:  # noqa: BLE001
        best = []
    instead = f" The engine's move here is {best[0]} — teach that one." if best else ""
    if move is None:
        return (f"the site lists {first} as the solution, but it is not a legal move in this position (a data "
                "error): do not teach it or guess what was meant; explain the lesson's idea in words.")
    try:
        issue = verify_recommendation(board, move, board.san(move), movetime_ms, 150, True)
    except Exception:  # noqa: BLE001
        issue = None
    if issue:
        tail = "" if "engine's move" in issue else instead
        return f"the site lists {board.san(move)} as the solution, but it is wrong here ({issue}).{tail} Do not call the site's move correct."
    return None


# A forced reply claimed in the answer («после Nxe5 чёрные обязаны ответить dxe5», prod 29.10 trap-legal: 5...Be6
# is +2.9 against +2.6 after dxe5 at depth 24) is judged on the scale of the verdicts above: another reply within
# an inaccuracy of the named one is as playable, so the named one is not forced; a named reply a mistake worse than
# the best is not the reply at all. A won or lost position (beyond FORCED_DECIDED) is too coarse at this depth to
# call two replies equal, and a mate is never «as good» as another reply.
FORCED_DECIDED = 4.0
FORCED_MOVETIME_FACTOR = 2
# The gap between two replies moves with the depth: trap-legal's was 0.69–0.72 at 600 ms (depth 16–17, by the
# host's load), so the same sentence was cut in one run and shown in the next (review 30.10). A timed look only
# clears a claim far from the lines; a verdict against it, or a gap near a line, is settled by a search to a fixed
# depth — the same numbers on every run (the engine server caches by depth; trap-legal: 0.50 at depth 17), and a
# search that does not reach that depth says nothing.
FORCED_CONFIRM_DEPTH = 17
# …bounded in time all the same (review 30.10: 1.6 s alone, 2.5 s with a second turn running, on top of the timed
# look): the confirming searches of one reading share this budget, and a search that runs out of it says nothing —
# the sentence stands. An unloaded host reaches depth 17 for trap-legal in about 0.9 s.
FORCED_CONFIRM_MAX_MS = 1000
FORCED_CONFIRM_BAND = (0.35, 1.1)
FORCED_MISTAKE_BAND = 1.0


def _mover_value(line: dict) -> tuple:
    """(pawns for the side to move, mate distance or None) of an engine line; mates as ±MATE_PAWNS."""
    if line.get("mate_in") is not None:
        return (MATE_PAWNS if line["mate_in"] > 0 else -MATE_PAWNS), line["mate_in"]
    return float(line.get("score") or 0.0), None


def _engine_lines(fen: str, multipv: int, movetime_ms: Optional[int], depth: Optional[int],
                  deadline: Optional[float] = None) -> Optional[dict]:
    """A timed look (*movetime_ms*), or one to a fixed *depth* — None when a line of it stopped short of that
    depth (the host's time cap under load: its lines mix depths, and their gaps with them); a line that found a
    mate ends early and counts."""
    if depth is None:
        res = analyze_timed(fen, movetime_ms, multipv=multipv, min_depth=MIN_DEPTH)
        return None if "error" in res else res
    # A search of its own, never the cache: a timed look that happened to reach the depth served it before, with
    # its gaps (trap-legal: 0.72 from the cache against 0.50 searched to depth 17 — the verdict flipped by what had
    # been looked at first; merge 30.10).
    if deadline is None:
        res = analyze_position(fen, depth=depth, multipv=multipv)
    else:
        left = int((deadline - time.monotonic()) * 1000)
        if left < 100:
            return None  # the confirming search's time is spent: it says nothing
        res = analyze_position(fen, depth=depth, multipv=multipv, max_ms=left)
    lines = (res.get("lines") or []) if "error" not in res else []
    if not lines or any(int(ln.get("depth") or 0) < depth and ln.get("mate_in") is None for ln in lines):
        return None
    return res


def _reply_rows(board: chess.Board, movetime_ms: Optional[int] = None, depth: Optional[int] = None,
                deadline: Optional[float] = None) -> list:
    """The engine's three best replies on *board*: [(move, pawns for the mover, mate, pawns for White)]."""
    res = _engine_lines(board.fen(), 3, movetime_ms, depth, deadline)
    rows = []
    for ln in (res or {}).get("lines") or []:
        try:
            mv = chess.Move.from_uci((ln.get("pv") or "").split()[0])
        except (ValueError, IndexError):
            continue
        if mv in board.legal_moves:
            rows.append((mv, *_mover_value(ln), _white_pawns(ln, board.turn)))
    return rows


def _forced_verdict(claim: dict, rows: list, reveal_best: bool, movetime_ms: Optional[int], depth: Optional[int],
                    deadline: Optional[float] = None) -> tuple:
    """(why the claim is wrong or None, whether a gap sits near a line) on one engine look *rows*."""
    board, claimed = claim["board"], set(claim["moves"])
    inside = [r for r in rows if r[0] in claimed]
    outside = [r for r in rows if r[0] not in claimed]
    if not rows or not outside:
        return None, False  # every reply the engine looks at is one the claim names
    bound = False
    if inside:
        named_value, named_mate, named_white = inside[0][1], inside[0][2], inside[0][3]
    elif len(rows) == 3 and rows[0][1] - rows[-1][1] >= MISTAKE and rows[-1][2] is None:
        # Not among the engine's three best: each claimed reply is at least as bad as the third one.
        named_value, named_mate, named_white, bound = rows[-1][1], None, None, True
    elif claim.get("named") and len(claimed) == 1:
        after = board.copy(stack=False)
        after.push(next(iter(claimed)))
        if after.is_game_over():
            return None, False
        res = _engine_lines(after.fen(), 1, movetime_ms, None if depth is None else depth - 1, deadline)
        line = ((res or {}).get("lines") or [None])[0]
        if not line:
            return None, False
        value, mate = _mover_value(line)
        named_value, named_mate, named_white = -value, (-mate if mate is not None else None), _white_pawns(line, after.turn)
    else:
        return None, False
    best = rows[0]
    side = "White" if board.turn == chess.WHITE else "Black"
    after_txt = f"after {claim['after']}" if claim.get("after") else "here"
    label = claim.get("named") or claim.get("kind") or "that reply"
    head = f"{after_txt} {side} is not forced to {'play' if claim.get('named') else 'make'} {label}"
    shown = claim.get("named") or (board.san(inside[0][0]) if inside else None)
    named_eval = f" against {_fmt(named_white)} after {shown}" if shown and named_white is not None else ""
    near = False
    # The named reply a mistake worse than the best: not the reply at all. Two mates for the mover, or the best
    # only a longer road to the same mate against it, are left alone.
    if best[0] not in claimed:
        mover_wins = best[2] is not None and best[2] > 0 and named_mate is not None and named_mate > 0
        both_mated = best[2] is not None and best[2] < 0 and named_mate is not None and named_mate < 0
        if not mover_wins and not both_mated:
            if best[1] - named_value >= MISTAKE:
                if not reveal_best:
                    return f"{head}: another reply is much better (engine) — do not call it forced or the only reply", near
                return (f"{head}: the best reply is {board.san(best[0])} ({_fmt(best[3])}{named_eval}, engine) — do "
                        "not call it forced or the only reply"), near
            near = best[1] - named_value >= FORCED_MISTAKE_BAND
    if bound or not claim.get("strict", True):
        return None, near  # «должны ответить dxe5» claims the best reply, and it is good enough
    for mv, value, mate, white in outside:
        # Mates are left alone here: in a mating line every reply may lose the same way, and the line the
        # coach tells is the main one («король вынужден взять, и Лh8#»).
        if mate is not None or named_mate is not None or abs(named_value) > FORCED_DECIDED:
            continue
        if abs(value - named_value) > INACCURACY:
            near = near or abs(value - named_value) <= FORCED_CONFIRM_BAND[1]
            continue
        if not reveal_best:
            return f"{head}: another reply is about as good (engine) — it is one good reply, not the only one", near
        return (f"{head}: {board.san(mv)} is about as good ({_fmt(white)}{named_eval}, engine) — it is one good "
                "reply, not the only one"), near
    return None, near


def _verify_one_reading(claim: dict, movetime_ms: int, reveal_best: bool) -> Optional[str]:
    board, claimed = claim["board"], set(claim["moves"])
    if board.is_game_over() or not claimed or all(mv in claimed for mv in board.legal_moves):
        return None  # forced by the rules themselves
    movetime = movetime_ms * FORCED_MOVETIME_FACTOR
    issue, near = _forced_verdict(claim, _reply_rows(board, movetime_ms=movetime), reveal_best, movetime, None)
    if issue is None and not near:
        return None  # far from every line: the timed look is enough to let it stand
    # Against the claim, or close to the line: only the fixed-depth search decides, within its time.
    deadline = time.monotonic() + FORCED_CONFIRM_MAX_MS / 1000.0
    return _forced_verdict(claim, _reply_rows(board, depth=FORCED_CONFIRM_DEPTH, deadline=deadline), reveal_best,
                           None, FORCED_CONFIRM_DEPTH, deadline)[0]


def verify_forced_reply(claim: dict, movetime_ms: int = 300, reveal_best: bool = True) -> Optional[str]:
    """Why the reply *claim* says is forced is not, by the engine; None when it holds or the engine cannot say.

    *claim* comes from src/answer_check_rules.forced_reply_claim: the board, the move it follows, the replies
    claimed (one named move, or every king move / capture for «король обязан отойти», «вынуждены взять»),
    and *strict* — forced, not merely best («должны ответить»). Its *also* are the other readings of the same
    sentence (the line the sentences before built, where the moves of this one are legal too): the claim is
    wrong only when it is wrong in each of them, and then the line's own reading speaks. *reveal_best* off (a
    live game) keeps the engine's own reply out of the text. Never raises.
    """
    try:
        issue = _verify_one_reading(claim, movetime_ms, reveal_best)
        for other in claim.get("also") or []:
            if issue is None:
                break
            issue = _verify_one_reading(other, movetime_ms, reveal_best)
        return issue
    except Exception:  # noqa: BLE001 — a failed check never blocks the answer
        logger.debug("verify_forced_reply failed", exc_info=True)
        return None
