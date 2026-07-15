#!/usr/bin/env python3
"""
Setup Supabase Database Schema for Chess Ultimate App - Phase 1
Run this script to create all tables, indexes, and seed data.

Usage:
    python setup_database.py

Make sure you have set environment variables:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
"""

import os
import sys
from supabase import create_client, Client

# Supabase credentials
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://qtzujwiqzbgyhdgulvcd.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF0enVqd2lxemJneWhkZ3VsdmNkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjcwOTY0MiwiZXhwIjoyMDc4Mjg1NjQyfQ.lWV9WrshHnv24UlVRXscNhphKKm9Xgqmfal5y4E5lVE")

# Read SQL schema
SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "schema.sql")

def main():
    print("=" * 60)
    print("Chess Ultimate App - Database Setup")
    print("=" * 60)
    print(f"\nSupabase URL: {SUPABASE_URL}")
    print(f"Schema file: {SCHEMA_FILE}\n")

    if not os.path.exists(SCHEMA_FILE):
        print(f"❌ Error: Schema file not found at {SCHEMA_FILE}")
        sys.exit(1)

    # Create Supabase client
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Connected to Supabase")
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        sys.exit(1)

    # Read schema SQL
    with open(SCHEMA_FILE, 'r') as f:
        sql_content = f.read()

    print(f"\n📄 Loaded schema ({len(sql_content)} characters)")
    print("\n" + "=" * 60)
    print("MANUAL SETUP REQUIRED")
    print("=" * 60)
    print("""
Unfortunately, the Supabase Python client doesn't support executing
raw SQL directly. You need to run the schema manually.

OPTION 1: Supabase Dashboard (Recommended)
1. Go to: https://supabase.com/dashboard/project/qtzujwiqzbgyhdgulvcd
2. Click "SQL Editor" in the left sidebar
3. Click "New Query"
4. Copy the contents of: backend/schema.sql
5. Paste into the SQL editor
6. Click "Run" button

OPTION 2: Use psql command line
Run this command:
    psql "postgresql://postgres:[YOUR_DB_PASSWORD]@db.qtzujwiqzbgyhdgulvcd.supabase.co:5432/postgres" < backend/schema.sql

Your database password is in: Project Settings → Database → Password
""")

    print("\n" + "=" * 60)
    print("After running the schema, verify with:")
    print("=" * 60)
    print("""
    python -c "from supabase import create_client; \
        c = create_client('{}', '{}'); \
        print('Tables:', c.table('courses').select('*').execute())"
    """.format(SUPABASE_URL, SUPABASE_KEY))

if __name__ == "__main__":
    main()
