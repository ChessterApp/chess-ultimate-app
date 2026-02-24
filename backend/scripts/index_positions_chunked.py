#!/usr/bin/env python3
"""
Chunked Position Indexer Orchestrator
Manages indexing of 4.35M games in manageable chunks to prevent interruptions.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Configuration
CHUNK_SIZE = 100_000  # Games per chunk
NICE_LEVEL = 5  # Process priority (0-19, higher = lower priority)
PROGRESS_FILE = Path(__file__).parent.parent / 'data' / 'twic' / 'position_index_progress.json'
DB_PATH = Path(__file__).parent.parent / 'data' / 'twic' / 'games_index.db'
INDEXER_SCRIPT = Path(__file__).parent / 'add_position_index.py'

class ChunkOrchestrator:
    def __init__(self, chunk_size: int = CHUNK_SIZE, nice_level: int = NICE_LEVEL):
        self.chunk_size = chunk_size
        self.nice_level = nice_level
        self.progress_file = PROGRESS_FILE
        self.db_path = DB_PATH
        self.indexer_script = INDEXER_SCRIPT

    def load_progress(self) -> Dict:
        """Load progress from JSON file or create new."""
        if self.progress_file.exists():
            with open(self.progress_file, 'r') as f:
                return json.load(f)
        return {
            "total_games": 0,
            "chunk_size": self.chunk_size,
            "total_chunks": 0,
            "completed_chunks": [],
            "failed_chunks": [],
            "last_updated": None
        }

    def save_progress(self, progress: Dict):
        """Save progress to JSON file."""
        progress["last_updated"] = datetime.utcnow().isoformat() + 'Z'
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.progress_file, 'w') as f:
            json.dump(progress, f, indent=2)

    def get_total_games(self) -> int:
        """Query database for total game count."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM games")
        total = cursor.fetchone()[0]
        conn.close()
        return total

    def calculate_chunks(self, total_games: int) -> List[tuple]:
        """Calculate chunk boundaries."""
        chunks = []
        chunk_id = 1
        for start_id in range(1, total_games + 1, self.chunk_size):
            end_id = min(start_id + self.chunk_size - 1, total_games)
            chunks.append((chunk_id, start_id, end_id))
            chunk_id += 1
        return chunks

    def is_chunk_completed(self, chunk_id: int, progress: Dict) -> bool:
        """Check if chunk is already completed."""
        return any(c['chunk_id'] == chunk_id for c in progress['completed_chunks'])

    def run_chunk(self, chunk_id: int, start_id: int, end_id: int) -> bool:
        """Run indexer for a single chunk. Returns True on success."""
        print(f"\n{'='*70}")
        print(f"Processing Chunk {chunk_id}: Games {start_id:,} to {end_id:,}")
        print(f"{'='*70}")

        cmd = [
            'python3', '-u', str(self.indexer_script),
            '--start-game-id', str(start_id),
            '--end-game-id', str(end_id),
            '--nice-level', str(self.nice_level)
        ]

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=True
            )

            duration = time.time() - start_time

            # Parse output for positions added (if available)
            positions_added = None
            for line in result.stdout.split('\n'):
                if 'positions stored' in line.lower():
                    import re
                    match = re.search(r'(\d+[\d,]*)\s+positions', line)
                    if match:
                        positions_added = int(match.group(1).replace(',', ''))

            print(f"\n✓ Chunk {chunk_id} completed in {duration:.1f}s")
            if positions_added:
                print(f"  Positions added: {positions_added:,}")

            return True

        except subprocess.CalledProcessError as e:
            print(f"\n✗ Chunk {chunk_id} FAILED")
            print(f"  Error: {e}")
            return False
        except KeyboardInterrupt:
            print(f"\n⚠ Chunk {chunk_id} interrupted by user")
            raise

    def run_all_chunks(self, start_from_chunk: Optional[int] = None):
        """Run all pending chunks."""
        progress = self.load_progress()
        total_games = self.get_total_games()
        print(f"Total games in database: {total_games:,}")

        if progress['total_games'] != total_games:
            progress['total_games'] = total_games
            progress['chunk_size'] = self.chunk_size

        all_chunks = self.calculate_chunks(total_games)
        progress['total_chunks'] = len(all_chunks)

        pending_chunks = [
            (cid, sid, eid) for cid, sid, eid in all_chunks
            if not self.is_chunk_completed(cid, progress)
            and (start_from_chunk is None or cid >= start_from_chunk)
        ]

        if not pending_chunks:
            print("\n✓ All chunks already completed!")
            self.print_status(progress)
            return

        print(f"\nPending chunks: {len(pending_chunks)} / {len(all_chunks)}")
        print(f"Completed chunks: {len(progress['completed_chunks'])}")
        print(f"Chunk size: {self.chunk_size:,} games")
        print(f"Nice level: {self.nice_level} (lower CPU priority)")

        for chunk_id, start_id, end_id in pending_chunks:
            try:
                success = self.run_chunk(chunk_id, start_id, end_id)

                if success:
                    progress['completed_chunks'].append({
                        "chunk_id": chunk_id,
                        "start_id": start_id,
                        "end_id": end_id,
                        "completed_at": datetime.utcnow().isoformat() + 'Z',
                        "positions_added": None,
                        "duration_seconds": None
                    })
                    self.save_progress(progress)
                else:
                    progress['failed_chunks'].append({
                        "chunk_id": chunk_id,
                        "start_id": start_id,
                        "end_id": end_id,
                        "failed_at": datetime.utcnow().isoformat() + 'Z'
                    })
                    self.save_progress(progress)
                    print(f"\n⚠ Chunk {chunk_id} failed. Continuing to next chunk...")

                self.print_status(progress)

            except KeyboardInterrupt:
                print("\n\n⚠ Interrupted by user. Progress saved.")
                self.save_progress(progress)
                sys.exit(0)

        print("\n" + "="*70)
        print("INDEXING COMPLETE!")
        print("="*70)
        self.print_status(progress)

    def print_status(self, progress: Dict):
        """Print current status."""
        total = progress['total_chunks']
        completed = len(progress['completed_chunks'])
        failed = len(progress['failed_chunks'])
        pending = total - completed - failed

        if total > 0:
            pct_complete = (completed / total) * 100
        else:
            pct_complete = 0

        print(f"\n--- Status ---")
        print(f"Completed: {completed}/{total} chunks ({pct_complete:.1f}%)")
        print(f"Pending:   {pending} chunks")
        if failed > 0:
            print(f"Failed:    {failed} chunks (will need retry)")

        if completed > 0:
            total_games_indexed = completed * self.chunk_size
            total_games = progress['total_games']
            game_pct = (total_games_indexed / total_games) * 100 if total_games > 0 else 0
            print(f"Games indexed: ~{total_games_indexed:,} / {total_games:,} ({game_pct:.1f}%)")

    def retry_failed_chunks(self):
        """Retry all failed chunks."""
        progress = self.load_progress()

        if not progress['failed_chunks']:
            print("No failed chunks to retry.")
            return

        print(f"\nRetrying {len(progress['failed_chunks'])} failed chunks...")

        failed_chunks = progress['failed_chunks'].copy()
        progress['failed_chunks'] = []
        self.save_progress(progress)

        for failed in failed_chunks:
            chunk_id = failed['chunk_id']
            start_id = failed['start_id']
            end_id = failed['end_id']

            success = self.run_chunk(chunk_id, start_id, end_id)

            if success:
                progress['completed_chunks'].append({
                    "chunk_id": chunk_id,
                    "start_id": start_id,
                    "end_id": end_id,
                    "completed_at": datetime.utcnow().isoformat() + 'Z',
                    "positions_added": None,
                    "duration_seconds": None
                })
            else:
                progress['failed_chunks'].append(failed)

            self.save_progress(progress)

        self.print_status(progress)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Chunked Position Indexer Orchestrator')
    parser.add_argument('--chunk-size', type=int, default=CHUNK_SIZE,
                        help=f'Games per chunk (default: {CHUNK_SIZE:,})')
    parser.add_argument('--nice-level', type=int, default=NICE_LEVEL,
                        help=f'Process nice level 0-19 (default: {NICE_LEVEL})')
    parser.add_argument('--start-from-chunk', type=int, default=None,
                        help='Start from specific chunk ID')
    parser.add_argument('--retry-failed', action='store_true',
                        help='Retry failed chunks only')
    parser.add_argument('--status', action='store_true',
                        help='Show status and exit')

    args = parser.parse_args()

    orchestrator = ChunkOrchestrator(
        chunk_size=args.chunk_size,
        nice_level=args.nice_level
    )

    if args.status:
        progress = orchestrator.load_progress()
        orchestrator.print_status(progress)
        return

    if args.retry_failed:
        orchestrator.retry_failed_chunks()
        return

    orchestrator.run_all_chunks(start_from_chunk=args.start_from_chunk)

if __name__ == '__main__':
    main()
