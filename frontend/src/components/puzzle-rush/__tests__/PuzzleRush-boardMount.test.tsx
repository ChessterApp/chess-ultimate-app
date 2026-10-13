/**
 * @vitest-environment jsdom
 *
 * Each phase gets its own board instance. The menu board and the run board sit
 * at different screen positions; reusing the menu's chessground for the run
 * left its cached bounds stale, so desktop clicks missed their squares.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React, { useEffect, useState } from 'react';
import { cleanup, render, screen, fireEvent, act } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import { initialRunState } from '@/lib/puzzle-rush/runReducer';

const boards = vi.hoisted(() => ({ mounted: [] as number[], unmounted: [] as number[], next: 0 }));

vi.mock('@clerk/nextjs', () => ({ useAuth: () => ({ isSignedIn: false, getToken: async () => null, userId: null }) }));
vi.mock('next/dynamic', () => ({
  default: () => () => {
    const [id] = useState(() => ++boards.next);
    useEffect(() => {
      boards.mounted.push(id);
      return () => { boards.unmounted.push(id); };
    }, [id]);
    return <div data-testid="cg-board" data-board-id={id} />;
  },
}));
vi.mock('canvas-confetti', () => ({ default: vi.fn() }));
vi.mock('../fonts', () => ({ fraunces: { variable: 'font-fraunces' } }));

const MENU = initialRunState('5min');
const auth = async () => null;

vi.mock('@/hooks/usePuzzleRush', () => ({
  usePuzzleRush: () => {
    const [state, setState] = useState(MENU);
    return {
      state,
      tiles: [],
      review: [],
      countdown: null,
      showResults: false,
      closeResults: vi.fn(),
      isPb: false,
      isGuest: true,
      guestBest: null,
      ranksPending: false,
      recorded: false,
      start: () => setState({ ...MENU, phase: 'countdown' as const }),
      onMove: vi.fn(),
      quit: vi.fn(),
      reset: vi.fn(),
      auth,
    };
  },
}));

import PuzzleRush from '../PuzzleRush';

beforeEach(() => {
  boards.mounted.length = 0;
  boards.unmounted.length = 0;
  localStorage.clear();
  localStorage.setItem('puzzleRush.rulesSeen', '1');
  global.fetch = vi.fn(async () => new Response('{}', { status: 200 })) as unknown as typeof fetch;
});
afterEach(() => cleanup());

describe('PuzzleRush page — board instances', () => {
  it('starting a run mounts a fresh board instead of reusing the menu board', async () => {
    await act(async () => {
      render(<NextIntlClientProvider locale="en" messages={en}><PuzzleRush /></NextIntlClientProvider>);
    });
    const menuId = screen.getByTestId('cg-board').dataset.boardId;
    expect(boards.mounted).toEqual([Number(menuId)]);

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Start/ })); });

    const runId = screen.getByTestId('cg-board').dataset.boardId;
    expect(runId).not.toBe(menuId);
    expect(boards.unmounted).toEqual([Number(menuId)]);
  });
});
