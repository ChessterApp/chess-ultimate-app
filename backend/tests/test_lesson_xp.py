"""lesson_xp table — and the frontend copy of it never drifts from the backend."""

import json
from pathlib import Path

from api.lesson_xp import LESSON_XP, lesson_xp

FRONTEND_TABLE = Path(__file__).resolve().parents[2] / 'frontend/src/lib/gamification/lessonXp.json'


def test_table_values():
    assert [(lvl, row['theory'], row['exercise']) for lvl, row in LESSON_XP.items()] == [
        ('beginner', 10, 15),
        ('intermediate', 15, 20),
        ('advanced', 20, 25),
        ('master', 25, 30),
        ('expert', 30, 35),
        ('legendary', 35, 40),
        ('grandmaster', 40, 50),
    ]


def test_lookup_and_fallbacks():
    assert lesson_xp('exercise', 'grandmaster') == 50
    assert lesson_xp('theory', 'advanced') == 20
    assert lesson_xp('exercise', 'nonsense') == 15  # unknown level → beginner
    assert lesson_xp('exercise', None) == 15
    assert lesson_xp('quiz', 'master') == 25  # unknown type → theory
    assert lesson_xp(None, None) == 10


def test_frontend_table_matches():
    assert json.loads(FRONTEND_TABLE.read_text()) == LESSON_XP
