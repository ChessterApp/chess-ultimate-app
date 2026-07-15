#!/usr/bin/env python3
"""Fix the King Move Right exercise"""

import sqlite3
import json

# Connect to database
db_path = 'database.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Update the lesson
cursor.execute("""
    UPDATE lessons
    SET
      exercise_fen = '7k/8/8/8/8/4K3/8/8 w - - 0 1',
      solution_move = 'e3h3',
      arrow_from_square = 'e3',
      arrow_path = '["f3", "g3"]',
      exercise_solution = json_set(
        COALESCE(exercise_solution, '{}'),
        '$.arrow',
        json('{"from": "e3", "path": ["f3", "g3"]}')
      )
    WHERE slug = 'the-king-move-right'
""")

conn.commit()

# Verify the update
cursor.execute("""
    SELECT title, exercise_fen, solution_move, arrow_from_square, arrow_path
    FROM lessons
    WHERE slug = 'the-king-move-right'
""")

result = cursor.fetchone()
if result:
    print("✅ Migration applied successfully!")
    print("\nUpdated lesson:")
    print(f"Title: {result[0]}")
    print(f"FEN: {result[1]}")
    print(f"Solution: {result[2]}")
    print(f"Arrow From: {result[3]}")
    print(f"Arrow Path: {result[4]}")
else:
    print("❌ Lesson not found!")

cursor.close()
conn.close()
