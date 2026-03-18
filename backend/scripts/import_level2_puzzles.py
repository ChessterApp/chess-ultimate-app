#!/usr/bin/env python3
"""
Level 2 (Chess Tactics) Batch Puzzle Importer

Imports puzzles from Lichess studies for all Level 2 lessons.
Reads lesson data from /tmp/level2_lessons.json and imports
puzzles for each lesson that has a study-format Lichess URL.

Usage:
    python import_level2_puzzles.py [--dry-run]

The script:
1. Reads /tmp/level2_lessons.json
2. For each lesson with study-format URL:
   - Extracts study_id and chapter_id from URL
   - Looks up lesson in Chesster DB by matching title
   - Imports that specific chapter as puzzles for that lesson
3. Adds 1-second delay between Lichess API calls
4. Reports progress and results
"""

import sys
import os
import json
import time
import re
from urllib.parse import urlparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client
from import_lichess_study import (
    fetch_lichess_study_pgn,
    parse_pgn_chapters,
    import_puzzles_to_lesson,
    load_env,
    get_supabase_client
)


def parse_lichess_study_url(url: str) -> dict:
    """
    Parse Lichess study URL to extract study_id and chapter_id.

    Args:
        url: Lichess URL (e.g., https://lichess.org/study/QVTlrUPC/hja8zqts)

    Returns:
        Dict with 'study_id' and 'chapter_id' or None if not a study URL
    """
    if not url or 'lichess.org/study/' not in url:
        return None

    # Extract study_id and chapter_id from URL
    # Format: https://lichess.org/study/{study_id}/{chapter_id}
    parts = urlparse(url).path.split('/')

    if len(parts) >= 4 and parts[1] == 'study':
        return {
            'study_id': parts[2],
            'chapter_id': parts[3] if len(parts) > 3 else None
        }

    return None


def find_lesson_by_title(supabase, title: str):
    """
    Find lesson in Chesster DB by matching title (Russian).

    Args:
        supabase: Supabase client
        title: Lesson title to search for

    Returns:
        Lesson dict or None
    """
    # Try exact match first
    lessons = supabase.table('lessons').select('*').eq('title_ru', title).execute()

    if lessons.data:
        return lessons.data[0]

    # Fallback: try title field
    lessons = supabase.table('lessons').select('*').eq('title', title).execute()

    if lessons.data:
        return lessons.data[0]

    return None


def import_lesson_puzzles(supabase, lesson_data: dict, dry_run: bool = False) -> dict:
    """
    Import puzzles for a single lesson.

    Args:
        supabase: Supabase client
        lesson_data: Lesson data from JSON file
        dry_run: If True, parse but don't insert

    Returns:
        Dict with 'success', 'message', 'puzzle_count'
    """
    result = {
        'success': False,
        'message': '',
        'puzzle_count': 0
    }

    # Parse Lichess URL
    url = lesson_data.get('lichess_embed_url')
    if not url:
        result['message'] = 'No Lichess URL'
        return result

    parsed_url = parse_lichess_study_url(url)
    if not parsed_url:
        result['message'] = f'Not a study URL: {url}'
        return result

    study_id = parsed_url['study_id']
    chapter_id = parsed_url['chapter_id']

    if not chapter_id:
        result['message'] = 'No chapter ID in URL'
        return result

    # Find lesson in DB
    title = lesson_data['title']
    lesson = find_lesson_by_title(supabase, title)

    if not lesson:
        result['message'] = f'Lesson not found in DB: {title}'
        return result

    lesson_id = lesson['id']

    try:
        # Fetch study PGN
        print(f"  Fetching study {study_id}...")
        pgn_content = fetch_lichess_study_pgn(study_id)

        # Parse only the specific chapter
        puzzles = parse_pgn_chapters(pgn_content, chapter_id=chapter_id)

        if not puzzles:
            result['message'] = f'No puzzles found in chapter {chapter_id}'
            return result

        result['puzzle_count'] = len(puzzles)

        if dry_run:
            result['success'] = True
            result['message'] = f'[DRY RUN] Would import {len(puzzles)} puzzles'
            return result

        # Import puzzles
        import_puzzles_to_lesson(supabase, lesson_id, puzzles, url)

        result['success'] = True
        result['message'] = f'Imported {len(puzzles)} puzzles'
        return result

    except Exception as e:
        result['message'] = f'Error: {str(e)}'
        return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Batch import Level 2 puzzles from Lichess')
    parser.add_argument('--dry-run', action='store_true', help='Parse but do not insert')
    parser.add_argument('--limit', type=int, help='Limit number of lessons to process')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between API calls (seconds)')

    args = parser.parse_args()

    print("=" * 60)
    print("Level 2 (Chess Tactics) Puzzle Importer")
    print("=" * 60)
    print()

    # Load lesson data from JSON
    json_path = '/tmp/level2_lessons.json'
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found")
        sys.exit(1)

    with open(json_path) as f:
        lessons_data = json.load(f)

    print(f"Loaded {len(lessons_data)} lessons from {json_path}")
    print()

    # Connect to Supabase
    print("Connecting to database...")
    try:
        supabase = get_supabase_client()
        print("✓ Connected to Supabase")
        print()
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        sys.exit(1)

    # Filter lessons to study-format URLs
    study_lessons = []
    for lesson in lessons_data:
        url = lesson.get('lichess_embed_url')
        if url and 'lichess.org/study/' in url and '/' in url.split('study/')[-1]:
            study_lessons.append(lesson)

    print(f"Found {len(study_lessons)} lessons with study-format URLs")
    print()

    if args.limit:
        study_lessons = study_lessons[:args.limit]
        print(f"Limited to first {args.limit} lessons")
        print()

    # Process each lesson
    results = []
    total_puzzles = 0

    for idx, lesson_data in enumerate(study_lessons):
        title = lesson_data['title']
        url = lesson_data.get('lichess_embed_url')

        print(f"[{idx + 1}/{len(study_lessons)}] {title}")
        print(f"  URL: {url}")

        # Import puzzles
        result = import_lesson_puzzles(supabase, lesson_data, dry_run=args.dry_run)

        print(f"  Result: {result['message']}")

        if result['success']:
            total_puzzles += result['puzzle_count']

        results.append({
            'title': title,
            'url': url,
            **result
        })

        print()

        # Rate limiting delay
        if idx < len(study_lessons) - 1:  # Don't delay after the last one
            time.sleep(args.delay)

    # Summary
    print("=" * 60)
    print("Import Summary")
    print("=" * 60)

    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]

    print(f"Total lessons processed: {len(results)}")
    print(f"Successful imports: {len(successful)}")
    print(f"Failed imports: {len(failed)}")
    print(f"Total puzzles imported: {total_puzzles}")
    print()

    if failed:
        print("Failed imports:")
        for r in failed:
            print(f"  - {r['title']}: {r['message']}")
        print()

    if args.dry_run:
        print("[DRY RUN] No data was written to the database")
    else:
        print("✓ Import complete!")

    print("=" * 60)


if __name__ == '__main__':
    main()
