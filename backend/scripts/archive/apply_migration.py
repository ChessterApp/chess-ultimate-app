#!/usr/bin/env python3
"""Apply migration 004_fix_king_move_right.sql"""

import os
from dotenv import load_dotenv

load_dotenv()

# Read DATABASE_URL
db_url = os.getenv('DATABASE_URL')

if not db_url:
    print("ERROR: DATABASE_URL not found in environment")
    exit(1)

# Read the migration file
migration_file = 'migrations/004_fix_king_move_right.sql'
with open(migration_file, 'r') as f:
    sql = f.read()

# Execute using psycopg library
try:
    import psycopg

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            # Fetch and print the SELECT results
            results = cur.fetchall()
            print("Migration applied successfully!")
            print("\nUpdated lesson:")
            for row in results:
                print(f"Title: {row[0]}")
                print(f"FEN: {row[1]}")
                print(f"Solution: {row[2]}")
                print(f"Arrow From: {row[3]}")
                print(f"Arrow Path: {row[4]}")
        conn.commit()

except ImportError:
    print("psycopg not available, trying psycopg2...")
    import psycopg2

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(sql)
    # Fetch and print the SELECT results
    results = cur.fetchall()
    print("Migration applied successfully!")
    print("\nUpdated lesson:")
    for row in results:
        print(f"Title: {row[0]}")
        print(f"FEN: {row[1]}")
        print(f"Solution: {row[2]}")
        print(f"Arrow From: {row[3]}")
        print(f"Arrow Path: {row[4]}")
    conn.commit()
    cur.close()
    conn.close()
