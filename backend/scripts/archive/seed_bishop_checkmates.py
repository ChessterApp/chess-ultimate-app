"""
Seed Script for Bishop Checkmates Lesson
Creates a new module and lesson under the existing Checkmate Patterns course

Run with: python seed_bishop_checkmates.py
"""

import os
from datetime import datetime
from services.supabase_client import supabase

def seed_bishop_checkmates():
    """Seed the database with Bishop Checkmates module and lesson"""

    print("Starting Bishop Checkmates lesson seeding...")

    # Get existing course (Checkmate Patterns)
    existing = supabase.table('courses').select('id').eq('title', 'Checkmate Patterns').execute()
    if not existing.data:
        print("Error: Course 'Checkmate Patterns' not found. Please run seed_rook_checkmates.py first.")
        return None

    course_id = existing.data[0]['id']
    print(f"Using existing course 'Checkmate Patterns' (ID: {course_id})")

    # Check if module already exists
    existing_module = supabase.table('modules').select('id').eq('title', 'Bishop Checkmates').eq('course_id', course_id).execute()
    if existing_module.data:
        print("Module 'Bishop Checkmates' already exists. Skipping module creation.")
        module_id = existing_module.data[0]['id']
    else:
        # Create Module: Bishop Checkmates
        print("\n Creating Module: Bishop Checkmates...")
        module_result = supabase.table('modules').insert({
            'course_id': course_id,
            'title': 'Bishop Checkmates',
            'description': 'Learn to deliver checkmate using the bishop',
            'order_index': 2,
            'created_at': datetime.utcnow().isoformat()
        }).execute()

        module_id = module_result.data[0]['id']
        print(f"Module created with ID: {module_id}")

    # Check if lesson already exists (check by title since slug column may not exist)
    existing_lesson = supabase.table('lessons').select('id').eq('title', 'Bishop Checkmates').eq('module_id', module_id).execute()
    if existing_lesson.data:
        print("Lesson 'Bishop Checkmates' already exists.")
        lesson_id = existing_lesson.data[0]['id']
        print(f"Existing lesson ID: {lesson_id}")
        print("\nTo import puzzles, run:")
        print(f"  python scripts/import_lichess_study.py mVH6NjuQ --lesson-id={lesson_id}")
        return lesson_id

    # Create Lesson: Bishop Checkmates
    print("\n Creating Lesson: Bishop Checkmates...")
    lesson_result = supabase.table('lessons').insert({
        'module_id': module_id,
        'title': 'Bishop Checkmates',
        'content': '''# Bishop Checkmates

The bishop is a sneaky piece that can deliver devastating checkmates along diagonals. In these puzzles, you'll practice using the bishop to deliver the final blow.

## How to Play
- Look at the position carefully
- Find the square where the bishop delivers checkmate
- Click on the bishop, then click on the target square
- If correct, you'll advance to the next puzzle

## Tips
- The bishop attacks along diagonals only
- Bishops are especially deadly when working with other pieces
- Look for enemy kings trapped in corners or on the edge
- Two bishops can create powerful mating nets

Good luck!
''',
        'lesson_type': 'exercise',
        'order_index': 2,
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
    print(f"Module: Bishop Checkmates (ID: {module_id})")
    print(f"Lesson: Bishop Checkmates (ID: {lesson_id})")
    print(f"\nURL: /learn/checkmate-patterns/bishop-checkmates")
    print("\nNext step - Import puzzles from Lichess study:")
    print(f"  python scripts/import_lichess_study.py mVH6NjuQ --lesson-id={lesson_id}")

    return lesson_id

if __name__ == '__main__':
    try:
        seed_bishop_checkmates()
    except Exception as e:
        print(f"\n Error during seeding: {str(e)}")
        print("\nMake sure:")
        print("1. Supabase credentials are set in .env")
        print("2. Database tables are created")
        print("3. You're running from the backend directory")
        exit(1)
