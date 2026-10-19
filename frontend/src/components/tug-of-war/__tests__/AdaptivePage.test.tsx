/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('next-intl', () => {
  const t = (k: string, v?: Record<string, unknown>) => (v ? `${k}:${JSON.stringify(v)}` : k);
  t.raw = () => [];
  return { useTranslations: () => t, useLocale: () => 'en' };
});
vi.mock('@/components/LanguageSwitcher', () => ({ default: () => null }));
vi.mock('../TugBoard', () => ({ default: () => <div data-testid="tug-board" /> }));
vi.mock('../RopeScene', () => ({ default: () => null }));
vi.mock('../BotBoard', () => ({ default: () => <div data-testid="tug-bot-board" /> }));
vi.mock('@/lib/tug-of-war/sound', () => ({
  TugSound: class {
    win() {}
    setMuted() {}
    unlock() {
      return true;
    }
  },
  loadMuted: () => true,
  saveMuted: () => {},
}));
vi.mock('@/lib/tug-of-war/confetti', () => ({
  fireWinConfetti: async () => {},
  resetConfetti: async () => {},
}));
const trackMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics/events', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics/events')>()),
  track: trackMock,
}));

import TugOfWarPage from '@/app/games/tug-of-war/page';
import { saveAdaptive } from '@/lib/tug-of-war/adaptive';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  trackMock.mockReset();
});

const packPuzzle = (i: number) => ({
  id: `p${i}`,
  fen: 'rnbk1r2/ppppn3/6pB/b3P3/3P4/2P5/PP4PP/RN3RK1 w - - 0 15',
  moves: ['f1f8'],
  rating: 1100,
  themes: [],
});

describe('Tug of War page — Adaptive', () => {
  it('starts an adaptive match from the saved estimate on a rating-targeted pack', async () => {
    saveAdaptive({ estimate: 1300, avgSeconds: 8, peakBotLevel: 'club', date: '2026-10-18T00:00:00Z' });
    const urls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        urls.push(url);
        return { ok: true, json: async () => ({ puzzles: Array.from({ length: 20 }, (_, i) => packPuzzle(i)) }) };
      }),
    );

    render(<TugOfWarPage />);
    fireEvent.click(screen.getByRole('radio', { name: /mode.bot.title/ }));
    fireEvent.click(await screen.findByTestId('zebra-adaptive'));

    await waitFor(() => expect(screen.getByTestId('tug-level-meter')).toBeTruthy());
    // Bot 1000 (1300 − 300), target 0.6·1000 + 0.4·1300 = 1120.
    const q = new URLSearchParams(urls[0].split('?')[1]);
    expect([q.get('rating'), q.get('spread'), q.get('count'), q.has('level')]).toEqual(['1120', '75', '20', false]);
    expect(screen.getByTestId('tug-bot-rank').textContent).toBe('bot.levels.club');
    expect(trackMock).toHaveBeenCalledWith('tug_of_war_started', { mode: 'bot', botMode: 'adaptive', estimate: 1300 });
  });

  it('deals a fixed rank puzzles within ±150 of its rating, tagged static', async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        urls.push(url);
        return { ok: true, json: async () => ({ puzzles: Array.from({ length: 60 }, (_, i) => packPuzzle(i)) }) };
      }),
    );
    render(<TugOfWarPage />);
    fireEvent.click(screen.getByRole('radio', { name: /mode.bot.title/ }));
    fireEvent.click(screen.getByTestId('zebra-expert'));
    await waitFor(() => expect(screen.getByTestId('tug-bot-rank')).toBeTruthy());
    const q = new URLSearchParams(urls[0].split('?')[1]);
    expect([q.get('rating'), q.get('spread'), q.get('count'), q.has('level')]).toEqual(['1400', '150', '60', false]);
    expect(screen.queryByTestId('tug-level-meter')).toBeNull();
    expect(trackMock).toHaveBeenCalledWith('tug_of_war_started', {
      mode: 'bot',
      botMode: 'static',
      botLevel: 'expert',
    });
  });
});
