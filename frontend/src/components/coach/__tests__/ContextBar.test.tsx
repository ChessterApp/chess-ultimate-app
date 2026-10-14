/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import en from '../../../../messages/en.json';

const router = vi.hoisted(() => ({ back: vi.fn(), push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => router }));

import ContextBar, { exitTarget, type ContextMenuActions } from '../ContextBar';

const coach = en.coach;

function menu(overrides: Partial<ContextMenuActions> = {}): ContextMenuActions {
  return {
    onPlay: vi.fn(),
    onImport: vi.fn(),
    onFlip: vi.fn(),
    onBoardTabs: vi.fn(),
    onNewSession: vi.fn(),
    ...overrides,
  };
}

function renderBar(actions: ContextMenuActions, onOpenSessions = vi.fn()) {
  render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <ContextBar title="Sicilian Defence" subtitle="Analysis" sessionsOpen={false} onOpenSessions={onOpenSessions} menu={actions} />
    </NextIntlClientProvider>,
  );
}

function openMenu() {
  fireEvent.click(screen.getByRole('button', { name: coach.moreActions }));
  return screen.getByRole('menu');
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ContextBar', () => {
  it('shows the session title and opens the sessions sheet from it', () => {
    const onOpenSessions = vi.fn();
    renderBar(menu(), onOpenSessions);
    expect(screen.getByText('Sicilian Defence')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Sessions: Sicilian Defence' }));
    expect(onOpenSessions).toHaveBeenCalledOnce();
  });

  it('runs each ⋯ menu action and closes the menu', () => {
    const actions = menu();
    renderBar(actions);
    const cases: Array<[string, keyof ContextMenuActions]> = [
      [coach.playWithCoach, 'onPlay'],
      [coach.importGame, 'onImport'],
      [coach.flipBoard, 'onFlip'],
      [coach.viewerTabs, 'onBoardTabs'],
      [coach.newSession, 'onNewSession'],
    ];
    for (const [label, key] of cases) {
      fireEvent.click(within(openMenu()).getByRole('menuitem', { name: label }));
      expect(actions[key]).toHaveBeenCalledOnce();
      expect(screen.queryByRole('menu')).toBeNull();
    }
  });

  it('greys out «Play the coach» during a game and hides «Board tabs» without opened games', () => {
    renderBar(menu({ onPlay: null, onBoardTabs: null }));
    const m = openMenu();
    expect((within(m).getByRole('menuitem', { name: coach.playWithCoach }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(m).queryByRole('menuitem', { name: coach.viewerTabs })).toBeNull();
  });

  it('Escape closes the menu', () => {
    renderBar(menu());
    openMenu();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('has no duplicated «New session» outside the menu, and 44px targets', () => {
    renderBar(menu());
    expect(screen.queryByText(coach.newSession)).toBeNull();
    for (const name of [coach.exitCoach, coach.moreActions]) {
      expect(screen.getByRole('button', { name }).className).toContain('h-11 w-11');
    }
  });

  it('✕ goes back within the app, else to the dashboard', () => {
    renderBar(menu());
    fireEvent.click(screen.getByRole('button', { name: coach.exitCoach }));
    // jsdom: a single history entry → the dashboard.
    expect(router.push).toHaveBeenCalledWith('/dashboard');
  });
});

describe('exitTarget', () => {
  const origin = 'https://chesster.io';
  it('goes back to a page of ours', () => {
    expect(exitTarget({ historyLength: 3, referrer: '', origin })).toBe('back');
    expect(exitTarget({ historyLength: 3, referrer: 'https://chesster.io/dashboard', origin })).toBe('back');
  });
  it('goes to the dashboard when the coach was the first page or came from elsewhere', () => {
    expect(exitTarget({ historyLength: 1, referrer: '', origin })).toBe('dashboard');
    expect(exitTarget({ historyLength: 2, referrer: 'https://t.me/', origin })).toBe('dashboard');
  });
});
