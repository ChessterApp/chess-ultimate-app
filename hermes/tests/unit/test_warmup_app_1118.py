"""The warm-up of five in the Android app: the ending is seen and no sixth puzzle comes (tester's report 18.11).

«Решил все пять задач, после пятой нажал "Дальше" и пришла шестая (старая задача с ладьёй, мат в один ход). Итога
разминки нет, номера задачи тоже нигде не видно.» The server's warm-up (src/warmup.py, 18.11) was right on the app's
own requests too — replayed here exactly: the card's «Разминка: …» on an empty screen (the session is born on it), the
study board the app then lists, its board saves (PATCH …/boards/{id} {position}, 700 ms after every change — the
puzzle's start, every move, the opponent's reply), the panel's «Дальше» (the plain «Дай мне тактическую задачу» with
the board's id and position): places 1..5, then the ending.

What went wrong was what the app showed. While a puzzle is up its sheet, at its smallest, shows the puzzle panel and
not the coach's last line — neither «Задача 2 из 5.» nor the ending was in sight; the ending changed nothing on the
board, the panel kept the solved fifth puzzle with its «Дальше», and that «Дальше» pressed again — the warm-up over by
then — was the programme's next task: the old rook mate in one. The ending now sets the board's own position again
(``set_fen``), which ends the puzzle mode in the site and the app: the panel goes, the sheet shows the coach's line —
the ending — and there is no «Дальше» to bring a sixth.

The same replay found the board saves turned the puzzle into a study board at the first one (src/boards.Board.
set_position → set_fen): the solution block, the hint guard and «сдаюсь» lost the puzzle in the middle of it. A position
of the puzzle's own solution line now keeps the board a puzzle, its progress read off the position.
"""

import csv
import json
from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src import config, puzzle_db
from src.boards import Board
from src.server import app, session_store
from src.solution_guard import secret_moves
from src.tools import learning_path as lp
from src.tools import puzzles as pz
from src.tools.puzzles import solution_line
from src.user_profile import UserProfile

WARMUP = "Разминка: дай мне 5 разных тактических задач по моему уровню."   # coach.promptWarmup
NEXT = "Дай мне тактическую задачу"                                         # coach.promptPuzzle — the panel's «Дальше»
HINT = "Подскажи идею в этой задаче, не называя ход."                         # coach.puzzleHintMessage

# Twelve mates in two of different themes — three plies each, the middle one the opponent's reply, as the tester's
# puzzles: 1.Rx8+ Rxx8 2.Rxx8#, the black rook on a8 defending, after a knight's move of Black's (the Lichess row's
# first move, the setup).
_TAGGED = [
    ("fork01", "fork", 1180), ("pin001", "pin", 1210), ("skew01", "skewer", 1250), ("mate01", "mateIn2", 1190),
    ("hang01", "hangingPiece", 1230), ("sacr01", "sacrifice", 1290), ("defl01", "deflection", 1205),
    ("fork02", "fork", 1215), ("pin002", "pin", 1220), ("mate02", "mateIn2", 1195), ("prom01", "promotion", 1260),
    ("intr01", "intermezzo", 1240),
]
_KNIGHTS = (("h5", "f4"), ("h6", "g4"), ("h5", "g3"))


def _row(i, pid, theme, rating):
    frm, to = _KNIGHTS[i // 4]
    f = "bcde"[i % 4]
    board = chess.Board(None)
    for square, piece in (("g1", "K"), ("f2", "P"), ("g2", "P"), ("h2", "P"), (f + "1", "R"), (f + "2", "R"),
                          ("g8", "k"), ("f7", "p"), ("g7", "p"), ("h7", "p"), ("a8", "r"), (frm, "n")):
        board.set_piece_at(chess.parse_square(square), chess.Piece.from_symbol(piece))
    board.turn = chess.BLACK
    moves = [f"{frm}{to}", f"{f}2{f}8", f"a8{f}8", f"{f}1{f}8"]
    line = board.copy()
    for uci in moves:
        line.push_uci(uci)
    assert line.is_checkmate()
    return {"PuzzleId": pid, "FEN": board.fen(), "Moves": " ".join(moves), "Rating": str(rating),
            "RatingDeviation": "80", "Popularity": "90", "NbPlays": "5000", "Themes": f"{theme} short",
            "GameUrl": "", "OpeningTags": ""}


ROWS = [_row(i, *tagged) for i, tagged in enumerate(_TAGGED)]


@pytest.fixture(scope="module")
def mates_db(tmp_path_factory):
    from scripts.import_puzzles import build

    path = tmp_path_factory.mktemp("warmup-app") / "lichess_db_puzzle.csv"
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(ROWS[0].keys()))
        writer.writeheader()
        writer.writerows(ROWS)
    db = str(tmp_path_factory.mktemp("warmup-app-db") / "puzzles.db")
    assert build(str(path), db) == len(ROWS)
    return db


@pytest.fixture(autouse=True)
def _stand(monkeypatch, mates_db):
    monkeypatch.setattr(puzzle_db, "PUZZLES_DB_PATH", mates_db)
    monkeypatch.setattr(pz, "profile_rating", lambda user_id: 1200)
    monkeypatch.setattr(config, "COACH_TWO_STAGE", False)
    # The programme: the old rook mate in one the tester got as the «sixth».
    monkeypatch.setattr(config, "COACH_PUZZLES_FROM_SITE", True)
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: {"courses": [{"id": "c1", "slug": "chess-basics", "title": "Основы", "modules": [
        {"id": "m1", "title": "Ладья", "lessons": [{"id": "l1", "slug": "rook-1", "title": "Ладья — Набор 1", "module_id": "m1",
                                                    "course_id": "c1", "lesson_type": "exercise"}]}]}]})
    monkeypatch.setattr(lp, "fetch_progress", lambda *a, **k: {})
    monkeypatch.setattr(lp, "get_lesson", lambda lid, **k: {
        "lesson_id": lid, "title": "Ладья — Набор 1", "course": {"title": "Основы"},
        "url": "https://chesster.io/learn/chess-basics/rook-1",
        "puzzles": [{"n": n, "fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "solution": ["Ra8#"]} for n in (1, 2, 3)]})


class _App:
    """The Android app's coach screen, request for request (mobile/src/app/coach.tsx `ask`, the board-sync effect,
    `restore`): the model is stubbed, the server is the real one."""

    def __init__(self, user, said="Ищи шах по последней горизонтали."):
        self.client, self.user, self.said = TestClient(app), {"X-User-Id": user}, said
        self.sid = self.board_id = None
        self.fen = chess.STARTING_FEN
        self.puzzle = None          # the set_puzzle action the screen is in puzzle mode with, or None
        self.message = None         # what the model was given last

    def ask(self, text):
        body = {"message": text, "fen": self.fen, "locale": "ru"}
        if self.sid:
            body["session_id"] = self.sid
        if self.board_id:
            body["board_id"] = self.board_id
        with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
            mock_profile.return_value = UserProfile(user_id=self.user["X-User-Id"])
            agent = MagicMock()

            def _chat(message, stream_callback=None):
                self.message = message
                if stream_callback:
                    stream_callback(self.said)
                return self.said

            agent.chat.side_effect = _chat
            mock_agent.return_value = agent
            resp = self.client.post("/api/coach/chat", headers=self.user, json=body)
        frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
        if not self.sid:
            # The session is born on this first question; the screen then lists its boards (the study one).
            self.sid = next(f["session_id"] for f in frames if f.get("session_id"))
            boards = self.client.get(f"/api/coach/sessions/{self.sid}/boards", headers=self.user).json()["boards"]
            self.board_id = next(b["id"] for b in boards if b["kind"] in ("study", "puzzle"))
        actions = [a for f in frames for a in f.get("board_actions", [])]
        for action in actions:          # the board reducer: set_puzzle enters the puzzle mode, set_fen leaves it
            if action["type"] == "set_puzzle":
                self.puzzle, self.fen = action, action["fen"]
                self.save()
            elif action["type"] == "set_fen":
                self.puzzle, self.fen = None, action["fen"]
        return {"text": "".join(f.get("delta", "") for f in frames), "actions": actions}

    def save(self):
        """The board-sync effect fires: PATCH {position}."""
        resp = self.client.patch(f"/api/coach/sessions/{self.sid}/boards/{self.board_id}", headers=self.user,
                                 json={"position": self.fen})
        assert resp.status_code == 200

    def play(self, plies=None, save_every=True):
        """The student plays the puzzle's solution on the board (and the page the opponent's reply), the page saving
        the board after every ply — or, a reply within 700 ms of the move, only after it."""
        board = chess.Board(self.puzzle["fen"])
        for i, san in enumerate(self.puzzle["solution"][:plies]):
            board.push_san(san)
            self.fen = board.fen()
            if save_every or i % 2 == 1 or i == len(self.puzzle["solution"]) - 1:
                self.save()

    def server_board(self):
        return session_store.get(self.sid).get_board(self.board_id)


def _five(app_screen):
    """The card, then five puzzles solved with the panel's «Дальше» between them; the answers in order."""
    answers = [app_screen.ask(WARMUP)]
    for n in range(2, 6):
        app_screen.play()
        answers.append(app_screen.ask(NEXT))
    app_screen.play()
    return answers


@pytest.mark.unit
class TestAppRun:
    def test_the_apps_requests_get_five_places_then_the_ending(self):
        """The tester's run as the app makes it: «Задача 1 из 5.» … «Задача 5 из 5.», and the sixth «Дальше» is
        the ending with the server's count — no sixth puzzle."""
        screen = _App("app-run")
        answers = _five(screen)
        assert [a["text"].split("\n")[0] for a in answers] == [f"Задача {n} из 5." for n in range(1, 6)]
        over = screen.ask(NEXT)
        assert over["text"].startswith("Разминка окончена: решено 5 из 5.\n\n")
        assert not [a for a in over["actions"] if a["type"] == "set_puzzle"]

    def test_the_ending_ends_the_puzzle_mode_so_it_is_seen(self):
        """The ending sets the board's own position again, stamped with the board: the app and the site leave the
        puzzle panel on it — the sheet shows the ending, the solved fifth puzzle stays on the board."""
        screen = _App("app-close")
        _five(screen)
        last = screen.fen
        over = screen.ask(NEXT)
        assert over["actions"] == [{"type": "set_fen", "fen": last, "board_id": screen.board_id}]
        assert screen.puzzle is None and screen.fen == last
        board = screen.server_board()
        assert board.kind == "study" and board.puzzle is None and board.fen == last

    def test_no_dalshe_is_left_to_bring_a_sixth_puzzle(self):
        """With the panel gone the next puzzle is a request of the student's own — the programme's task, as the
        ending offers; before, the panel's «Дальше» on the solved fifth puzzle brought it unasked."""
        screen = _App("app-after")
        _five(screen)
        screen.ask(NEXT)
        assert screen.puzzle is None              # nothing for the panel to show: no «Дальше» under the board
        after = screen.ask(NEXT)
        assert [a["puzzle_id"] for a in after["actions"] if a["type"] == "set_puzzle"] == ["site:l1:1"]
        assert "Разминка" not in after["text"]

    def test_the_count_holds_when_only_the_position_after_the_reply_is_saved(self):
        """The page plays the opponent's reply itself (clients, 18.11): a reply within 700 ms of the move leaves
        only the position after it saved — still the puzzle's line, and the final position still counts."""
        screen = _App("app-debounce")
        screen.ask(WARMUP)
        for _ in range(4):
            screen.play(save_every=False)
            screen.ask(NEXT)
        screen.play(save_every=False)
        assert screen.ask(NEXT)["text"].startswith("Разминка окончена: решено 5 из 5.")

    def test_a_hint_in_the_middle_of_the_puzzle_still_knows_the_puzzle(self):
        """«Подсказка» after the first move and the reply: the model gets the puzzle with its progress (it got
        none once the page had saved the board)."""
        screen = _App("app-hint")
        screen.ask(WARMUP)
        screen.play(plies=2)
        screen.ask(HINT)
        assert "## The puzzle on the board" in screen.message
        assert "the student is 2 half-move(s) into it" in screen.message


@pytest.mark.unit
class TestPuzzleBoardSaves:
    def _board(self):
        board = Board(session_id="s")
        row = ROWS[0]
        start = chess.Board(row["FEN"])
        start.push_uci(row["Moves"].split()[0])
        solution = []
        for uci in row["Moves"].split()[1:]:
            move = chess.Move.from_uci(uci)
            solution.append(start.san(move))
            start.push(move)
        fen = chess.Board(row["FEN"])
        fen.push_uci(row["Moves"].split()[0])
        board.apply_action({"type": "set_puzzle", "fen": fen.fen(), "solution": solution, "puzzle_id": "p"})
        return board, fen, solution

    def test_the_page_saving_the_puzzles_own_start_keeps_the_puzzle(self):
        """The first save comes 700 ms after the puzzle went up, with its own position: it was a study board then."""
        board, start, _ = self._board()
        board.set_position(start.fen())
        assert board.kind == "puzzle" and board.puzzle["puzzle_id"] == "p"

    def test_a_position_along_the_solution_is_the_puzzle_in_progress(self):
        """The move and the reply saved: still the puzzle, two half-moves in — the hint guard still hides the last
        move (it switched off in the middle of a multi-move puzzle)."""
        board, start, solution = self._board()
        start.push_san(solution[0])
        start.push_san(solution[1])
        board.set_position(start.fen())
        assert board.kind == "puzzle" and solution_line(board)["reached"] == 2
        last = start.parse_san(solution[2])
        assert secret_moves(board) == [(chess.square_name(last.from_square), chess.square_name(last.to_square))]

    def test_the_final_position_is_the_puzzle_solved(self):
        board, start, solution = self._board()
        for san in solution:
            start.push_san(san)
        board.set_position(start.fen())
        assert board.kind == "puzzle" and solution_line(board)["reached"] == 3 and secret_moves(board) == []

    def test_a_position_off_the_line_is_a_new_position(self):
        """Anything else the page saves — another move tried and kept, a position set by hand — is the student's
        own position, as before."""
        board, start, solution = self._board()
        start.push(next(m for m in start.legal_moves if start.san(m) != solution[0]))
        board.set_position(start.fen())
        assert board.kind == "study" and board.puzzle is None

    def test_the_coachs_own_set_fen_still_ends_the_puzzle(self):
        """A position put up by the coach (set_fen — the warm-up's ending among them) leaves the puzzle mode even
        when it is the puzzle's position: only the page's report of the board is progress."""
        board, start, _ = self._board()
        board.apply_action({"type": "set_fen", "fen": start.fen()})
        assert board.kind == "study" and board.puzzle is None
