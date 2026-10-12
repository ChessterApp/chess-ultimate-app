/**
 * @vitest-environment jsdom
 *
 * Puzzle Rush UI: results modal PB / tough states, the ✓/✕ results grid, the
 * mode preselect on the real page component, and en/ru/kz key coverage.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render, screen, fireEvent, within, act } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import ru from '../../../../messages/ru.json';
import kz from '../../../../messages/kz.json';

vi.mock('@clerk/nextjs', () => ({ useAuth: () => ({ isSignedIn: false, getToken: async () => null, userId: null }) }));
vi.mock('next/dynamic', () => ({ default: () => () => <div data-testid="cg-board" /> }));
vi.mock('canvas-confetti', () => ({ default: vi.fn() }));
vi.mock('../fonts', () => ({ fraunces: { variable: 'font-fraunces' } }));

import ResultsModal, { resultTone } from '../ResultsModal';
import { ResultsGrid } from '../RunTiles';
import PuzzleRush from '../PuzzleRush';

const RESULTS = {
  score: 14,
  is_new_pb: true,
  longest_streak: 9,
  highest_solved_rating: 1532,
  avg_ms_per_puzzle: 6400,
  duration_ms: 180000,
  personal_rank: 1,
  global_rank: { daily: 3, weekly: 12, all: 87 },
};

function withIntl(node: React.ReactNode, locale = 'en', messages: Record<string, unknown> = en) {
  return render(<NextIntlClientProvider locale={locale} messages={messages}>{node}</NextIntlClientProvider>);
}

function modal(props: Partial<React.ComponentProps<typeof ResultsModal>> = {}) {
  const handlers = { onPlayAgain: vi.fn(), onNewRush: vi.fn(), onClose: vi.fn() };
  withIntl(
    <ResultsModal
      mode="3min"
      score={14}
      results={RESULTS}
      endReason="timeout"
      isPb
      isGuest={false}
      signInHref="/sign-in"
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

beforeEach(() => {
  localStorage.clear();
  global.fetch = vi.fn(async () => new Response('{}', { status: 200 })) as unknown as typeof fetch;
});
afterEach(() => cleanup());

describe('ResultsModal', () => {
  it('PB: "New Personal Best!" on the teal header with ranks and stats', () => {
    modal();
    const dialog = screen.getByTestId('rush-results');
    expect(dialog.dataset.tone).toBe('pb');
    expect(screen.getByRole('heading', { name: 'New Personal Best!' })).toBeTruthy();
    expect(within(dialog).getByText('#1')).toBeTruthy();
    expect(within(dialog).getByText('#3')).toBeTruthy();
    expect(within(dialog).getByText('#87')).toBeTruthy();
    expect(within(dialog).getByText('1532')).toBeTruthy();
    expect(within(dialog).getByText('0:06')).toBeTruthy();
    expect(screen.getByText("Time's up · 3 Minutes")).toBeTruthy();
  });

  it('low non-PB score gets the red "Tough One" header', () => {
    modal({ isPb: false, score: 3, results: { ...RESULTS, is_new_pb: false, score: 3 } });
    expect(screen.getByTestId('rush-results').dataset.tone).toBe('tough');
    expect(screen.getByRole('heading', { name: 'Tough One' })).toBeTruthy();
  });

  it('guests see their on-device bests in the tiles (never ranks) and a sign-in prompt', () => {
    modal({
      isGuest: true,
      isPb: true,
      results: { ...RESULTS, is_new_pb: false, personal_rank: null, global_rank: null },
      guestBests: { top_score: 14, best_today: 14, top_run_id: null, achieved_at: null },
    });
    const cells = screen.getByTestId('rush-ranks').querySelectorAll('[class*="rankValue"]');
    expect([...cells].map((c) => c.textContent)).toEqual(['14', '14', '14']);
    expect(screen.getByRole('heading', { name: 'New Personal Best!' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Sign in to save scores' }).getAttribute('href')).toBe('/sign-in');
  });

  it('guest run below the device best: no PB title, tiles show the standing bests', () => {
    modal({
      isGuest: true,
      isPb: false,
      score: 12,
      results: { ...RESULTS, score: 12, is_new_pb: false, personal_rank: null, global_rank: null },
      guestBests: { top_score: 30, best_today: 12, top_run_id: null, achieved_at: null },
    });
    expect(screen.getByTestId('rush-results').dataset.tone).toBe('great');
    expect(screen.queryByRole('heading', { name: 'New Personal Best!' })).toBeNull();
    const cells = screen.getByTestId('rush-ranks').querySelectorAll('[class*="rankValue"]');
    expect([...cells].map((c) => c.textContent)).toEqual(['30', '12', '30']);
  });

  it('signed-in ranks show a placeholder while /runs/finish is in flight', () => {
    modal({ isPb: false, results: { ...RESULTS, is_new_pb: false, personal_rank: null, global_rank: null }, ranksPending: true });
    const cells = screen.getByTestId('rush-ranks').querySelectorAll('[class*="rankValue"]');
    expect([...cells].map((c) => c.textContent)).toEqual(['…', '…', '…']);
    expect(screen.getByTestId('rush-results').dataset.tone).toBe('great');
  });

  it('focuses Play Again on the frame after the first paint (not during the commit)', async () => {
    modal();
    const button = screen.getByRole('button', { name: 'Play Again' });
    expect(document.activeElement).not.toBe(button);
    await act(async () => { await new Promise((r) => requestAnimationFrame(() => r(null))); });
    expect(document.activeElement).toBe(button);
  });

  it('Enter plays again, Esc closes', () => {
    const h = modal();
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(h.onPlayAgain).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(h.onClose).toHaveBeenCalledTimes(1);
  });

  it('resultTone thresholds', () => {
    expect(resultTone(0, false)).toBe('tough');
    expect(resultTone(10, false)).toBe('great');
    expect(resultTone(3, true)).toBe('pb');
  });
});

describe('ResultsGrid', () => {
  const tiles = [
    { index: 0, rating: 400, solved: true },
    { index: 1, rating: 461, solved: false },
    { index: 2, rating: 523, solved: true },
  ];

  it('renders one ✓/✕ tile per finished puzzle with its rating', () => {
    withIntl(<ResultsGrid tiles={tiles} />);
    const grid = screen.getByTestId('rush-grid');
    const cells = grid.querySelectorAll('[data-result]');
    expect([...cells].map((c) => c.getAttribute('data-result'))).toEqual(['solved', 'failed', 'solved']);
    expect(within(grid).getByText('461')).toBeTruthy();
    expect(within(grid).getAllByText('✓')).toHaveLength(2);
    expect(within(grid).getAllByText('✕')).toHaveLength(1);
    // In-run tiles are not interactive.
    expect(within(grid).queryAllByRole('button')).toHaveLength(0);
  });

  it('summary tiles are clickable for review', () => {
    const onSelect = vi.fn();
    withIntl(<ResultsGrid tiles={tiles} summary onSelect={onSelect} puzzleLabel={(n) => `Puzzle ${n}`} />);
    fireEvent.click(screen.getByRole('button', { name: 'Puzzle 2' }));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it('renders nothing before the first puzzle is finished', () => {
    withIntl(<ResultsGrid tiles={[]} />);
    expect(screen.queryByTestId('rush-grid')).toBeNull();
  });
});

describe('PuzzleRush page — mode select', () => {
  it('lists 3 min / 5 min / Survival in order and preselects 5 min by default', async () => {
    localStorage.setItem('puzzleRush.rulesSeen', '1');
    await act(async () => { withIntl(<PuzzleRush />); });
    const radios = screen.getAllByRole('radio');
    expect(radios.map((r) => r.getAttribute('data-mode'))).toEqual(['3min', '5min', 'survival']);
    expect(screen.getByRole('radio', { checked: true }).getAttribute('data-mode')).toBe('5min');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('preselects the last-played mode and shows the rules on first visit', async () => {
    localStorage.setItem('puzzleRush.lastMode', 'survival');
    await act(async () => { withIntl(<PuzzleRush />); });
    expect(screen.getByRole('radio', { checked: true }).getAttribute('data-mode')).toBe('survival');
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Got it' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(localStorage.getItem('puzzleRush.rulesSeen')).toBe('1');
  });

  it('shows on-device guest bests on the mode cards', async () => {
    localStorage.setItem('puzzleRush.rulesSeen', '1');
    const d = new Date();
    const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    localStorage.setItem('puzzleRush.guestBests', JSON.stringify({ '3min': { top: 21, today: 9, day } }));
    await act(async () => { withIntl(<PuzzleRush />); });
    const card = screen.getAllByRole('radio')[0];
    expect(within(card).getByText('Best 21')).toBeTruthy();
    expect(within(card).getByText('Today 9')).toBeTruthy();
  });

  it.each([['ru', ru], ['kz', kz]] as const)('renders in %s', async (locale, messages) => {
    localStorage.setItem('puzzleRush.rulesSeen', '1');
    await act(async () => { withIntl(<PuzzleRush />, locale, messages as Record<string, unknown>); });
    const pr = (messages as { puzzleRush: { modes: { survival: { title: string } } } }).puzzleRush;
    expect(screen.getByText(pr.modes.survival.title)).toBeTruthy();
  });
});

describe('i18n coverage', () => {
  function keys(obj: unknown, prefix = ''): string[] {
    return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
      v && typeof v === 'object' ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`]);
  }
  it('ru and kz have every puzzleRush key en has', () => {
    const want = keys(en.puzzleRush).sort();
    expect(keys((ru as typeof en).puzzleRush).sort()).toEqual(want);
    expect(keys((kz as typeof en).puzzleRush).sort()).toEqual(want);
  });
});
