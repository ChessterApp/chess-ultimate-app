// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import React from 'react';

// The real ChessgroundBoard, synchronously (next/dynamic is client-only in the app).
vi.mock('next/dynamic', async () => {
  const mod = await import('@/components/chess/ChessgroundBoard');
  return { default: () => mod.default };
});

const init = vi.fn();
const set = vi.fn();
const destroy = vi.fn();
vi.mock('chessground', () => ({
  Chessground: (_el: HTMLElement, config: unknown) => {
    init(config);
    return { set, setShapes: vi.fn(), setAutoShapes: vi.fn(), selectSquare: vi.fn(), destroy, redrawAll: vi.fn() };
  },
}));

import RushBoard from '../RushBoard';
import { initialRunState, runReducer, type RunUiState } from '@/lib/puzzle-rush/runReducer';
import type { RushPuzzle } from '@/lib/puzzle-rush/types';

const PUZZLES: RushPuzzle[] = [
  { index: 0, id: 'a', fen: 'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3', moves: ['f1c4', 'g8f6', 'f3g5'], rating: 400, themes: [], color: 'black' },
  { index: 1, id: 'b', fen: '6k1/5ppp/8/8/8/8/5PPP/R5K1 b - - 0 1', moves: ['g8f8', 'a1a8'], rating: 450, themes: [], color: 'white' },
];

function board(s: RunUiState) {
  return <RushBoard fen={s.fen} orientation={s.orientation} lastMove={s.lastMove} movable={!s.inputLocked} />;
}

beforeEach(() => {
  init.mockClear();
  set.mockClear();
  destroy.mockClear();
  (globalThis as any).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
});
afterEach(() => {
  cleanup();
  delete (globalThis as any).ResizeObserver;
});

describe('RushBoard across puzzles', () => {
  it('advancing to the next puzzle updates the same chessground instead of remounting it', () => {
    let s = runReducer(initialRunState('3min'), { type: 'START_REQUESTED', mode: '3min' });
    s = runReducer(s, { type: 'RUN_STARTED', runId: 'r', seed: 'x', puzzles: PUZZLES });
    s = runReducer(s, { type: 'GO', now: 0, wallNow: 0 });
    const { rerender } = render(board(s));
    expect(init).toHaveBeenCalledTimes(1);

    s = runReducer(s, { type: 'USER_MOVED', uci: 'g8f6', now: 10 });
    rerender(board(s));
    const before = s.boardKey;
    s = runReducer(s, { type: 'ADVANCE' });
    expect(s.boardKey).toBe(before + 1); // the reducer still bumps it — the board must not care
    expect(s.fen).toBe(PUZZLES[1].fen);
    rerender(board(s));

    expect(init).toHaveBeenCalledTimes(1);
    expect(destroy).not.toHaveBeenCalled();
    expect(set).toHaveBeenCalledWith(expect.objectContaining({ fen: PUZZLES[1].fen }));
    expect(set).toHaveBeenCalledWith({ orientation: 'white' });
    // The previous puzzle's last-move highlight is cleared for the fresh position.
    expect(set).toHaveBeenCalledWith({ lastMove: undefined });
  });
});
