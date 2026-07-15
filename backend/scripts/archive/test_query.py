import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import supabase client
from services.supabase_client import supabase

if supabase:
    print("✅ Supabase client connected")
    
    # Try to query lessons table
    try:
        result = supabase.table('lessons').select('*').limit(1).execute()
        print(f"\n✅ Query successful!")
        if result.data:
            lesson = result.data[0]
            print(f"\nLesson columns:")
            for key in lesson.keys():
                print(f"  - {key}: {type(lesson[key]).__name__}")
        else:
            print("\nNo lessons found in database")
    except Exception as e:
        print(f"\n❌ Query failed: {e}")
        import traceback
        traceback.print_exc()
else:
    print("❌ Supabase client not initialized")
