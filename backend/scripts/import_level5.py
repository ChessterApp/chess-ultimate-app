#!/usr/bin/env python3
"""
Import Level 5 (Winning the Queen) from Lichess study into Chesster.

Study: https://lichess.org/study/wZBmF90N
64 chapters — tactical puzzles themed "Winning the Queen" (Выигрыш ферзя).
Mostly white to move (60 white, 4 black).

This script:
1. Fetches all chapters from the Lichess study
2. Creates the Level 5 course, 1 module, and exercise lessons
3. Distributes 64 puzzles across 7 lessons (~9-10 per lesson)
4. Inserts puzzles into lesson_puzzles table

Usage:
    python import_level5.py [--dry-run]
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

STUDY_ID = "wZBmF90N"
STUDY_URL = f"https://lichess.org/study/{STUDY_ID}"

# Lesson distribution: 7 lessons of ~9-10 puzzles each (64 total)
LESSONS = [
    {"title": "Winning the Queen — Set 1", "title_ru": "Выигрыш ферзя — Набор 1", "title_kk": "Ферзьді ұту — 1-жинақ", "start": 0, "end": 10},
    {"title": "Winning the Queen — Set 2", "title_ru": "Выигрыш ферзя — Набор 2", "title_kk": "Ферзьді ұту — 2-жинақ", "start": 10, "end": 19},
    {"title": "Winning the Queen — Set 3", "title_ru": "Выигрыш ферзя — Набор 3", "title_kk": "Ферзьді ұту — 3-жинақ", "start": 19, "end": 28},
    {"title": "Winning the Queen — Set 4", "title_ru": "Выигрыш ферзя — Набор 4", "title_kk": "Ферзьді ұту — 4-жинақ", "start": 28, "end": 37},
    {"title": "Winning the Queen — Set 5", "title_ru": "Выигрыш ферзя — Набор 5", "title_kk": "Ферзьді ұту — 5-жинақ", "start": 37, "end": 46},
    {"title": "Winning the Queen — Set 6", "title_ru": "Выигрыш ферзя — Набор 6", "title_kk": "Ферзьді ұту — 6-жинақ", "start": 46, "end": 55},
    {"title": "Winning the Queen — Set 7", "title_ru": "Выигрыш ферзя — Набор 7", "title_kk": "Ферзьді ұту — 7-жинақ", "start": 55, "end": 64},
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
        print(f"  1 course (Winning the Queen, level=master)")
        print(f"  1 module")
        print(f"  {len(LESSONS)} lessons")
        print(f"  {len(all_puzzles)} puzzles total")
        for i, lesson in enumerate(LESSONS):
            chunk = all_puzzles[lesson["start"]:lesson["end"]]
            print(f"  Lesson {i+1}: {lesson['title']} — {len(chunk)} puzzles")
        return

    # Step 3: Create course
    print("\n=== Creating Course ===")
    course_id = str(uuid.uuid4())
    course_data = {
        "id": course_id,
        "title": "Winning the Queen",
        "description": "Practice tactical patterns to win your opponent's queen through forks, discovered attacks, pins, and more.",
        "level": "master",
        "order_index": 8,
        "title_ru": "Выигрыш ферзя",
        "description_ru": "Тренируйте тактические приёмы для выигрыша ферзя — вилки, открытые нападения, связки и другое.",
        "title_kk": "Ферзьді ұту",
        "description_kk": "Шанышқылар, ашық шабуылдар, байланыстар арқылы қарсыластың ферзін ұтуды жаттығыңыз.",
    }

    print(f"Creating course: {course_data['title']} (level={course_data['level']}, order_index=8)")
    try:
        result = api_post("courses", course_data)
    except SystemExit:
        print("  Retrying with level='advanced'...")
        course_data["level"] = "advanced"
        result = api_post("courses", course_data)

    print(f"  Course ID: {course_id}")

    # Step 4: Create module
    print("\n=== Creating Module ===")
    module_id = str(uuid.uuid4())
    module_data = {
        "id": module_id,
        "course_id": course_id,
        "title": "Winning the Queen",
        "description": "64 tactical puzzles from Chess Empire training materials — win the queen!",
        "order_index": 1,
        "title_ru": "Выигрыш ферзя",
        "description_ru": "64 тактические задачи из учебных материалов Chess Empire — выиграйте ферзя!",
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
            "content": f"# {lesson_def['title']}\n\nSolve all {len(chunk)} tactical puzzles to win the queen.",
            "lesson_type": "exercise",
            "order_index": i + 1,
            "title_ru": lesson_def["title_ru"],
            "content_ru": f"# {lesson_def['title_ru']}\n\nРешите все {len(chunk)} задач на выигрыш ферзя.",
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

        time.sleep(0.5)

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


if __name__ == "__main__":
    main()
