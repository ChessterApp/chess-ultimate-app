"""
Standard FIDE Elo Rating Calculator

Pure functions — no database access. All inputs/outputs are plain values.

FIDE Elo parameters:
  - Starting rating: 1200
  - K-factor: 40 (provisional, <30 games), 20 (rating <2300), 10 (rating >=2300)
  - Rating floor: 800
  - Expected score: E = 1 / (1 + 10^((Ro - Rp) / 400))
  - New rating:     R' = R + K * (S - E)
"""

RATING_FLOOR = 800
PROVISIONAL_THRESHOLD = 30


def expected_score(player_rating: int, opponent_rating: int) -> float:
    """
    FIDE expected score formula.
    E = 1 / (1 + 10^((Ro - Rp) / 400))
    where Rp = player_rating, Ro = opponent_rating.
    """
    exponent = (opponent_rating - player_rating) / 400.0
    return 1.0 / (1.0 + 10.0 ** exponent)


def get_k_factor(games_played: int, current_rating: int) -> int:
    """
    FIDE K-factor selection.
    - 40 if games_played < 30 (provisional)
    - 10 if current_rating >= 2300
    - 20 otherwise
    """
    if games_played < PROVISIONAL_THRESHOLD:
        return 40
    if current_rating >= 2300:
        return 10
    return 20


def update_rating(player_rating: int, opponent_rating: int, result: float, k_factor: int) -> int:
    """
    Compute new rating after a single game.
    result: 1.0 = win, 0.5 = draw, 0.0 = loss
    Returns new rating (integer, floored at RATING_FLOOR).
    """
    e = expected_score(player_rating, opponent_rating)
    new_rating = player_rating + k_factor * (result - e)
    return max(RATING_FLOOR, round(new_rating))


def assign_league(rating: int) -> str:
    """
    League assignment based on current rating.
    C: <1400, B: 1400-1799, A: 1800-2199, Master: 2200+
    """
    if rating >= 2200:
        return 'Master'
    if rating >= 1800:
        return 'A'
    if rating >= 1400:
        return 'B'
    return 'C'


def is_provisional(games_played: int) -> bool:
    """True if player has fewer than 30 rated games."""
    return games_played < PROVISIONAL_THRESHOLD


def update_ratings_batch(games: list) -> list:
    """
    Process a list of games, compute rating changes for all players.

    Each game dict must contain:
      - white_id: str
      - black_id: str
      - white_rating: int
      - black_rating: int
      - result: float (1.0 = white wins, 0.5 = draw, 0.0 = black wins)
      - white_games_played: int
      - black_games_played: int

    Returns a list of change dicts:
      [
        {
          'player_id': str,
          'rating_before': int,
          'rating_after': int,
          'change': int,
          'k_factor_used': int,
          'opponent_id': str,
        },
        ...
      ]
    """
    changes = []
    for game in games:
        white_k = get_k_factor(game['white_games_played'], game['white_rating'])
        black_k = get_k_factor(game['black_games_played'], game['black_rating'])

        white_new = update_rating(game['white_rating'], game['black_rating'], game['result'], white_k)
        black_new = update_rating(game['black_rating'], game['white_rating'], 1.0 - game['result'], black_k)

        changes.append({
            'player_id': game['white_id'],
            'rating_before': game['white_rating'],
            'rating_after': white_new,
            'change': white_new - game['white_rating'],
            'k_factor_used': white_k,
            'opponent_id': game['black_id'],
        })
        changes.append({
            'player_id': game['black_id'],
            'rating_before': game['black_rating'],
            'rating_after': black_new,
            'change': black_new - game['black_rating'],
            'k_factor_used': black_k,
            'opponent_id': game['white_id'],
        })

    return changes
