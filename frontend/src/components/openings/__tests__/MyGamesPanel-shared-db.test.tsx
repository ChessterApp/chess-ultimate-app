// @vitest-environment jsdom
//
// Covers the per-database shared (sdb) read-only mode of MyGamesPanel: it lists
// the shared database's games without any mutation UI and offers a
// "Copy to my workspace" CTA that hands the new owned db back to the parent.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import React from 'react';

// next-intl: echo the key so assertions stay locale-independent.
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: () => Promise.resolve('clerk-tok') }),
}));

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

// Owner-mode games hook — not exercised in shared mode, just needs to exist.
vi.mock('@/hooks/useUserGames', () => ({
  useUserGames: () => ({
    games: [], total: 0, page: 1, perPage: 20, loading: false, error: null,
    fetchGames: vi.fn(), createGame: vi.fn(), updateGame: vi.fn(),
    deleteGame: vi.fn(), toggleFavorite: vi.fn(),
  }),
}));

const copyShared = vi.fn();
vi.mock('@/hooks/useDatabases', () => ({
  useDatabases: () => ({ copyShared }),
}));

// Child modules only render in owner mode; stub them so their transitive
// imports don't load in this read-only test.
vi.mock('../AddGameModal', () => ({ default: () => null }));
vi.mock('../EditGameModal', () => ({ default: () => null }));
vi.mock('../ShareMyGameButton', () => ({ default: () => null }));
vi.mock('../ShareMyGamesButton', () => ({ default: () => null }));

import { apiFetch } from '@/lib/api';
import MyGamesPanel from '../MyGamesPanel';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

const SHARED_RESPONSE = {
  database: { id: 'db-remote', name: 'Coach Repertoire', game_count: 2 },
  owner_name: 'Coach',
  games: [
    { id: 'g1', white: 'Alice', black: 'Bob', result: '1-0', date: '2024.01.01', pgn: '1. e4 *' },
    { id: 'g2', white: 'Carol', black: 'Dan', result: '0-1', date: '2024.02.02', pgn: '1. d4 *' },
  ],
};

beforeEach(() => {
  mockApiFetch.mockReset();
  copyShared.mockReset();
});

afterEach(() => {
  // Unmount prior renders so lingering panels don't leak into later queries.
  cleanup();
});

describe('MyGamesPanel — shared database (sdb) mode', () => {
  it('lists the shared games read-only (no add/import UI)', async () => {
    mockApiFetch.mockResolvedValueOnce(SHARED_RESPONSE);
    render(<MyGamesPanel sharedDatabaseToken="tok-shared" onOpenGame={vi.fn()} />);

    expect(await screen.findByText('Alice')).toBeTruthy();
    expect(screen.getByText('Carol')).toBeTruthy();
    // Owner-only "add game" button must not render in shared mode.
    expect(screen.queryByText('myGames.addGame')).toBeNull();
    // Copy CTA is present.
    expect(screen.getByText('myGames.copyShared')).toBeTruthy();
  });

  it('copies to workspace and hands the new owned db to the parent', async () => {
    mockApiFetch.mockResolvedValueOnce(SHARED_RESPONSE);
    const newDb = { id: 'db-copy', name: 'Coach Repertoire (copy)', is_default: false, game_count: 2 };
    copyShared.mockResolvedValueOnce(newDb);
    const onCopyShared = vi.fn();

    render(<MyGamesPanel sharedDatabaseToken="tok-shared" onOpenGame={vi.fn()} onCopyShared={onCopyShared} />);
    await screen.findByText('Alice');

    fireEvent.click(screen.getByText('myGames.copyShared'));
    await waitFor(() => expect(copyShared).toHaveBeenCalledWith('tok-shared'));
    await waitFor(() => expect(onCopyShared).toHaveBeenCalledWith(newDb));
  });

  it('shows the unavailable state when the token is revoked (404)', async () => {
    mockApiFetch.mockRejectedValueOnce(Object.assign(new Error('gone'), { status: 404 }));
    render(<MyGamesPanel sharedDatabaseToken="tok-dead" onOpenGame={vi.fn()} />);

    expect(await screen.findByText('myGames.sharedUnavailable')).toBeTruthy();
    expect(screen.queryByText('myGames.copyShared')).toBeNull();
  });
});
