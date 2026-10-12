"""
Micro-benchmark for Puzzle Rush puzzle selection against the real puzzles DB.

Simulates full runs (picks for ramp index 0..N-1, excluding ids already used in
the run) and reports per-pick latency percentiles. Read-only.

Usage (from backend/):
    venv/bin/python scripts/bench_puzzle_rush_pick.py [--runs 50] [--length 60]
"""

import argparse
import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.puzzle_rush_source import PuzzleSource  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=None, help='puzzles.db path (default: PUZZLE_RUSH_DB_PATH or hermes DB)')
    parser.add_argument('--runs', type=int, default=50)
    parser.add_argument('--length', type=int, default=60, help='puzzles per simulated run')
    args = parser.parse_args()

    source = PuzzleSource(args.db)
    rng = random.Random(42)

    t0 = time.perf_counter()
    source.pick(0, rng=rng)  # warm-up: connection + max(rowid)
    print(f'first pick (cold, incl. connect): {(time.perf_counter() - t0) * 1000:.2f} ms')

    timings = []
    for _ in range(args.runs):
        used = []
        for i in range(args.length):
            t = time.perf_counter()
            puzzle = source.pick(i, exclude_ids=used, rng=rng)
            timings.append((time.perf_counter() - t) * 1000)
            used.append(puzzle['id'])

    timings.sort()
    pct = lambda p: timings[min(len(timings) - 1, int(p * len(timings)))]  # noqa: E731
    print(f'db: {source.db_path}')
    print(f'picks: {len(timings)} ({args.runs} runs x {args.length})')
    print(f'mean {statistics.mean(timings):.3f} ms | p50 {pct(0.5):.3f} | p95 {pct(0.95):.3f} '
          f'| p99 {pct(0.99):.3f} | max {timings[-1]:.3f}')


if __name__ == '__main__':
    main()
