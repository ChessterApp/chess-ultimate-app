"""
Tests for Rating Service (recalculate_ratings_for_tournament).
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.rating_service import recalculate_ratings_for_tournament


class FakeQueryResult:
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


class FakeQueryBuilder:
    def __init__(self, data=None, count=None, sink=None):
        self._data = data or []
        self._count = count
        # `sink` lets tests observe insert/update payloads.
        self._sink = sink

    def select(self, *args, **kwargs):
        return self

    def insert(self, data, **kwargs):
        if self._sink is not None:
            if isinstance(data, list):
                self._sink.extend(data)
            else:
                self._sink.append(data)
        if isinstance(data, list):
            self._data = [{**row, 'id': f'new-{i}'} for i, row in enumerate(data)]
        else:
            self._data = [{**data, 'id': 'new-id'}]
        return self

    def update(self, data, **kwargs):
        if self._sink is not None:
            self._sink.append(('update', data))
        if self._data:
            self._data = [{**self._data[0], **data}]
        return self

    def eq(self, *args, **kwargs):
        return self

    def neq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def execute(self):
        return FakeQueryResult(data=self._data, count=self._count)


TOURNAMENT_ID = 'test-tournament-001'

RATED_OFFLINE_TOURNAMENT = {
    'id': TOURNAMENT_ID,
    'is_rated': True,
    'tournament_mode': 'offline',
    'status': 'completed',
}

UNRATED_OFFLINE_TOURNAMENT = {
    'id': TOURNAMENT_ID,
    'is_rated': False,
    'tournament_mode': 'offline',
    'status': 'completed',
}

RATED_ONLINE_TOURNAMENT = {
    'id': TOURNAMENT_ID,
    'is_rated': True,
    'tournament_mode': 'online',
    'status': 'completed',
}

SAMPLE_GAMES = [
    {
        'white_player_id': 'player_a',
        'black_player_id': 'player_b',
        'result': '1-0',
        'round': 1,
        'board': 1,
    },
    {
        'white_player_id': 'player_c',
        'black_player_id': 'player_d',
        'result': '1/2-1/2',
        'round': 1,
        'board': 2,
    },
]

SAMPLE_RATINGS = [
    {'user_id': 'player_a', 'rating': 1500, 'games_played': 10, 'peak_rating': 1520},
    {'user_id': 'player_b', 'rating': 1500, 'games_played': 10, 'peak_rating': 1510},
    {'user_id': 'player_c', 'rating': 1200, 'games_played': 50, 'peak_rating': 1250},
    {'user_id': 'player_d', 'rating': 1200, 'games_played': 50, 'peak_rating': 1230},
]


def _make_table_router(games_data, ratings_data, tournament=RATED_OFFLINE_TOURNAMENT, history_sink=None):
    """Route different table queries to different data."""
    call_counts = {'tournament_games': 0, 'player_ratings': 0, 'rating_history': 0, 'tournaments': 0}
    tournament_data = [tournament] if tournament else []

    def table(name):
        call_counts[name] = call_counts.get(name, 0) + 1
        if name == 'tournaments':
            return FakeQueryBuilder(data=tournament_data)
        if name == 'tournament_games':
            return FakeQueryBuilder(data=games_data)
        if name == 'player_ratings':
            return FakeQueryBuilder(data=ratings_data)
        if name == 'rating_history':
            return FakeQueryBuilder(data=[], sink=history_sink)
        return FakeQueryBuilder()

    return table, call_counts


class TestRecalculateRatings:
    def test_no_games_returns_zero(self):
        """Empty tournament produces no changes."""
        table, _ = _make_table_router([], [])
        with patch('services.rating_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = table
            result = recalculate_ratings_for_tournament(TOURNAMENT_ID)

        assert result['games_processed'] == 0
        assert result['players_updated'] == 0
        assert result['changes'] == []

    def test_single_game_produces_two_changes(self):
        """One game produces changes for both white and black."""
        games = [SAMPLE_GAMES[0]]
        table, _ = _make_table_router(games, SAMPLE_RATINGS[:2])
        with patch('services.rating_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = table
            result = recalculate_ratings_for_tournament(TOURNAMENT_ID)

        assert result['games_processed'] == 1
        assert result['players_updated'] == 2
        assert len(result['changes']) == 2

        # player_a won: should gain rating
        a_change = next(c for c in result['changes'] if c['player_id'] == 'player_a')
        assert a_change['change'] > 0
        assert a_change['rating_after'] > a_change['rating_before']

        # player_b lost: should lose rating
        b_change = next(c for c in result['changes'] if c['player_id'] == 'player_b')
        assert b_change['change'] < 0
        assert b_change['rating_after'] < b_change['rating_before']

    def test_draw_between_equal_ratings(self):
        """Draw between equal-rated players produces no rating change."""
        games = [SAMPLE_GAMES[1]]  # 1/2-1/2 between player_c and player_d
        table, _ = _make_table_router(games, SAMPLE_RATINGS[2:])
        with patch('services.rating_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = table
            result = recalculate_ratings_for_tournament(TOURNAMENT_ID)

        assert result['games_processed'] == 1
        c_change = next(c for c in result['changes'] if c['player_id'] == 'player_c')
        d_change = next(c for c in result['changes'] if c['player_id'] == 'player_d')
        assert c_change['change'] == 0
        assert d_change['change'] == 0

    def test_multiple_games_aggregated(self):
        """Multiple games are processed correctly."""
        table, _ = _make_table_router(SAMPLE_GAMES, SAMPLE_RATINGS)
        with patch('services.rating_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = table
            result = recalculate_ratings_for_tournament(TOURNAMENT_ID)

        assert result['games_processed'] == 2
        assert result['players_updated'] == 4
        assert len(result['changes']) == 4

    def test_new_player_gets_default_rating(self):
        """Player with no existing rating gets default 1200."""
        games = [{
            'white_player_id': 'new_player',
            'black_player_id': 'player_a',
            'result': '0-1',
            'round': 1,
            'board': 1,
        }]
        # Only player_a has existing rating
        table, _ = _make_table_router(games, [SAMPLE_RATINGS[0]])
        with patch('services.rating_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = table
            result = recalculate_ratings_for_tournament(TOURNAMENT_ID)

        new_change = next(c for c in result['changes'] if c['player_id'] == 'new_player')
        assert new_change['rating_before'] == 1200  # default

    def test_k_factor_used_correctly(self):
        """Provisional players use K=40, established use K=20 or K=10."""
        games = [{
            'white_player_id': 'player_a',  # 10 games = provisional, K=40
            'black_player_id': 'player_c',  # 50 games = established, K=20
            'result': '1-0',
            'round': 1,
            'board': 1,
        }]
        table, _ = _make_table_router(games, [SAMPLE_RATINGS[0], SAMPLE_RATINGS[2]])
        with patch('services.rating_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = table
            result = recalculate_ratings_for_tournament(TOURNAMENT_ID)

        a_change = next(c for c in result['changes'] if c['player_id'] == 'player_a')
        c_change = next(c for c in result['changes'] if c['player_id'] == 'player_c')
        assert a_change['k_factor_used'] == 40  # provisional
        assert c_change['k_factor_used'] == 20  # established

    def test_invalid_results_skipped(self):
        """Games with non-standard results are skipped."""
        games = [
            {
                'white_player_id': 'player_a',
                'black_player_id': 'player_b',
                'result': '+/-',  # forfeit — not in result_map
                'round': 1,
                'board': 1,
            },
        ]
        table, _ = _make_table_router(games, SAMPLE_RATINGS[:2])
        with patch('services.rating_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = table
            result = recalculate_ratings_for_tournament(TOURNAMENT_ID)

        # Forfeits are not in result_map, so skipped
        assert result['games_processed'] == 0


class TestRecalculateGating:
    """Verify the rated/offline hard-gate at the top of the recalc."""

    def test_recalculate_skips_when_tournament_not_rated(self):
        """is_rated=false → skipped_reason='not_rated', no DB rating writes."""
        history_sink = []
        table, _ = _make_table_router(
            SAMPLE_GAMES, SAMPLE_RATINGS,
            tournament=UNRATED_OFFLINE_TOURNAMENT,
            history_sink=history_sink,
        )
        with patch('services.rating_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = table
            result = recalculate_ratings_for_tournament(TOURNAMENT_ID)

        assert result['skipped_reason'] == 'not_rated'
        assert result['games_processed'] == 0
        assert result['players_updated'] == 0
        assert result['changes'] == []
        assert history_sink == []  # no rating_history rows inserted

    def test_recalculate_skips_when_tournament_online(self):
        """tournament_mode='online' → skipped_reason='not_offline', no DB writes."""
        history_sink = []
        table, _ = _make_table_router(
            SAMPLE_GAMES, SAMPLE_RATINGS,
            tournament=RATED_ONLINE_TOURNAMENT,
            history_sink=history_sink,
        )
        with patch('services.rating_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = table
            result = recalculate_ratings_for_tournament(TOURNAMENT_ID)

        assert result['skipped_reason'] == 'not_offline'
        assert result['games_processed'] == 0
        assert result['players_updated'] == 0
        assert result['changes'] == []
        assert history_sink == []

    def test_recalculate_runs_when_rated_offline(self):
        """is_rated=true AND tournament_mode='offline' → ratings update + history rows."""
        history_sink = []
        table, _ = _make_table_router(
            [SAMPLE_GAMES[0]], SAMPLE_RATINGS[:2],
            tournament=RATED_OFFLINE_TOURNAMENT,
            history_sink=history_sink,
        )
        with patch('services.rating_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = table
            result = recalculate_ratings_for_tournament(TOURNAMENT_ID)

        assert 'skipped_reason' not in result
        assert result['games_processed'] == 1
        assert result['players_updated'] == 2
        assert len(history_sink) == 2  # one row per player
        for row in history_sink:
            assert row['source_type'] == 'tournament'

    def test_recalculate_raises_when_tournament_missing(self):
        """Non-existent tournament_id → ValueError."""
        table, _ = _make_table_router([], [], tournament=None)
        with patch('services.rating_service._get_supabase') as mock_sb:
            mock_sb.return_value.table = table
            with pytest.raises(ValueError, match='Tournament not found'):
                recalculate_ratings_for_tournament(TOURNAMENT_ID)
