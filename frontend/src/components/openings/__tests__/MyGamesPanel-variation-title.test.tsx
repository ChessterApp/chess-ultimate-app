// @vitest-environment jsdom
//
// Saved variations list in the Analysis section (title or the untitled
// fallback); the Games table only holds regular games.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';
import React from 'react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'en',
}));

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: () => Promise.resolve('clerk-tok') }),
}));

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

const base = {
  user_id: 'u', white_elo: null, black_elo: null, date: null, eco: null, opening_name: null,
  pgn: '1. e4', notes: null, tags: [], is_favorite: false, source: 'board_entry', created_at: '', updated_at: '',
};
const variations = [
  { ...base, id: 'v1', title: 'Najdorf idea', white: '?', black: '?', result: '*', event: 'Variation' },
  { ...base, id: 'v2', title: null, white: '?', black: '?', result: '*', event: 'Variation' },
];
const regular = [
  { ...base, id: 'n1', title: null, white: 'Carlsen', black: 'Nepo', result: '1-0', event: 'WCh' },
];

const fetchGames = vi.fn();
vi.mock('@/hooks/useUserGames', () => ({
  useUserGames: (_db?: string, kind?: string) => {
    const games = kind === 'analysis' ? variations : regular;
    return {
      games, total: games.length, page: 1, perPage: 20, loading: false, error: null,
      fetchGames, createGame: vi.fn(), updateGame: vi.fn(),
      deleteGame: vi.fn(), toggleFavorite: vi.fn(),
    };
  },
}));

vi.mock('@/hooks/useDatabases', () => ({
  useDatabases: () => ({ copyShared: vi.fn() }),
}));

vi.mock('../AddGameModal', () => ({ default: () => null }));
vi.mock('../EditGameModal', () => ({ default: () => null }));
vi.mock('../ShareMyGameButton', () => ({ default: () => null }));
vi.mock('../ShareMyGamesButton', () => ({ default: () => null }));

import MyGamesPanel from '../MyGamesPanel';

afterEach(() => cleanup());

describe('MyGamesPanel — Analysis / Games split', () => {
  it('lists variations under Analysis and keeps them out of the Games table', () => {
    render(<MyGamesPanel onOpenGame={vi.fn()} />);
    expect(screen.getByText('myGames.analysis')).toBeTruthy();
    expect(screen.getByText('myGames.games')).toBeTruthy();
    expect(screen.getByText('Najdorf idea')).toBeTruthy();
    expect(screen.getByText('myGames.untitledVariation')).toBeTruthy();

    const table = screen.getByRole('table');
    expect(within(table).queryByText('Najdorf idea')).toBeNull();
    expect(within(table).queryAllByText('?')).toHaveLength(0);
    // Normal games keep their player columns
    expect(within(table).getByText('Carlsen')).toBeTruthy();
    expect(within(table).getByText('Nepo')).toBeTruthy();
  });

  it('fetches each section with its own kind', () => {
    render(<MyGamesPanel onOpenGame={vi.fn()} />);
    const kinds = fetchGames.mock.calls.map((c) => (c[2] as { kind?: string }).kind);
    expect(kinds).toContain('games');
    expect(kinds).toContain('analysis');
  });
});
