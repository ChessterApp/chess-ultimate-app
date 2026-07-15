"""
Seed Script for Rook Checkmates Course
Creates a new course, module, and lesson for importing Lichess study puzzles

Run with: python seed_rook_checkmates.py
"""

import os
from datetime import datetime
from services.supabase_client import supabase

def seed_rook_checkmates():
    """Seed the database with Rook Checkmates course, module, and lesson"""

    print("Starting Rook Checkmates course seeding...")

    # Check if course already exists
    existing = supabase.table('courses').select('id').eq('title', 'Checkmate Patterns').execute()
    if existing.data:
        print("Course 'Checkmate Patterns' already exists. Skipping course creation.")
        course_id = existing.data[0]['id']
    else:
        # Create Course: Checkmate Patterns
        print("\n Creating Course: Checkmate Patterns...")
        course_result = supabase.table('courses').insert({
            'title': 'Checkmate Patterns',
            'description': 'Master essential checkmate patterns with interactive puzzles. Learn to deliver checkmate with different pieces.',
            'level': 'beginner',
            'order_index': 3,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }).execute()

        course_id = course_result.data[0]['id']
        print(f"Course created with ID: {course_id}")

    # Check if module already exists
    existing_module = supabase.table('modules').select('id').eq('title', 'Rook Checkmates').eq('course_id', course_id).execute()
    if existing_module.data:
        print("Module 'Rook Checkmates' already exists. Skipping module creation.")
        module_id = existing_module.data[0]['id']
    else:
        # Create Module: Rook Checkmates
        print("\n Creating Module: Rook Checkmates...")
        module_result = supabase.table('modules').insert({
            'course_id': course_id,
            'title': 'Rook Checkmates',
            'description': 'Learn to deliver checkmate using the rook',
            'order_index': 1,
            'created_at': datetime.utcnow().isoformat()
        }).execute()

        module_id = module_result.data[0]['id']
        print(f"Module created with ID: {module_id}")

    # Check if lesson already exists (check by title since slug column may not exist)
    existing_lesson = supabase.table('lessons').select('id').eq('title', 'Rook Checkmates').eq('module_id', module_id).execute()
    if existing_lesson.data:
        print("Lesson 'Rook Checkmates' already exists.")
        lesson_id = existing_lesson.data[0]['id']
        print(f"Existing lesson ID: {lesson_id}")
        print("\nTo import puzzles, run:")
        print(f"  python scripts/import_lichess_study.py VTUxy8HW --lesson-id={lesson_id}")
        return lesson_id

    # Create Lesson: Rook Checkmates
    print("\n Creating Lesson: Rook Checkmates...")
    lesson_result = supabase.table('lessons').insert({
        'module_id': module_id,
        'title': 'Rook Checkmates',
        'content': '''# Rook Checkmates

The rook is a powerful piece for delivering checkmate. In these puzzles, you'll practice using the rook to deliver the final blow.

## How to Play
- Look at the position carefully
- Find the square where the rook delivers checkmate
- Click on the rook, then click on the target square
- If correct, you'll advance to the next puzzle

## Tips
- The rook attacks along ranks (rows) and files (columns)
- Look for enemy kings trapped on the edge of the board
- Back rank mates are common rook checkmate patterns

Good luck!
''',
        'lesson_type': 'exercise',
        'order_index': 1,
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
    print(f"Module: Rook Checkmates (ID: {module_id})")
    print(f"Lesson: Rook Checkmates (ID: {lesson_id})")
    print(f"\nURL: /learn/checkmate-patterns/rook-checkmates")
    print("\nNext step - Import puzzles from Lichess study:")
    print(f"  python scripts/import_lichess_study.py VTUxy8HW --lesson-id={lesson_id}")

    return lesson_id

if __name__ == '__main__':
    try:
        seed_rook_checkmates()
    except Exception as e:
        print(f"\n Error during seeding: {str(e)}")
        print("\nMake sure:")
        print("1. Supabase credentials are set in .env")
        print("2. Database tables are created")
        print("3. You're running from the backend directory")
        exit(1)
