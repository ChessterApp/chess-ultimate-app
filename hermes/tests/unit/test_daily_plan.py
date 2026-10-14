"""Today's plan for the coach's home (src/daily_plan.py, P3b): stored data only, never made up."""

import json
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src import daily_plan
from src.daily_plan import build_daily_plan, load_daily_plan

pytestmark = pytest.mark.unit

PGN = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 1-0"
GAMES = [
    {"id": "g1", "white": "Student", "black": "Bot 1500", "eco": "C50", "opening_name": "Italian Game", "pgn": PGN},
    {"id": "g0", "white": "Bot", "black": "Student", "eco": "B20", "opening_name": "Sicilian Defense", "pgn": PGN},
]


def _insight(ref, *themes):
    return {"game_ref": ref, "blunders": [{"theme": t, "classification": "blunder", "cp_loss": 300} for t in themes]}


# Ten reviewed games: four with an endgame blunder; g1's review found three mistakes.
INSIGHTS = [_insight("g1", "endgame", "middlegame", "opening")] + [_insight(f"r{i}", "endgame") for i in range(3)] + [
    _insight(f"q{i}", "middlegame") for i in range(2)] + [_insight(f"c{i}") for i in range(4)]
FOCUS = [{"theme": "endgame", "score": 0.9, "blunder_count": 4}]
MINIMAL = {"kind": "daily_plan", "cards": [{"type": "weak_spot", "puzzles": 5}, {"type": "play_coach"}]}


def test_full_data():
    assert build_daily_plan(GAMES, INSIGHTS, FOCUS) == {"kind": "daily_plan", "cards": [
        {"type": "review_last_game", "game_id": "g1", "title": "Student – Bot 1500", "moments_count": 3},
        {"type": "weak_spot", "puzzles": 5, "theme": "endgame", "stat": {"games_with": 4, "games": 10}},
        {"type": "opening_lesson", "eco": "C50", "name": "Italian Game"},
        {"type": "play_coach"},
    ]}


@pytest.mark.parametrize("args", [(), (None, None, None), ([], [], []), ("x", {"a": 1}, 5)])
def test_no_data_gives_the_minimal_plan(args):
    assert build_daily_plan(*args) == MINIMAL


def test_games_without_reviews():
    cards = build_daily_plan(GAMES, None, None)["cards"]
    assert cards[0] == {"type": "review_last_game", "game_id": "g1", "title": "Student – Bot 1500"}  # no count
    assert cards[1] == {"type": "weak_spot", "puzzles": 5}  # no theme: puzzles on any theme
    assert [c["type"] for c in cards] == ["review_last_game", "weak_spot", "opening_lesson", "play_coach"]


def test_reviews_without_games_or_focus():
    cards = build_daily_plan(None, INSIGHTS, None)["cards"]
    # The most-blundered theme of the reviews stands in for the curriculum.
    assert cards == [
        {"type": "weak_spot", "puzzles": 5, "theme": "endgame", "stat": {"games_with": 4, "games": 10}},
        {"type": "play_coach"},
    ]


def test_too_few_reviews_for_a_stat():
    card = build_daily_plan(None, INSIGHTS[:2], FOCUS)["cards"][0]
    assert card == {"type": "weak_spot", "puzzles": 5, "theme": "endgame"}


def test_focus_theme_the_puzzles_do_not_know_falls_back():
    card = build_daily_plan(None, INSIGHTS, [{"theme": "blunder"}, "junk"])["cards"][0]
    assert card["theme"] == "endgame"


def test_stat_is_only_a_real_count():
    # Focus says middlegame; two of the ten reviews (plus g1) have a middlegame blunder.
    card = build_daily_plan(None, INSIGHTS, [{"theme": "middlegame"}])["cards"][0]
    assert card["stat"] == {"games_with": 3, "games": 10}
    # A theme no review has: no «0 of 10» line.
    card = build_daily_plan(None, INSIGHTS, [{"theme": "fork"}])["cards"][0]
    assert card == {"type": "weak_spot", "puzzles": 5, "theme": "fork"}


def test_no_review_card_for_a_short_or_broken_game():
    for game in ({**GAMES[0], "pgn": "1. e4 e5"}, {**GAMES[0], "pgn": None}, {**GAMES[0], "id": None}, "row"):
        cards = build_daily_plan([game], None, None)["cards"]
        assert "review_last_game" not in [c["type"] for c in cards]


def test_opening_needs_a_real_eco():
    games = [{"id": "g", "eco": "Z99", "opening_name": "Nonsense"}, {"id": "h", "eco": "b20", "opening_name": "Sicilian"}]
    cards = build_daily_plan(games, None, None)["cards"]
    assert {"type": "opening_lesson", "eco": "B20", "name": "Sicilian"} in cards


def test_at_most_four_cards_and_json_safe():
    plan = build_daily_plan(GAMES, INSIGHTS, FOCUS)
    assert len(plan["cards"]) <= 4
    assert json.loads(json.dumps(plan)) == plan


class TestLoad:
    def test_reads_every_source(self):
        sources = {"games": lambda: GAMES, "insights": lambda: INSIGHTS, "focus": lambda: FOCUS}
        with patch.object(daily_plan, "_sources", return_value=sources):
            assert load_daily_plan("u1") == build_daily_plan(GAMES, INSIGHTS, FOCUS)

    def test_a_late_source_is_left_out_within_the_budget(self):
        def slow():
            time.sleep(1.5)
            return GAMES

        sources = {"games": slow, "insights": lambda: INSIGHTS, "focus": lambda: FOCUS}
        started = time.monotonic()
        with patch.object(daily_plan, "_sources", return_value=sources):
            plan = load_daily_plan("u1", budget_s=0.2)
        assert time.monotonic() - started < 1.0
        assert [c["type"] for c in plan["cards"]] == ["weak_spot", "play_coach"]

    def test_a_failing_source_is_left_out(self):
        def boom():
            raise RuntimeError("supabase down")

        sources = {"games": boom, "insights": boom, "focus": boom}
        with patch.object(daily_plan, "_sources", return_value=sources):
            assert load_daily_plan("u1") == MINIMAL

    def test_real_sources_are_scoped_to_the_user(self):
        with patch("src.tools.user_data._query_user_games", return_value=None) as games, \
             patch("src.tools.game_insights.get_game_insights", return_value=[]) as insights, \
             patch("src.curriculum.get_cached_curriculum", return_value=[]) as focus:
            assert load_daily_plan("u1") == MINIMAL
        games.assert_called_once_with("u1", limit=5)
        insights.assert_called_once_with("u1", limit=10)
        focus.assert_called_once_with("u1")


class TestEndpoint:
    def setup_method(self):
        from src.server import app

        self.client = TestClient(app)

    def test_requires_user(self):
        assert self.client.get("/api/coach/daily-plan").status_code == 401

    def test_returns_the_plan(self):
        with patch("src.daily_plan.load_daily_plan", return_value=MINIMAL) as load:
            resp = self.client.get("/api/coach/daily-plan", headers={"X-User-Id": "u1"})
        assert resp.status_code == 200 and resp.json() == MINIMAL
        load.assert_called_once_with("u1")
