#!/usr/bin/env python3
"""
Import Level 4 (Mate in 3 Moves) from Lichess study into Chesster.

Study: https://lichess.org/study/qPlsu8dF
All 64 chapters are white-to-move mate-in-3 (or mate-in-2) puzzles.

This script:
1. Fetches all chapters from the Lichess study
2. Creates the Level 4 course, 1 module, and exercise lessons
3. Distributes puzzles across lessons (~10 per lesson)
4. Inserts puzzles into lesson_puzzles table
5. Correctly handles player_color based on FEN active color

Usage:
    python import_level4.py [--dry-run]
"""

import re
import sys
import time
import uuid
import requests

# Chesster Supabase
CHESSTER_URL = "https://qtzujwiqzbgyhdgulvcd.supabase.co/rest/v1"
CHESSTER_ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF0enVqd2lxemJneWhkZ3VsdmNkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI3MDk2NDIsImV4cCI6MjA3ODI4NTY0Mn0.KVSFN0hmhH6vOuk1kfzfzxekrmIwwzcJn895H3giHD4"
CHESSTER_SRK = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF0enVqd2lxemJneWhkZ3VsdmNkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjcwOTY0MiwiZXhwIjoyMDc4Mjg1NjQyfQ.lWV9WrshHnv24UlVRXscNhphKKm9Xgqmfal5y4E5lVE"

HEADERS = {
    "apikey": CHESSTER_ANON,
    "Authorization": f"Bearer {CHESSTER_SRK}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

STUDY_ID = "qPlsu8dF"
STUDY_URL = f"https://lichess.org/study/{STUDY_ID}"

# Lesson distribution: 7 lessons of ~9-10 puzzles each
LESSONS = [
    {"title": "Mate in 3 — Set 1", "title_ru": "Мат в 3 хода — Набор 1", "title_kk": "3 жүрісте мат — 1-жинақ", "start": 0, "end": 10},
    {"title": "Mate in 3 — Set 2", "title_ru": "Мат в 3 хода — Набор 2", "title_kk": "3 жүрісте мат — 2-жинақ", "start": 10, "end": 19},
    {"title": "Mate in 3 — Set 3", "title_ru": "Мат в 3 хода — Набор 3", "title_kk": "3 жүрісте мат — 3-жинақ", "start": 19, "end": 28},
    {"title": "Mate in 3 — Set 4", "title_ru": "Мат в 3 хода — Набор 4", "title_kk": "3 жүрісте мат — 4-жинақ", "start": 28, "end": 37},
    {"title": "Mate in 3 — Set 5", "title_ru": "Мат в 3 хода — Набор 5", "title_kk": "3 жүрісте мат — 5-жинақ", "start": 37, "end": 46},
    {"title": "Mate in 3 — Set 6", "title_ru": "Мат в 3 хода — Набор 6", "title_kk": "3 жүрісте мат — 6-жинақ", "start": 46, "end": 55},
    {"title": "Mate in 3 — Set 7", "title_ru": "Мат в 3 хода — Набор 7", "title_kk": "3 жүрісте мат — 7-жинақ", "start": 55, "end": 64},
]


def fetch_study_pgn(study_id: str) -> str:
    """Fetch PGN from Lichess study API."""
    url = f"https://lichess.org/api/study/{study_id}.pgn"
    headers = {
        "Accept": "application/x-chess-pgn",
        "User-Agent": "ChessUltimateApp/1.0 (Educational)"
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.text


def san_to_uci(san_move: str, fen: str) -> str:
    """Convert SAN move to UCI format using python-chess."""
    import chess
    board = chess.Board(fen)
    move = board.parse_san(san_move)
    return move.uci()


def parse_chapters(pgn_content: str) -> list:
    """Parse PGN into puzzle dicts with FEN, solution_move, and player_color."""
    puzzles = []
    games = re.split(r'\n\n(?=\[Event)', pgn_content)

    for idx, game in enumerate(games):
        if not game.strip():
            continue

        # Extract headers
        headers = {}
        for m in re.finditer(r'\[(\w+)\s+"([^"]+)"\]', game):
            headers[m.group(1)] = m.group(2)

        fen = headers.get("FEN", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        event = headers.get("Event", f"Puzzle {idx + 1}")

        # Determine active color from FEN
        active_color = fen.split(" ")[1] if " " in fen else "w"
        player_color = "white" if active_color == "w" else "black"

        # Extract moves
        moves_section = re.sub(r'\[.*?\]', '', game).strip()
        moves_clean = re.sub(r'\{[^}]*\}', '', moves_section)
        moves_clean = re.sub(r'\([^)]*\)', '', moves_clean)
        moves_clean = re.sub(r'[!?]+', '', moves_clean)
        moves_clean = re.sub(r'\$\d+', '', moves_clean)
        moves_clean = re.sub(r'\d+\.+', '', moves_clean)
        moves_clean = ' '.join(moves_clean.split())

        moves = [m for m in moves_clean.split() if m not in ['1-0', '0-1', '1/2-1/2', '*']]

        if not moves:
            print(f"  SKIP chapter {idx + 1}: no moves found")
            continue

        first_move_san = moves[0]
        try:
            uci_move = san_to_uci(first_move_san, fen)
        except Exception as e:
            print(f"  SKIP chapter {idx + 1}: can't convert {first_move_san} — {e}")
            continue

        puzzles.append({
            "fen": fen,
            "solution_move": uci_move,
            "player_color": player_color,
            "source_name": event,
            "source_url": STUDY_URL,
        })
        print(f"  Parsed {idx + 1}: [{player_color}] {first_move_san} -> {uci_move}")

    return puzzles


def api_post(endpoint: str, data: dict) -> dict:
    """POST to Supabase REST API."""
    resp = requests.post(f"{CHESSTER_URL}/{endpoint}", headers=HEADERS, json=data)
    if resp.status_code not in (200, 201):
        print(f"  ERROR {endpoint}: {resp.status_code} {resp.text[:200]}")
        sys.exit(1)
    return resp.json()


def main():
    dry_run = "--dry-run" in sys.argv

    # Step 1: Fetch study
    print("=== Fetching Lichess Study ===")
    pgn = fetch_study_pgn(STUDY_ID)
    print(f"Fetched {len(pgn)} bytes")

    # Step 2: Parse all chapters
    print("\n=== Parsing Chapters ===")
    all_puzzles = parse_chapters(pgn)
    print(f"\nTotal puzzles parsed: {len(all_puzzles)}")

    # Count by color
    white_count = sum(1 for p in all_puzzles if p["player_color"] == "white")
    black_count = sum(1 for p in all_puzzles if p["player_color"] == "black")
    print(f"White to move: {white_count}, Black to move: {black_count}")

    if dry_run:
        print("\n[DRY RUN] Would create:")
        print(f"  1 course (Mate in 3 Moves, level=master)")
        print(f"  1 module")
        print(f"  {len(LESSONS)} lessons")
        print(f"  {len(all_puzzles)} puzzles total")
        for i, lesson in enumerate(LESSONS):
            chunk = all_puzzles[lesson["start"]:lesson["end"]]
            print(f"  Lesson {i+1}: {lesson['title']} — {len(chunk)} puzzles")
        return

    # Step 3: Create course
    # NOTE: DB constraint must allow 'master'. If not, use 'advanced' temporarily.
    print("\n=== Creating Course ===")
    course_id = str(uuid.uuid4())
    course_data = {
        "id": course_id,
        "title": "Mate in 3 Moves",
        "description": "Solve checkmate-in-three puzzles to sharpen your tactical vision.",
        "level": "master",
        "order_index": 7,
        "title_ru": "Мат в 3 хода",
        "description_ru": "Решайте задачи на мат в 3 хода для развития тактического зрения.",
        "title_kk": "3 жүрісте мат",
        "description_kk": "Тактикалық көзқарасыңызды жетілдіру үшін 3 жүрістегі мат есептерін шешіңіз.",
    }

    print(f"Creating course: {course_data['title']} (level={course_data['level']})")
    try:
        result = api_post("courses", course_data)
    except SystemExit:
        # Constraint might not allow 'master' yet — fall back to 'advanced'
        print("  Retrying with level='advanced' (constraint not updated yet)...")
        course_data["level"] = "advanced"
        result = api_post("courses", course_data)
        print("  NOTE: Update level to 'master' after running ALTER constraint!")

    print(f"  Course ID: {course_id}")

    # Step 4: Create module
    print("\n=== Creating Module ===")
    module_id = str(uuid.uuid4())
    module_data = {
        "id": module_id,
        "course_id": course_id,
        "title": "Mate in 3 Moves",
        "description": "64 checkmate puzzles from Chess Empire training materials",
        "order_index": 1,
        "title_ru": "Мат в 3 хода",
        "description_ru": "64 задачи на мат из учебных материалов Chess Empire",
    }
    api_post("modules", module_data)
    print(f"  Module ID: {module_id}")

    # Step 5: Create lessons and insert puzzles
    print("\n=== Creating Lessons & Importing Puzzles ===")
    total_imported = 0

    for i, lesson_def in enumerate(LESSONS):
        lesson_id = str(uuid.uuid4())
        chunk = all_puzzles[lesson_def["start"]:lesson_def["end"]]

        lesson_data = {
            "id": lesson_id,
            "module_id": module_id,
            "title": lesson_def["title"],
            "content": f"# {lesson_def['title']}\n\nSolve all {len(chunk)} checkmate puzzles.",
            "lesson_type": "exercise",
            "order_index": i + 1,
            "title_ru": lesson_def["title_ru"],
            "content_ru": f"# {lesson_def['title_ru']}\n\nРешите все {len(chunk)} задач на мат.",
            "title_kk": lesson_def.get("title_kk"),
            "has_multiple_puzzles": True,
            "puzzle_count": len(chunk),
        }
        api_post("lessons", lesson_data)
        print(f"\n  Lesson {i+1}: {lesson_def['title']} ({len(chunk)} puzzles) -> {lesson_id}")

        # Insert puzzles for this lesson
        for j, puzzle in enumerate(chunk):
            puzzle_data = {
                "lesson_id": lesson_id,
                "order_index": j + 1,
                "fen": puzzle["fen"],
                "solution_move": puzzle["solution_move"],
                "source_url": puzzle["source_url"],
                "source_name": puzzle["source_name"],
            }
            resp = requests.post(f"{CHESSTER_URL}/lesson_puzzles", headers=HEADERS, json=puzzle_data)
            if resp.status_code not in (200, 201):
                print(f"    ERROR puzzle {j+1}: {resp.status_code} {resp.text[:100]}")
            else:
                total_imported += 1

        time.sleep(0.5)  # Small delay between lessons

    # Summary
    print(f"\n{'='*50}")
    print(f"=== Import Complete ===")
    print(f"{'='*50}")
    print(f"Course: {course_data['title']} (ID: {course_id})")
    print(f"Level: {course_data['level']}")
    print(f"Module: 1")
    print(f"Lessons: {len(LESSONS)}")
    print(f"Puzzles imported: {total_imported}/{len(all_puzzles)}")
    print(f"White to move: {white_count}, Black to move: {black_count}")

    if course_data["level"] == "advanced":
        print(f"\n⚠️  IMPORTANT: Run this SQL in Supabase dashboard to enable 'master' level:")
        print(f"  ALTER TABLE courses DROP CONSTRAINT IF EXISTS courses_level_check;")
        print(f"  ALTER TABLE courses ADD CONSTRAINT courses_level_check CHECK (level IN ('beginner', 'intermediate', 'advanced', 'master'));")
        print(f"  UPDATE courses SET level = 'master' WHERE id = '{course_id}';")


if __name__ == "__main__":
    main()
