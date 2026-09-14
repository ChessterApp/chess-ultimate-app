/**
 * Build the two teams' puzzle queues at match start.
 */

import type { TugPuzzle } from './types';

/** Fisher–Yates shuffle returning a new array. */
export function shuffle<T>(items: T[], rng: () => number = Math.random): T[] {
  const out = items.slice();
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/**
 * Split the puzzle pool into two disjoint, shuffled queues — one per team — so
 * the same puzzle never appears on both boards in a match. Odd pools give one
 * side the extra puzzle.
 */
export function splitQueues(
  puzzles: TugPuzzle[],
  rng: () => number = Math.random,
): { queueA: TugPuzzle[]; queueB: TugPuzzle[] } {
  const shuffled = shuffle(puzzles, rng);
  const mid = Math.ceil(shuffled.length / 2);
  return { queueA: shuffled.slice(0, mid), queueB: shuffled.slice(mid) };
}
