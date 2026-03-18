#!/usr/bin/env python3
"""
Level 2 Puzzle Importer - Local PGN Version

Workaround for private Lichess studies.
Imports puzzles from locally downloaded PGN files.

Setup:
1. Download each study's PGN manually from Lichess
2. Save them in backend/data/lichess_studies/ directory
3. Name them: {study_id}.pgn (e.g., QVTlrUPC.pgn)

Usage:
    python import_level2_from_local_pgn.py [--dry-run]

The script:
1. Reads /tmp/level2_lessons.json
2. Looks for corresponding PGN files in data/lichess_studies/
3. Parses specific chapters from each PGN
4. Imports puzzles to the database
"""

import sys
import os
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client
from import_lichess_study import (
    parse_pgn_chapters,
    import_puzzles_to_lesson,
    get_supabase_client
)
from import_level2_puzzles import (
    parse_lichess_study_url,
    find_lesson_by_title
)


def load_local_pgn(study_id: str, pgn_dir: str = None) -> str:
    """
    Load PGN content from local file.

    Args:
        study_id: Lichess study ID
        pgn_dir: Directory containing PGN files

    Returns:
        PGN content as string

    Raises:
        FileNotFoundError: If PGN file not found
    """
    if pgn_dir is None:
        # Default to backend/data/lichess_studies/
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pgn_dir = os.path.join(backend_dir, 'data', 'lichess_studies')

    pgn_path = os.path.join(pgn_dir, f'{study_id}.pgn')

    if not os.path.exists(pgn_path):
        raise FileNotFoundError(f"PGN file not found: {pgn_path}")

    with open(pgn_path, 'r', encoding='utf-8') as f:
        return f.read()


def import_lesson_puzzles(supabase, lesson_data: dict, pgn_dir: str = None, dry_run: bool = False) -> dict:
    """
    Import puzzles for a single lesson from local PGN.

    Args:
        supabase: Supabase client
        lesson_data: Lesson data from JSON file
        pgn_dir: Directory containing PGN files
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
        # Load PGN from local file
        print(f"  Loading {study_id}.pgn...")
        pgn_content = load_local_pgn(study_id, pgn_dir)

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

    except FileNotFoundError as e:
        result['message'] = f'PGN file not found: {e}'
        return result
    except Exception as e:
        result['message'] = f'Error: {str(e)}'
        return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Batch import Level 2 puzzles from local PGN files')
    parser.add_argument('--dry-run', action='store_true', help='Parse but do not insert')
    parser.add_argument('--limit', type=int, help='Limit number of lessons to process')
    parser.add_argument('--pgn-dir', help='Directory containing PGN files (default: backend/data/lichess_studies)')

    args = parser.parse_args()

    print("=" * 60)
    print("Level 2 Puzzle Importer - Local PGN")
    print("=" * 60)
    print()

    # Check PGN directory
    if args.pgn_dir:
        pgn_dir = args.pgn_dir
    else:
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pgn_dir = os.path.join(backend_dir, 'data', 'lichess_studies')

    if not os.path.exists(pgn_dir):
        print(f"Error: PGN directory not found: {pgn_dir}")
        print("Please create it and download the study PGN files.")
        sys.exit(1)

    print(f"PGN directory: {pgn_dir}")
    pgn_files = [f for f in os.listdir(pgn_dir) if f.endswith('.pgn')]
    print(f"Found {len(pgn_files)} PGN files")
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
        result = import_lesson_puzzles(supabase, lesson_data, pgn_dir, dry_run=args.dry_run)

        print(f"  Result: {result['message']}")

        if result['success']:
            total_puzzles += result['puzzle_count']

        results.append({
            'title': title,
            'url': url,
            **result
        })

        print()

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

    # Check for missing PGN files
    missing_studies = set()
    for r in failed:
        if 'PGN file not found' in r['message']:
            url = r.get('url', '')
            parsed = parse_lichess_study_url(url)
            if parsed:
                missing_studies.add(parsed['study_id'])

    if missing_studies:
        print("Missing PGN files:")
        for study_id in sorted(missing_studies):
            print(f"  - {study_id}.pgn")
            print(f"    Download from: https://lichess.org/study/{study_id}")
        print()

    if args.dry_run:
        print("[DRY RUN] No data was written to the database")
    else:
        print("✓ Import complete!")

    print("=" * 60)


if __name__ == '__main__':
    main()
