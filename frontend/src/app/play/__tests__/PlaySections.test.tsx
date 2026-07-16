/**
 * @vitest-environment jsdom
 *
 * PlayPage sections (phase 6): the bot selection screen is split into two
 * clearly labeled, localized sections — "Play the bots" (always) and "Play a
 * friend" (only when ONLINE_PLAY_ENABLED). This test drives the flag on/off and
 * backs next-intl with the real English catalog so header copy is asserted
 * against real localized strings.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

vi.mock('next/font/google', () => ({
  Fredoka: () => ({ style: { fontFamily: 'Fredoka' }, variable: 'fredoka', className: 'fredoka' }),
  Nunito: () => ({ style: { fontFamily: 'Nunito' }, variable: 'nunito', className: 'nunito' }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// Real English `bots` catalog behind next-intl so section headers resolve to
// the actual localized strings.
vi.mock('next-intl', async () => {
  const en = (await import('../../../../messages/en.json')).default as Record<string, unknown>;
  const bots = (en as { bots: Record<string, unknown> }).bots;
  const walk = (key: string): unknown =>
    key.split('.').reduce<unknown>((cur, p) => (cur as Record<string, unknown> | undefined)?.[p], bots);
  const useTranslations = () => {
    const t = (key: string, values?: Record<string, string | number>) => {
      const v = walk(key);
      return typeof v === 'string'
        ? v.replace(/\{(\w+)\}/g, (_m, k) => String(values?.[k] ?? ''))
        : key;
    };
    (t as unknown as { has: (k: string) => boolean }).has = (key: string) =>
      typeof walk(key) === 'string';
    return t;
  };
  return { useTranslations };
});

vi.mock('@/hooks/useMaia', () => ({
  useMaia: () => ({
    status: 'ready',
    error: null,
    evaluatePosition: vi.fn(),
    downloadModel: vi.fn(),
    usingServerFallback: false,
  }),
}));

vi.mock('@/hooks/useStockfishPlay', () => ({
  useStockfishPlay: () => ({ status: 'ready', error: null, getMove: vi.fn() }),
}));

vi.mock('@/lib/analytics/events', () => ({
  ANALYTICS_EVENTS: { PLAY_ENGINE_WAIT: 'play_engine_wait' },
  track: vi.fn(),
}));

// BotGrid + in-game chrome are irrelevant to section layout; stub them out.
vi.mock('@/components/play/BotGrid', () => ({ default: () => <div data-testid="bot-grid" /> }));
vi.mock('@/components/play/GameSetup', () => ({ default: () => null }));
vi.mock('@/components/play/GameHeader', () => ({ default: () => null }));
vi.mock('@/components/play/GameDock', () => ({ default: () => null }));
vi.mock('@/components/play/GameEndModal', () => ({ default: () => null }));
vi.mock('@/components/chess/ChessgroundBoard', () => ({ default: () => null }));

async function renderWithFlag(enabled: boolean) {
  vi.resetModules();
  vi.doMock('@/lib/feature-flags', () => ({ ONLINE_PLAY_ENABLED: enabled }));
  const { default: PlayPage } = await import('../page');
  return render(<PlayPage />);
}

afterEach(() => {
  cleanup();
  vi.resetModules();
});

describe('PlayPage sections', () => {
  it('flag ON: shows both localized section headers and the friend card', async () => {
    const { getByText, getByTestId } = await renderWithFlag(true);
    expect(getByText('Play the bots')).toBeTruthy();
    expect(getByText('Play a friend')).toBeTruthy();
    expect(getByTestId('play-friend-card')).toBeTruthy();
  });

  it('flag OFF: shows the bots section but no friend section at all', async () => {
    const { getByText, queryByText, queryByTestId } = await renderWithFlag(false);
    expect(getByText('Play the bots')).toBeTruthy();
    expect(queryByText('Play a friend')).toBeNull();
    expect(queryByTestId('play-friend-card')).toBeNull();
  });
});
