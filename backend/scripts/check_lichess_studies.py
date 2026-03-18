#!/usr/bin/env python3
"""
Check Lichess Study Availability

Checks which Lichess studies are accessible via API and which need
to be downloaded manually.

Usage:
    python check_lichess_studies.py
"""

import json
import requests
from collections import defaultdict


def check_study_access(study_id: str) -> dict:
    """
    Check if a Lichess study is accessible via API.

    Args:
        study_id: Lichess study ID

    Returns:
        Dict with 'accessible' (bool) and 'message' (str)
    """
    url = f"https://lichess.org/api/study/{study_id}.pgn"
    headers = {
        'Accept': 'application/x-chess-pgn',
        'User-Agent': 'ChessUltimateApp/1.0 (Educational)'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)

        # Check if we got PGN content (not HTML)
        content = response.text[:100].lower()

        if 'html' in content or 'DOCTYPE' in content or 'sorry' in content:
            return {
                'accessible': False,
                'message': 'Private study (returns HTML login page)'
            }

        if response.status_code == 204:
            return {
                'accessible': False,
                'message': 'Study is empty or inaccessible (HTTP 204)'
            }

        if response.status_code == 200 and '[Event' in response.text[:200]:
            return {
                'accessible': True,
                'message': 'Study is accessible ✓'
            }

        return {
            'accessible': False,
            'message': f'HTTP {response.status_code}: {response.reason}'
        }

    except Exception as e:
        return {
            'accessible': False,
            'message': f'Error: {str(e)}'
        }


def main():
    print("=" * 60)
    print("Lichess Study Accessibility Check")
    print("=" * 60)
    print()

    # Load lesson data
    json_path = '/tmp/level2_lessons.json'
    with open(json_path) as f:
        lessons_data = json.load(f)

    # Group lessons by study ID
    studies = defaultdict(list)
    for lesson in lessons_data:
        url = lesson.get('lichess_embed_url')
        if url and 'study' in url:
            parts = url.split('/')
            if 'study' in parts:
                study_idx = parts.index('study')
                if len(parts) > study_idx + 1:
                    study_id = parts[study_idx + 1]
                    studies[study_id].append(lesson['title'])

    print(f"Found {len(studies)} unique studies")
    print()

    # Check each study
    results = {}
    for study_id in sorted(studies.keys()):
        lessons = studies[study_id]
        print(f"Checking {study_id} ({len(lessons)} lessons)...")

        result = check_study_access(study_id)
        results[study_id] = result

        status = "✓" if result['accessible'] else "✗"
        print(f"  {status} {result['message']}")
        print()

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    accessible = [sid for sid, r in results.items() if r['accessible']]
    private = [sid for sid, r in results.items() if not r['accessible']]

    print(f"Accessible studies: {len(accessible)}")
    if accessible:
        for sid in accessible:
            print(f"  ✓ {sid} ({len(studies[sid])} lessons)")

    print()
    print(f"Private/inaccessible studies: {len(private)}")
    if private:
        for sid in private:
            print(f"  ✗ {sid} ({len(studies[sid])} lessons)")

    print()

    if private:
        print("=" * 60)
        print("Action Required")
        print("=" * 60)
        print()
        print("The following studies need to be made public or downloaded manually:")
        print()
        for sid in private:
            print(f"  Study: {sid}")
            print(f"  URL:   https://lichess.org/study/{sid}")
            print(f"  Lessons: {len(studies[sid])}")
            print()

        print("To make a study public:")
        print("  1. Log in to Lichess as the study owner")
        print("  2. Open the study URL")
        print("  3. Click 'Share' → Set visibility to 'Public'")
        print()
        print("Or download manually:")
        print("  1. Open each study URL while logged in")
        print("  2. Click '...' menu → 'Study PGN'")
        print(f"  3. Save as backend/data/lichess_studies/{{study_id}}.pgn")
        print()
    else:
        print("✓ All studies are accessible! You can run the automated import script.")
        print()
        print("Run:")
        print("  python3 scripts/import_level2_puzzles.py")

    print("=" * 60)


if __name__ == '__main__':
    main()
