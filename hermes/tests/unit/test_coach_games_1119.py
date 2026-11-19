"""Tester, 19.11: right after a game with the coach, «Разбор последней партии» still offered DrNykterstein –
Night-King96, opened in the Database the day before. A game against the coach is a board of its session, never a row
of user_games; the plan now reads both (src/coach_games.py) and the card's review loads the coach's game."""

import chess
import pytest

from src import coach_games, daily_plan, game_owner
from src.tools import user_data

BOARD = "0f8fad5b-d9cb-469f-a165-70867728950e"
LONG = "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 0-1"
SAVED = {"id": "b1", "source": "lichess", "white": "DrNykterstein", "black": "Night-King96",
         "pgn": "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 *", "created_at": "2026-11-18T10:00:00+00:00"}


def _board(pgn=LONG, finished=True, color="black", when=1_763_546_400.0):  # 2025-11-19 — any fixed time
    return {"id": BOARD, "pgn": pgn, "updated_at": "2026-11-19T09:00:00+00:00",
            "game_state": {"status": "finished" if finished else "playing", "result": "0-1",
                           "student_color": color, "finished_at": when},
            "coach_sessions": {"user_id": "u1"}}


@pytest.fixture
def query(monkeypatch):
    calls = []

    def fake(table, params, **_):
        calls.append((table, params))
        return calls_rows.get(table)
    calls_rows = {}
    monkeypatch.setattr(user_data, "_supabase_query", fake)
    return calls, calls_rows


@pytest.mark.unit
class TestTheRows:
    def test_a_finished_game_reads_as_a_row_of_the_students_games(self, query):
        calls, rows = query
        rows["coach_boards"] = [_board(), _board(finished=False)]
        got = coach_games.recent("u1")
        assert [g["id"] for g in got] == [coach_games.PREFIX + BOARD]
        assert got[0]["source"] == "coach_game" and got[0]["title"] == "1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 … 0-1"
        params = calls[0][1]
        assert params["coach_sessions.user_id"] == "eq.u1" and params["kind"] == "eq.game"
        assert "coach_sessions!inner(user_id)" in params["select"]

    def test_not_read_is_none_and_the_plan_goes_on_without(self, query):
        assert coach_games.recent("u1") is None

    def test_one_game_only_through_the_students_session(self, query):
        calls, rows = query
        rows["coach_boards"] = [_board()]
        assert coach_games.game("u1", coach_games.PREFIX + BOARD)["pgn"] == LONG
        assert calls[-1][1]["coach_sessions.user_id"] == "eq.u1" and calls[-1][1]["id"] == f"eq.{BOARD}"
        assert coach_games.game("u1", coach_games.PREFIX + "x;drop") is None
        assert coach_games.game("u1", BOARD) is None  # a bare id is a user_games id

    def test_the_title_of_a_game_started_by_the_engine(self):
        assert coach_games.title("1. e4 e5 *", "*") == "1.e4 e5"
        assert coach_games.title("", "1-0") == "1-0"


@pytest.mark.unit
class TestTheCard:
    def _coach(self, when="2026-11-19T09:00:00+00:00", pgn=LONG):
        return {**coach_games._row(_board(pgn=pgn)), "created_at": when}

    def test_the_game_with_the_coach_after_the_saved_one_is_the_last_game(self):
        plan = daily_plan.build_daily_plan([SAVED], [], [], set(), [self._coach()])
        card = plan["cards"][0]
        assert card["type"] == "review_last_game" and card["game_id"] == coach_games.PREFIX + BOARD
        assert card["title"].startswith("1.e4 c5") and "whose" not in card

    def test_a_saved_game_after_it_is_still_the_last(self):
        newer = {**SAVED, "created_at": "2026-11-19T12:00:00+00:00"}
        card = daily_plan.build_daily_plan([newer], [], [], set(), [self._coach()])["cards"][0]
        assert card["game_id"] == "b1" and card["whose"] == "saved"

    def test_a_game_resigned_on_the_second_move_is_passed_over(self):
        short = self._coach(when="2026-11-19T11:00:00+00:00", pgn="1. e4 e5 2. Nf3 Nf6 0-1")
        card = daily_plan.build_daily_plan([SAVED], [], [], set(), [short, self._coach()])["cards"][0]
        assert card["game_id"] == coach_games.PREFIX + BOARD

    def test_without_the_coach_games_as_before(self):
        card = daily_plan.build_daily_plan([SAVED], [], [], set(), None)["cards"][0]
        assert card["game_id"] == "b1"


@pytest.mark.unit
class TestTheReview:
    def test_the_card_review_loads_the_game_and_tells_it_from_the_students_side(self, query):
        _, rows = query
        rows["coach_boards"] = [_board(color="black")]
        gid = coach_games.PREFIX + BOARD
        assert user_data.get_user_game_pgn("u1", gid) == LONG
        row, who = game_owner.review_owner("u1", gid)
        assert who.verdict == "own" and who.color == chess.BLACK and not who.neutral
        assert "The student played Black" in game_owner.review_block(row, who)

    def test_another_students_board_is_not_found(self, query):
        _, rows = query
        rows["coach_boards"] = []
        assert user_data.get_user_game_pgn("u2", coach_games.PREFIX + BOARD) is None
