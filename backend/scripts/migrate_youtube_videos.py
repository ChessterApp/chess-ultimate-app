#!/usr/bin/env python3
"""
Migrate YouTube videos for dual-video lessons.
Moves Kazakh videos from content/content_ru into content_kk.
"""

import os
import sys
import re
import argparse
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from backend/.env
backend_dir = Path(__file__).parent.parent
load_dotenv(backend_dir / '.env')

# Dual-video lesson mappings (lesson title contains these patterns -> video IDs)
DUAL_VIDEO_LESSONS = {
    'Check': {'ru': 'JJLiGr_e57o', 'kk': 'kUyGUCeMt7w'},
    'Checkmate': {'ru': 'leHhUag7CkE', 'kk': 'QGmkx2-sPZI'},
    'The Pawn': {'ru': 'dDVyfOMWTNo', 'kk': 'MYpa00Vr9B0'},
    'The Knight': {'ru': 'oSh_Glu8nRQ', 'kk': '-FxFa31tiOM'},
    'The King': {'ru': 'wfb5UYf54qE', 'kk': 'vPuewRyXMtU'},
    'The Rook': {'ru': 'B5KJXmM1qSc', 'kk': 'MrkUaEcnwVg'},
    'The Bishop': {'ru': 'fLLl5OT_XPQ', 'kk': 'ej0MTV0JLVU'},
    'The Queen': {'ru': 'a2TjkGqtQkY', 'kk': 'wxf5fty7ZiQ'},
}


def get_supabase_client() -> Client:
    """Create Supabase client from environment variables."""
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_KEY')

    if not url or not key:
        raise ValueError('SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in backend/.env')

    return create_client(url, key)


def extract_video_id_from_url(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def find_kazakh_video_section(content: str) -> tuple[str | None, int, int]:
    """
    Find the Kazakh video section in content.
    Returns (video_url, start_index, end_index) or (None, -1, -1) if not found.
    """
    # Look for "## Видео (Қазақша)" heading followed by YouTube URL
    pattern = r'##\s*Видео\s*\(Қазақша\)(.*?)(?=\n##|\Z)'
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        return None, -1, -1

    section_text = match.group(1)
    start_idx = match.start()
    end_idx = match.end()

    # Extract YouTube URL from the section
    url_pattern = r'https?://(?:www\.)?(?:youtube\.com/(?:embed/|watch\?v=)|youtu\.be/)[^\s\n]+'
    url_match = re.search(url_pattern, section_text)

    if url_match:
        return url_match.group(0), start_idx, end_idx

    return None, -1, -1


def remove_kazakh_section(content: str) -> str:
    """Remove the Kazakh video section from content."""
    if not content:
        return content

    # Remove "## Видео (Қазақша)" section
    pattern = r'\n*##\s*Видео\s*\(Қазақша\).*?(?=\n##|\Z)'
    cleaned = re.sub(pattern, '', content, flags=re.DOTALL)

    # Clean up extra newlines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned.strip()


def ensure_video_in_content_kk(content_kk: str | None, content_ru: str, video_url: str) -> str:
    """
    Ensure content_kk has the Kazakh video.
    If content_kk is empty, copy from content_ru and replace video.
    If content_kk has text, append Kazakh video section.
    """
    if not content_kk or content_kk.strip() == '':
        # Copy from content_ru and replace Russian video with Kazakh video
        result = content_ru

        # Find and replace Russian video URL
        ru_video_pattern = r'(##\s*Видео урок\s*\n+)(https?://(?:www\.)?(?:youtube\.com/(?:embed/|watch\?v=)|youtu\.be/)[^\s\n]+)'
        result = re.sub(ru_video_pattern, rf'\1{video_url}', result)

        # Remove any Kazakh section if it exists
        result = remove_kazakh_section(result)

        return result
    else:
        # content_kk already has text, append Kazakh video section
        result = content_kk

        # Remove existing Kazakh video section if present
        result = remove_kazakh_section(result)

        # Check if there's already a video section
        if 'Видео сабағы' not in result and 'Видео урок' not in result:
            # Add new video section
            result += f'\n\n## Видео сабағы\n{video_url}'
        else:
            # Replace existing video URL
            video_pattern = r'(##\s*Видео\s*(?:сабағы|урок)\s*\n+)(https?://(?:www\.)?(?:youtube\.com/(?:embed/|watch\?v=)|youtu\.be/)[^\s\n]+)'
            result = re.sub(video_pattern, rf'\1{video_url}', result)

        return result


def migrate_lesson(supabase: Client, lesson: dict, dry_run: bool = True) -> dict:
    """
    Migrate a single lesson.
    Returns a dict with migration results.
    """
    title = lesson['title']
    lesson_id = lesson['id']
    content = lesson.get('content', '')
    content_ru = lesson.get('content_ru', '')
    content_kk = lesson.get('content_kk', '')

    # Find Kazakh video section
    kk_video_url, start_idx, end_idx = find_kazakh_video_section(content)

    if not kk_video_url:
        return {
            'lesson_id': lesson_id,
            'title': title,
            'status': 'skipped',
            'reason': 'No Kazakh video section found'
        }

    # Remove Kazakh section from content and content_ru
    new_content = remove_kazakh_section(content)
    new_content_ru = remove_kazakh_section(content_ru) if content_ru else content_ru

    # Ensure Kazakh video is in content_kk
    new_content_kk = ensure_video_in_content_kk(content_kk, content_ru or content, kk_video_url)

    result = {
        'lesson_id': lesson_id,
        'title': title,
        'status': 'success',
        'kazakh_video': kk_video_url,
        'changes': {
            'content': len(content) != len(new_content),
            'content_ru': len(content_ru or '') != len(new_content_ru or ''),
            'content_kk': content_kk != new_content_kk
        }
    }

    if dry_run:
        result['status'] = 'dry_run'
        return result

    # Update database
    try:
        supabase.table('lessons').update({
            'content': new_content,
            'content_ru': new_content_ru,
            'content_kk': new_content_kk
        }).eq('id', lesson_id).execute()

        result['status'] = 'updated'
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(description='Migrate YouTube videos for dual-video lessons')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without updating database')
    args = parser.parse_args()

    print('=== YouTube Video Migration Script ===')
    print(f'Mode: {"DRY RUN" if args.dry_run else "LIVE UPDATE"}')
    print()

    # Connect to Supabase
    try:
        supabase = get_supabase_client()
        print('✓ Connected to Supabase')
    except Exception as e:
        print(f'✗ Failed to connect to Supabase: {e}', file=sys.stderr)
        return 1

    # Fetch all lessons with YouTube URLs
    try:
        response = supabase.table('lessons').select('id, title, content, content_ru, content_kk').execute()
        all_lessons = response.data
        print(f'✓ Fetched {len(all_lessons)} lessons')
    except Exception as e:
        print(f'✗ Failed to fetch lessons: {e}', file=sys.stderr)
        return 1

    # Filter lessons with Kazakh video sections
    lessons_to_migrate = []
    for lesson in all_lessons:
        content = lesson.get('content', '')
        if 'Видео (Қазақша)' in content:
            lessons_to_migrate.append(lesson)

    print(f'✓ Found {len(lessons_to_migrate)} lessons with dual videos')
    print()

    if not lessons_to_migrate:
        print('No lessons to migrate.')
        return 0

    # Migrate each lesson
    results = []
    for lesson in lessons_to_migrate:
        result = migrate_lesson(supabase, lesson, dry_run=args.dry_run)
        results.append(result)

        status_icon = '→' if result['status'] == 'dry_run' else '✓' if result['status'] == 'updated' else '✗'
        print(f"{status_icon} {result['title']} (ID: {result['lesson_id']})")

        if result['status'] == 'error':
            print(f"  Error: {result['error']}")
        elif result['status'] in ('dry_run', 'updated'):
            if 'kazakh_video' in result:
                print(f"  Kazakh video: {result['kazakh_video']}")
            if 'changes' in result:
                changed_fields = [k for k, v in result['changes'].items() if v]
                if changed_fields:
                    print(f"  Changed fields: {', '.join(changed_fields)}")

        print()

    # Summary
    print('=== Migration Summary ===')
    total = len(results)
    updated = sum(1 for r in results if r['status'] == 'updated')
    dry_run_count = sum(1 for r in results if r['status'] == 'dry_run')
    skipped = sum(1 for r in results if r['status'] == 'skipped')
    errors = sum(1 for r in results if r['status'] == 'error')

    print(f'Total lessons: {total}')
    if args.dry_run:
        print(f'Would update: {dry_run_count}')
    else:
        print(f'Updated: {updated}')
    print(f'Skipped: {skipped}')
    print(f'Errors: {errors}')

    if args.dry_run:
        print()
        print('This was a dry run. To apply changes, run without --dry-run flag.')

    return 0 if errors == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
