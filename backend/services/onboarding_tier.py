"""
Onboarding skill-tier + starting-level derivation (single source of truth).

Pure, framework-free. Mirror of the TS implementation at
`frontend/src/lib/onboarding/deriveTier.ts` — keep the bands/outputs IDENTICAL
on both sides (see the onboarding-persist spec). If you change a band here,
change it there too.

Inputs (from the anonymous onboarding funnel, camelCase; snake_case also
accepted for robustness):
  experience    "beginner" | "intermediate" | "advanced"
  onlineRating  number, rating pulled from Chess.com/Lichess (0 if none)
  eloRating     number, self-rated slider (defaults to 800)
  noRating      bool, user checked "I don't have a rating"

Effective rating:
  rating = onlineRating > 0 ? onlineRating : (noRating ? None : eloRating)
  i.e. a platform rating wins; otherwise the self-rated slider applies unless the
  user explicitly has no rating, in which case experience decides the tier.

Derivation table (first match wins; rating bands beat experience):
  rating >= 1600                         -> elo_1600    level 6   mateIn3
  rating 1500-1599                       -> elo_1500    level 5   mateIn3
  rating 1400-1499                       -> elo_1400    level 4   mateIn3
  rating 1-1399 (has some rating)        -> advanced    level 3   mateIn2
  no rating, experience == advanced      -> advanced    level 3   mateIn2
  no rating, experience == intermediate  -> knows_rules level 2   mateIn1
  otherwise (beginner / unknown)         -> beginner    level 1   level-1 lesson

starting_level is clamped server-side to [1, num_levels] (never below 1).
"""

from __future__ import annotations

# Default self-rated elo when the slider value is absent (see frontend default).
DEFAULT_ELO_RATING = 800

# Puzzle theme per tier — kept here so the mapping is centralized and trivially
# adjustable. Not part of the derive return value, but the TS mirror exposes it
# as `puzzleTheme`; consumers that need it can look it up.
PUZZLE_THEME_BY_TIER = {
    'elo_1600': 'mateIn3',
    'elo_1500': 'mateIn3',
    'elo_1400': 'mateIn3',
    'advanced': 'mateIn2',
    'knows_rules': 'mateIn1',
    'beginner': 'beginner',
}


def _pick(answers: dict, *keys):
    """Return the first present (non-None) value among keys (camelCase first)."""
    for key in keys:
        value = answers.get(key)
        if value is not None:
            return value
    return None


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def derive_tier_and_level(answers: dict, num_levels: int) -> dict:
    """Derive {skill_tier, starting_level} from onboarding answers.

    `num_levels` clamps starting_level to [1, num_levels]. A non-positive
    num_levels is treated as 1 (there is always at least a level 1).
    """
    answers = answers or {}

    online_rating = _to_int(_pick(answers, 'onlineRating', 'online_rating'))
    no_rating = bool(_pick(answers, 'noRating', 'no_rating'))

    elo_raw = _pick(answers, 'eloRating', 'elo_rating')
    elo_rating = _to_int(elo_raw) if elo_raw is not None else DEFAULT_ELO_RATING

    experience = str(_pick(answers, 'experience') or '').strip().lower()

    # Effective rating: platform rating wins; else slider unless "no rating".
    if online_rating > 0:
        rating = online_rating
    elif no_rating:
        rating = None
    else:
        rating = elo_rating

    if rating is not None and rating >= 1600:
        skill_tier, level = 'elo_1600', 6
    elif rating is not None and 1500 <= rating <= 1599:
        skill_tier, level = 'elo_1500', 5
    elif rating is not None and 1400 <= rating <= 1499:
        skill_tier, level = 'elo_1400', 4
    elif rating is not None and rating >= 1:
        skill_tier, level = 'advanced', 3
    elif experience == 'advanced':
        skill_tier, level = 'advanced', 3
    elif experience == 'intermediate':
        skill_tier, level = 'knows_rules', 2
    else:
        skill_tier, level = 'beginner', 1

    max_level = max(1, _to_int(num_levels))
    starting_level = min(max(level, 1), max_level)

    return {'skill_tier': skill_tier, 'starting_level': starting_level}
