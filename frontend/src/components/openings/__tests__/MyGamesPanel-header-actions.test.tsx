// @vitest-environment jsdom
//
// "Add game" lives in the Games section header (owner only) and "Share database"
// sits next to the search box, sharing the selected database — hidden on the
// "All games" view and in shared read-only modes.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import React from 'react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'en',
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

vi.mock('../AddGameModal', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div data-testid="add-game-modal" /> : null),
}));
vi.mock('../EditGameModal', () => ({ default: () => null }));
vi.mock('../ShareMyGameButton', () => ({ default: () => null }));
vi.mock('../ShareMyGamesButton', () => ({
  default: ({ databaseId }: { databaseId: string }) => <button data-testid="share-db" data-db={databaseId}>share</button>,
}));

import { apiFetch } from '@/lib/api';
import MyGamesPanel from '../MyGamesPanel';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockApiFetch.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('MyGamesPanel — Add game in the Games header', () => {
  it('sits in the Games section header and opens the add-game modal', () => {
    render(<MyGamesPanel onOpenGame={vi.fn()} />);
    const gamesToggle = screen.getByText('myGames.games').closest('button')!;
    const header = gamesToggle.parentElement!;
    const addGame = within(header).getByText('myGames.addGame');

    fireEvent.click(addGame);
    expect(screen.getByTestId('add-game-modal')).toBeTruthy();
  });

  it('is hidden in shared database mode', async () => {
    mockApiFetch.mockResolvedValueOnce({ database: { id: 'd', name: 'D', game_count: 0 }, games: [] });
    render(<MyGamesPanel sharedDatabaseToken="tok" onOpenGame={vi.fn()} />);
    expect(await screen.findByText('myGames.copyShared')).toBeTruthy();
    expect(screen.queryByText('myGames.addGame')).toBeNull();
  });

  it('is hidden in shared collection mode', () => {
    mockApiFetch.mockResolvedValue({ games: [], total: 0, page: 1, per_page: 20 });
    render(<MyGamesPanel sharedToken="tok" onOpenGame={vi.fn()} />);
    expect(screen.queryByText('myGames.addGame')).toBeNull();
  });
});

describe('MyGamesPanel — Share database', () => {
  it('shares the selected database from the search row', () => {
    render(<MyGamesPanel onOpenGame={vi.fn()} databaseId="db-42" />);
    const share = screen.getByTestId('share-db');
    expect(share.getAttribute('data-db')).toBe('db-42');
    const search = screen.getByPlaceholderText('myGames.searchPlaceholder');
    expect(search.closest('.MuiTextField-root')!.parentElement!.contains(share)).toBe(true);
  });

  it('is hidden on the "All games" view', () => {
    render(<MyGamesPanel onOpenGame={vi.fn()} />);
    expect(screen.queryByTestId('share-db')).toBeNull();
  });

  it('is hidden in shared database mode', async () => {
    mockApiFetch.mockResolvedValueOnce({ database: { id: 'd', name: 'D', game_count: 0 }, games: [] });
    render(<MyGamesPanel sharedDatabaseToken="tok" databaseId="db-42" onOpenGame={vi.fn()} />);
    expect(await screen.findByText('myGames.copyShared')).toBeTruthy();
    expect(screen.queryByTestId('share-db')).toBeNull();
  });
});
