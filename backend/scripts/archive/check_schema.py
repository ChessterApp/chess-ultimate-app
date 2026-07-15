#!/usr/bin/env python3
"""Check the actual schema of lessons table"""

import os
from dotenv import load_dotenv

load_dotenv()

# Setup environment variables
os.environ['SUPABASE_URL'] = 'https://qtzujwiqzbgyhdgulvcd.supabase.co'
if not os.getenv('SUPABASE_SERVICE_KEY'):
    os.environ['SUPABASE_SERVICE_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF0enVqd2lxemJneWhkZ3VsdmNkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjcwOTY0MiwiZXhwIjoyMDc4Mjg1NjQyfQ.lWV9WrshHnv24UlVRXscNhphKKm9Xgqmfal5y4E5lVE'

from services.supabase_client import supabase

def main():
    print("=== Checking Lessons Schema ===\n")

    # Get one lesson to see all columns
    result = supabase.table('lessons').select('*').limit(1).execute()

    if result.data:
        lesson = result.data[0]
        print("Available columns in 'lessons' table:")
        for key in sorted(lesson.keys()):
            print(f"  - {key}")

        print("\n=== Checking Courses Schema ===\n")
        courses_result = supabase.table('courses').select('*').limit(1).execute()
        if courses_result.data:
            course = courses_result.data[0]
            print("Available columns in 'courses' table:")
            for key in sorted(course.keys()):
                print(f"  - {key}")
    else:
        print("No lessons found")

if __name__ == '__main__':
    main()
