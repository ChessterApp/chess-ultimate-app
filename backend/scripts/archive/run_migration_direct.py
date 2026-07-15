#!/usr/bin/env python3
"""
Run database migrations directly using psycopg2.
This bypasses Supabase RPC which doesn't support DDL statements.

Usage:
    python run_migration_direct.py migrations/005_add_lesson_puzzles.sql
"""

import sys
import os
import re

def run_migration(sql_file_path: str):
    """Run a SQL migration file using psycopg2."""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Run: pip install psycopg2-binary")
        return False

    # Load .env file
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

    # Get database URL from environment
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        # Construct from Supabase URL
        supabase_url = os.environ.get('SUPABASE_URL', '')
        supabase_key = os.environ.get('SUPABASE_KEY', '')

        # Extract project reference from URL
        # https://qtzujwiqzbgyhdgulvcd.supabase.co -> qtzujwiqzbgyhdgulvcd
        match = re.search(r'https://([^.]+)\.supabase\.co', supabase_url)
        if match:
            project_ref = match.group(1)
            # Default Supabase password is the service role key
            db_url = f"postgresql://postgres.{project_ref}:{supabase_key}@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
        else:
            print("❌ Could not construct DATABASE_URL. Please set DATABASE_URL in .env")
            return False

    # Read SQL file
    if not os.path.exists(sql_file_path):
        print(f"❌ Error: SQL file not found: {sql_file_path}")
        return False

    with open(sql_file_path, 'r') as f:
        sql_content = f.read()

    print(f"📄 Running migration: {sql_file_path}")
    print(f"{'='*60}")

    try:
        # Connect to database
        print("🔌 Connecting to database...")
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
        print("✅ Connected to database")

        # Execute the entire SQL file
        print(f"\n📊 Executing migration...")
        cur.execute(sql_content)
        print("✅ Migration executed successfully")

        # Verify tables
        print("\n🔍 Verifying tables created...")
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('lesson_puzzles', 'user_puzzle_progress')
        """)
        tables = cur.fetchall()
        if tables:
            print(f"✅ Found {len(tables)} new tables:")
            for table in tables:
                print(f"   - {table[0]}")
        else:
            print("⚠️  Could not find new tables (they may already exist)")

        # Verify columns added to lessons
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'lessons'
            AND column_name IN ('has_multiple_puzzles', 'puzzle_count')
        """)
        columns = cur.fetchall()
        if columns:
            print(f"✅ Added columns to lessons table:")
            for col in columns:
                print(f"   - {col[0]}")

        cur.close()
        conn.close()

        print(f"\n{'='*60}")
        print("✅ Migration completed successfully!")
        print(f"{'='*60}\n")
        return True

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_migration_direct.py <sql_file_path>")
        print("Example: python run_migration_direct.py migrations/005_add_lesson_puzzles.sql")
        sys.exit(1)

    sql_file = sys.argv[1]
    success = run_migration(sql_file)
    sys.exit(0 if success else 1)
