#!/usr/bin/env python3
"""Update 'The King - Move Right' lesson to remove pawn and add arrow data"""

from services.supabase_client import supabase

def main():
    print("=== Updating 'The King - Move Right' Lesson ===\n")

    lesson_id = '7f878d78-43d3-4e60-b3e7-f26e6205f68a'

    # Update the lesson with correct FEN (no pawn) and arrow data
    update_data = {
        'exercise_fen': '7k/8/8/8/8/4K3/8/8 w - - 0 1',  # King on e3, no pawn
        'exercise_solution': {
            'arrow': {
                'from': 'e3',
                'path': ['f3', 'g3']  # King moves e3->f3->g3->h3
            }
        }
    }

    print(f"Updating lesson {lesson_id}...")
    print(f"New FEN: {update_data['exercise_fen']}")
    print(f"Arrow: from={update_data['exercise_solution']['arrow']['from']}, path={update_data['exercise_solution']['arrow']['path']}\n")

    result = supabase.table('lessons').update(update_data).eq('id', lesson_id).execute()

    if result.data:
        print("✅ Lesson updated successfully!")
        print(f"\nUpdated lesson:")
        print(f"  Title: {result.data[0].get('title')}")
        print(f"  FEN: {result.data[0].get('exercise_fen')}")
        print(f"  Arrow: {result.data[0].get('exercise_solution')}")
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
