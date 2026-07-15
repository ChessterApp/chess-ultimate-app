#!/usr/bin/env python3
"""Remove black King from 'The King - Move Up' exercise"""

import os
from dotenv import load_dotenv

load_dotenv()

# Setup environment variables
os.environ['SUPABASE_URL'] = 'https://qtzujwiqzbgyhdgulvcd.supabase.co'
if not os.getenv('SUPABASE_SERVICE_KEY'):
    os.environ['SUPABASE_SERVICE_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF0enVqd2lxemJneWhkZ3VsdmNkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjcwOTY0MiwiZXhwIjoyMDc4Mjg1NjQyfQ.lWV9WrshHnv24UlVRXscNhphKKm9Xgqmfal5y4E5lVE'

from services.supabase_client import supabase
import json

def main():
    lesson_id = '081c469e-6324-464a-bc66-f4d35b349d11'

    print("=== Removing Black King from Exercise ===\n")

    # Update FEN - completely empty board except white King on e4
    # Old FEN: 7k/8/8/8/4K3/8/8/8 w - - 0 1 (had black king on h8)
    # New FEN: 8/8/8/8/4K3/8/8/8 w - - 0 1 (no black king)

    update_data = {
        'exercise_fen': '8/8/8/8/4K3/8/8/8 w - - 0 1'
    }

    result = supabase.table('lessons').update(update_data).eq('id', lesson_id).execute()

    if result.data:
        lesson = result.data[0]
        print(f"✅ Successfully updated FEN")
        print(f"\nLesson: {lesson.get('title')}")
        print(f"New FEN: {lesson.get('exercise_fen')}")
        print(f"Solution: {json.dumps(lesson.get('exercise_solution'), indent=2)}")
        return 0
    else:
        print("❌ Failed to update lesson")
        return 1

if __name__ == '__main__':
    import sys
    sys.exit(main())
