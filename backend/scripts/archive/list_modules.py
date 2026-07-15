#!/usr/bin/env python3
"""List all modules and their parent courses"""

import os
from dotenv import load_dotenv

load_dotenv()

# Setup environment variables
os.environ['SUPABASE_URL'] = 'https://qtzujwiqzbgyhdgulvcd.supabase.co'
if not os.getenv('SUPABASE_SERVICE_KEY'):
    os.environ['SUPABASE_SERVICE_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF0enVqd2lxemJneWhkZ3VsdmNkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjcwOTY0MiwiZXhwIjoyMDc4Mjg1NjQyfQ.lWV9WrshHnv24UlVRXscNhphKKm9Xgqmfal5y4E5lVE'

from services.supabase_client import supabase

def main():
    print("=== All Modules ===\n")

    # Get all modules
    modules_result = supabase.table('modules').select('*').execute()

    if modules_result.data:
        for module in modules_result.data:
            print(f"\nModule: {module.get('title')}")
            print(f"ID: {module.get('id')}")
            print(f"Course ID: {module.get('course_id')}")

            # Get course info
            if module.get('course_id'):
                course = supabase.table('courses').select('title').eq('id', module['course_id']).execute()
                if course.data:
                    print(f"Course: {course.data[0]['title']}")

            # Get lessons count for this module
            lessons = supabase.table('lessons').select('id').eq('module_id', module['id']).execute()
            print(f"Lessons: {len(lessons.data) if lessons.data else 0}")
    else:
        print("No modules found")

    # Check the King lesson's current module assignment
    print("\n\n=== The King - Move Up Lesson ===\n")
    lesson = supabase.table('lessons').select('*').eq('id', '081c469e-6324-464a-bc66-f4d35b349d11').execute()
    if lesson.data:
        l = lesson.data[0]
        print(f"Title: {l.get('title')}")
        print(f"Module ID: {l.get('module_id')}")

        if l.get('module_id'):
            module = supabase.table('modules').select('title, course_id').eq('id', l['module_id']).execute()
            if module.data:
                print(f"Module: {module.data[0]['title']}")
                print(f"Course ID: {module.data[0].get('course_id')}")

if __name__ == '__main__':
    main()
