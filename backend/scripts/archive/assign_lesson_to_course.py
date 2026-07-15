#!/usr/bin/env python3
"""Assign 'The King - Move Up' lesson to Chess Fundamentals course"""

import os
from dotenv import load_dotenv

load_dotenv()

# Setup environment variables
os.environ['SUPABASE_URL'] = 'https://qtzujwiqzbgyhdgulvcd.supabase.co'
if not os.getenv('SUPABASE_SERVICE_KEY'):
    os.environ['SUPABASE_SERVICE_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF0enVqd2lxemJneWhkZ3VsdmNkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjcwOTY0MiwiZXhwIjoyMDc4Mjg1NjQyfQ.lWV9WrshHnv24UlVRXscNhphKKm9Xgqmfal5y4E5lVE'

from services.supabase_client import supabase

def main():
    lesson_id = '081c469e-6324-464a-bc66-f4d35b349d11'
    course_id = '11111111-1111-1111-1111-111111111111'  # Chess Fundamentals

    print("=== Assigning Lesson to Course ===\n")

    # Update the lesson with course_id
    result = supabase.table('lessons').update({
        'course_id': course_id
    }).eq('id', lesson_id).execute()

    if result.data:
        print(f"✅ Successfully assigned lesson to Chess Fundamentals course")
        lesson = result.data[0]
        print(f"\nLesson: {lesson.get('title')}")
        print(f"Course ID: {lesson.get('course_id')}")
    else:
        print("❌ Failed to assign lesson")
        return 1

    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
