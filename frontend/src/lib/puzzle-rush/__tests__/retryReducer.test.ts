import { describe, it, expect } from 'vitest';
import { applyUci } from '../validate';
import type { ResultTile, ReviewAttempt } from '../runReducer';
import type { RushPuzzle } from '../types';
import {
  nextMistakeIndex,
  recordOutcome,
  retryHint,
  retryReducer,
  startRetry,
  type RetryAction,
  type RetryState,
} from '../retryReducer';
import { MATE1, MULTI } from './fixtures';

function attempt(p: RushPuzzle, index = 0): ReviewAttempt {
  return {
    index, puzzle_id: p.id, rating: p.rating, result: 'failed', user_moves: ['g1h1'], ms: 3000,
    fen: p.fen, solution: p.moves,
  };
}

function run(state: RetryState | null, ...actions: RetryAction[]): RetryState {
  return actions.reduce<RetryState | null>(retryReducer, state)!;
}

const afterSetup = (p: RushPuzzle) => applyUci(p.fen, p.moves[0])!.fen;

describe('retryReducer', () => {
  it('start applies the setup move, user to move', () => {
    const s = run(null, { type: 'start', attempt: attempt(MULTI, 4) });
    expect(s.index).toBe(4);
    expect(s.fen).toBe(afterSetup(MULTI));
    expect(s.fen.split(' ')[1]).toBe('w');
    expect(s.lastMove).toEqual(['f2', 'g3']);
    expect(s).toMatchObject({ ply: 1, status: 'playing', hintLevel: 0, usedHint: false, usedSolution: false });
  });

  it('a wrong move → wrong, position unchanged; clearWrong resumes', () => {
    const s0 = startRetry(attempt(MULTI));
    const s1 = run(s0, { type: 'move', uci: 'h6h7' });
    expect(s1.status).toBe('wrong');
    expect(s1.fen).toBe(s0.fen);
    expect(s1.ply).toBe(1);
    expect(s1.lastWrong).toMatchObject({ square: 'h7', uci: 'h6h7', from: 'h6' });
    // No moves while the ✕ is up.
    expect(run(s1, { type: 'move', uci: 'e6e7' })).toBe(s1);
    const s2 = run(s1, { type: 'clearWrong' });
    expect(s2).toMatchObject({ status: 'playing', lastWrong: null, fen: s0.fen });
  });

  it('ignores illegal moves', () => {
    const s0 = startRetry(attempt(MULTI));
    expect(run(s0, { type: 'move', uci: 'a1a8' })).toBe(s0);
  });

  it('a correct move auto-applies the reply; the last move solves', () => {
    const s1 = run(startRetry(attempt(MULTI)), { type: 'move', uci: 'e6e7' });
    let fen = afterSetup(MULTI);
    for (const m of ['e6e7', 'b2b1']) fen = applyUci(fen, m)!.fen;
    expect(s1).toMatchObject({ status: 'playing', ply: 3, fen, lastMove: ['b2', 'b1'] });
    const s2 = run(s1, { type: 'move', uci: 'b3c1' }, { type: 'move', uci: 'h6c1' });
    expect(s2).toMatchObject({ status: 'solved', ply: 6, lastMove: ['h6', 'c1'] });
  });

  it('accepts an alternative mate as solved', () => {
    const s = run(startRetry(attempt(MATE1)), { type: 'move', uci: 'e1e8' });
    expect(s.status).toBe('solved');
  });

  it('hint: level 1 = from-square, level 2 = arrow; resets after a correct move', () => {
    const s0 = startRetry(attempt(MULTI));
    expect(retryHint(s0)).toEqual({ square: null, move: null });
    const s1 = run(s0, { type: 'hint' });
    expect(s1).toMatchObject({ hintLevel: 1, usedHint: true });
    expect(retryHint(s1)).toEqual({ square: 'e6', move: null });
    const s2 = run(s1, { type: 'hint' });
    expect(retryHint(s2)).toEqual({ square: null, move: ['e6', 'e7'] });
    expect(run(s2, { type: 'hint' })).toBe(s2);
    const s3 = run(s2, { type: 'move', uci: 'e6e7' });
    expect(s3.hintLevel).toBe(0);
    expect(s3.usedHint).toBe(true);
  });

  it('retry resets to the start but keeps the help flags', () => {
    const s = run(
      startRetry(attempt(MULTI)),
      { type: 'hint' },
      { type: 'move', uci: 'e6e7' },
      { type: 'retry' },
    );
    expect(s).toMatchObject({ fen: afterSetup(MULTI), ply: 1, status: 'playing', hintLevel: 0, usedHint: true });
    expect(s.lastMove).toEqual(['f2', 'g3']);
  });

  it('showSolution → revealed (not after solving)', () => {
    const s = run(startRetry(attempt(MULTI)), { type: 'showSolution' });
    expect(s).toMatchObject({ status: 'revealed', usedSolution: true });
    expect(retryHint(run(s, { type: 'hint' }))).toEqual({ square: null, move: null });
    const solved = run(startRetry(attempt(MATE1)), { type: 'move', uci: 'd1d8' });
    expect(run(solved, { type: 'showSolution' })).toBe(solved);
  });
});

describe('recordOutcome', () => {
  it('records solved / solved_with_help / revealed, keeping the best', () => {
    const clean = run(startRetry(attempt(MATE1, 2)), { type: 'move', uci: 'd1d8' });
    expect(recordOutcome({}, clean)).toEqual({ 2: 'solved' });
    const helped = run(startRetry(attempt(MATE1, 2)), { type: 'hint' }, { type: 'move', uci: 'd1d8' });
    expect(recordOutcome({}, helped)).toEqual({ 2: 'solved_with_help' });
    const revealed = run(startRetry(attempt(MATE1, 2)), { type: 'showSolution' });
    expect(recordOutcome({}, revealed)).toEqual({ 2: 'revealed' });
    expect(recordOutcome({ 2: 'solved' }, helped)).toEqual({ 2: 'solved' });
    // Solving after looking at the solution counts as helped.
    expect(recordOutcome({ 2: 'revealed' }, run(revealed, { type: 'retry' }, { type: 'move', uci: 'd1d8' })))
      .toEqual({ 2: 'solved_with_help' });
    // Still playing → nothing recorded.
    const o = {};
    expect(recordOutcome(o, startRetry(attempt(MATE1)))).toBe(o);
  });
});

describe('nextMistakeIndex', () => {
  const tiles: ResultTile[] = [
    { index: 0, rating: 400, solved: false },
    { index: 1, rating: 450, solved: true },
    { index: 2, rating: 500, solved: false },
    { index: 3, rating: 550, solved: false },
  ];

  it('walks the ✕ tiles in order and wraps', () => {
    expect(nextMistakeIndex(tiles, {}, null)).toBe(0);
    expect(nextMistakeIndex(tiles, {}, 0)).toBe(2);
    expect(nextMistakeIndex(tiles, {}, 1)).toBe(2);
    expect(nextMistakeIndex(tiles, {}, 2)).toBe(3);
    expect(nextMistakeIndex(tiles, {}, 3)).toBe(0);
  });

  it('skips puzzles solved in retry; null when all are solved', () => {
    expect(nextMistakeIndex(tiles, { 2: 'solved' }, 0)).toBe(3);
    expect(nextMistakeIndex(tiles, { 2: 'solved_with_help', 3: 'solved' }, 3)).toBe(0);
    expect(nextMistakeIndex(tiles, { 0: 'solved', 2: 'solved', 3: 'solved_with_help' }, 3)).toBeNull();
    expect(nextMistakeIndex(tiles.filter((t) => t.solved), {}, null)).toBeNull();
  });

  it('a revealed solution counts as reviewed', () => {
    const revealed = recordOutcome({}, run(startRetry(attempt(MATE1, 2)), { type: 'showSolution' }));
    expect(nextMistakeIndex(tiles, revealed, 0)).toBe(3);
    expect(nextMistakeIndex(tiles, revealed, 3)).toBe(0);
  });

  it('done after revealing every miss', () => {
    let outcomes = {};
    let current: number | null = null;
    for (const expected of [0, 2, 3]) {
      current = nextMistakeIndex(tiles, outcomes, current);
      expect(current).toBe(expected);
      outcomes = recordOutcome(outcomes, run(startRetry(attempt(MATE1, current!)), { type: 'showSolution' }));
    }
    expect(nextMistakeIndex(tiles, outcomes, current)).toBeNull();
  });

  it('mixed solved / revealed: done once each miss is one or the other', () => {
    expect(nextMistakeIndex(tiles, { 0: 'revealed', 2: 'solved' }, 2)).toBe(3);
    expect(nextMistakeIndex(tiles, { 0: 'revealed', 2: 'solved', 3: 'solved_with_help' }, 3)).toBeNull();
    expect(nextMistakeIndex(tiles, { 0: 'solved', 2: 'revealed', 3: 'revealed' }, 3)).toBeNull();
  });
});
