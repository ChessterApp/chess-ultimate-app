/**
 * @vitest-environment jsdom
 *
 * Results modal → Retry mode on the real page component, with the run hook
 * stubbed to a finished run (2 misses out of 3, all mate-in-1s) and the board
 * stubbed to record its props.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React, { useState } from 'react';
import { cleanup, render, screen, fireEvent, within, act } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import { initialRunState, type ResultTile, type ReviewAttempt } from '@/lib/puzzle-rush/runReducer';
import { MATE1, MISS, SOLVE } from '@/lib/puzzle-rush/__tests__/fixtures';
import { analyzeHref, SOLUTION_PLY_MS, WRONG_HOLD_MS } from '../RunSummary';
import { applyUci } from '@/lib/puzzle-rush/validate';

type BoardProps = {
  movable?: boolean;
  hintMove?: [string, string] | null;
  hintSquare?: string | null;
  onMove?: (from: string, to: string) => void;
};
const board = vi.hoisted(() => ({ props: {} as BoardProps }));
const sound = vi.hoisted(() => ({ play: vi.fn() }));

vi.mock('@clerk/nextjs', () => ({ useAuth: () => ({ isSignedIn: false, getToken: async () => null, userId: null }) }));
vi.mock('next/dynamic', () => ({
  default: () => (props: BoardProps) => {
    board.props = props;
    return <div data-testid="cg-board" />;
  },
}));
vi.mock('@/hooks/useSoundEffects', () => ({ useSoundEffects: () => sound }));
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
  user_moves: tile.solved ? [SOLVE] : [MISS],
  ms: 4000,
  fen: MATE1.fen,
  solution: MATE1.moves,
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
  sound.play.mockClear();
  localStorage.clear();
  localStorage.setItem('puzzleRush.rulesSeen', '1');
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const play = (from: string, to: string) => act(() => board.props.onMove!(from, to));
const banner = () => screen.getByTestId('retry-banner').textContent;
const panelTitle = () => within(screen.getByTestId('rush-review')).getByRole('heading').textContent;

describe('PuzzleRush page — results modal → Retry mode', () => {
  it('clicking a ✕ tile closes the modal and opens that puzzle in Retry mode', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /^Puzzles/ }));
    fireEvent.click(within(screen.getByTestId('rush-results')).getByRole('button', { name: 'Puzzle 3, missed' }));

    expect(screen.queryByTestId('rush-results')).toBeNull();
    expect(panelTitle()).toBe('Puzzle 3 · 523');
    expect(within(screen.getByTestId('rush-review')).getByText('Missed')).toBeTruthy();
    expect(banner()).toBe('Find the best move for WhiteRating 523');
    expect(screen.getByText('In the run you played: Kh1')).toBeTruthy();
    expect(board.props.movable).toBe(true);
  });

  it('Retry mistakes opens the first miss', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Retry mistakes (2)' }));

    expect(screen.queryByTestId('rush-results')).toBeNull();
    expect(panelTitle()).toBe('Puzzle 2 · 461');
  });

  it('wrong move → Incorrect, snaps back; Hint twice → circle then arrow; Next mistake → next ✕', async () => {
    vi.useFakeTimers();
    await renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /^Puzzles/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Puzzle 2, missed' }));
    expect(board.props.movable).toBe(true);

    play('g1', 'h1');
    expect(banner()).toContain('Incorrect — try again');
    expect(screen.getByTestId('badge-fail')).toBeTruthy();
    expect(board.props.movable).toBe(false);
    act(() => { vi.advanceTimersByTime(WRONG_HOLD_MS); });
    expect(banner()).toContain('Find the best move for White');
    expect(screen.queryByTestId('badge-fail')).toBeNull();
    expect(board.props.movable).toBe(true);

    const hint = screen.getByRole('button', { name: 'Hint' });
    fireEvent.click(hint);
    expect(board.props.hintSquare).toBe('d1');
    expect(board.props.hintMove).toBeNull();
    fireEvent.click(hint);
    expect(board.props.hintSquare).toBeNull();
    expect(board.props.hintMove).toEqual(['d1', 'd8']);
    expect((hint as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Next mistake' }));
    expect(panelTitle()).toBe('Puzzle 3 · 523');
    expect(board.props.hintMove).toBeNull();
  });

  it('solving marks the tile amber (with a help marker after a hint); all reviewed → Play Again', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Retry mistakes (2)' }));
    play('d1', 'd8');
    expect(banner()).toContain('Solved!');
    expect(screen.getByTestId('badge-ok')).toBeTruthy();
    const tile = screen.getByRole('button', { name: 'Puzzle 2, solved on retry' });
    expect(tile.getAttribute('data-retry')).toBe('solved');
    expect(within(tile).getByText('↻✓')).toBeTruthy();
    expect(screen.queryByTestId('retry-done')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Next mistake' }));
    fireEvent.click(screen.getByRole('button', { name: 'Hint' }));
    play('e1', 'e8'); // the other mate counts too
    expect(screen.getByRole('button', { name: 'Puzzle 3, solved on retry with help' }).getAttribute('data-retry'))
      .toBe('solved_with_help');
    expect(screen.getAllByTestId('cell-help')).toHaveLength(1);

    const done = screen.getByTestId('retry-done');
    expect(done.textContent).toContain('All mistakes reviewed');
    expect((screen.getByRole('button', { name: 'Next mistake' }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(done).getByRole('button', { name: 'Play Again' })).toBeTruthy();
  });

  it('Solution auto-plays the line then shows the stepper; Retry resets; Exit leaves', async () => {
    vi.useFakeTimers();
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Retry mistakes (2)' }));
    fireEvent.click(screen.getByRole('button', { name: 'Solution' }));
    expect(banner()).toContain('Solution');
    expect(board.props.movable).toBe(false);
    expect(screen.queryByRole('button', { name: 'Previous move' })).toBeNull();
    act(() => { vi.advanceTimersByTime(SOLUTION_PLY_MS); });
    expect(screen.getByText('2 / 2')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Previous move' })).toBeTruthy();
    // Revealed without solving: still a ✕, marked as viewed.
    const tile = screen.getByRole('button', { name: 'Puzzle 2, missed, solution viewed' });
    expect(tile.getAttribute('data-result')).toBe('failed');
    expect(within(tile).getByTestId('cell-revealed')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(banner()).toContain('Find the best move');
    expect(board.props.movable).toBe(true);
    play('d1', 'd8');
    expect(screen.getByRole('button', { name: 'Puzzle 2, solved on retry with help' })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Exit' }));
    expect(screen.queryByTestId('retry-banner')).toBeNull();
    expect(screen.queryByTestId('rush-review')).toBeNull();
    expect(board.props.movable).toBe(false);
  });

  it('revealing the solution counts as reviewed: Next mistake moves on, then all reviewed', async () => {
    vi.useFakeTimers();
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Retry mistakes (2)' }));
    fireEvent.click(screen.getByRole('button', { name: 'Solution' }));
    expect(screen.queryByTestId('retry-done')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Next mistake' }));
    expect(panelTitle()).toBe('Puzzle 3 · 523');
    fireEvent.click(screen.getByRole('button', { name: 'Solution' }));
    expect(screen.getByTestId('retry-done').textContent).toContain('All mistakes reviewed');
    expect((screen.getByRole('button', { name: 'Next mistake' }) as HTMLButtonElement).disabled).toBe(true);
  });
});

const key = (k: string, init: KeyboardEventInit = {}) => act(() => { fireEvent.keyDown(window, { key: k, ...init }); });

describe('PuzzleRush page — Retry mode shortcuts, Analyze, sounds', () => {
  it('H twice draws the arrow, N goes to the next miss, Esc exits', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Retry mistakes (2)' }));
    key('h');
    expect(board.props.hintSquare).toBe('d1');
    key('H');
    expect(board.props.hintMove).toEqual(['d1', 'd8']);
    key('n');
    expect(panelTitle()).toBe('Puzzle 3 · 523');
    key('Escape');
    expect(screen.queryByTestId('rush-review')).toBeNull();
  });

  it('ignores shortcuts while typing or with a modifier held', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Retry mistakes (2)' }));
    const input = document.createElement('input');
    document.body.appendChild(input);
    act(() => { fireEvent.keyDown(input, { key: 'h' }); });
    act(() => { fireEvent.keyDown(input, { key: 'n' }); });
    key('n', { ctrlKey: true });
    key('h', { metaKey: true });
    expect(board.props.hintSquare).toBeNull();
    expect(panelTitle()).toBe('Puzzle 2 · 461');
    input.remove();
  });

  it('S reveals, ←/→ step the solution, R resets; buttons advertise their keys', async () => {
    vi.useFakeTimers();
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Retry mistakes (2)' }));
    expect(screen.getByRole('button', { name: 'Hint' }).getAttribute('aria-keyshortcuts')).toBe('H');
    expect(screen.getByRole('button', { name: 'Exit' }).getAttribute('title')).toBe('Exit (Esc)');
    key('s');
    act(() => { vi.advanceTimersByTime(SOLUTION_PLY_MS); });
    expect(screen.getByText('2 / 2')).toBeTruthy();
    key('ArrowLeft');
    expect(screen.getByText('1 / 2')).toBeTruthy();
    key('ArrowRight');
    expect(screen.getByText('2 / 2')).toBeTruthy();
    key('r');
    expect(board.props.movable).toBe(true);
  });

  it('Analyze opens the current position on the analysis board in a new tab', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Retry mistakes (2)' }));
    const link = screen.getByRole('link', { name: 'Analyze' });
    const fen = applyUci(MATE1.fen, MATE1.moves[0])!.fen;
    expect(link.getAttribute('href')).toBe(analyzeHref(fen));
    expect(link.getAttribute('href')).toContain(encodeURIComponent(fen));
    expect(link.getAttribute('target')).toBe('_blank');
  });

  it('plays the error sound on a wrong move, move + success when solved', async () => {
    vi.useFakeTimers();
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Retry mistakes (2)' }));
    play('g1', 'h1');
    expect(sound.play.mock.calls).toEqual([['error']]);
    act(() => { vi.advanceTimersByTime(WRONG_HOLD_MS); });
    sound.play.mockClear();
    play('a1', 'a5'); // illegal: silent
    expect(sound.play).not.toHaveBeenCalled();
    play('d1', 'd8');
    expect(sound.play.mock.calls).toEqual([['move'], ['success']]);
  });
});
