/**
 * @vitest-environment jsdom
 *
 * OpponentAnalysisPage URL/history sync: the selected player and game are
 * mirrored to `?player=&game=` via the shared usePhaseHistory hook, so each
 * drill-down (search → profile → replay) is a history entry the Back button
 * can step through, deep links restore the view, and invalid params fall back
 * to search gracefully. Child components and the API layer are stubbed so the
 * test targets the page's own state/URL/restore logic.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent, act, waitFor } from '@testing-library/react';

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock('next-intl', () => ({
  useTranslations: () => (k: string) => k,
}));

vi.mock('@/lib/api', () => {
  class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
    }
  }
  return { apiFetch: apiFetchMock, ApiError };
});

vi.mock('@/components/ToastProvider', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

vi.mock('@/components/LoadingScreen', () => ({
  default: ({ isVisible }: { isVisible: boolean }) =>
    isVisible ? <div data-testid="loading" /> : null,
}));

vi.mock('@/components/RateLimitNotice', () => ({ default: () => null }));
vi.mock('@/components/opponent/PlayerProfile', () => ({
  default: () => <div data-testid="profile" />,
}));
vi.mock('@/components/opponent/GameFilters', () => ({ default: () => null }));
vi.mock('@/components/opponent/OpeningAnalysis', () => ({ default: () => null }));
vi.mock('@/components/opponent/FrequentOpponents', () => ({ default: () => null }));
vi.mock('@/components/opponent/DatabaseStatus', () => ({ default: () => null }));

vi.mock('@/components/opponent/PlayerSearch', () => ({
  default: ({ onSelect }: { onSelect: (name: string) => void }) => (
    <button data-testid="search-select" onClick={() => onSelect('Magnus Carlsen')}>
      select player
    </button>
  ),
}));

vi.mock('@/components/opponent/GamesList', () => ({
  default: ({ games, onSelectGame }: { games: Array<{ id: number }>; onSelectGame?: (g: unknown, pgn: string) => void }) => (
    <div>
      {games.map((g) => (
        <button
          key={g.id}
          data-testid={`game-select-${g.id}`}
          onClick={() => onSelectGame && onSelectGame(g, `PGN-${g.id}`)}
        >
          game {g.id}
        </button>
      ))}
    </div>
  ),
}));

vi.mock('@/components/opponent/GameReplayBoard', () => ({
  default: ({ onClose }: { onClose: () => void }) => (
    <div data-testid="replay">
      <button data-testid="replay-close" onClick={onClose}>close</button>
    </div>
  ),
}));

import OpponentAnalysisPage from '../page';

const PROFILE = {
  name: 'Magnus Carlsen',
  name_normalized: 'magnus carlsen',
  fide_id: null,
  title: 'GM',
  highest_elo: 2882,
  latest_elo: 2850,
  total_games: 1,
  stats: { wins_white: 1, wins_black: 0, losses_white: 0, losses_black: 0, draws: 0, win_rate: 100 },
  first_game: '2020.01.01',
  last_game: '2020.01.01',
};

const GAMES = {
  games: [
    {
      id: 101,
      white: { name: 'Magnus Carlsen', elo: 2850, title: 'GM' },
      black: { name: 'Hikaru Nakamura', elo: 2800, title: 'GM' },
      result: '1-0',
      date: '2020.01.01',
      eco: 'B90',
      opening: 'Sicilian',
      event: 'Test Open',
      site: 'x',
    },
  ],
  pagination: { total: 1, page: 1 },
};

// Default handler: routes by URL. `?player=Ghost` profiles reject (invalid).
function defaultHandler(url: string) {
  if (url.includes('/status')) return Promise.resolve({ ready: true, game_count: 1, player_count: 1, indexed_at: null, message: 'ok' });
  if (url.includes('Ghost') && url.includes('/profile')) return Promise.reject(new Error('not found'));
  if (url.includes('/profile')) return Promise.resolve(PROFILE);
  if (url.includes('/games')) return Promise.resolve(GAMES);
  if (url.includes('/openings')) return Promise.resolve({ openings: [] });
  if (url.includes('/opponents')) return Promise.resolve({ opponents: [] });
  if (url.includes('/pgn')) return Promise.resolve({ pgn: 'PGN-101' });
  return Promise.resolve({});
}

describe('OpponentAnalysisPage URL history sync', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/opponent');
    apiFetchMock.mockReset();
    apiFetchMock.mockImplementation((url: string) => defaultHandler(url));
  });

  afterEach(() => {
    cleanup();
  });

  it('mirrors drill-downs to the URL and pushes a history entry each step', async () => {
    const { getByTestId } = render(<OpponentAnalysisPage />);
    const before = window.history.length;

    // search → profile
    fireEvent.click(getByTestId('search-select'));
    await waitFor(() => expect(getByTestId('profile')).toBeTruthy());
    expect(window.location.search).toBe('?player=Magnus+Carlsen');
    expect(window.history.length).toBe(before + 1);

    // profile → replay
    await waitFor(() => expect(getByTestId('game-select-101')).toBeTruthy());
    fireEvent.click(getByTestId('game-select-101'));
    await waitFor(() => expect(getByTestId('replay')).toBeTruthy());
    expect(window.location.search).toContain('game=101');
    expect(window.history.length).toBe(before + 2);
  });

  it('steps replay → profile → search on Back (popstate)', async () => {
    const { getByTestId, queryByTestId } = render(<OpponentAnalysisPage />);

    fireEvent.click(getByTestId('search-select'));
    await waitFor(() => expect(getByTestId('game-select-101')).toBeTruthy());
    fireEvent.click(getByTestId('game-select-101'));
    await waitFor(() => expect(getByTestId('replay')).toBeTruthy());

    // Back to the profile entry (game param dropped) → replay closes.
    act(() => {
      window.history.replaceState(null, '', '/opponent?player=Magnus+Carlsen');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await waitFor(() => expect(queryByTestId('replay')).toBeNull());
    expect(getByTestId('profile')).toBeTruthy();

    // Back to the search entry (no params) → profile cleared.
    act(() => {
      window.history.replaceState(null, '', '/opponent');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await waitFor(() => expect(queryByTestId('profile')).toBeNull());
    expect(getByTestId('search-select')).toBeTruthy();
  });

  it('the replay close button steps back to the profile', async () => {
    const { getByTestId, queryByTestId } = render(<OpponentAnalysisPage />);

    fireEvent.click(getByTestId('search-select'));
    await waitFor(() => expect(getByTestId('game-select-101')).toBeTruthy());
    fireEvent.click(getByTestId('game-select-101'));
    await waitFor(() => expect(getByTestId('replay')).toBeTruthy());

    // Close mirrors Back: it pops the replay entry via history.back(). Stub
    // back() so jsdom doesn't fire a stray popstate into the next test; drive
    // the browser's popstate response manually instead.
    const backSpy = vi.spyOn(window.history, 'back').mockImplementation(() => {});
    fireEvent.click(getByTestId('replay-close'));
    expect(backSpy).toHaveBeenCalled();
    act(() => {
      window.history.replaceState(null, '', '/opponent?player=Magnus+Carlsen');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await waitFor(() => expect(queryByTestId('replay')).toBeNull());
    expect(getByTestId('profile')).toBeTruthy();
    backSpy.mockRestore();
  });

  it('restores the profile and replay from a deep link on load', async () => {
    window.history.replaceState(null, '', '/opponent?player=Magnus+Carlsen&game=101');
    const { getByTestId } = render(<OpponentAnalysisPage />);

    await waitFor(() => expect(getByTestId('profile')).toBeTruthy());
    await waitFor(() => expect(getByTestId('replay')).toBeTruthy());
  });

  it('falls back to search when the deep-linked player cannot be loaded', async () => {
    window.history.replaceState(null, '', '/opponent?player=Ghost');
    const { getByTestId, queryByTestId } = render(<OpponentAnalysisPage />);

    // Profile fetch rejects → no crash, loading resolves, search stays visible.
    await waitFor(() => expect(queryByTestId('loading')).toBeNull());
    expect(queryByTestId('profile')).toBeNull();
    expect(getByTestId('search-select')).toBeTruthy();
  });

  it('stays on the profile when a deep-linked game id is not in the list', async () => {
    window.history.replaceState(null, '', '/opponent?player=Magnus+Carlsen&game=999');
    const { getByTestId, queryByTestId } = render(<OpponentAnalysisPage />);

    await waitFor(() => expect(getByTestId('profile')).toBeTruthy());
    await waitFor(() => expect(getByTestId('game-select-101')).toBeTruthy());
    expect(queryByTestId('replay')).toBeNull();
  });
});
