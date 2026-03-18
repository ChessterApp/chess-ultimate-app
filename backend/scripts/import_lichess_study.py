#!/usr/bin/env python3
"""
Lichess Study Importer

Imports puzzles from a Lichess study into the lesson_puzzles table.
Each chapter in the study becomes a puzzle.

Usage:
    python import_lichess_study.py <study_id> <lesson_slug> [--course-slug=<slug>]

Example:
    python import_lichess_study.py VTUxy8HW rook-mate-in-1 --course-slug=checkmate-patterns

The script:
1. Fetches the study PGN from Lichess API
2. Parses each chapter as a puzzle
3. Extracts the starting FEN and first move as solution
4. Inserts into lesson_puzzles table
5. Updates the lesson's has_multiple_puzzles and puzzle_count fields
"""

import sys
import os
import re
import requests
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client


def load_env():
    """Load environment variables from .env file."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()


def get_supabase_client():
    """Create and return Supabase client."""
    load_env()
    url = os.environ.get('SUPABASE_URL', 'https://qtzujwiqzbgyhdgulvcd.supabase.co')
    # Try multiple possible env var names
    key = os.environ.get('SUPABASE_SERVICE_KEY') or os.environ.get('SUPABASE_KEY') or os.environ.get('SUPABASE_ANON_KEY')
    if not key:
        raise ValueError("SUPABASE_KEY/SUPABASE_SERVICE_KEY not found in environment")
    return create_client(url, key)


def fetch_lichess_study_pgn(study_id: str) -> str:
    """
    Fetch PGN content from a Lichess study.

    Args:
        study_id: The study ID from the Lichess URL (e.g., VTUxy8HW)

    Returns:
        PGN content as string
    """
    url = f"https://lichess.org/api/study/{study_id}.pgn"
    headers = {
        'Accept': 'application/x-chess-pgn',
        'User-Agent': 'ChessUltimateApp/1.0 (Educational)'
    }

    print(f"Fetching study from: {url}")
    response = requests.get(url, headers=headers)

    if response.status_code == 404:
        raise ValueError(f"Study {study_id} not found. Make sure the study is public.")

    response.raise_for_status()
    return response.text


def parse_pgn_chapters(pgn_content: str, chapter_id: str = None) -> list:
    """
    Parse PGN content into individual chapters (puzzles).

    Each chapter in the PGN represents one puzzle.
    We extract:
    - FEN position (starting position)
    - First move as solution
    - Chapter name

    Args:
        pgn_content: PGN text content
        chapter_id: Optional chapter ID to filter (e.g., 'hja8zqts')

    Returns:
        List of dicts with puzzle data
    """
    puzzles = []

    # Split PGN into individual games/chapters
    # PGN games are separated by double newlines between result and next game
    games = re.split(r'\n\n(?=\[Event)', pgn_content)

    for game_idx, game in enumerate(games):
        if not game.strip():
            continue

        puzzle = {
            'order_index': game_idx + 1,
            'fen': None,
            'solution_move': None,
            'hint_text': None,
            'source_name': None
        }

        # Extract headers
        headers = {}
        for match in re.finditer(r'\[(\w+)\s+"([^"]+)"\]', game):
            headers[match.group(1)] = match.group(2)

        # Get FEN (starting position)
        puzzle['fen'] = headers.get('FEN', 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')

        # Get chapter name
        site = headers.get('Site', '')
        event = headers.get('Event', f'Puzzle {game_idx + 1}')

        # Lichess study chapter name is usually in Event or extracted from Site
        current_chapter_id = None
        if 'lichess.org/study' in site:
            current_chapter_id = site.split('/')[-1] if '/' in site else None
            puzzle['source_id'] = current_chapter_id

        # If chapter_id filter is specified, skip chapters that don't match
        if chapter_id and current_chapter_id != chapter_id:
            continue

        puzzle['source_name'] = event

        # Extract moves section (after headers)
        moves_section = re.sub(r'\[.*?\]', '', game).strip()

        # Parse moves - handle various PGN formats
        # Remove comments {}, variations (), and annotations
        moves_clean = re.sub(r'\{[^}]*\}', '', moves_section)  # Remove comments
        moves_clean = re.sub(r'\([^)]*\)', '', moves_clean)     # Remove variations
        moves_clean = re.sub(r'[!?]+', '', moves_clean)         # Remove annotations
        moves_clean = re.sub(r'\$\d+', '', moves_clean)         # Remove NAG symbols
        moves_clean = re.sub(r'\d+\.+', '', moves_clean)        # Remove move numbers
        moves_clean = ' '.join(moves_clean.split())             # Normalize whitespace

        # Get the first move (this is the solution)
        moves = moves_clean.split()
        moves = [m for m in moves if m not in ['1-0', '0-1', '1/2-1/2', '*']]

        if moves:
            first_move_san = moves[0]
            # Convert SAN to UCI format
            uci_move = san_to_uci(first_move_san, puzzle['fen'])
            puzzle['solution_move'] = uci_move
        else:
            print(f"  Warning: No moves found in chapter {game_idx + 1}")
            continue

        # Only add puzzle if we have both FEN and solution
        if puzzle['fen'] and puzzle['solution_move']:
            puzzles.append(puzzle)
            print(f"  Parsed puzzle {puzzle['order_index']}: {puzzle['source_name']} -> {puzzle['solution_move']}")
        else:
            print(f"  Skipping chapter {game_idx + 1}: missing FEN or solution")

    return puzzles


def san_to_uci(san_move: str, fen: str) -> str:
    """
    Convert Standard Algebraic Notation (SAN) to UCI format.

    Uses python-chess library for accurate conversion.

    Args:
        san_move: Move in SAN format (e.g., "Rxh8#", "e4")
        fen: Current position FEN

    Returns:
        Move in UCI format (e.g., "a1h8", "e2e4")
    """
    try:
        import chess
        board = chess.Board(fen)
        move = board.parse_san(san_move)
        return move.uci()
    except ImportError:
        print("Warning: python-chess not installed. Install with: pip install chess")
        # Fallback: Try basic conversion for simple moves
        return san_move.lower().replace('x', '').replace('+', '').replace('#', '')
    except Exception as e:
        print(f"  Warning: Could not convert '{san_move}' to UCI: {e}")
        return san_move


def find_lesson_by_slug(supabase, course_slug: str, lesson_slug: str):
    """
    Find lesson by course and lesson slugs.

    Returns:
        Lesson dict or None
    """
    # First find the course
    courses = supabase.table('courses').select('*').execute()

    course = None
    for c in courses.data:
        c_slug = c.get('slug') or generate_slug(c.get('title', ''))
        if c_slug == course_slug:
            course = c
            break

    if not course:
        print(f"Course not found with slug: {course_slug}")
        return None

    # Get modules for course
    modules = supabase.table('modules').select('id').eq('course_id', course['id']).execute()
    if not modules.data:
        print(f"No modules found for course: {course_slug}")
        return None

    module_ids = [m['id'] for m in modules.data]

    # Find lesson
    lessons = supabase.table('lessons').select('*').in_('module_id', module_ids).execute()

    for lesson in lessons.data:
        l_slug = lesson.get('slug') or generate_slug(lesson.get('title', ''))
        if l_slug == lesson_slug:
            return lesson

    print(f"Lesson not found with slug: {lesson_slug}")
    return None


def generate_slug(title: str) -> str:
    """Generate URL-friendly slug from title."""
    slug = title.lower()
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


def import_puzzles_to_lesson(supabase, lesson_id: str, puzzles: list, study_url: str):
    """
    Insert puzzles into lesson_puzzles table and update lesson.

    Args:
        supabase: Supabase client
        lesson_id: UUID of the target lesson
        puzzles: List of puzzle dicts
        study_url: Original Lichess study URL
    """
    # First, clear any existing puzzles for this lesson
    print(f"\nClearing existing puzzles for lesson {lesson_id}...")
    supabase.table('lesson_puzzles').delete().eq('lesson_id', lesson_id).execute()

    # Insert new puzzles
    print(f"Inserting {len(puzzles)} puzzles...")

    for puzzle in puzzles:
        puzzle_data = {
            'lesson_id': lesson_id,
            'order_index': puzzle['order_index'],
            'fen': puzzle['fen'],
            'solution_move': puzzle['solution_move'],
            'hint_text': puzzle.get('hint_text'),
            'source_url': study_url,
            'source_id': puzzle.get('source_id'),
            'source_name': puzzle.get('source_name')
        }

        result = supabase.table('lesson_puzzles').insert(puzzle_data).execute()
        if result.data:
            print(f"  Inserted puzzle {puzzle['order_index']}: {puzzle['source_name']}")

    # Update lesson to mark it as multi-puzzle
    print(f"\nUpdating lesson metadata...")
    supabase.table('lessons').update({
        'has_multiple_puzzles': True,
        'puzzle_count': len(puzzles)
    }).eq('id', lesson_id).execute()

    print(f"✓ Successfully imported {len(puzzles)} puzzles to lesson")


def main():
    parser = argparse.ArgumentParser(description='Import Lichess study as lesson puzzles')
    parser.add_argument('study_id', help='Lichess study ID (e.g., VTUxy8HW)')
    parser.add_argument('--lesson-id', help='Target lesson UUID directly')
    parser.add_argument('--lesson-slug', help='Target lesson slug (e.g., rook-mate-in-1)')
    parser.add_argument('--course-slug', help='Course slug (e.g., checkmate-patterns)')
    parser.add_argument('--chapter-id', help='Import only specific chapter ID (e.g., hja8zqts)')
    parser.add_argument('--dry-run', action='store_true', help='Parse but do not insert')

    args = parser.parse_args()

    # Validate arguments
    if not args.lesson_id and not (args.lesson_slug and args.course_slug):
        print("Error: Either --lesson-id OR both --lesson-slug and --course-slug are required")
        sys.exit(1)

    print(f"=" * 50)
    print(f"Lichess Study Importer")
    print(f"=" * 50)
    print(f"Study ID: {args.study_id}")
    if args.lesson_id:
        print(f"Target lesson ID: {args.lesson_id}")
    else:
        print(f"Target: {args.course_slug}/{args.lesson_slug}")
    print()

    # Fetch study PGN
    try:
        pgn_content = fetch_lichess_study_pgn(args.study_id)
        print(f"✓ Fetched study PGN ({len(pgn_content)} bytes)")
    except Exception as e:
        print(f"✗ Failed to fetch study: {e}")
        sys.exit(1)

    # Parse chapters into puzzles
    print(f"\nParsing chapters...")
    if args.chapter_id:
        print(f"  Filtering to chapter: {args.chapter_id}")
    puzzles = parse_pgn_chapters(pgn_content, chapter_id=args.chapter_id)
    print(f"✓ Found {len(puzzles)} puzzles")

    if not puzzles:
        print("No puzzles found in study. Exiting.")
        sys.exit(1)

    if args.dry_run:
        print("\n[DRY RUN] Would import these puzzles:")
        for p in puzzles:
            print(f"  {p['order_index']}. {p['source_name']}: FEN={p['fen'][:30]}... Move={p['solution_move']}")
        sys.exit(0)

    # Connect to Supabase
    print(f"\nConnecting to database...")
    try:
        supabase = get_supabase_client()
        print("✓ Connected to Supabase")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        sys.exit(1)

    # Find target lesson
    if args.lesson_id:
        # Use lesson ID directly
        lesson_id = args.lesson_id
        lesson_result = supabase.table('lessons').select('*').eq('id', lesson_id).execute()
        if not lesson_result.data:
            print(f"✗ Lesson not found with ID: {lesson_id}")
            sys.exit(1)
        lesson = lesson_result.data[0]
        print(f"✓ Found lesson: {lesson['title']} (ID: {lesson['id']})")
    else:
        # Find by slugs
        print(f"\nFinding lesson '{args.lesson_slug}' in course '{args.course_slug}'...")
        lesson = find_lesson_by_slug(supabase, args.course_slug, args.lesson_slug)

        if not lesson:
            print(f"✗ Lesson not found")
            sys.exit(1)

        print(f"✓ Found lesson: {lesson['title']} (ID: {lesson['id']})")
        lesson_id = lesson['id']

    # Import puzzles
    study_url = f"https://lichess.org/study/{args.study_id}"
    import_puzzles_to_lesson(supabase, lesson_id, puzzles, study_url)

    print(f"\n" + "=" * 50)
    print(f"Import complete!")
    print(f"=" * 50)


if __name__ == '__main__':
    main()
