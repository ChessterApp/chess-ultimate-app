#!/usr/bin/env python3
"""Fix the King Move Right exercise in Supabase"""

import os
import sys
from services.supabase_client import supabase

def main():
    print("=== Fixing 'The King - Move Right' Exercise ===\n")

    # Find the lesson by slug
    print("1. Finding lesson 'the-king-move-right'...")
    result = supabase.table('lessons').select('*').eq('slug', 'the-king-move-right').execute()

    if not result.data or len(result.data) == 0:
        print("❌ Lesson 'the-king-move-right' not found!")
        return 1

    lesson = result.data[0]
    print(f"   Found lesson: {lesson['title']}")
    print(f"   Current FEN: {lesson.get('exercise_fen', 'N/A')}")
    print(f"   Current solution: {lesson.get('solution_move', 'N/A')}\n")

    # Update the lesson
    print("2. Updating lesson data...")
    update_result = supabase.table('lessons').update({
        'exercise_fen': '7k/8/8/8/8/4K3/8/8 w - - 0 1',  # Remove pawn, King on e3
        'solution_move': 'e3h3',  # King moves from e3 to h3
        'arrow_from_square': 'e3',  # Arrow starts at e3
        'arrow_path': ['f3', 'g3'],  # Intermediate squares for path
        'exercise_solution': {
            'arrow': {
                'from': 'e3',
                'path': ['f3', 'g3']
            }
        }
    }).eq('slug', 'the-king-move-right').execute()

    if update_result.data:
        print("✅ Update successful!\n")

        # Verify the update
        print("3. Verifying changes...")
        verify_result = supabase.table('lessons').select('*').eq('slug', 'the-king-move-right').execute()

        if verify_result.data:
            updated_lesson = verify_result.data[0]
            print(f"   Title: {updated_lesson['title']}")
            print(f"   FEN: {updated_lesson['exercise_fen']}")
            print(f"   Solution: {updated_lesson['solution_move']}")
            print(f"   Arrow From: {updated_lesson['arrow_from_square']}")
            print(f"   Arrow Path: {updated_lesson['arrow_path']}")
            print(f"   Exercise Solution: {updated_lesson['exercise_solution']}")
            print("\n✅ All changes applied successfully!")
            return 0
        else:
            print("❌ Could not verify changes")
            return 1
    else:
        print("❌ Update failed!")
        return 1

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
