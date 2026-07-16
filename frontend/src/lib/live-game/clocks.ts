/**
 * Pure clock math for online play. No I/O, no chess.js — unit-testable in
 * isolation. All banks are milliseconds; timestamps are epoch-ms numbers.
 *
 * Server-authoritative model: a mover's bank is only debited when they actually
 * move (`computeClocksAfterMove`), while `remainingMs` projects the current
 * live banks for hydration/display without mutating anything.
 *
 * Untimed games carry `null` banks and short-circuit everywhere: no deduction,
 * never flagged.
 */

import type { Turn, Clocks } from './types';

export interface ComputeClocksInput {
  /** White bank before the move (ms), or null for an untimed game. */
  whiteMs: number | null;
  /** Black bank before the move (ms), or null for an untimed game. */
  blackMs: number | null;
  /** Epoch-ms of the previous move (game clock start). null → no elapsed time. */
  lastMoveAt: number | null;
  /** Epoch-ms "now" (server time the move landed). */
  now: number;
  /** Side that is moving. */
  turn: Turn;
  /** Increment in seconds added after the move, or null/0 for none. */
  incrementSec: number | null;
}

export interface ComputeClocksResult {
  whiteMs: number | null;
  blackMs: number | null;
  /** True when the mover's bank ran out (bank − elapsed ≤ 0). */
  flagged: boolean;
}

/**
 * New clock banks after the mover's elapsed time is deducted and (if they did
 * not flag) their increment is applied.
 *
 * When flagged, the mover's bank is pinned to 0 and no increment is granted —
 * the caller (move route) treats this as a loss on time and does NOT apply the
 * move.
 */
export function computeClocksAfterMove(
  input: ComputeClocksInput,
): ComputeClocksResult {
  const { whiteMs, blackMs, lastMoveAt, now, turn, incrementSec } = input;

  // Untimed game: banks stay null, never flagged.
  if (whiteMs === null || blackMs === null) {
    return { whiteMs, blackMs, flagged: false };
  }

  const elapsed = lastMoveAt === null ? 0 : Math.max(0, now - lastMoveAt);
  const incMs = (incrementSec ?? 0) * 1000;

  const moverBank = turn === 'w' ? whiteMs : blackMs;
  const remaining = moverBank - elapsed;

  if (remaining <= 0) {
    // Flag: pin to 0, no increment. Move is rejected by the caller.
    return {
      whiteMs: turn === 'w' ? 0 : whiteMs,
      blackMs: turn === 'b' ? 0 : blackMs,
      flagged: true,
    };
  }

  const newBank = remaining + incMs;
  return {
    whiteMs: turn === 'w' ? newBank : whiteMs,
    blackMs: turn === 'b' ? newBank : blackMs,
    flagged: false,
  };
}

export interface RemainingMsInput {
  whiteMs: number | null;
  blackMs: number | null;
  lastMoveAt: number | null;
  /** Side to move (whose bank is currently ticking down). */
  turn: Turn;
  /** Clocks only tick while the game is 'active'. */
  status: string;
}

/**
 * Project the live clock banks at time `now` for a hydration payload. Only the
 * side to move is debited (by `now − lastMoveAt`); the idle side is unchanged.
 * Untimed or non-active games return the stored banks verbatim.
 */
export function remainingMs(game: RemainingMsInput, now: number): Clocks {
  const { whiteMs, blackMs, lastMoveAt, turn, status } = game;

  if (whiteMs === null || blackMs === null || status !== 'active') {
    return { whiteMs, blackMs };
  }

  const elapsed = lastMoveAt === null ? 0 : Math.max(0, now - lastMoveAt);
  const moverBank = turn === 'w' ? whiteMs : blackMs;
  const debited = Math.max(0, moverBank - elapsed);

  return {
    whiteMs: turn === 'w' ? debited : whiteMs,
    blackMs: turn === 'b' ? debited : blackMs,
  };
}
