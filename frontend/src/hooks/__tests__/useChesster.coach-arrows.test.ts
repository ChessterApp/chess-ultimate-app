/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { Chess } from 'chess.js';
import type { MoveAnalysis } from '../useGameReview';
import { coachArrowsFor } from '@/lib/coach/click-analysis';

// The coach's arrows from a click-analysis must land on the board the student looks at (site review 28.10):
// «Analyze move» kept them under the position after the move while the board stayed put, and the review clicks
// under the position before the move while the review board shows the one after — so they were never drawn.

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  ApiError: class ApiError extends Error {
    status = 0;
  },
}));
vi.mock('@clerk/nextjs', () => ({ useAuth: () => ({ getToken: async () => 'token' }) }));
vi.mock('@/stockfish/hooks/useEngine', () => ({ useEngine: () => undefined }));
vi.mock('usehooks-ts', () => ({
  useLocalStorage: <T,>(_key: string, initial: T) => React.useState<T>(initial),
}));
vi.mock('@/components/tabs/Chessdb', () => ({
  useChessDB: () => ({ data: null, loading: false, error: null, queueing: false, refetch: vi.fn(), requestAnalysis: vi.fn() }),
  getChessDBSpeech: () => '',
}));
vi.mock('@/hooks/useGameReview', () => ({
  default: () => ({
    gameReview: [],
    setGameReview: vi.fn(),
    gameReviewLoading: false,
    gameReviewProgress: 0,
    setGameReviewLoading: vi.fn(),
    generateGameReview: vi.fn(),
  }),
}));
vi.mock('@/lib/openingdatabase/helper', () => ({
  getOpeningStats: async () => null,
  getOpeningStatSpeech: () => '',
  getLichessOpeningStats: async () => null,
}));

import useChesster from '../useChesster';

const START = new Chess().fen();
const AFTER_E4 = (() => {
  const c = new Chess();
  c.move('e4');
  return c.fen();
})();
const ARROWS = [{ from: 'e7', to: 'e5', brush: 'green' }];

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({
    response: 'Black answers in the centre [[arrows: e7e5 green]].',
    tokens_used: 10,
    board_actions: [{ type: 'draw_arrows', arrows: ARROWS }],
  });
});

describe('useChesster — the coach arrows of a click-analysis', () => {
  it('«Analyze move» from the legal moves: drawn on the board the student is on', async () => {
    const { result, rerender } = renderHook(({ fen }) => useChesster(fen), { initialProps: { fen: START } });
    await act(async () => {
      await result.current.handleFutureMoveLegalClick('e4');
    });
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(coachArrowsFor(result.current.coachArrows, START)).toEqual(ARROWS);
    // …and still there when the student plays that move.
    rerender({ fen: AFTER_E4 });
    expect(coachArrowsFor(result.current.coachArrows, AFTER_E4)).toEqual(ARROWS);
  });

  it('«Chesster, analyze move» in the game review: drawn on the position after the move the board shows', async () => {
    const review: MoveAnalysis = {
      plyNumber: 0,
      notation: 'e4',
      sanNotation: 'e4',
      quality: 'Best',
      arrowMove: { from: 'e2', to: 'e4' } as MoveAnalysis['arrowMove'],
      evalMove: 30,
      fen: START,
      currenFen: AFTER_E4,
      player: 'w',
    };
    const { result } = renderHook(({ fen }) => useChesster(fen), { initialProps: { fen: AFTER_E4 } });
    await act(async () => {
      await result.current.handleMoveCoachClick(review);
    });
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(coachArrowsFor(result.current.coachArrows, AFTER_E4)).toEqual(ARROWS);
  });

  it('the annotation click too', async () => {
    const review: MoveAnalysis = {
      plyNumber: 0, notation: 'e4', sanNotation: 'e4', quality: 'Best',
      arrowMove: { from: 'e2', to: 'e4' } as MoveAnalysis['arrowMove'], evalMove: 30,
      fen: START, currenFen: AFTER_E4, player: 'w',
    };
    const { result } = renderHook(({ fen }) => useChesster(fen), { initialProps: { fen: AFTER_E4 } });
    await act(async () => {
      await result.current.handleMoveAnnontateClick(review);
    });
    expect(coachArrowsFor(result.current.coachArrows, AFTER_E4)).toEqual(ARROWS);
  });

  it('not on some other position the student moved to', async () => {
    const { result, rerender } = renderHook(({ fen }) => useChesster(fen), { initialProps: { fen: START } });
    await act(async () => {
      await result.current.handleFutureMoveLegalClick('e4');
    });
    const c = new Chess();
    c.move('d4');
    rerender({ fen: c.fen() });
    expect(coachArrowsFor(result.current.coachArrows, c.fen())).toEqual([]);
  });
});
