#!/usr/bin/env python3
"""Update 'The King - Move Up' to be a 5-star collection exercise"""

from services.supabase_client import supabase
import json

def main():
    print("=== Updating 'The King - Move Up' to 5-Star Exercise ===\n")

    # Find the lesson by slug
    print("1. Finding lesson 'the-king-move-up'...")
    result = supabase.table('lessons').select('*').eq('slug', 'the-king-move-up').execute()

    if not result.data or len(result.data) == 0:
        print("❌ Lesson 'the-king-move-up' not found!")
        return 1

    lesson = result.data[0]
    lesson_id = lesson['id']
    print(f"   Found lesson: {lesson['title']}")
    print(f"   ID: {lesson_id}")
    print(f"   Current FEN: {lesson.get('exercise_fen', 'N/A')}")
    print(f"   Current solution: {json.dumps(lesson.get('exercise_solution', {}), indent=2)}\n")

    # King on e4, place 5 stars at random locations (at least 2 squares away)
    # Star locations: a7, h7, a1, h1, e8
    # Distances from e4:
    # - a7: max(|0-4|, |6-3|) = 4 ✓
    # - h7: max(|7-4|, |6-3|) = 3 ✓
    # - a1: max(|0-4|, |0-3|) = 4 ✓
    # - h1: max(|7-4|, |0-3|) = 3 ✓
    # - e8: max(|4-4|, |7-3|) = 4 ✓
    update_data = {
        'exercise_fen': '7k/8/8/8/4K3/8/8/8 w - - 0 1',  # King on e4
        'exercise_solution': {
            'targets': ['a7', 'h7', 'a1', 'h1', 'e8'],  # 5 target squares
            'requireAll': True  # Must capture all to complete
        }
    }

    print(f"2. Updating lesson {lesson_id}...")
    print(f"   New FEN: {update_data['exercise_fen']}")
    print(f"   Target squares: {update_data['exercise_solution']['targets']}")
    print(f"   Require all: {update_data['exercise_solution']['requireAll']}\n")

    update_result = supabase.table('lessons').update(update_data).eq('id', lesson_id).execute()

    if update_result.data:
        print("✅ Update successful!\n")

        # Verify the update
        print("3. Verifying changes...")
        verify_result = supabase.table('lessons').select('*').eq('id', lesson_id).execute()

        if verify_result.data:
            updated_lesson = verify_result.data[0]
            print(f"   Title: {updated_lesson['title']}")
            print(f"   FEN: {updated_lesson['exercise_fen']}")
            print(f"   Solution: {json.dumps(updated_lesson['exercise_solution'], indent=2)}")
            print("\n✅ All changes applied successfully!")
            return 0
        else:
            print("❌ Could not verify changes")
            return 1
    else:
        print("❌ Update failed!")
        return 1

if __name__ == '__main__':
    import sys
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
