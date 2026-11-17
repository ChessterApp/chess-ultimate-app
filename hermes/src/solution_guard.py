"""A hint never draws the puzzle's solution on the board (17.11).

Tester's report of 16.11: the puzzle panel's «Подсказка» sends «Подскажи идею в этой задаче, не называя ход.» — the
coach answered in words as asked, and a green arrow a1→a8, the solution itself, appeared on the board. The arrow was
the model's own mark ([[arrows: …]], src/board_markup.py) or a board_control call; nothing on the way to the board
knew that the move it drew was the one the student is solving for.

The server knows it exactly: the puzzle on the board carries its verified solution, and how far along it the board
is (src/tools/puzzles.solution_line). While that puzzle is unsolved and the system itself has not shown the solution
(``reveal`` — the student gave up or asked for it: the server's solution step and the puzzle_solution tool), every
board action that draws a move still to be played of it is withheld — the text turn's marks and tools and the voice
tools alike. An arrow that is not a solution move is never touched, and nothing is once the puzzle is solved, left
or revealed.
"""

from types import SimpleNamespace
from typing import Optional

REVEALED = "revealed"


def secret_moves(board_rec) -> list[tuple[str, str]]:
    """The (from, to) squares of the solution moves still to be played of the unsolved puzzle on *board_rec*, in the
    solution's order — [] when the board is no puzzle, the puzzle is solved or left, or its solution was shown."""
    pz = getattr(board_rec, "puzzle", None) or {}
    if not pz or pz.get(REVEALED):
        return []
    try:
        from src.tools.puzzles import solution_line

        sol = solution_line(board_rec)
    except Exception:  # noqa: BLE001 — a puzzle that cannot be read hides nothing
        return []
    if not sol:
        return []
    return [(u[:2], u[2:4]) for u in sol["ucis"][sol["reached"]:]]


def reveal(session, board_rec) -> None:
    """The system has shown the solution of the puzzle on *board_rec* (the student asked for it): from now on its
    moves may be drawn — «а почему не сразу Nh3?» on the next turn is answered with arrows. A new puzzle on the board
    is a new record (src/boards.Board.apply_action), hidden again."""
    pz = getattr(board_rec, "puzzle", None)
    if not pz or pz.get(REVEALED):
        return
    board_rec.puzzle = {**pz, REVEALED: True}
    try:
        session.save_board(board_rec)
    except Exception:  # noqa: BLE001 — the flag still holds for this process
        pass


def is_revealed(board_rec) -> bool:
    return bool((getattr(board_rec, "puzzle", None) or {}).get(REVEALED))


def withhold_solution(actions: list, board_rec) -> tuple[list, list]:
    """(*actions* without the marks that draw a remaining solution move of the puzzle on *board_rec*, the moves
    withheld as 'a1a8').

    An arrow from → to of such a move goes; a highlight that holds both squares of one loses those two (the same
    move drawn as two squares). An action left with nothing to draw goes whole. The board follows the position
    actions of the list, as the arrows' own check does (src/board_markup.prune_board_actions): after a set_puzzle the
    marks are judged against that puzzle from its start, after any other position there is nothing to hide."""
    secret = set(secret_moves(board_rec))
    kept, withheld = [], []
    for action in actions or []:
        if not isinstance(action, dict):
            kept.append(action)
            continue
        kind = action.get("type")
        if kind == "set_puzzle" and action.get("fen"):
            secret = set(secret_moves(SimpleNamespace(
                kind="puzzle", fen=action["fen"],
                puzzle={"fen": action["fen"], "solution": action.get("solution") or []})))
        elif kind in ("set_fen", "load_pgn", "clear_board"):
            secret = set()
        elif kind == "draw_arrows" and secret:
            arrows = []
            for arrow in action.get("arrows") or []:
                move = _squares_of(arrow)
                if move in secret:
                    withheld.append("".join(move))
                else:
                    arrows.append(arrow)
            if not arrows:
                continue
            if len(arrows) != len(action.get("arrows") or []):
                action = {**action, "arrows": arrows}
        elif kind == "highlight_squares" and secret:
            squares = [str(s).lower() for s in action.get("squares") or []]
            hide = set()
            for a, b in secret:
                if a in squares and b in squares:
                    hide |= {a, b}
                    withheld.append(a + b)
            if hide:
                left = [s for s in action.get("squares") or [] if str(s).lower() not in hide]
                if not left:
                    continue
                action = {**action, "squares": left}
        kept.append(action)
    return kept, list(dict.fromkeys(withheld))


def _squares_of(arrow) -> Optional[tuple[str, str]]:
    try:
        return str(arrow.get("from")).lower(), str(arrow.get("to")).lower()
    except AttributeError:
        return None
