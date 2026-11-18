"""Someone else's game saved to «Мои партии» is not offered or told as the student's own (tester's report 18.11).

The daily plan's card «Разбор последней партии» showed DrNykterstein – Night-King96: a game the tester had opened in
the Database section and saved («Сохранить в Мои партии»). It became a row of user_games like the games he played; the
card took the latest row, its request said «Разбери мою последнюю партию» and the coach answered «нападением на твоего
ферзя». The server now decides whose a saved game is (src/game_owner.py) — by the student's linked Lichess / Chess.com
names when it knows them, else by where the row came from (the site and the app tag a game saved from the Database
section with its base: twic, lichess, chesscom) — and the card offers only a game not known to be someone else's; a
review of someone else's game is told about the players, never «ты», «твой».
"""

import json
from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src import daily_plan, game_owner
from src.daily_plan import build_daily_plan, load_daily_plan
from src.game_owner import owner, review_block
from src.server import app
from src.user_profile import UserProfile

pytestmark = pytest.mark.unit

PGN = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 1-0"
DATABASE_GAME = {"id": "db1", "white": "DrNykterstein", "black": "Night-King96", "source": "lichess",
                 "eco": "B90", "opening_name": "Sicilian Defense: Najdorf Variation", "pgn": PGN}
MASTER_GAME = {"id": "tw1", "white": "Carlsen, Magnus", "black": "Nepomniachtchi, Ian", "source": "twic",
               "eco": "C65", "opening_name": "Ruy Lopez: Berlin Defense", "pgn": PGN}
OWN_GAME = {"id": "g1", "white": "Student", "black": "Bot 1500", "source": "manual", "eco": "C50",
            "opening_name": "Italian Game", "pgn": PGN}


class TestWhose:
    def test_a_game_saved_from_the_database_is_someone_elses(self):
        """The tester's game: a Lichess game saved from the Database section, no linked account."""
        assert owner(DATABASE_GAME).foreign and owner(DATABASE_GAME, set()).foreign
        assert owner(MASTER_GAME).foreign

    def test_a_game_with_the_coach_is_the_students(self):
        assert owner({"white": "Вы", "black": "Тренер", "source": "coach_game"}).verdict == "own"

    def test_a_pasted_game_is_not_known_either_way(self):
        """As before: a pasted or imported game is reviewed as the student's (it mostly is)."""
        assert owner(OWN_GAME).verdict == "unknown" and owner({"white": "A", "black": "B"}).verdict == "unknown"

    def test_a_linked_name_makes_a_lichess_game_the_students_with_its_side(self):
        """The student looked up their own Lichess games in the Database section and saved one: it is theirs, and
        their colour is known."""
        who = owner({**DATABASE_GAME, "black": "asan_k"}, {"asan_k"})
        assert who.verdict == "own" and who.color == chess.BLACK

    def test_linked_names_that_play_neither_side_make_a_platform_game_someone_elses(self):
        assert owner({**DATABASE_GAME, "source": "chesscom"}, {"asan_k"}).foreign

    def test_an_over_the_board_game_is_not_judged_by_an_online_name(self):
        """Real names typed into a pasted game are no online account: not known, as before."""
        assert owner({"white": "Иван Петров", "black": "Сергей", "source": "manual"}, {"asan_k"}).verdict == "unknown"


class TestTheCard:
    def test_the_card_skips_a_saved_database_game_for_the_students_own(self):
        """The latest row is DrNykterstein – Night-King96: the card offers the game before it, the student's."""
        cards = build_daily_plan([DATABASE_GAME, MASTER_GAME, OWN_GAME], None, None)["cards"]
        assert cards[0] == {"type": "review_last_game", "game_id": "g1", "title": "Student – Bot 1500"}

    def test_no_card_when_every_recent_game_is_someone_elses(self):
        cards = build_daily_plan([DATABASE_GAME, MASTER_GAME], None, None)["cards"]
        assert "review_last_game" not in [c["type"] for c in cards]

    def test_the_opening_card_is_not_from_someone_elses_game(self):
        """«The opening of your latest game» is the Italian of the student's game, not the Najdorf they looked at."""
        cards = build_daily_plan([DATABASE_GAME, OWN_GAME], None, None)["cards"]
        assert {"type": "opening_lesson", "eco": "C50", "name": "Italian Game"} in cards

    def test_the_plan_reads_the_linked_names(self):
        """A linked Lichess name that plays in the saved game makes it the student's again."""
        mine = {**DATABASE_GAME, "white": "Asan_K"}
        sources = {"games": lambda: [mine], "insights": lambda: [], "focus": lambda: [], "names": lambda: {"asan_k"}}
        with patch.object(daily_plan, "_sources", return_value=sources), \
                patch("src.engine_precompute.game_offered"):
            plan = load_daily_plan("u1")
        assert plan["cards"][0]["game_id"] == "db1"


class TestTheReview:
    def test_the_note_for_someone_elses_game(self):
        note = review_block(DATABASE_GAME, owner(DATABASE_GAME))
        assert "NOT the student's own" in note and "DrNykterstein (White) – Night-King96 (Black)" in note
        assert "never «ты», «твой»" in note

    def test_the_note_for_the_students_game_names_their_side(self):
        game = {**DATABASE_GAME, "black": "asan_k"}
        note = review_block(game, owner(game, {"asan_k"}))
        assert "The student played Black" in note

    def test_no_note_when_not_known(self):
        assert review_block(OWN_GAME, owner(OWN_GAME)) == ""

    @patch("src.tools.critical_moments.find_critical_moments")
    @patch("src.tools.user_data.get_user_game_pgn")
    @patch("src.server._create_agent")
    @patch("src.server.load_user_profile")
    def test_the_cards_request_for_someone_elses_game_is_reviewed_neutrally(self, mock_profile, mock_agent,
                                                                             mock_pgn, mock_scan):
        """«Разбери мою последнюю партию» with the id of the saved database game: the model is told whose it is, and
        the moments are not «the student's game»."""
        mock_profile.return_value = UserProfile(user_id="owner-user")
        mock_pgn.return_value = ('[White "DrNykterstein"]\n[Black "Night-King96"]\n[Result "1-0"]\n\n'
                                 "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nd4 4. Nxe5 Qg5 1-0")
        mock_scan.return_value = {"total_moves": 8, "engine_depth": 12, "critical_moments": [{
            "move_number": 4, "side": "white", "move": "Nxe5", "eval_before": 0.5, "eval_after": -4.0,
            "type": "blunder", "fen_before": "r1bqkbnr/pppp1ppp/8/4p3/2BnP3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
            "best_move": "Nxd4"}]}
        seen = {}
        agent = MagicMock()
        agent.chat.side_effect = lambda message, stream_callback=None: (seen.update(message=message), "Разберём.")[1]
        mock_agent.return_value = agent
        with patch.object(game_owner, "game_row", return_value=DATABASE_GAME), \
                patch.object(game_owner, "linked_names", return_value=set()):
            resp = TestClient(app).post("/api/coach/chat", headers={"X-User-Id": "owner-user"}, json={
                "message": "Разбери мою последнюю партию: где я ошибся и что стоило играть.", "review_game_id": "db1"})
        assert resp.status_code == 200
        assert "## Whose game this is" in seen["message"] and "NOT the student's own" in seen["message"]
        assert "someone else's game, not theirs" in seen["message"]
        assert "Critical moments of the student's game" not in seen["message"]


def test_the_games_tool_marks_someone_elses_rows():
    """The model's own get_user_games for «мою последнюю партию»: the saved database game says whose it is."""
    from src.tools.user_data import _handle_get_user_games

    with patch("src.tools.user_data._query_user_games", return_value=[dict(DATABASE_GAME), dict(OWN_GAME)]), \
            patch.object(game_owner, "linked_names", return_value=set()):
        games = json.loads(_handle_get_user_games({"user_id": "u1"}, user_id="u1"))["games"]
    assert "someone else's game" in games[0]["whose"] and "whose" not in games[1]
