"""A hint never shows the puzzle's solution on the board (tester's report 16.11, fixed 17.11).

«Подскажи идею в этой задаче, не называя ход.» — the coach answered in words, and the solution's arrow a1→a8 went
to the board. The server knows the solution of the puzzle on the board (src/solution_guard.py): until the puzzle is
solved or the system has shown the solution, no arrow or highlight of a remaining solution move is drawn — the
model's inline marks, its board tools, text and voice alike —, the mark is not written out as the move, and the
puzzle_solution tool answers only a student who asked for the solution.
"""

import json
from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src.board_markup import MarkupFilter, strip_markup
from src.server import app, session_store
from src.solution_guard import is_revealed, reveal, secret_moves, withhold_solution
from src.tools.puzzles import _handle_puzzle_solution
from src.user_profile import UserProfile

BACK_RANK = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"   # the report's picture: Ra8# — the arrow a1→a8
MATE2 = "3rkr2/1Qpb4/p1B1pq2/7p/3PN1p1/B1P3P1/P4nKP/R4R2 b - - 3 24"   # Qf3+ Kg1 Nh3#
MATE2_SOLUTION = ["Qf3+", "Kg1", "Nh3#"]
HINT = "Подскажи идею в этой задаче, не называя ход."


def _puzzle_session(user, fen=BACK_RANK, solution=("Ra8#",)):
    session = session_store.create(user)
    board = session.ensure_board()
    session.apply_board_actions([{"type": "set_puzzle", "fen": fen, "solution": list(solution), "puzzle_id": "h1"}],
                                board_id=board.id)
    return session, session.get_board(session.active_board_id)


def _arrows(*moves, brush="green"):
    return {"type": "draw_arrows", "arrows": [{"from": m[:2], "to": m[2:4], "brush": brush} for m in moves]}


# ── what is secret ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSecretMoves:
    def test_the_remaining_solution_moves_of_an_unsolved_puzzle(self):
        _, board = _puzzle_session("hint-secret", MATE2, MATE2_SOLUTION)
        assert secret_moves(board) == [("f6", "f3"), ("g2", "g1"), ("f2", "h3")]
        b = chess.Board(MATE2)
        b.push_san("Qf3+")
        b.push_san("Kg1")
        board.fen = b.fen()  # two half-moves in: only the last move is still hidden
        assert secret_moves(board) == [("f2", "h3")]

    def test_nothing_is_secret_once_solved_revealed_or_without_a_puzzle(self):
        session, board = _puzzle_session("hint-open", MATE2, MATE2_SOLUTION)
        b = chess.Board(MATE2)
        for san in MATE2_SOLUTION:
            b.push_san(san)
        board.fen = b.fen()
        assert secret_moves(board) == []                       # solved
        board.fen = MATE2
        reveal(session, board)
        assert is_revealed(board) and secret_moves(board) == []  # shown by the system
        study = session_store.create("hint-study").ensure_board()
        assert secret_moves(study) == [] and secret_moves(None) == []

    def test_a_new_puzzle_on_the_board_is_hidden_again(self):
        session, board = _puzzle_session("hint-next")
        reveal(session, board)
        session.apply_board_actions([{"type": "set_puzzle", "fen": MATE2, "solution": MATE2_SOLUTION, "puzzle_id": "h2"}],
                                    board_id=board.id)
        assert secret_moves(session.get_board(board.id)) == [("f6", "f3"), ("g2", "g1"), ("f2", "h3")]


# ── the board actions ───────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestWithholdSolution:
    def test_the_solution_arrow_goes_another_arrow_stays(self):
        _, board = _puzzle_session("hint-arrows")
        kept, withheld = withhold_solution([_arrows("a1a8")], board)
        assert kept == [] and withheld == ["a1a8"]
        kept, withheld = withhold_solution([_arrows("g8h8", "a1a8", "h2h3")], board)
        assert [a["from"] + a["to"] for a in kept[0]["arrows"]] == ["g8h8", "h2h3"] and withheld == ["a1a8"]
        untouched = [_arrows("a1d1"), {"type": "flip_board"}]
        assert withhold_solution(untouched, board) == (untouched, [])

    def test_every_remaining_move_of_a_longer_solution(self):
        _, board = _puzzle_session("hint-line", MATE2, MATE2_SOLUTION)
        kept, withheld = withhold_solution([_arrows("f6f3", "g2g1", "f2h3", "d7c6")], board)
        assert [a["from"] + a["to"] for a in kept[0]["arrows"]] == ["d7c6"]
        assert withheld == ["f6f3", "g2g1", "f2h3"]

    def test_a_highlight_of_both_squares_of_the_move_is_the_move(self):
        _, board = _puzzle_session("hint-squares")
        kept, withheld = withhold_solution([{"type": "highlight_squares", "squares": ["a1", "a8"], "color": "green"}], board)
        assert kept == [] and withheld == ["a1a8"]
        kept, _ = withhold_solution([{"type": "highlight_squares", "squares": ["a8", "g8", "a1"], "color": "red"}], board)
        assert kept == [{"type": "highlight_squares", "squares": ["g8"], "color": "red"}]
        # One square alone is a hint — the piece to look at, the weak square — and stays.
        for squares in (["a1"], ["a8", "g8"], ["f7", "g7", "h7"]):
            action = {"type": "highlight_squares", "squares": squares, "color": "yellow"}
            assert withhold_solution([action], board) == ([action], [])

    def test_nothing_is_withheld_once_the_solution_was_shown_or_the_puzzle_solved(self):
        session, board = _puzzle_session("hint-shown")
        reveal(session, board)
        assert withhold_solution([_arrows("a1a8")], board) == ([_arrows("a1a8")], [])
        _, solved = _puzzle_session("hint-solved")
        b = chess.Board(BACK_RANK)
        b.push_san("Ra8#")
        solved.fen = b.fen()
        assert withhold_solution([_arrows("a1a8")], solved) == ([_arrows("a1a8")], [])

    def test_the_board_follows_the_position_actions_of_the_list(self):
        study = session_store.create("hint-follow").ensure_board()
        put = {"type": "set_puzzle", "fen": BACK_RANK, "solution": ["Ra8#"], "puzzle_id": "h1"}
        kept, withheld = withhold_solution([put, _arrows("a1a8")], study)
        assert kept == [put] and withheld == ["a1a8"]          # a puzzle put up and its solution drawn in one call
        _, board = _puzzle_session("hint-replaced")
        other = {"type": "set_fen", "fen": chess.STARTING_FEN}
        assert withhold_solution([other, _arrows("a1a8")], board) == ([other, _arrows("a1a8")], [])


# ── the inline marks ────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestMarks:
    def test_a_solution_mark_is_cut_and_not_written_out_as_the_move(self):
        # Without the guard the mark standing where the move's words are due is written out: «…шаха — Ra8#.»
        open_text, open_actions = strip_markup("Начни с шаха — [[arrows: a1a8]].", BACK_RANK)
        assert "Ra8" in open_text and open_actions
        text, actions = strip_markup("Начни с шаха — [[arrows: a1a8]].", BACK_RANK, secret=lambda: [("a1", "a8")])
        assert actions == [] and "a8" not in text and "Ra8" not in text and "[[" not in text

    def test_the_other_arrows_of_the_same_answer_are_drawn(self):
        f = MarkupFilter(BACK_RANK, secret=lambda: [("a1", "a8")])
        text, actions = f.feed("Посмотри на короля [[arrows: g8h8 red, a1a8 green]] и на последнюю горизонталь.")
        text += f.flush()
        assert actions == [{"type": "draw_arrows", "arrows": [{"from": "g8", "to": "h8", "brush": "red"}]}]
        assert f.withheld == ["a1a8"] and "[[" not in text

    def test_the_secret_is_read_at_every_mark(self):
        secret = []
        f = MarkupFilter(BACK_RANK, secret=lambda: secret)
        _, first = f.feed("Ладья [[arrows: a1a8]] ")
        secret.append(("a1", "b1"))   # a puzzle came onto the board mid-answer
        _, second = f.feed("и ещё [[arrows: a1b1]].")
        assert first and not second


# ── the puzzle_solution tool ────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSolutionTool:
    @pytest.mark.parametrize("words", [HINT, "Дай подсказку", "что здесь делать?", "", "give me a hint"])
    def test_unasked_it_shows_nothing(self, words):
        session, board = _puzzle_session("hint-tool-closed")
        out = json.loads(_handle_puzzle_solution({}, session_id=session.id, student_message=words))
        assert out["withheld"] and "board_actions" not in out and "Ra8" not in json.dumps(out)
        assert not is_revealed(board) and secret_moves(board) == [("a1", "a8")]

    @pytest.mark.parametrize("kwargs", [
        {"student_message": "Сдаюсь, покажи решение"}, {"student_message": "I give up"},
        {"student_message": "берілемін"}, {"caller": "site"},   # the voice page, for the words the server read
    ])
    def test_asked_it_shows_and_the_solution_is_open_from_then_on(self, kwargs):
        session, board = _puzzle_session("hint-tool-open")
        out = json.loads(_handle_puzzle_solution({}, session_id=session.id, **kwargs))
        assert out["ok"] and out["board_actions"][0]["arrows"][0]["from"] == "a1"
        board = session.get_board(board.id)
        assert is_revealed(board)
        # «а почему именно так?» on the next turn: the model may call the tool and draw the move again.
        again = json.loads(_handle_puzzle_solution({}, session_id=session.id, student_message="а почему именно так?"))
        assert again["ok"] and withhold_solution(again["board_actions"], board)[0] == again["board_actions"]


# ── the turn ────────────────────────────────────────────────────────────────────────────────────

def _turn(user, message, said, fen=BACK_RANK, solution=("Ra8#",)):
    client = TestClient(app)
    headers = {"X-User-Id": user}
    sid = client.post("/api/coach/sessions", headers=headers).json()["id"]
    session = session_store.get(sid, user)
    board = session.ensure_board()
    session.apply_board_actions([{"type": "set_puzzle", "fen": fen, "solution": list(solution), "puzzle_id": "h1"}],
                                board_id=board.id)
    with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
        mock_profile.return_value = UserProfile(user_id=user)
        agent = MagicMock()

        def _chat(_message, stream_callback=None):
            if stream_callback:
                for part in said:
                    stream_callback(part)
            return "ok"

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent
        resp = client.post("/api/coach/chat", headers=headers, json={"message": message, "session_id": sid, "fen": fen})
        assert resp.status_code == 200
    frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
    drawn = [a["from"] + a["to"] for f in frames for act in f.get("board_actions", [])
             if act.get("type") == "draw_arrows" for a in act["arrows"]]
    text = "".join(f.get("delta", "") for f in frames)
    return drawn, text, session


@pytest.mark.unit
class TestTurn:
    def test_a_hint_draws_no_solution_arrow(self):
        drawn, text, session = _turn("hint-turn", HINT, [
            "Посмотри на последнюю горизонталь: король чёрных заперт своими пешками. ",
            "[[arrows: a1a8 green]] Какая фигура может туда попасть?"])
        assert drawn == [] and "[[" not in text and "заперт" in text
        assert (session.active_board().annotations or {}).get("arrows") in (None, [])

    def test_a_hint_keeps_the_arrows_that_are_not_the_solution(self):
        drawn, _, _ = _turn("hint-turn-other", HINT, [
            "Король заперт пешками [[arrows: g8h8 red]]. Подумай, чем дать шах [[arrows: a1a8]]."])
        assert drawn == ["g8h8"]

    def test_the_solution_asked_for_is_still_shown_and_the_models_arrows_pass(self):
        drawn, text, session = _turn("hint-turn-asked", "Сдаюсь, покажи решение", [
            "Решение: 1.Ra8#. Ладья идёт на последнюю горизонталь [[arrows: a1a8 green]]."])
        assert "a1a8" in drawn and "Ra8#" in text and is_revealed(session.active_board())

    def test_a_position_that_is_no_puzzle_hides_nothing(self):
        b = chess.Board(MATE2)
        for san in MATE2_SOLUTION[:2]:
            b.push_san(san)
        # The same position as a study board (no puzzle record): the mating move is drawn as before.
        client = TestClient(app)
        headers = {"X-User-Id": "hint-turn-study"}
        sid = client.post("/api/coach/sessions", headers=headers).json()["id"]
        with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
            mock_profile.return_value = UserProfile(user_id="hint-turn-study")
            agent = MagicMock()
            agent.chat.side_effect = lambda _m, stream_callback=None: (
                stream_callback("Конь ставит мат [[arrows: f2h3 green]].") if stream_callback else None) or "ok"
            mock_agent.return_value = agent
            resp = client.post("/api/coach/chat", headers=headers,
                               json={"message": "Что здесь лучше всего?", "session_id": sid, "fen": b.fen()})
        frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
        assert any(act.get("type") == "draw_arrows" for f in frames for act in f.get("board_actions", []))


# ── the voice tools ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestVoiceTools:
    def _call(self, user, name, body, session):
        return TestClient(app).post(f"/api/coach/tool/{name}", headers={"X-User-Id": user},
                                    json={"session_id": session.id, **body}).json()

    def test_board_control_cannot_draw_the_solution(self):
        session, _ = _puzzle_session("hint-voice")
        out = self._call("hint-voice", "board_control", {
            "args": {"action_type": "draw_arrows", "arrows": [{"from": "a1", "to": "a8", "brush": "green"}]},
            "utterance": "подскажи идею"}, session)
        assert out["board_actions"] == [] and out["result"]["solution_withheld"] == ["a1a8"]

    def test_the_models_own_call_for_the_solution_is_refused_the_sites_is_not(self):
        session, _ = _puzzle_session("hint-voice-tool")
        out = self._call("hint-voice-tool", "puzzle_solution", {"args": {}, "utterance": "подскажи идею"}, session)
        assert out["board_actions"] == [] and out["result"]["withheld"]
        out = self._call("hint-voice-tool", "puzzle_solution", {"args": {}, "utterance": "сдаюсь", "caller": "site"}, session)
        assert [a["from"] + a["to"] for a in out["board_actions"][0]["arrows"]] == ["a1a8"]
