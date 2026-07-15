#!/usr/bin/env python3
"""Update 'The King - Move Right' to be a multi-star collection exercise"""

from services.supabase_client import supabase

def main():
    print("=== Updating to Multi-Star Exercise ===\n")

    lesson_id = '7f878d78-43d3-4e60-b3e7-f26e6205f68a'

    # King on e3, place 3 stars at: h3, b5, h6 (all at least 2 squares away)
    update_data = {
        'exercise_fen': '7k/8/8/8/8/4K3/8/8 w - - 0 1',  # King on e3
        'exercise_solution': {
            'targets': ['h3', 'b5', 'h6'],  # Multiple target squares
            'requireAll': True  # Must capture all to complete
        }
    }

    print(f"Updating lesson {lesson_id}...")
    print(f"FEN: {update_data['exercise_fen']}")
    print(f"Target squares: {update_data['exercise_solution']['targets']}")
    print(f"Require all: {update_data['exercise_solution']['requireAll']}\n")

    result = supabase.table('lessons').update(update_data).eq('id', lesson_id).execute()

    if result.data:
        print("✅ Lesson updated successfully!")
        print(f"\nUpdated lesson:")
        print(f"  Title: {result.data[0].get('title')}")
        print(f"  FEN: {result.data[0].get('exercise_fen')}")
        print(f"  Solution: {result.data[0].get('exercise_solution')}")
        return 0
    else:
        print("❌ Failed to update lesson")
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
