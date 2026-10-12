import { describe, it, expect } from 'vitest';
import { applyUci, initialRunState, runReducer, type RunAction, type RunUiState } from '../runReducer';
import { MULTI, NEXT, RESULTS, T0, created, moveRes } from './fixtures';

function run(actions: RunAction[], from: RunUiState = initialRunState('3min')): RunUiState {
  return actions.reduce(runReducer, from);
}

/** A run whose first puzzle is on the board and playable. */
function playing(): RunUiState {
  return run([
    { type: 'START_REQUESTED', mode: '3min' },
    { type: 'RUN_CREATED', response: created(), clientNow: T0 },
    { type: 'PUZZLE_REVEALED' },
    { type: 'SETUP_PLAYED' },
  ]);
}

describe('runReducer — start + countdown', () => {
  it('mounts the first puzzle covered and locked, oriented to the user side', () => {
    const s = run([
      { type: 'START_REQUESTED', mode: '3min' },
      { type: 'RUN_CREATED', response: created(), clientNow: T0 },
    ]);
    expect(s.phase).toBe('countdown');
    expect(s.fen).toBe(MULTI.fen);
    expect(s.orientation).toBe('white');
    expect(s.covered).toBe(true);
    expect(s.inputLocked).toBe(true);
  });

  it('maps the server clock onto the client clock (skew-corrected)', () => {
    // Client clock runs 2 s behind the server.
    const s = run([
      { type: 'START_REQUESTED', mode: '3min' },
      { type: 'RUN_CREATED', response: created(), clientNow: T0 - 2000 },
    ]);
    expect(s.startedAtMs).toBe(T0 - 2000 + 3000);
    expect(s.deadlineMs).toBe(T0 - 2000 + 183_000);
  });

  it('plays the opponent setup move and unlocks input', () => {
    const s = playing();
    expect(s.phase).toBe('playing');
    expect(s.inputLocked).toBe(false);
    expect(s.lastMove).toEqual(['f2', 'g3']);
    expect(s.fen).toBe(applyUci(MULTI.fen, 'f2g3')!.fen);
  });

  it('START_FAILED returns to idle with the error code', () => {
    const s = run([{ type: 'START_REQUESTED', mode: '5min' }, { type: 'START_FAILED', error: 'rate_limited' }]);
    expect(s.phase).toBe('idle');
    expect(s.error).toBe('rate_limited');
  });
});

describe('runReducer — moves', () => {
  it('correct (non-final) move: ✓ badge, then the opponent reply is applied (multi-move)', () => {
    let s = runReducer(playing(), { type: 'USER_MOVED', uci: 'e6e7' });
    expect(s.inputLocked).toBe(true);
    s = runReducer(s, { type: 'MOVE_RESULT', response: moveRes({ result: 'correct', reply: 'b2b1' }), clientNow: T0 });
    expect(s.badge).toEqual({ square: 'e7', kind: 'ok' });
    expect(s.pendingReply).toBe('b2b1');
    expect(s.tiles).toHaveLength(0);
    expect(s.inputLocked).toBe(true);

    s = runReducer(s, { type: 'REPLY_PLAYED' });
    expect(s.lastMove).toEqual(['b2', 'b1']);
    expect(s.badge).toBeNull();
    expect(s.inputLocked).toBe(false);

    // Second user move + second reply, then the final solving move.
    s = runReducer(s, { type: 'USER_MOVED', uci: 'b3c1' });
    s = runReducer(s, { type: 'MOVE_RESULT', response: moveRes({ result: 'correct', reply: 'b1c1' }), clientNow: T0 });
    s = runReducer(s, { type: 'REPLY_PLAYED' });
    expect(s.fen.startsWith('r6k/pp2R2p/5p1Q/3p4/8/3P2b1/P1P3PP/2q4K')).toBe(true);
    s = runReducer(s, { type: 'USER_MOVED', uci: 'h6c1' });
    s = runReducer(s, {
      type: 'MOVE_RESULT',
      response: moveRes({ result: 'solved', score: 1, streak: 1, next_puzzle: NEXT }),
      clientNow: T0,
    });
    expect(s.score).toBe(1);
    expect(s.tiles).toEqual([{ index: 0, rating: 1800, solved: true }]);
    expect(s.pending).toEqual(NEXT);
  });

  it('wrong move: strike, ✕ badge, wrong move left on the board, next puzzle queued', () => {
    let s = runReducer(playing(), { type: 'USER_MOVED', uci: 'h6h7' });
    const afterWrong = s.fen;
    s = runReducer(s, {
      type: 'MOVE_RESULT',
      response: moveRes({ result: 'wrong', strikes: 1, next_puzzle: NEXT }),
      clientNow: T0,
    });
    expect(s.strikes).toBe(1);
    expect(s.badge).toEqual({ square: 'h7', kind: 'fail' });
    expect(s.fen).toBe(afterWrong);
    expect(s.tiles).toEqual([{ index: 0, rating: 1800, solved: false }]);
    expect(s.phase).toBe('playing');

    s = runReducer(s, { type: 'ADVANCE' });
    expect(s.puzzle).toEqual(NEXT);
    expect(s.orientation).toBe('black');
    expect(s.covered).toBe(true);
    expect(s.badge).toBeNull();
    expect(s.boardKey).toBeGreaterThan(playing().boardKey);
  });

  it('3rd strike ends the run with the server results; ADVANCE is then ignored', () => {
    let s: RunUiState = { ...playing(), strikes: 2 };
    s = runReducer(s, { type: 'USER_MOVED', uci: 'h6h7' });
    s = runReducer(s, {
      type: 'MOVE_RESULT',
      response: moveRes({ result: 'wrong', strikes: 3, run_over: true, end_reason: 'strikes', results: RESULTS }),
      clientNow: T0,
    });
    expect(s.phase).toBe('over');
    expect(s.endReason).toBe('strikes');
    expect(s.results).toEqual(RESULTS);
    expect(s.inputLocked).toBe(true);
    expect(s.badge?.kind).toBe('fail');
    expect(runReducer(s, { type: 'ADVANCE' })).toBe(s);
  });

  it('timeout reported by the server ends the run', () => {
    const s = runReducer(playing(), {
      type: 'RUN_OVER',
      state: { run_over: true, end_reason: 'timeout', score: 7, strikes: 1 },
      results: { ...RESULTS, score: 7 },
      clientNow: T0,
    });
    expect(s.phase).toBe('over');
    expect(s.endReason).toBe('timeout');
    expect(s.score).toBe(7);
    expect(s.inputLocked).toBe(true);
  });

  it('a rejected move restores the previous position and unlocks', () => {
    const before = playing();
    let s = runReducer(before, { type: 'USER_MOVED', uci: 'e6e7' });
    s = runReducer(s, { type: 'MOVE_REJECTED', fen: before.fen, lastMove: before.lastMove });
    expect(s.fen).toBe(before.fen);
    expect(s.inputLocked).toBe(false);
  });

  it('ignores moves while input is locked', () => {
    const locked = { ...playing(), inputLocked: true };
    expect(runReducer(locked, { type: 'USER_MOVED', uci: 'e6e7' })).toBe(locked);
  });
});

describe('runReducer — coach cues', () => {
  it('fires on streak 5, streak 10 and the last heart only', () => {
    const solve = (streak: number) => runReducer({ ...playing(), streak: streak - 1 }, {
      type: 'MOVE_RESULT', response: moveRes({ result: 'solved', streak, score: streak, next_puzzle: NEXT }), clientNow: T0,
    });
    expect(solve(4).coach).toBeNull();
    expect(solve(5).coach?.cue).toBe('streak5');
    expect(solve(10).coach?.cue).toBe('streak10');

    const miss = (strikes: number) => runReducer(playing(), {
      type: 'MOVE_RESULT', response: moveRes({ result: 'wrong', strikes, next_puzzle: NEXT }), clientNow: T0,
    });
    expect(miss(1).coach).toBeNull();
    expect(miss(2).coach?.cue).toBe('lastHeart');
  });

  it('COACH_DISMISS only clears the matching toast', () => {
    const s = { ...playing(), coach: { cue: 'streak5' as const, seq: 3 } };
    expect(runReducer(s, { type: 'COACH_DISMISS', seq: 2 }).coach).not.toBeNull();
    expect(runReducer(s, { type: 'COACH_DISMISS', seq: 3 }).coach).toBeNull();
  });
});
