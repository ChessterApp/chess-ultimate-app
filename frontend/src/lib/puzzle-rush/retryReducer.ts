/**
 * Puzzle Rush review — Retry mode (pure). After a run, any puzzle can be
 * replayed on the main board with unlimited attempts: wrong moves are rejected
 * (the position stays put so the UI can snap the piece back), correct moves
 * auto-play the opponent's reply, Hint escalates square → arrow, and Solution
 * hands over to the read-only line stepper. Nothing here touches the run's
 * score or submitted result.
 *
 * Framework-free (shared with the mobile app): chess.js only.
 */

import { applyUci, judgeMove } from './validate';
import type { ResultTile, ReviewAttempt } from './runReducer';
import type { Square } from './types';

export type RetryStatus = 'playing' | 'wrong' | 'solved' | 'revealed';
export type HintLevel = 0 | 1 | 2;

export interface RetryState {
  index: number;
  /** Full solution line; moves[0] is the opponent's setup move. */
  moves: string[];
  /** Position after the setup move (what Retry resets to). */
  startFen: string;
  startLastMove: [Square, Square] | null;
  fen: string;
  /** Index into `moves` of the user's next expected move. */
  ply: number;
  lastMove: [Square, Square] | null;
  status: RetryStatus;
  hintLevel: HintLevel;
  usedHint: boolean;
  usedSolution: boolean;
  /** The rejected move, for the ✕ badge (shown on `fen` after it until cleared). */
  lastWrong: { square: Square; uci: string; fen: string; from: Square } | null;
}

export type RetryAction =
  | { type: 'start'; attempt: ReviewAttempt }
  | { type: 'move'; uci: string }
  | { type: 'clearWrong' }
  | { type: 'hint' }
  | { type: 'retry' }
  | { type: 'showSolution' };

export type RetryOutcome = 'solved' | 'solved_with_help' | 'unsolved';
export type RetryOutcomes = Record<number, RetryOutcome>;

export function startRetry(attempt: ReviewAttempt): RetryState {
  const setup = attempt.solution[0] ? applyUci(attempt.fen, attempt.solution[0]) : null;
  const fen = setup?.fen ?? attempt.fen;
  const lastMove: [Square, Square] | null = setup ? [setup.from, setup.to] : null;
  return {
    index: attempt.index,
    moves: attempt.solution,
    startFen: fen,
    startLastMove: lastMove,
    fen,
    ply: 1,
    lastMove,
    status: 'playing',
    hintLevel: 0,
    usedHint: false,
    usedSolution: false,
    lastWrong: null,
  };
}

export function retryReducer(state: RetryState | null, action: RetryAction): RetryState | null {
  if (action.type === 'start') return startRetry(action.attempt);
  if (!state) return state;

  switch (action.type) {
    case 'move': {
      if (state.status !== 'playing') return state;
      const v = judgeMove(state.fen, state.moves, state.ply, action.uci);
      if (v.kind === 'illegal') return state;
      if (v.kind === 'wrong') {
        return { ...state, status: 'wrong', lastWrong: { square: v.to, uci: v.uci, fen: v.fen, from: v.from } };
      }
      if (v.kind === 'solved') {
        return { ...state, fen: v.fen, lastMove: [v.from, v.to], ply: state.ply + 1, status: 'solved', hintLevel: 0 };
      }
      const reply = v.reply ? applyUci(v.fen, v.reply) : null;
      return {
        ...state,
        fen: reply?.fen ?? v.fen,
        lastMove: reply ? [reply.from, reply.to] : [v.from, v.to],
        ply: state.ply + 2,
        hintLevel: 0,
      };
    }
    case 'clearWrong':
      return state.status === 'wrong' ? { ...state, status: 'playing', lastWrong: null } : state;
    case 'hint':
      if (state.status !== 'playing' || state.hintLevel === 2) return state;
      return { ...state, hintLevel: (state.hintLevel + 1) as HintLevel, usedHint: true };
    case 'retry':
      return {
        ...state,
        fen: state.startFen,
        lastMove: state.startLastMove,
        ply: 1,
        status: 'playing',
        hintLevel: 0,
        lastWrong: null,
      };
    case 'showSolution':
      if (state.status === 'solved' || state.status === 'revealed') return state;
      return { ...state, status: 'revealed', usedSolution: true, hintLevel: 0, lastWrong: null };
    default:
      return state;
  }
}

/** Hint shapes for the board: level 1 circles the piece, level 2 draws the move. */
export function retryHint(state: RetryState | null): { square: Square | null; move: [Square, Square] | null } {
  const expected = state && state.status === 'playing' ? state.moves[state.ply] : undefined;
  if (!expected || state!.hintLevel === 0) return { square: null, move: null };
  const from = expected.slice(0, 2) as Square;
  if (state!.hintLevel === 1) return { square: from, move: null };
  return { square: null, move: [from, expected.slice(2, 4) as Square] };
}

const RANK: Record<RetryOutcome, number> = { unsolved: 0, solved_with_help: 1, solved: 2 };

/** Fold the puzzle's current state into the run's outcome map, keeping the best result. */
export function recordOutcome(outcomes: RetryOutcomes, state: RetryState | null): RetryOutcomes {
  if (!state || (state.status !== 'solved' && state.status !== 'revealed')) return outcomes;
  const next: RetryOutcome = state.status === 'revealed'
    ? 'unsolved'
    : state.usedHint || state.usedSolution ? 'solved_with_help' : 'solved';
  const cur = outcomes[state.index];
  if (cur && RANK[cur] >= RANK[next]) return outcomes;
  return { ...outcomes, [state.index]: next };
}

export function isRetrySolved(outcome: RetryOutcome | undefined): boolean {
  return outcome === 'solved' || outcome === 'solved_with_help';
}

/**
 * The next missed puzzle after `current` (in run order, wrapping around to
 * `current` itself last) not yet solved in retry, or null when none is left.
 */
export function nextMistakeIndex(tiles: ResultTile[], outcomes: RetryOutcomes, current: number | null): number | null {
  const open = tiles.filter((t) => !t.solved && !isRetrySolved(outcomes[t.index])).map((t) => t.index);
  if (!open.length) return null;
  if (current === null) return open[0];
  return open.find((i) => i > current) ?? open[0];
}
