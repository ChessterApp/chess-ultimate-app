/**
 * @vitest-environment jsdom
 *
 * Results modal → review drawer hand-off on the real page component, with the
 * run hook stubbed to a finished run (2 misses out of 3).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React, { useState } from 'react';
import { cleanup, render, screen, fireEvent, within, act } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import { initialRunState, STARTING_FEN, type ResultTile, type ReviewAttempt } from '@/lib/puzzle-rush/runReducer';

vi.mock('@clerk/nextjs', () => ({ useAuth: () => ({ isSignedIn: false, getToken: async () => null, userId: null }) }));
vi.mock('next/dynamic', () => ({ default: () => () => <div data-testid="cg-board" /> }));
vi.mock('canvas-confetti', () => ({ default: vi.fn() }));
vi.mock('../fonts', () => ({ fraunces: { variable: 'font-fraunces' } }));

const TILES: ResultTile[] = [
  { index: 0, rating: 400, solved: true },
  { index: 1, rating: 461, solved: false },
  { index: 2, rating: 523, solved: false },
];
const REVIEW: ReviewAttempt[] = TILES.map((tile) => ({
  index: tile.index,
  puzzle_id: `p${tile.index}`,
  rating: tile.rating,
  result: tile.solved ? 'solved' : 'failed',
  user_moves: [],
  ms: 4000,
  fen: STARTING_FEN,
  solution: ['e2e4', 'e7e5', 'g1f3'],
}));

// Stable references: the page's effects depend on them.
const STATE = { ...initialRunState('3min'), phase: 'over' as const, runId: 'run-1', score: 1, endReason: 'strikes' as const };
const auth = async () => null;

vi.mock('@/hooks/usePuzzleRush', () => ({
  usePuzzleRush: () => {
    const [showResults, setShowResults] = useState(true);
    return {
      state: STATE,
      tiles: TILES,
      review: REVIEW,
      countdown: null,
      showResults,
      closeResults: () => setShowResults(false),
      isPb: false,
      isGuest: true,
      guestBest: null,
      ranksPending: false,
      recorded: false,
      start: vi.fn(),
      onMove: vi.fn(),
      quit: vi.fn(),
      reset: vi.fn(),
      auth,
    };
  },
}));

import PuzzleRush from '../PuzzleRush';

async function renderPage() {
  await act(async () => {
    render(<NextIntlClientProvider locale="en" messages={en}><PuzzleRush /></NextIntlClientProvider>);
  });
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('puzzleRush.rulesSeen', '1');
});
afterEach(() => cleanup());

describe('PuzzleRush page — results modal → review', () => {
  it('clicking a ✕ tile closes the modal and opens the review on that puzzle', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /^Puzzles/ }));
    fireEvent.click(within(screen.getByTestId('rush-results')).getByRole('button', { name: 'Puzzle 3' }));

    expect(screen.queryByTestId('rush-results')).toBeNull();
    const drawer = screen.getByTestId('rush-review');
    expect(within(drawer).getByRole('heading').textContent).toBe('Puzzle 3 · 523');
    expect(within(drawer).getByText('Missed')).toBeTruthy();
  });

  it('Retry mistakes opens the review on the first miss', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Retry mistakes (2)' }));

    expect(screen.queryByTestId('rush-results')).toBeNull();
    expect(within(screen.getByTestId('rush-review')).getByRole('heading').textContent).toBe('Puzzle 2 · 461');
  });
});
