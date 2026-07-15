"""
Seed Script for Knight Checkmates Lesson
Creates a new module and lesson under the existing Checkmate Patterns course

Run with: python seed_knight_checkmates.py
"""

import os
from datetime import datetime
from services.supabase_client import supabase

def seed_knight_checkmates():
    """Seed the database with Knight Checkmates module and lesson"""

    print("Starting Knight Checkmates lesson seeding...")

    # Get existing course (Checkmate Patterns)
    existing = supabase.table('courses').select('id').eq('title', 'Checkmate Patterns').execute()
    if not existing.data:
        print("Error: Course 'Checkmate Patterns' not found. Please run seed_rook_checkmates.py first.")
        return None

    course_id = existing.data[0]['id']
    print(f"Using existing course 'Checkmate Patterns' (ID: {course_id})")

    # Check if module already exists
    existing_module = supabase.table('modules').select('id').eq('title', 'Knight Checkmates').eq('course_id', course_id).execute()
    if existing_module.data:
        print("Module 'Knight Checkmates' already exists. Skipping module creation.")
        module_id = existing_module.data[0]['id']
    else:
        # Create Module: Knight Checkmates
        print("\n Creating Module: Knight Checkmates...")
        module_result = supabase.table('modules').insert({
            'course_id': course_id,
            'title': 'Knight Checkmates',
            'description': 'Learn to deliver checkmate using the knight',
            'order_index': 3,
            'created_at': datetime.utcnow().isoformat()
        }).execute()

        module_id = module_result.data[0]['id']
        print(f"Module created with ID: {module_id}")

    # Check if lesson already exists (check by title since slug column may not exist)
    existing_lesson = supabase.table('lessons').select('id').eq('title', 'Knight Checkmates').eq('module_id', module_id).execute()
    if existing_lesson.data:
        print("Lesson 'Knight Checkmates' already exists.")
        lesson_id = existing_lesson.data[0]['id']
        print(f"Existing lesson ID: {lesson_id}")
        print("\nTo import puzzles, run:")
        print(f"  python scripts/import_lichess_study.py n0HKuSqc --lesson-id={lesson_id}")
        return lesson_id

    # Create Lesson: Knight Checkmates
    print("\n Creating Lesson: Knight Checkmates...")
    lesson_result = supabase.table('lessons').insert({
        'module_id': module_id,
        'title': 'Knight Checkmates',
        'content': '''# Knight Checkmates

The knight is a tricky piece that can deliver surprising checkmates! Its unique L-shaped movement makes it impossible to block, and it can jump over other pieces.

## How to Play
- Look at the position carefully
- Find the square where the knight delivers checkmate
- Click on the knight, then click on the target square
- If correct, you'll advance to the next puzzle

## Tips
- The knight moves in an "L" shape: two squares in one direction, then one square perpendicular
- Knight checks cannot be blocked - the king must move or the knight must be captured
- Knights are especially dangerous near the enemy king
- Look for smothered mates where the king is trapped by its own pieces

Good luck!
''',
        'lesson_type': 'exercise',
        'order_index': 3,
        'has_multiple_puzzles': True,
        'puzzle_count': 12,
        'requires_lesson_id': None,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }).execute()

    lesson_id = lesson_result.data[0]['id']
    print(f"Lesson created with ID: {lesson_id}")

    print("\n" + "=" * 50)
    print("Seeding completed!")
    print("=" * 50)
    print(f"\nCourse: Checkmate Patterns (ID: {course_id})")
    print(f"Module: Knight Checkmates (ID: {module_id})")
    print(f"Lesson: Knight Checkmates (ID: {lesson_id})")
    print(f"\nURL: /learn/checkmate-patterns/knight-checkmates")
    print("\nNext step - Import puzzles from Lichess study:")
    print(f"  python scripts/import_lichess_study.py n0HKuSqc --lesson-id={lesson_id}")

    return lesson_id

if __name__ == '__main__':
    try:
        seed_knight_checkmates()
    except Exception as e:
        print(f"\n Error during seeding: {str(e)}")
        print("\nMake sure:")
        print("1. Supabase credentials are set in .env")
        print("2. Database tables are created")
        print("3. You're running from the backend directory")
        exit(1)
