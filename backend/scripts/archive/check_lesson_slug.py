#!/usr/bin/env python3
"""Check the lesson slug for 'The King - Move Up'"""

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
    print("=== Checking Lesson Slug ===\n")

    # Find lesson by ID
    result = supabase.table('lessons').select('*').eq('id', '081c469e-6324-464a-bc66-f4d35b349d11').execute()

    if result.data:
        lesson = result.data[0]
        print(f"Title: {lesson.get('title')}")
        print(f"Slug: {lesson.get('slug', 'NO SLUG COLUMN')}")
        print(f"Course ID: {lesson.get('course_id')}")
        print(f"FEN: {lesson.get('exercise_fen')}")
        print(f"Solution: {json.dumps(lesson.get('exercise_solution'), indent=2)}")

        # Also get the course slug
        if lesson.get('course_id'):
            course_result = supabase.table('courses').select('*').eq('id', lesson['course_id']).execute()
            if course_result.data:
                course = course_result.data[0]
                print(f"\nCourse Title: {course.get('title')}")
                print(f"Course Slug: {course.get('slug', 'NO SLUG COLUMN')}")
    else:
        print("Lesson not found!")

if __name__ == '__main__':
    main()
