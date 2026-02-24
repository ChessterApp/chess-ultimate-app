#!/usr/bin/env python3
"""
Download and integrate new TWIC issues into the master database.

Usage:
    python scripts/download_twic_updates.py [start_issue] [end_issue]

Example:
    python scripts/download_twic_updates.py 1619 1623
"""

import os
import sys
import requests
import zipfile
import io
import time
from datetime import datetime

# Configuration
TWIC_BASE_URL = "https://theweekinchess.com/zips/twic"
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BACKEND_DIR, "data/twic")
MASTER_PGN = os.path.join(DATA_DIR, "twic_master_database.pgn")
DOWNLOADS_DIR = os.path.join(DATA_DIR, "downloads")

# HTTP Headers to avoid 406 errors
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/zip, application/octet-stream, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}


def download_twic_issue(issue_number: int) -> str | None:
    """Download a single TWIC issue and return the PGN content."""
    url = f"{TWIC_BASE_URL}{issue_number}g.zip"
    print(f"  Downloading TWIC {issue_number} from {url}...")

    try:
        response = requests.get(url, headers=HEADERS, timeout=60)
        if response.status_code == 200:
            # Extract PGN from ZIP
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                for name in zf.namelist():
                    if name.endswith('.pgn'):
                        pgn_content = zf.read(name).decode('latin-1')
                        print(f"    ✓ Downloaded {len(pgn_content):,} bytes")
                        return pgn_content
            print(f"    ✗ No PGN file found in ZIP")
            return None
        else:
            print(f"    ✗ HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return None


def count_games_in_pgn(pgn_content: str) -> int:
    """Count the number of games in a PGN string."""
    return pgn_content.count('[Event "')


def append_to_master(pgn_content: str, issue_number: int):
    """Append PGN content to the master database."""
    # Add a separator comment
    separator = f"\n\n{{ TWIC Issue {issue_number} - Added {datetime.now().isoformat()} }}\n\n"

    with open(MASTER_PGN, 'a', encoding='utf-8') as f:
        f.write(separator)
        f.write(pgn_content)

    print(f"    ✓ Appended to master database")


def get_master_stats():
    """Get current stats of the master PGN file."""
    if not os.path.exists(MASTER_PGN):
        return 0, 0

    size = os.path.getsize(MASTER_PGN)

    # Get game count from SQLite DB (fast) instead of scanning the 4GB PGN
    db_path = os.path.join(DATA_DIR, "games_index.db")
    game_count = 0
    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            game_count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
            conn.close()
        except Exception:
            game_count = 0  # DB might not have games table yet

    return size, game_count


def main():
    # Parse arguments
    if len(sys.argv) >= 3:
        start_issue = int(sys.argv[1])
        end_issue = int(sys.argv[2])
    else:
        # Default: download issues 1619-1623
        start_issue = 1619
        end_issue = 1623

    print("=" * 60)
    print("TWIC Database Update Script")
    print("=" * 60)
    print(f"Issues to download: {start_issue} - {end_issue}")
    print(f"Master PGN: {MASTER_PGN}")
    print()

    # Get initial stats
    initial_size, initial_games = get_master_stats()
    print(f"Current database: {initial_size / (1024**3):.2f} GB, ~{initial_games:,} games")
    print()

    # Create downloads directory
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)

    # Download and append each issue
    total_new_games = 0
    successful_issues = []

    for issue in range(start_issue, end_issue + 1):
        print(f"\n[{issue}] Processing TWIC {issue}...")

        pgn_content = download_twic_issue(issue)

        if pgn_content:
            game_count = count_games_in_pgn(pgn_content)
            total_new_games += game_count
            print(f"    Games in issue: {game_count:,}")

            # Save individual PGN file for backup
            backup_path = os.path.join(DOWNLOADS_DIR, f"twic{issue}.pgn")
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(pgn_content)
            print(f"    ✓ Saved backup to {backup_path}")

            # Append to master
            append_to_master(pgn_content, issue)
            successful_issues.append(issue)
        else:
            print(f"    ✗ Skipping issue {issue}")

        # Rate limiting
        time.sleep(1)

    # Final stats
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    final_size, final_games = get_master_stats()

    print(f"Successfully downloaded: {len(successful_issues)} issues")
    print(f"Issues: {successful_issues}")
    print(f"New games added: ~{total_new_games:,}")
    print(f"Database size: {initial_size / (1024**3):.2f} GB → {final_size / (1024**3):.2f} GB")
    print(f"Total games: ~{initial_games:,} → ~{final_games:,}")
    print()
    print("Next step: Run INCREMENTAL indexing to add new games to SQLite:")
    print("  cd /root/chess-app/backend && python3 scripts/index_pgn_database.py")
    print()
    print("WARNING: index_pgn_database.py will REFUSE to run if >4M games exist (safety check).")
    print("         If the DB already has games, only NEW games from appended PGN will be added.")
    print("         NEVER use --fresh flag — it DESTROYS the entire database including position index.")
    print("         NEVER run add_position_index.py --fresh either.")

    return len(successful_issues) > 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
