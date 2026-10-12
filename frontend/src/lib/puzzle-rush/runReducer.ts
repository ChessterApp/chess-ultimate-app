/**
 * Puzzle Rush run engine (pure). The whole run is local: clock, move
 * validation, score / strikes / streaks, the ✓/✕ grid and the puzzle index all
 * live here, and a move's verdict lands in the same state update as the move
 * itself. The hook (`usePuzzleRush`) only owns timers, sounds and network
 * (pack prefetch / top-up, the background `/runs/finish`).
 *
 * Clock: callers pass a monotonic `now` (performance.now() on web). The clock
 * starts at GO (end of the 3-2-1 countdown); timed modes end at
 * `deadlineMs = startedAtMs + mode seconds`.
 *
 * Per-puzzle pipeline (§2 S7, §3): ADVANCE (board covered, next position
 * mounted) → PUZZLE_REVEALED (pieces fade in) → SETUP_PLAYED (opponent setup
 * move, input unlocks) → USER_MOVED (verdict + badge) → [REPLY_PLAYED …] → ADVANCE.
 *
 * Framework-free (shared with the mobile app): chess.js only.
 */

import { applyUci, judgeMove } from './validate';
import {
  MODE_SECONDS,
  type EndReason,
  type FinishRequest,
  type RunAttempt,
  type RushMode,
  type RushPuzzle,
  type RushResults,
  type Square,
} from './types';

export const MAX_STRIKES = 3;

export type Phase = 'idle' | 'starting' | 'countdown' | 'playing' | 'over';
export type CoachCue = 'streak5' | 'streak10' | 'lastHeart';

export interface ResultTile {
  index: number;
  rating: number;
  solved: boolean;
}

export interface MoveOutcome {
  /** Bumped per judged move so effects can react exactly once. */
  seq: number;
  result: 'correct' | 'solved' | 'wrong';
  capture: boolean;
}

export interface RunUiState {
  phase: Phase;
  mode: RushMode;
  runId: string | null;
  seed: string | null;
  /** This run's puzzles, pack[i].index === i. */
  pack: RushPuzzle[];
  puzzle: RushPuzzle | null;
  /** Index into puzzle.moves of the user's next expected move. */
  ply: number;
  /** The user's moves on the current puzzle. */
  userMoves: string[];
  /** The current puzzle has been solved / failed (it stays on the board until ADVANCE). */
  answered: boolean;
  /** Opponent reply waiting to be played after a correct (non-final) move. */
  pendingReply: string | null;
  /** The next puzzle isn't in the pack yet (top-up in flight). */
  stalled: boolean;
  fen: string;
  lastMove: [Square, Square] | null;
  orientation: 'white' | 'black';
  /** Bumped per puzzle so the board remounts instead of sliding pieces across. */
  boardKey: number;
  /** Board-clear cover is up (pieces hidden). */
  covered: boolean;
  inputLocked: boolean;
  badge: { square: Square; kind: 'ok' | 'fail' } | null;
  score: number;
  strikes: number;
  streak: number;
  longestStreak: number;
  highestSolved: number | null;
  attempts: RunAttempt[];
  /** Monotonic-clock ms. */
  startedAtMs: number | null;
  deadlineMs: number | null;
  servedAtMs: number | null;
  endedAtMs: number | null;
  /** Wall-clock epoch ms at GO (for the finish record). */
  startedAtWall: number | null;
  /** Local stats at run end; ranks / PB merged in when `/runs/finish` returns. */
  results: RushResults | null;
  endReason: EndReason | null;
  outcome: MoveOutcome | null;
  coach: { cue: CoachCue; seq: number } | null;
  error: string | null;
}

export type RunAction =
  | { type: 'START_REQUESTED'; mode: RushMode }
  | { type: 'START_FAILED'; error: string }
  | { type: 'RUN_STARTED'; runId: string; seed: string; puzzles: RushPuzzle[] }
  | { type: 'PUZZLE_REVEALED' }
  | { type: 'GO'; now: number; wallNow: number }
  | { type: 'SETUP_PLAYED' }
  | { type: 'USER_MOVED'; uci: string; now: number }
  | { type: 'REPLY_PLAYED' }
  | { type: 'ADVANCE' }
  | { type: 'PACK_EXTENDED'; puzzles: RushPuzzle[] }
  | { type: 'TIME_UP'; now: number }
  | { type: 'QUIT'; now: number }
  | { type: 'FINISH_RESULT'; results: RushResults }
  | { type: 'COACH_DISMISS'; seq: number }
  | { type: 'RESET' };

export const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

export function initialRunState(mode: RushMode): RunUiState {
  return {
    phase: 'idle',
    mode,
    runId: null,
    seed: null,
    pack: [],
    puzzle: null,
    ply: 1,
    userMoves: [],
    answered: false,
    pendingReply: null,
    stalled: false,
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
    longestStreak: 0,
    highestSolved: null,
    attempts: [],
    startedAtMs: null,
    deadlineMs: null,
    servedAtMs: null,
    endedAtMs: null,
    startedAtWall: null,
    results: null,
    endReason: null,
    outcome: null,
    coach: null,
    error: null,
  };
}

/** The ✓/✕ grid: one tile per answered puzzle. */
export function resultTiles(state: RunUiState): ResultTile[] {
  return state.attempts
    .filter((a) => a.result !== 'unfinished')
    .map((a) => ({ index: a.index, rating: a.rating, solved: a.result === 'solved' }));
}

function mountPuzzle(state: RunUiState, puzzle: RushPuzzle): RunUiState {
  return {
    ...state,
    puzzle,
    ply: 1,
    userMoves: [],
    answered: false,
    pendingReply: null,
    stalled: false,
    fen: puzzle.fen,
    lastMove: null,
    orientation: puzzle.color,
    boardKey: state.boardKey + 1,
    covered: true,
    inputLocked: true,
    badge: null,
  };
}

function playSetup(state: RunUiState): RunUiState {
  if (!state.puzzle || state.phase === 'over') return state;
  const moved = applyUci(state.puzzle.fen, state.puzzle.moves[0]);
  if (!moved) return state;
  return {
    ...state,
    phase: 'playing',
    covered: false,
    fen: moved.fen,
    lastMove: [moved.from, moved.to],
    inputLocked: false,
  };
}

function localResults(state: RunUiState, endedAtMs: number): RushResults {
  const timed = state.attempts.filter((a) => a.result !== 'unfinished' && a.ms !== null).map((a) => a.ms as number);
  return {
    score: state.score,
    is_new_pb: false,
    longest_streak: state.longestStreak,
    highest_solved_rating: state.highestSolved,
    avg_ms_per_puzzle: timed.length ? Math.round(timed.reduce((s, x) => s + x, 0) / timed.length) : null,
    duration_ms: state.startedAtMs === null ? 0 : Math.max(0, Math.round(endedAtMs - state.startedAtMs)),
    personal_rank: null,
    global_rank: null,
  };
}

function endRun(state: RunUiState, reason: EndReason, endedAtMs: number): RunUiState {
  if (state.phase === 'over') return state;
  const unfinished = state.puzzle && !state.answered && state.startedAtMs !== null;
  const attempts = unfinished
    ? [...state.attempts, {
        index: state.puzzle!.index,
        puzzle_id: state.puzzle!.id,
        rating: state.puzzle!.rating,
        result: 'unfinished' as const,
        user_moves: state.userMoves,
        ms: null,
      }]
    : state.attempts;
  const ended = { ...state, attempts };
  return {
    ...ended,
    phase: 'over',
    pendingReply: null,
    stalled: false,
    inputLocked: true,
    covered: false,
    endedAtMs,
    endReason: reason,
    results: localResults(ended, endedAtMs),
  };
}

function timeIsUp(state: RunUiState, now: number): boolean {
  return state.deadlineMs !== null && now >= state.deadlineMs;
}

function onUserMove(state: RunUiState, uci: string, now: number): RunUiState {
  if (state.inputLocked || state.phase !== 'playing' || !state.puzzle) return state;
  if (timeIsUp(state, now)) return endRun(state, 'timeout', state.deadlineMs!);

  const p = state.puzzle;
  const v = judgeMove(state.fen, p.moves, state.ply, uci);
  if (v.kind === 'illegal') return state;

  const userMoves = [...state.userMoves, v.uci];
  const outcome: MoveOutcome = { seq: (state.outcome?.seq ?? 0) + 1, result: v.kind, capture: v.capture };
  const base: RunUiState = {
    ...state,
    fen: v.fen,
    lastMove: [v.from, v.to],
    inputLocked: true,
    userMoves,
    outcome,
    badge: { square: v.to, kind: v.kind === 'wrong' ? 'fail' : 'ok' },
  };

  if (v.kind === 'correct') {
    return { ...base, ply: state.ply + 2, pendingReply: v.reply };
  }

  const solved = v.kind === 'solved';
  const attempt: RunAttempt = {
    index: p.index,
    puzzle_id: p.id,
    rating: p.rating,
    result: solved ? 'solved' : 'failed',
    user_moves: userMoves,
    ms: state.servedAtMs === null ? null : Math.max(0, Math.round(now - state.servedAtMs)),
  };
  const streak = solved ? state.streak + 1 : 0;
  const strikes = solved ? state.strikes : state.strikes + 1;
  const next: RunUiState = {
    ...base,
    answered: true,
    servedAtMs: now,
    attempts: [...state.attempts, attempt],
    score: solved ? state.score + 1 : state.score,
    strikes,
    streak,
    longestStreak: Math.max(state.longestStreak, streak),
    highestSolved: solved ? Math.max(state.highestSolved ?? 0, p.rating) : state.highestSolved,
  };
  if (strikes >= MAX_STRIKES) return endRun(next, 'strikes', now);

  let cue: CoachCue | null = null;
  if (solved && (streak === 5 || streak === 10)) cue = streak === 5 ? 'streak5' : 'streak10';
  else if (!solved && strikes === MAX_STRIKES - 1) cue = 'lastHeart';
  if (cue) next.coach = { cue, seq: (state.coach?.seq ?? 0) + 1 };
  return next;
}

export function runReducer(state: RunUiState, action: RunAction): RunUiState {
  switch (action.type) {
    case 'START_REQUESTED':
      return { ...initialRunState(action.mode), phase: 'starting', boardKey: state.boardKey + 1, covered: true };

    case 'START_FAILED':
      return { ...initialRunState(state.mode), boardKey: state.boardKey + 1, error: action.error };

    case 'RUN_STARTED': {
      if (state.phase !== 'starting' || !action.puzzles.length) return state;
      const started = { ...state, runId: action.runId, seed: action.seed, pack: action.puzzles, phase: 'countdown' as const };
      return mountPuzzle(started, action.puzzles[0]);
    }

    case 'PUZZLE_REVEALED':
      return { ...state, covered: false };

    case 'GO': {
      if (state.phase !== 'countdown') return state;
      const seconds = MODE_SECONDS[state.mode];
      return playSetup({
        ...state,
        startedAtMs: action.now,
        servedAtMs: action.now,
        startedAtWall: action.wallNow,
        deadlineMs: seconds === null ? null : action.now + seconds * 1000,
      });
    }

    case 'SETUP_PLAYED':
      // Only on a freshly mounted puzzle (a stale timer must not replay it).
      return state.phase === 'playing' && state.puzzle && !state.answered && state.fen === state.puzzle.fen
        ? playSetup(state) : state;

    case 'USER_MOVED':
      return onUserMove(state, action.uci, action.now);

    case 'REPLY_PLAYED': {
      if (!state.pendingReply || state.phase === 'over') return state;
      const moved = applyUci(state.fen, state.pendingReply);
      if (!moved) return { ...state, pendingReply: null };
      return {
        ...state,
        fen: moved.fen,
        lastMove: [moved.from, moved.to],
        pendingReply: null,
        badge: null,
        inputLocked: false,
      };
    }

    case 'ADVANCE': {
      if (state.phase !== 'playing' || !state.puzzle) return state;
      const next = state.pack[state.puzzle.index + 1];
      return next ? mountPuzzle(state, next) : { ...state, stalled: true, inputLocked: true };
    }

    case 'PACK_EXTENDED': {
      const fresh = action.puzzles.filter((p, i) => p.index === state.pack.length + i);
      if (!fresh.length) return state;
      const extended = { ...state, pack: [...state.pack, ...fresh] };
      if (!state.stalled || !state.puzzle) return extended;
      const next = extended.pack[state.puzzle.index + 1];
      return next ? mountPuzzle(extended, next) : extended;
    }

    case 'TIME_UP':
      if (state.phase !== 'playing' || !timeIsUp(state, action.now)) return state;
      return endRun(state, 'timeout', state.deadlineMs!);

    case 'QUIT':
      if (state.phase !== 'playing' && state.phase !== 'countdown') return state;
      return endRun(state, 'quit', action.now);

    case 'FINISH_RESULT':
      if (state.phase !== 'over' || !state.results) return state;
      return { ...state, results: { ...state.results, ...action.results } };

    case 'COACH_DISMISS':
      return state.coach?.seq === action.seq ? { ...state, coach: null } : state;

    case 'RESET':
      return { ...initialRunState(state.mode), boardKey: state.boardKey + 1 };
  }
}

/** The `/runs/finish` body for an ended run (null if the run never started). */
export function finishRequest(state: RunUiState): FinishRequest | null {
  if (state.phase !== 'over' || !state.runId || !state.seed || !state.endReason
    || state.startedAtWall === null || state.startedAtMs === null || state.endedAtMs === null) return null;
  const endedWall = state.startedAtWall + (state.endedAtMs - state.startedAtMs);
  return {
    run_id: state.runId,
    mode: state.mode,
    seed: state.seed,
    started_at: new Date(state.startedAtWall).toISOString(),
    ended_at: new Date(endedWall).toISOString(),
    end_reason: state.endReason,
    attempts: state.attempts,
  };
}

export interface ReviewAttempt extends RunAttempt {
  /** Position before the setup move, and the full solution line (from the pack). */
  fen: string;
  solution: string[];
}

/** Attempts joined with their pack puzzles — the review drawer needs no network. */
export function reviewAttempts(state: RunUiState): ReviewAttempt[] {
  return state.attempts.flatMap((a) => {
    const p = state.pack[a.index];
    return p ? [{ ...a, fen: p.fen, solution: p.moves }] : [];
  });
}
