#!/usr/bin/env python3
"""List all courses and their lessons"""

import os
from dotenv import load_dotenv

load_dotenv()

# Setup environment variables
os.environ['SUPABASE_URL'] = 'https://qtzujwiqzbgyhdgulvcd.supabase.co'
if not os.getenv('SUPABASE_SERVICE_KEY'):
    os.environ['SUPABASE_SERVICE_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF0enVqd2lxemJneWhkZ3VsdmNkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjcwOTY0MiwiZXhwIjoyMDc4Mjg1NjQyfQ.lWV9WrshHnv24UlVRXscNhphKKm9Xgqmfal5y4E5lVE'

from services.supabase_client import supabase

def main():
    print("=== All Courses ===\n")

    # Get all courses
    courses = supabase.table('courses').select('*').execute()

    if courses.data:
        for course in courses.data:
            print(f"\nCourse: {course.get('title')}")
            print(f"ID: {course.get('id')}")
            print(f"Slug: {course.get('slug', 'N/A')}")

            # Get lessons for this course
            lessons = supabase.table('lessons').select('id, title, numbering').eq('course_id', course['id']).order('numbering').execute()

            if lessons.data:
                print(f"Lessons ({len(lessons.data)}):")
                for lesson in lessons.data:
                    print(f"  {lesson.get('numbering', '?')}. {lesson.get('title')}")
            else:
                print("  No lessons")

    # Also check for orphaned lessons (no course_id)
    print("\n\n=== Orphaned Lessons (no course_id) ===\n")
    orphaned = supabase.table('lessons').select('*').is_('course_id', 'null').execute()

    if orphaned.data:
        for lesson in orphaned.data:
            print(f"ID: {lesson.get('id')}")
            print(f"Title: {lesson.get('title')}")
            print(f"Numbering: {lesson.get('numbering', 'N/A')}")
            print("-" * 40)
    else:
        print("No orphaned lessons")

if __name__ == '__main__':
    main()
