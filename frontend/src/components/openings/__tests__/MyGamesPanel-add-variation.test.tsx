// @vitest-environment jsdom
//
// The "Add variation" button sits beside Add Game in owner mode and hands off
// to the parent (which opens a fresh board tab); shared modes hide it.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React from 'react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: () => Promise.resolve('clerk-tok') }),
}));

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

vi.mock('@/hooks/useUserGames', () => ({
  useUserGames: () => ({
    games: [], total: 0, page: 1, perPage: 20, loading: false, error: null,
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

import { apiFetch } from '@/lib/api';
import MyGamesPanel from '../MyGamesPanel';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockApiFetch.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('MyGamesPanel — Add variation', () => {
  it('renders beside Add Game and calls onAddVariation', () => {
    const onAddVariation = vi.fn();
    render(<MyGamesPanel onOpenGame={vi.fn()} onAddVariation={onAddVariation} />);

    expect(screen.getByText('myGames.addGame')).toBeTruthy();
    fireEvent.click(screen.getByText('myGames.addVariation'));
    expect(onAddVariation).toHaveBeenCalledTimes(1);
  });

  it('is hidden without a handler', () => {
    render(<MyGamesPanel onOpenGame={vi.fn()} />);
    expect(screen.queryByText('myGames.addVariation')).toBeNull();
  });

  it('is hidden in shared database mode', async () => {
    mockApiFetch.mockResolvedValueOnce({ database: { id: 'd', name: 'D', game_count: 0 }, games: [] });
    render(<MyGamesPanel sharedDatabaseToken="tok" onOpenGame={vi.fn()} onAddVariation={vi.fn()} />);
    expect(await screen.findByText('myGames.copyShared')).toBeTruthy();
    expect(screen.queryByText('myGames.addVariation')).toBeNull();
  });

  it('is hidden in shared collection mode', () => {
    mockApiFetch.mockResolvedValue({ games: [], total: 0, page: 1, per_page: 20 });
    render(<MyGamesPanel sharedToken="tok" onOpenGame={vi.fn()} onAddVariation={vi.fn()} />);
    expect(screen.queryByText('myGames.addVariation')).toBeNull();
  });
});
