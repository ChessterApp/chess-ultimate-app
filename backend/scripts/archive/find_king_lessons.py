#!/usr/bin/env python3
"""Find all King-related lessons in Supabase"""

from services.supabase_client import supabase
import json

def main():
    print("=== Finding King Lessons ===\n")

    # Get all lessons (only query fields that exist in schema)
    result = supabase.table('lessons').select('id, title, exercise_fen, exercise_solution').execute()

    if not result.data:
        print("❌ No lessons found in database!")
        return 1

    print(f"Found {len(result.data)} total lessons\n")

    # Filter for King lessons
    king_lessons = [l for l in result.data if 'king' in l.get('title', '').lower()]

    if not king_lessons:
        print("❌ No King lessons found!")
        return 1

    print(f"Found {len(king_lessons)} King lessons:\n")
    for lesson in king_lessons:
        print(f"Title: {lesson.get('title')}")
        print(f"ID: {lesson.get('id')}")
        print(f"FEN: {lesson.get('exercise_fen', 'N/A')}")

        # Extract arrow data from exercise_solution if it exists
        solution = lesson.get('exercise_solution', {})
        if solution and isinstance(solution, dict):
            arrow = solution.get('arrow', {})
            print(f"Arrow From: {arrow.get('from', 'N/A')}")
            print(f"Arrow Path: {arrow.get('path', 'N/A')}")
        else:
            print(f"Arrow From: N/A")
            print(f"Arrow Path: N/A")

        print(f"Exercise Solution (full): {json.dumps(solution, indent=2)}")
        print("-" * 80)

    return 0

if __name__ == '__main__':
    import sys
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
