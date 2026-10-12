/**
 * Puzzle pack bookkeeping: run seeds / ids and the top-up decision.
 * A pack is a slice of the deterministic sequence `GET /pack` serves per seed.
 *
 * Framework-free (shared with the mobile app).
 */

/** Puzzles per request; also the size of the prefetched first pack. */
export const PACK_SIZE = 40;
/** Top up when fewer than this many puzzles remain after the current one. */
export const TOPUP_THRESHOLD = 15;
/** The server serves (and records) at most this many puzzles per run. */
export const MAX_RUN_PUZZLES = 500;

const hex = (n: number, rand: () => number) =>
  Array.from({ length: n }, () => Math.floor(rand() * 16).toString(16)).join('');

/** 16 hex chars. Not security-sensitive: it only picks the puzzle sequence. */
export function newSeed(rand: () => number = Math.random): string {
  return hex(16, rand);
}

/** Client-generated run id (UUID v4) — `/runs/finish` is idempotent on it. */
export function newRunId(rand: () => number = Math.random): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  if (c?.randomUUID) return c.randomUUID();
  const h = hex(32, rand).split('');
  h[12] = '4';
  h[16] = '89ab'[Math.floor(rand() * 4)];
  const s = h.join('');
  return `${s.slice(0, 8)}-${s.slice(8, 12)}-${s.slice(12, 16)}-${s.slice(16, 20)}-${s.slice(20)}`;
}

/**
 * Index to fetch the next pack from, or null when no top-up is needed yet
 * (or the run is already at the server's cap).
 */
export function topUpFrom(packLength: number, currentIndex: number): number | null {
  if (packLength >= MAX_RUN_PUZZLES) return null;
  return packLength - currentIndex - 1 < TOPUP_THRESHOLD ? packLength : null;
}

/** Silent retry backoff for a failed top-up: 1 s, 2 s, 4 s, then every 8 s. */
export function retryDelay(failures: number): number {
  return Math.min(1000 * 2 ** failures, 8000);
}
