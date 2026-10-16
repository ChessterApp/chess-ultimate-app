// @vitest-environment jsdom
//
// Variation rows in My Games show the title in place of the player columns.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: () => Promise.resolve('clerk-tok') }),
}));

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

const base = {
  user_id: 'u', white_elo: null, black_elo: null, date: null, eco: null, opening_name: null,
  pgn: '1. e4', notes: null, tags: [], is_favorite: false, source: 'board_entry', created_at: '', updated_at: '',
};
const games = [
  { ...base, id: 'v1', title: 'Najdorf idea', white: '?', black: '?', result: '*', event: 'Variation' },
  { ...base, id: 'v2', title: null, white: '?', black: '?', result: '*', event: 'Variation' },
  { ...base, id: 'n1', title: null, white: 'Carlsen', black: 'Nepo', result: '1-0', event: 'WCh' },
];

vi.mock('@/hooks/useUserGames', () => ({
  useUserGames: () => ({
    games, total: games.length, page: 1, perPage: 20, loading: false, error: null,
    fetchGames: vi.fn(), createGame: vi.fn(), updateGame: vi.fn(),
    deleteGame: vi.fn(), toggleFavorite: vi.fn(),
  }),
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

describe('MyGamesPanel — variation rows', () => {
  it('shows the title (or the untitled fallback) instead of the players', () => {
    render(<MyGamesPanel onOpenGame={vi.fn()} />);
    expect(screen.getByText('Najdorf idea')).toBeTruthy();
    expect(screen.getByText('myGames.untitledVariation')).toBeTruthy();
    expect(screen.queryAllByText('?')).toHaveLength(0);
    // Normal games keep their player columns
    expect(screen.getByText('Carlsen')).toBeTruthy();
    expect(screen.getByText('Nepo')).toBeTruthy();
  });
});
