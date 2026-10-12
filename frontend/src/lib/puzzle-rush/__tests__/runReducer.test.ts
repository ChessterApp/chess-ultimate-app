import { describe, it, expect } from 'vitest';
import {
  finishRequest, initialRunState, resultTiles, reviewAttempts, runReducer, type RunAction, type RunUiState,
} from '../runReducer';
import { applyUci } from '../validate';
import type { RushMode, RushPuzzle } from '../types';
import { MISS, MULTI, NEXT, SOLVE, matePack } from './fixtures';

const RUN_ID = '11111111-2222-4333-8444-555555555555';
const T = 10_000; // monotonic ms at GO
const WALL = Date.parse('2026-10-12T10:00:00Z');

function run(actions: RunAction[], from: RunUiState): RunUiState {
  return actions.reduce(runReducer, from);
}

/** A run whose first puzzle is on the board and playable (clock started at T). */
function playing(puzzles: RushPuzzle[] = [MULTI, NEXT], mode: RushMode = '3min'): RunUiState {
  return run([
    { type: 'START_REQUESTED', mode },
    { type: 'RUN_STARTED', runId: RUN_ID, seed: 'abcdef0123456789', puzzles },
    { type: 'PUZZLE_REVEALED' },
    { type: 'GO', now: T, wallNow: WALL },
  ], initialRunState(mode));
}

const move = (uci: string, now = T + 1000): RunAction => ({ type: 'USER_MOVED', uci, now });

/** Solve / miss the current mate-in-1 and move on to the next puzzle. */
function answer(s: RunUiState, uci: string, now: number): RunUiState {
  s = runReducer(s, move(uci, now));
  if (s.phase === 'over') return s;
  return run([{ type: 'ADVANCE' }, { type: 'PUZZLE_REVEALED' }, { type: 'SETUP_PLAYED' }], s);
}

describe('runReducer — start + countdown', () => {
  it('mounts the first pack puzzle covered and locked, oriented to the user side', () => {
    const s = run([
      { type: 'START_REQUESTED', mode: '3min' },
      { type: 'RUN_STARTED', runId: RUN_ID, seed: 'abcdef0123456789', puzzles: [MULTI, NEXT] },
    ], initialRunState('3min'));
    expect(s.phase).toBe('countdown');
    expect(s.fen).toBe(MULTI.fen);
    expect(s.orientation).toBe('white');
    expect(s.covered).toBe(true);
    expect(s.inputLocked).toBe(true);
    expect(s.startedAtMs).toBeNull();
  });

  it('GO starts the local clock and plays the setup move', () => {
    const s = playing();
    expect(s.phase).toBe('playing');
    expect(s.startedAtMs).toBe(T);
    expect(s.deadlineMs).toBe(T + 180_000);
    expect(s.inputLocked).toBe(false);
    expect(s.lastMove).toEqual(['f2', 'g3']);
    expect(s.fen).toBe(applyUci(MULTI.fen, 'f2g3')!.fen);
    expect(playing(undefined, 'survival').deadlineMs).toBeNull();
  });

  it('START_FAILED returns to idle with the error code', () => {
    const s = run([{ type: 'START_REQUESTED', mode: '5min' }, { type: 'START_FAILED', error: 'network' }], initialRunState('5min'));
    expect(s.phase).toBe('idle');
    expect(s.error).toBe('network');
  });
});

describe('runReducer — moves (verdict in the same update as the move)', () => {
  it('correct non-final move: ✓ badge at once, then the opponent reply (multi-move)', () => {
    let s = runReducer(playing(), move('e6e7'));
    expect(s.badge).toEqual({ square: 'e7', kind: 'ok' });
    expect(s.outcome).toMatchObject({ seq: 1, result: 'correct', capture: true });
    expect(s.pendingReply).toBe('b2b1');
    expect(s.inputLocked).toBe(true);
    expect(resultTiles(s)).toHaveLength(0);

    s = runReducer(s, { type: 'REPLY_PLAYED' });
    expect(s.lastMove).toEqual(['b2', 'b1']);
    expect(s.badge).toBeNull();
    expect(s.inputLocked).toBe(false);

    s = run([move('b3c1'), { type: 'REPLY_PLAYED' }], s);
    expect(s.fen.startsWith('r6k/pp2R2p/5p1Q/3p4/8/3P2b1/P1P3PP/2q4K')).toBe(true);
    s = runReducer(s, move('h6c1', T + 4200));
    expect(s.outcome?.result).toBe('solved');
    expect(s.score).toBe(1);
    expect(s.streak).toBe(1);
    expect(s.answered).toBe(true);
    expect(resultTiles(s)).toEqual([{ index: 0, rating: 1797, solved: true }]);
    expect(s.attempts[0]).toEqual({
      index: 0, puzzle_id: '00008', rating: 1797, result: 'solved',
      user_moves: ['e6e7', 'b3c1', 'h6c1'], ms: 4200,
    });
  });

  it('wrong move: strike, ✕ badge, wrong move left on the board; ADVANCE mounts the next pack puzzle', () => {
    let s = runReducer(playing(), move('h6h7'));
    const afterWrong = s.fen;
    expect(s.strikes).toBe(1);
    expect(s.streak).toBe(0);
    expect(s.badge).toEqual({ square: 'h7', kind: 'fail' });
    expect(s.fen).toBe(afterWrong);
    expect(resultTiles(s)).toEqual([{ index: 0, rating: 1797, solved: false }]);
    expect(s.phase).toBe('playing');

    const key = s.boardKey;
    s = runReducer(s, { type: 'ADVANCE' });
    expect(s.puzzle).toEqual(NEXT);
    expect(s.orientation).toBe('black');
    expect(s.covered).toBe(true);
    expect(s.badge).toBeNull();
    expect(s.boardKey).toBe(key + 1);
    s = run([{ type: 'PUZZLE_REVEALED' }, { type: 'SETUP_PLAYED' }], s);
    expect(s.lastMove).toEqual(['g5', 'e7']);
    expect(s.inputLocked).toBe(false);
    // A stale SETUP_PLAYED never replays the setup move.
    expect(runReducer(s, { type: 'SETUP_PLAYED' })).toBe(s);
  });

  it('an alternative mate is accepted', () => {
    const s = runReducer(playing(matePack(2)), move('e1e8'));
    expect(s.outcome?.result).toBe('solved');
    expect(s.score).toBe(1);
  });

  it('ignores illegal moves and moves while input is locked', () => {
    const s = playing();
    expect(runReducer(s, move('h1h3'))).toBe(s);
    const locked = { ...s, inputLocked: true };
    expect(runReducer(locked, move('e6e7'))).toBe(locked);
  });

  it('per-puzzle ms runs from the previous answer (or GO)', () => {
    let s = answer(playing(matePack(5)), SOLVE, T + 3000);
    s = answer(s, MISS, T + 3000 + 5500);
    expect(s.attempts.map((a) => a.ms)).toEqual([3000, 5500]);
  });
});

describe('runReducer — strikes, streaks, clock', () => {
  it('streaks: longest kept, reset by a miss; highest solved rating tracked', () => {
    let s = playing(matePack(10));
    let t = T;
    for (const uci of [SOLVE, SOLVE, SOLVE, MISS, SOLVE]) s = answer(s, uci, (t += 1000));
    expect(s.score).toBe(4);
    expect(s.streak).toBe(1);
    expect(s.longestStreak).toBe(3);
    expect(s.highestSolved).toBe(400 + 45 * 4);
  });

  it('3rd strike ends the run on the spot with local results; ADVANCE is then ignored', () => {
    let s = playing(matePack(10));
    s = answer(s, SOLVE, T + 1000);
    s = answer(s, MISS, T + 2000);
    s = answer(s, MISS, T + 3000);
    s = runReducer(s, move(MISS, T + 4000));
    expect(s.phase).toBe('over');
    expect(s.endReason).toBe('strikes');
    expect(s.endedAtMs).toBe(T + 4000);
    expect(s.inputLocked).toBe(true);
    expect(s.badge?.kind).toBe('fail');
    expect(s.results).toEqual({
      score: 1, is_new_pb: false, longest_streak: 1, highest_solved_rating: 400,
      avg_ms_per_puzzle: 1000, duration_ms: 4000, personal_rank: null, global_rank: null,
    });
    expect(runReducer(s, { type: 'ADVANCE' })).toBe(s);
    expect(runReducer(s, move(SOLVE, T + 5000))).toBe(s);
  });

  it('clock: TIME_UP before the deadline is ignored, at it the run ends (unfinished puzzle kept)', () => {
    let s = runReducer(playing(), move('e6e7', T + 1000));
    s = runReducer(s, { type: 'REPLY_PLAYED' });
    expect(runReducer(s, { type: 'TIME_UP', now: T + 179_999 })).toBe(s);
    s = runReducer(s, { type: 'TIME_UP', now: T + 180_004 });
    expect(s.phase).toBe('over');
    expect(s.endReason).toBe('timeout');
    expect(s.endedAtMs).toBe(T + 180_000);
    expect(s.results?.duration_ms).toBe(180_000);
    expect(s.attempts).toEqual([{
      index: 0, puzzle_id: '00008', rating: 1797, result: 'unfinished', user_moves: ['e6e7'], ms: null,
    }]);
  });

  it('a move after the deadline ends the run instead of counting', () => {
    const s = runReducer(playing(matePack(3)), move(SOLVE, T + 180_000));
    expect(s.phase).toBe('over');
    expect(s.endReason).toBe('timeout');
    expect(s.score).toBe(0);
  });

  it('survival has no clock; QUIT ends the run and keeps the score', () => {
    let s = answer(playing(matePack(3), 'survival'), SOLVE, T + 1000);
    expect(runReducer(s, { type: 'TIME_UP', now: T + 10_000_000 })).toBe(s);
    s = runReducer(s, { type: 'QUIT', now: T + 2000 });
    expect(s.phase).toBe('over');
    expect(s.endReason).toBe('quit');
    expect(s.score).toBe(1);
  });
});

describe('runReducer — pack top-up', () => {
  it('stalls when the next puzzle is not in the pack, and mounts it when the top-up lands', () => {
    let s = runReducer(playing(matePack(1)), move(SOLVE));
    s = runReducer(s, { type: 'ADVANCE' });
    expect(s.stalled).toBe(true);
    expect(s.inputLocked).toBe(true);
    expect(s.puzzle?.index).toBe(0);

    s = runReducer(s, { type: 'PACK_EXTENDED', puzzles: matePack(2, 1) });
    expect(s.pack).toHaveLength(3);
    expect(s.stalled).toBe(false);
    expect(s.puzzle?.index).toBe(1);
    expect(s.covered).toBe(true);
  });

  it('ignores out-of-order or duplicate slices', () => {
    const s = playing(matePack(2));
    expect(runReducer(s, { type: 'PACK_EXTENDED', puzzles: matePack(2, 5) })).toBe(s);
    expect(runReducer(s, { type: 'PACK_EXTENDED', puzzles: matePack(2) })).toBe(s);
  });
});

describe('runReducer — finish', () => {
  function ended() {
    let s = playing(matePack(5));
    s = answer(s, SOLVE, T + 2000);
    s = answer(s, MISS, T + 4000);
    return runReducer(s, { type: 'QUIT', now: T + 6500 });
  }

  it('builds the /runs/finish body from local state', () => {
    expect(finishRequest(ended())).toEqual({
      run_id: RUN_ID,
      mode: '3min',
      seed: 'abcdef0123456789',
      started_at: '2026-10-12T10:00:00.000Z',
      ended_at: '2026-10-12T10:00:06.500Z',
      end_reason: 'quit',
      attempts: [
        { index: 0, puzzle_id: 'M0', rating: 400, result: 'solved', user_moves: ['d1d8'], ms: 2000 },
        { index: 1, puzzle_id: 'M1', rating: 445, result: 'failed', user_moves: ['g1h1'], ms: 2000 },
        { index: 2, puzzle_id: 'M2', rating: 490, result: 'unfinished', user_moves: [], ms: null },
      ],
    });
    expect(finishRequest(playing())).toBeNull();
  });

  it('FINISH_RESULT merges the server ranks / PB into the local results', () => {
    const s = runReducer(ended(), {
      type: 'FINISH_RESULT',
      results: {
        score: 1, is_new_pb: true, longest_streak: 1, highest_solved_rating: 400, avg_ms_per_puzzle: 2000,
        duration_ms: 6500, personal_rank: 1, global_rank: { daily: 3, weekly: 4, all: 9 },
      },
    });
    expect(s.results).toMatchObject({ is_new_pb: true, personal_rank: 1, global_rank: { daily: 3, weekly: 4, all: 9 } });
  });

  it('review attempts carry the full solution from the pack (offline drawer)', () => {
    const r = reviewAttempts(ended());
    expect(r[1]).toMatchObject({ index: 1, result: 'failed', fen: matePack(2)[1].fen, solution: ['a7a6', 'd1d8'] });
  });
});

describe('runReducer — coach cues', () => {
  it('fires on streak 5, streak 10 and the last heart only', () => {
    let s = playing(matePack(20));
    let t = T;
    const cues: (string | null)[] = [];
    for (let i = 0; i < 10; i += 1) {
      s = answer(s, SOLVE, (t += 1000));
      cues.push(s.coach?.cue ?? null);
    }
    expect(cues[3]).toBeNull();
    expect(cues[4]).toBe('streak5');
    expect(cues[9]).toBe('streak10');

    s = answer({ ...s, coach: null }, MISS, (t += 1000));
    expect(s.coach).toBeNull();
    s = answer(s, MISS, (t += 1000));
    expect(s.coach?.cue).toBe('lastHeart');
  });

  it('COACH_DISMISS only clears the matching toast', () => {
    const s = { ...playing(), coach: { cue: 'streak5' as const, seq: 3 } };
    expect(runReducer(s, { type: 'COACH_DISMISS', seq: 2 }).coach).not.toBeNull();
    expect(runReducer(s, { type: 'COACH_DISMISS', seq: 3 }).coach).toBeNull();
  });
});
