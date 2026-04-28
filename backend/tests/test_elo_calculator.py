"""
Tests for FIDE Elo Calculator (pure functions, no DB needed).
"""

import pytest
import sys
import os

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.elo_calculator import (
    expected_score,
    get_k_factor,
    update_rating,
    assign_league,
    is_provisional,
    update_ratings_batch,
    RATING_FLOOR,
    PROVISIONAL_THRESHOLD,
)


class TestExpectedScore:
    def test_equal_ratings(self):
        """Equal ratings should produce expected score of 0.5."""
        assert expected_score(1500, 1500) == pytest.approx(0.5)

    def test_200_point_advantage(self):
        """200-point advantage should give ~0.76 expected score."""
        score = expected_score(1600, 1400)
        assert score == pytest.approx(0.7597, abs=0.001)

    def test_200_point_disadvantage(self):
        """200-point disadvantage should give ~0.24 expected score."""
        score = expected_score(1400, 1600)
        assert score == pytest.approx(0.2403, abs=0.001)

    def test_400_point_advantage(self):
        """400-point advantage should give ~0.91 expected score."""
        score = expected_score(1800, 1400)
        assert score == pytest.approx(0.9091, abs=0.001)

    def test_symmetry(self):
        """Expected scores for both sides should sum to 1.0."""
        e1 = expected_score(1500, 1700)
        e2 = expected_score(1700, 1500)
        assert e1 + e2 == pytest.approx(1.0)

    def test_large_difference(self):
        """Very large rating difference should not cause overflow."""
        score = expected_score(2800, 800)
        assert 0.99 < score <= 1.0


class TestKFactor:
    def test_provisional_player(self):
        """K=40 for players with <30 games."""
        assert get_k_factor(0, 1200) == 40
        assert get_k_factor(15, 1500) == 40
        assert get_k_factor(29, 2400) == 40  # still provisional even if high-rated

    def test_normal_player(self):
        """K=20 for players with >=30 games and rating <2300."""
        assert get_k_factor(30, 1200) == 20
        assert get_k_factor(100, 2000) == 20
        assert get_k_factor(50, 2299) == 20

    def test_high_rated_player(self):
        """K=10 for players with >=30 games and rating >=2300."""
        assert get_k_factor(30, 2300) == 10
        assert get_k_factor(100, 2500) == 10
        assert get_k_factor(500, 2800) == 10


class TestUpdateRating:
    def test_win_against_equal(self):
        """Win against equal-rated opponent with K=20."""
        new = update_rating(1500, 1500, 1.0, 20)
        # E=0.5, change = 20*(1-0.5) = 10
        assert new == 1510

    def test_loss_against_equal(self):
        """Loss against equal-rated opponent with K=20."""
        new = update_rating(1500, 1500, 0.0, 20)
        # E=0.5, change = 20*(0-0.5) = -10
        assert new == 1490

    def test_draw_against_equal(self):
        """Draw against equal-rated opponent with K=20."""
        new = update_rating(1500, 1500, 0.5, 20)
        assert new == 1500

    def test_win_against_weaker(self):
        """Win against much weaker opponent gives small gain."""
        new = update_rating(1800, 1400, 1.0, 20)
        # E ≈ 0.91, change ≈ 20*(1-0.91) ≈ 1.8 → rounds to 2
        assert new == 1802

    def test_loss_against_weaker(self):
        """Loss against much weaker opponent gives large loss."""
        new = update_rating(1800, 1400, 0.0, 20)
        # E ≈ 0.91, change ≈ 20*(0-0.91) ≈ -18.2 → rounds to -18
        assert new == 1782

    def test_rating_floor(self):
        """Rating should never go below floor of 800."""
        new = update_rating(810, 2000, 0.0, 40)
        assert new >= RATING_FLOOR

    def test_rating_floor_exact(self):
        """Even extreme loss should be floored at 800."""
        new = update_rating(800, 2800, 0.0, 40)
        assert new == RATING_FLOOR

    def test_provisional_k_factor(self):
        """Provisional K=40 produces larger swings."""
        new = update_rating(1200, 1200, 1.0, 40)
        # E=0.5, change = 40*(1-0.5) = 20
        assert new == 1220

    def test_known_fide_vector(self):
        """
        Known FIDE calculation example:
        Player rated 1800 vs opponent 1600, K=20, win.
        E = 1/(1+10^((1600-1800)/400)) = 1/(1+10^(-0.5)) ≈ 0.7597
        New = 1800 + 20*(1 - 0.7597) = 1800 + 4.806 ≈ 1805
        """
        new = update_rating(1800, 1600, 1.0, 20)
        assert new == 1805


class TestAssignLeague:
    def test_league_c_low(self):
        assert assign_league(800) == 'C'

    def test_league_c_boundary(self):
        assert assign_league(1399) == 'C'

    def test_league_b_lower(self):
        assert assign_league(1400) == 'B'

    def test_league_b_upper(self):
        assert assign_league(1799) == 'B'

    def test_league_a_lower(self):
        assert assign_league(1800) == 'A'

    def test_league_a_upper(self):
        assert assign_league(2199) == 'A'

    def test_league_master_lower(self):
        assert assign_league(2200) == 'Master'

    def test_league_master_high(self):
        assert assign_league(2800) == 'Master'


class TestIsProvisional:
    def test_zero_games(self):
        assert is_provisional(0) is True

    def test_under_threshold(self):
        assert is_provisional(29) is True

    def test_at_threshold(self):
        assert is_provisional(30) is False

    def test_over_threshold(self):
        assert is_provisional(100) is False


class TestUpdateRatingsBatch:
    def test_single_game(self):
        """Batch with one game should produce two changes (one per player)."""
        games = [{
            'white_id': 'w1',
            'black_id': 'b1',
            'white_rating': 1500,
            'black_rating': 1500,
            'result': 1.0,
            'white_games_played': 10,
            'black_games_played': 10,
        }]
        changes = update_ratings_batch(games)
        assert len(changes) == 2

        white_change = next(c for c in changes if c['player_id'] == 'w1')
        black_change = next(c for c in changes if c['player_id'] == 'b1')

        # K=40 for both (provisional), E=0.5
        assert white_change['k_factor_used'] == 40
        assert black_change['k_factor_used'] == 40
        assert white_change['change'] == 20   # 40*(1-0.5)
        assert black_change['change'] == -20  # 40*(0-0.5)

    def test_multiple_games(self):
        """Batch with two games should produce four changes."""
        games = [
            {
                'white_id': 'p1', 'black_id': 'p2',
                'white_rating': 1600, 'black_rating': 1400,
                'result': 1.0,
                'white_games_played': 50, 'black_games_played': 50,
            },
            {
                'white_id': 'p3', 'black_id': 'p4',
                'white_rating': 1200, 'black_rating': 1200,
                'result': 0.5,
                'white_games_played': 5, 'black_games_played': 5,
            },
        ]
        changes = update_ratings_batch(games)
        assert len(changes) == 4

        # p3 and p4 drew with equal ratings — no change
        p3 = next(c for c in changes if c['player_id'] == 'p3')
        p4 = next(c for c in changes if c['player_id'] == 'p4')
        assert p3['change'] == 0
        assert p4['change'] == 0

    def test_draw_between_unequal(self):
        """Draw between unequal ratings: weaker player gains, stronger loses."""
        games = [{
            'white_id': 'strong',
            'black_id': 'weak',
            'white_rating': 1800,
            'black_rating': 1400,
            'result': 0.5,
            'white_games_played': 50,
            'black_games_played': 50,
        }]
        changes = update_ratings_batch(games)
        strong = next(c for c in changes if c['player_id'] == 'strong')
        weak = next(c for c in changes if c['player_id'] == 'weak')

        assert strong['change'] < 0  # strong player lost rating (drew expected win)
        assert weak['change'] > 0    # weak player gained rating (drew expected loss)

    def test_empty_batch(self):
        """Empty game list returns empty changes."""
        assert update_ratings_batch([]) == []
