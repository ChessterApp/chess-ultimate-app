"""
XP a completed lesson is worth: by lesson type, growing with the course level.

The frontend holds the same table in `frontend/src/lib/gamification/lessonXp.json`;
`tests/test_lesson_xp.py` asserts the two never drift apart.
"""

LESSON_XP = {
    'beginner': {'theory': 10, 'exercise': 15},
    'intermediate': {'theory': 15, 'exercise': 20},
    'advanced': {'theory': 20, 'exercise': 25},
    'master': {'theory': 25, 'exercise': 30},
    'expert': {'theory': 30, 'exercise': 35},
    'legendary': {'theory': 35, 'exercise': 40},
    'grandmaster': {'theory': 40, 'exercise': 50},
}


def lesson_xp(lesson_type, course_level):
    """Unknown level → beginner; unknown type → theory."""
    row = LESSON_XP.get(course_level, LESSON_XP['beginner'])
    return row.get(lesson_type, row['theory'])
