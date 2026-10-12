/**
 * Puzzle Rush run state machine (pure). The hook (`usePuzzleRush`) owns the
 * timers and API calls and feeds results in here; everything the screen shows
 * during a run is derived from this state.
 *
 * Per-puzzle pipeline (§2 S7, §3): ADVANCE (board covered, new position mounted)
 * → PUZZLE_REVEALED (pieces fade in) → SETUP_PLAYED (opponent's setup move
 * animates, input unlocks) → USER_MOVED → MOVE_RESULT → [REPLY_PLAYED…] → ADVANCE.
 */

import { Chess } from 'chess.js';
import type { Key } from 'chessground/types';
import type {
  CreateRunResponse,
  EndReason,
  MoveResponse,
  RunState,
  RushMode,
  RushPuzzle,
  RushResults,
} from './types';

export const MAX_STRIKES = 3;

export type Phase = 'idle' | 'starting' | 'countdown' | 'playing' | 'over';
export type CoachCue = 'streak5' | 'streak10' | 'lastHeart';

export interface ResultTile {
  index: number;
  rating: number;
  solved: boolean;
}

export interface RunUiState {
  phase: Phase;
  mode: RushMode;
  runId: string | null;
  puzzle: RushPuzzle | null;
  /** Puzzle queued behind the current feedback badge. */
  pending: RushPuzzle | null;
  /** Opponent reply waiting to be played after a correct (non-final) move. */
  pendingReply: string | null;
  fen: string;
  lastMove: [Key, Key] | null;
  orientation: 'white' | 'black';
  /** Bumped per puzzle so the board remounts instead of sliding pieces across. */
  boardKey: number;
  /** Board-clear cover is up (pieces hidden). */
  covered: boolean;
  inputLocked: boolean;
  badge: { square: Key; kind: 'ok' | 'fail' } | null;
  score: number;
  strikes: number;
  streak: number;
  tiles: ResultTile[];
  /** Client-clock ms when the server clock starts / runs out. */
  startedAtMs: number | null;
  deadlineMs: number | null;
  results: RushResults | null;
  endReason: EndReason | null;
  coach: { cue: CoachCue; seq: number } | null;
  error: string | null;
}

export type RunAction =
  | { type: 'START_REQUESTED'; mode: RushMode }
  | { type: 'START_FAILED'; error: string }
  | { type: 'RUN_CREATED'; response: CreateRunResponse; clientNow: number }
  | { type: 'PUZZLE_REVEALED' }
  | { type: 'SETUP_PLAYED' }
  | { type: 'USER_MOVED'; uci: string }
  | { type: 'MOVE_REJECTED'; fen: string; lastMove: [Key, Key] | null }
  | { type: 'MOVE_RESULT'; response: MoveResponse; clientNow: number }
  | { type: 'REPLY_PLAYED' }
  | { type: 'ADVANCE' }
  | { type: 'RUN_OVER'; state: Partial<RunState>; results: RushResults | null; clientNow: number }
  | { type: 'COACH_DISMISS'; seq: number }
  | { type: 'RESET' };

export const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

export function initialRunState(mode: RushMode): RunUiState {
  return {
    phase: 'idle',
    mode,
    runId: null,
    puzzle: null,
    pending: null,
    pendingReply: null,
    fen: STARTING_FEN,
    lastMove: null,
    orientation: 'white',
    boardKey: 0,
    covered: false,
    inputLocked: true,
    badge: null,
    score: 0,
    strikes: 0,
    streak: 0,
    tiles: [],
    startedAtMs: null,
    deadlineMs: null,
    results: null,
    endReason: null,
    coach: null,
    error: null,
  };
}

/** Apply a UCI move to a FEN; null if the move is not legal there. */
export function applyUci(fen: string, uci: string): { fen: string; from: Key; to: Key } | null {
  try {
    const chess = new Chess(fen);
    const from = uci.slice(0, 2);
    const to = uci.slice(2, 4);
    chess.move({ from, to, promotion: uci[4] || undefined });
    return { fen: chess.fen(), from: from as Key, to: to as Key };
  } catch {
    return null;
  }
}

/** Server timestamp → client-clock ms, correcting for clock skew. */
function toClientMs(iso: string | null | undefined, skewMs: number): number | null {
  return iso ? Date.parse(iso) - skewMs : null;
}

function skewOf(serverNow: string | undefined, clientNow: number): number {
  return serverNow ? Date.parse(serverNow) - clientNow : 0;
}

function syncClock(state: RunUiState, s: Partial<RunState>, clientNow: number) {
  const skew = skewOf(s.server_now, clientNow);
  return {
    startedAtMs: toClientMs(s.started_at, skew) ?? state.startedAtMs,
    deadlineMs: s.deadline === undefined ? state.deadlineMs : toClientMs(s.deadline, skew),
  };
}

function mountPuzzle(state: RunUiState, puzzle: RushPuzzle): RunUiState {
  return {
    ...state,
    puzzle,
    pending: null,
    pendingReply: null,
    fen: puzzle.fen,
    lastMove: null,
    orientation: puzzle.color,
    boardKey: state.boardKey + 1,
    covered: true,
    inputLocked: true,
    badge: null,
  };
}

function overState(state: RunUiState, s: Partial<RunState>, results: RushResults | null, clientNow: number): RunUiState {
  return {
    ...state,
    ...syncClock(state, s, clientNow),
    phase: 'over',
    pending: null,
    pendingReply: null,
    inputLocked: true,
    covered: false,
    score: s.score ?? state.score,
    strikes: s.strikes ?? state.strikes,
    streak: s.streak ?? state.streak,
    results: results ?? state.results,
    endReason: s.end_reason ?? state.endReason,
  };
}

function coachFor(prev: RunUiState, r: MoveResponse): CoachCue | null {
  if (r.run_over) return null;
  if (r.result === 'solved' && r.streak !== prev.streak) {
    if (r.streak === 5) return 'streak5';
    if (r.streak === 10) return 'streak10';
  }
  if (r.result === 'wrong' && r.strikes === MAX_STRIKES - 1) return 'lastHeart';
  return null;
}

export function runReducer(state: RunUiState, action: RunAction): RunUiState {
  switch (action.type) {
    case 'START_REQUESTED':
      return { ...initialRunState(action.mode), phase: 'starting', boardKey: state.boardKey + 1, covered: true, fen: STARTING_FEN };

    case 'START_FAILED':
      return { ...initialRunState(state.mode), boardKey: state.boardKey + 1, error: action.error };

    case 'RUN_CREATED': {
      const r = action.response;
      const next = mountPuzzle({ ...state, runId: r.run_id, mode: r.mode, phase: 'countdown' }, r.puzzle);
      return { ...next, ...syncClock(next, r, action.clientNow) };
    }

    case 'PUZZLE_REVEALED':
      return { ...state, covered: false };

    case 'SETUP_PLAYED': {
      if (!state.puzzle) return state;
      const moved = applyUci(state.puzzle.fen, state.puzzle.setup_move);
      if (!moved) return state;
      return {
        ...state,
        phase: state.phase === 'over' ? 'over' : 'playing',
        covered: false,
        fen: moved.fen,
        lastMove: [moved.from, moved.to],
        inputLocked: state.phase === 'over',
      };
    }

    case 'USER_MOVED': {
      const moved = applyUci(state.fen, action.uci);
      if (!moved || state.inputLocked) return state;
      return { ...state, fen: moved.fen, lastMove: [moved.from, moved.to], inputLocked: true };
    }

    case 'MOVE_REJECTED':
      return { ...state, fen: action.fen, lastMove: action.lastMove, inputLocked: state.phase !== 'playing' };

    case 'MOVE_RESULT': {
      const r = action.response;
      const dest = state.lastMove?.[1] ?? null;
      const base: RunUiState = {
        ...state,
        ...syncClock(state, r, action.clientNow),
        score: r.score,
        strikes: r.strikes,
        streak: r.streak,
        badge: dest ? { square: dest, kind: r.result === 'wrong' ? 'fail' : 'ok' } : null,
      };
      const cue = coachFor(state, r);
      if (cue) base.coach = { cue, seq: (state.coach?.seq ?? 0) + 1 };

      if (r.result === 'correct') {
        return { ...base, pendingReply: r.reply ?? null };
      }
      const puzzle = state.puzzle;
      const tiles = puzzle
        ? [...state.tiles, { index: puzzle.index, rating: puzzle.rating, solved: r.result === 'solved' }]
        : state.tiles;
      const withTile = { ...base, tiles };
      if (r.run_over) return overState(withTile, r, r.results ?? null, action.clientNow);
      return { ...withTile, pending: r.next_puzzle ?? null };
    }

    case 'REPLY_PLAYED': {
      if (!state.pendingReply) return state;
      const moved = applyUci(state.fen, state.pendingReply);
      if (!moved) return { ...state, pendingReply: null };
      return {
        ...state,
        fen: moved.fen,
        lastMove: [moved.from, moved.to],
        pendingReply: null,
        badge: null,
        inputLocked: state.phase !== 'playing',
      };
    }

    case 'ADVANCE':
      if (!state.pending || state.phase === 'over') return state;
      return mountPuzzle(state, state.pending);

    case 'RUN_OVER':
      if (state.phase === 'over' && state.results) return state;
      return overState(state, action.state, action.results, action.clientNow);

    case 'COACH_DISMISS':
      return state.coach?.seq === action.seq ? { ...state, coach: null } : state;

    case 'RESET':
      return { ...initialRunState(state.mode), boardKey: state.boardKey + 1 };
  }
}
