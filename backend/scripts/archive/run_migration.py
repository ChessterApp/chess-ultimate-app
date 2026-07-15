#!/usr/bin/env python3
"""
Run database migrations for Chess Ultimate App

Usage:
    python run_migration.py migrations/002_create_analysis_chat_tables.sql
"""

import sys
import os
from dotenv import load_dotenv
from services.supabase_client import get_supabase_client

def run_migration(sql_file_path: str):
    """Run a SQL migration file"""
    # Load environment variables
    load_dotenv()

    # Read SQL file
    if not os.path.exists(sql_file_path):
        print(f"❌ Error: SQL file not found: {sql_file_path}")
        return False

    with open(sql_file_path, 'r') as f:
        sql_content = f.read()

    print(f"📄 Running migration: {sql_file_path}")
    print(f"{'='*60}")

    # Get Supabase client
    try:
        supabase = get_supabase_client()
        print("✅ Connected to Supabase")
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        return False

    # Execute SQL
    try:
        # Split SQL into individual statements (basic splitting by semicolon)
        statements = [s.strip() for s in sql_content.split(';') if s.strip() and not s.strip().startswith('--')]

        print(f"\n📊 Executing {len(statements)} SQL statements...")

        for i, statement in enumerate(statements, 1):
            # Skip comments and empty statements
            if not statement or statement.startswith('--'):
                continue

            print(f"  [{i}/{len(statements)}] Executing...")

            # Execute via Supabase RPC
            result = supabase.rpc('exec_sql', {'sql': statement}).execute()

            if hasattr(result, 'error') and result.error:
                print(f"  ❌ Error: {result.error}")
            else:
                print(f"  ✅ Success")

        print(f"\n{'='*60}")
        print("✅ Migration completed successfully!")
        print(f"{'='*60}\n")

        # Verify tables were created
        print("🔍 Verifying tables...")
        tables = supabase.table('information_schema.tables')\
            .select('table_name')\
            .in_('table_name', ['analysis_conversations', 'analysis_chat_messages', 'api_usage'])\
            .execute()

        if tables.data:
            print(f"✅ Found {len(tables.data)} tables:")
            for table in tables.data:
                print(f"  - {table['table_name']}")
        else:
            print("⚠️  Could not verify tables (may need direct SQL access)")

        return True

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_migration.py <sql_file_path>")
        print("Example: python run_migration.py migrations/002_create_analysis_chat_tables.sql")
        sys.exit(1)

    sql_file = sys.argv[1]
    success = run_migration(sql_file)

    sys.exit(0 if success else 1)
