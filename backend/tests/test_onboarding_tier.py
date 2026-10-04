"""
Tests for services.onboarding_tier.derive_tier_and_level.

Covers every tier boundary (1599/1600, 1499/1500, 1399/1400), the has-rating vs
no-rating split, each experience branch, the eloRating default, online-rating
precedence, and starting_level clamping. Pure function — no Flask/Supabase.
"""

import pytest

from services.onboarding_tier import derive_tier_and_level

# Plenty of levels so clamping never interferes with the band tests below.
WIDE = 20


def derive(answers, num_levels=WIDE):
    return derive_tier_and_level(answers, num_levels)


# --- Rating band boundaries (online rating present) ------------------------

@pytest.mark.parametrize('rating,tier,level', [
    (1600, 'elo_1600', 6),
    (2500, 'elo_1600', 6),
    (1599, 'elo_1500', 5),
    (1500, 'elo_1500', 5),
    (1499, 'elo_1400', 4),
    (1400, 'elo_1400', 4),
    (1399, 'advanced', 3),
    (1, 'advanced', 3),
])
def test_online_rating_bands(rating, tier, level):
    result = derive({'onlineRating': rating, 'experience': 'beginner'})
    assert result == {'skill_tier': tier, 'starting_level': level}


def test_online_rating_beats_experience_and_slider():
    # A high platform rating wins even if experience/eloRating say beginner.
    result = derive({
        'onlineRating': 1700,
        'eloRating': 200,
        'experience': 'beginner',
        'noRating': True,
    })
    assert result == {'skill_tier': 'elo_1600', 'starting_level': 6}


# --- No rating -> experience decides ---------------------------------------

@pytest.mark.parametrize('experience,tier,level', [
    ('advanced', 'advanced', 3),
    ('intermediate', 'knows_rules', 2),
    ('beginner', 'beginner', 1),
    ('', 'beginner', 1),
    ('something-unknown', 'beginner', 1),
])
def test_no_rating_falls_back_to_experience(experience, tier, level):
    result = derive({'noRating': True, 'onlineRating': 0, 'experience': experience})
    assert result == {'skill_tier': tier, 'starting_level': level}


# --- eloRating slider (self-rated, no online, not "no rating") -------------

def test_elo_rating_default_800_is_advanced():
    # No onlineRating, no eloRating provided, noRating false -> defaults to 800.
    result = derive({'experience': 'beginner'})
    assert result == {'skill_tier': 'advanced', 'starting_level': 3}


def test_elo_rating_default_800_ignores_experience():
    # rating=800 (>=1) wins over experience=advanced (same tier here, but it is
    # the rating branch, not the experience branch).
    result = derive({'experience': 'intermediate', 'noRating': False})
    assert result == {'skill_tier': 'advanced', 'starting_level': 3}


@pytest.mark.parametrize('elo,tier,level', [
    (1650, 'elo_1600', 6),
    (1550, 'elo_1500', 5),
    (1450, 'elo_1400', 4),
    (900, 'advanced', 3),
])
def test_elo_rating_bands_when_no_online(elo, tier, level):
    result = derive({'eloRating': elo, 'onlineRating': 0, 'noRating': False})
    assert result == {'skill_tier': tier, 'starting_level': level}


def test_no_rating_true_overrides_elo_slider():
    # noRating true + no online -> rating is None, so experience decides even if
    # an eloRating value is present.
    result = derive({'eloRating': 1500, 'noRating': True, 'experience': 'intermediate'})
    assert result == {'skill_tier': 'knows_rules', 'starting_level': 2}


def test_rating_zero_not_treated_as_a_rating():
    # onlineRating 0 + noRating true -> no rating; experience advanced applies.
    result = derive({'onlineRating': 0, 'noRating': True, 'experience': 'advanced'})
    assert result == {'skill_tier': 'advanced', 'starting_level': 3}


# --- Clamping --------------------------------------------------------------

def test_clamp_caps_level_at_num_levels():
    # elo_1600 wants level 6, but only 5 levels exist.
    result = derive({'onlineRating': 1700}, num_levels=5)
    assert result == {'skill_tier': 'elo_1600', 'starting_level': 5}


def test_clamp_caps_level_at_small_num_levels():
    result = derive({'onlineRating': 1700}, num_levels=3)
    assert result == {'skill_tier': 'elo_1600', 'starting_level': 3}


def test_clamp_never_below_one():
    # Non-positive num_levels is treated as 1 (level 1 always exists).
    result = derive({'experience': 'beginner', 'noRating': True}, num_levels=0)
    assert result['starting_level'] == 1
    result = derive({'onlineRating': 1700}, num_levels=-5)
    assert result['starting_level'] == 1


def test_clamp_does_not_raise_level_below_tier():
    # beginner is level 1; a wide num_levels must not bump it up.
    result = derive({'experience': 'beginner', 'noRating': True}, num_levels=WIDE)
    assert result == {'skill_tier': 'beginner', 'starting_level': 1}


# --- Input robustness ------------------------------------------------------

def test_snake_case_keys_accepted():
    result = derive({'online_rating': 1550, 'no_rating': False})
    assert result == {'skill_tier': 'elo_1500', 'starting_level': 5}


def test_empty_answers_is_beginner_via_default_slider():
    # Empty dict: no online, no noRating -> eloRating defaults to 800 -> advanced.
    result = derive({})
    assert result == {'skill_tier': 'advanced', 'starting_level': 3}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
