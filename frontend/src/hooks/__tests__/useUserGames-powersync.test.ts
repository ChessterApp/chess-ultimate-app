/**
 * @vitest-environment jsdom
 *
 * Tests for useUserGames in both legacy and PowerSync modes.
 * The legacy mode tests are in useUserGames.test.ts.
 * This file tests the PowerSync integration path.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// ─── Feature flag mock ──────────────────

let mockLocalFirstGames = true;
vi.mock('@/lib/feature-flags', () => ({
  get LOCAL_FIRST_GAMES() { return mockLocalFirstGames; },
}));

// ─── Clerk mock ─────────────────────────

const mockGetToken = vi.fn().mockResolvedValue('test-token');
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({
    getToken: mockGetToken,
    userId: 'user-123',
  }),
}));

// ─── API mock ───────────────────────────

const mockApiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
}));

// ─── PowerSync context mock ─────────────

const mockExecute = vi.fn();
const mockDatabase = { execute: mockExecute };
const mockCollections = {
  userGames: { id: 'user-games-collection' },
};

vi.mock('@/lib/powersync/PowerSyncProvider', () => ({
  usePowerSyncContext: () => ({
    database: mockDatabase,
    collections: mockCollections,
    isReady: true,
  }),
}));

// ─── useLiveQuery mock ──────────────────

const mockLiveQueryData = vi.fn().mockReturnValue([]);
vi.mock('@tanstack/react-db', () => ({
  useLiveQuery: () => ({
    data: mockLiveQueryData(),
    isLoading: false,
    isReady: true,
  }),
}));

vi.mock('@tanstack/db', () => ({
  eq: vi.fn(),
}));

import { useUserGames } from '../useUserGames';
import type { UserGame } from '../useUserGames';

// ─── Fixtures ───────────────────────────

const GAME_ROW = {
  id: 'game-1',
  user_id: 'user-123',
  title: 'Test Game',
  white: 'Magnus',
  black: 'Hikaru',
  white_elo: 2800,
  black_elo: 2750,
  result: '1-0',
  date: '2024-06-01',
  event: 'Blitz',
  eco: 'C50',
  opening_name: 'Italian Game',
  pgn: '1. e4 e5 *',
  notes: null,
  tags: '["blitz"]',
  is_favorite: 0,
  source: 'manual',
  created_at: '2024-06-01T10:00:00Z',
  updated_at: '2024-06-01T10:00:00Z',
};

// ─── Tests ──────────────────────────────

describe('useUserGames (PowerSync mode)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocalFirstGames = true;
    mockLiveQueryData.mockReturnValue([]);
    mockGetToken.mockResolvedValue('test-token');
  });

  it('should return empty games when live query has no data', () => {
    const { result } = renderHook(() => useUserGames());
    expect(result.current.games).toEqual([]);
    expect(result.current.total).toBe(0);
  });

  it('should return games from live query with correct type conversion', () => {
    mockLiveQueryData.mockReturnValue([GAME_ROW]);

    const { result } = renderHook(() => useUserGames());

    expect(result.current.games).toHaveLength(1);
    const game = result.current.games[0];
    expect(game.id).toBe('game-1');
    expect(game.white).toBe('Magnus');
    expect(game.tags).toEqual(['blitz']);
    expect(game.is_favorite).toBe(false);
    expect(result.current.total).toBe(1);
  });

  it('should convert is_favorite integer to boolean', () => {
    mockLiveQueryData.mockReturnValue([{ ...GAME_ROW, is_favorite: 1 }]);

    const { result } = renderHook(() => useUserGames());
    expect(result.current.games[0].is_favorite).toBe(true);
  });

  it('should parse JSON tags', () => {
    mockLiveQueryData.mockReturnValue([{ ...GAME_ROW, tags: '["rapid","tactics"]' }]);

    const { result } = renderHook(() => useUserGames());
    expect(result.current.games[0].tags).toEqual(['rapid', 'tactics']);
  });

  it('should handle invalid JSON tags gracefully', () => {
    mockLiveQueryData.mockReturnValue([{ ...GAME_ROW, tags: 'not-json' }]);

    const { result } = renderHook(() => useUserGames());
    expect(result.current.games[0].tags).toEqual([]);
  });

  it('fetchGames should return current data (no-op in PowerSync mode)', async () => {
    mockLiveQueryData.mockReturnValue([GAME_ROW]);

    const { result } = renderHook(() => useUserGames());

    let response: any;
    await act(async () => {
      response = await result.current.fetchGames();
    });

    expect(response.games).toHaveLength(1);
    expect(response.total).toBe(1);
  });

  it('should find a game locally via getGame', async () => {
    mockLiveQueryData.mockReturnValue([GAME_ROW]);

    const { result } = renderHook(() => useUserGames());

    let game: UserGame | null = null;
    await act(async () => {
      game = await result.current.getGame('game-1');
    });

    expect(game).not.toBeNull();
    expect(game!.id).toBe('game-1');
    // Should NOT call API
    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it('should fallback to API for getGame when not in local store', async () => {
    mockLiveQueryData.mockReturnValue([]);
    mockApiFetch.mockResolvedValueOnce({ ...GAME_ROW, tags: ['blitz'], is_favorite: false });

    const { result } = renderHook(() => useUserGames());

    let game: UserGame | null = null;
    await act(async () => {
      game = await result.current.getGame('game-99');
    });

    expect(mockApiFetch).toHaveBeenCalled();
  });

  it('should create game via API (PowerSync syncs back via CDC)', async () => {
    const newGame = { ...GAME_ROW, id: 'game-new', tags: ['blitz'], is_favorite: false };
    mockApiFetch.mockResolvedValueOnce(newGame);

    const { result } = renderHook(() => useUserGames());

    let created: UserGame | null = null;
    await act(async () => {
      created = await result.current.createGame('1. e4 e5 *');
    });

    expect(created).not.toBeNull();
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/games',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('should update game via PowerSync local write', async () => {
    mockLiveQueryData.mockReturnValue([GAME_ROW]);

    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.updateGame('game-1', { notes: 'Updated' });
    });

    expect(mockExecute).toHaveBeenCalledWith(
      expect.stringContaining('UPDATE user_games SET'),
      expect.arrayContaining(['Updated']),
    );
  });

  it('should delete game via PowerSync local write', async () => {
    const { result } = renderHook(() => useUserGames());

    let success = false;
    await act(async () => {
      success = await result.current.deleteGame('game-1');
    });

    expect(success).toBe(true);
    expect(mockExecute).toHaveBeenCalledWith(
      'DELETE FROM user_games WHERE id = ?',
      ['game-1'],
    );
  });

  it('should toggle favorite via optimistic update', async () => {
    mockLiveQueryData.mockReturnValue([GAME_ROW]); // is_favorite: 0 (false)

    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.toggleFavorite('game-1');
    });

    // Should write is_favorite: 1 (true) since current is false
    expect(mockExecute).toHaveBeenCalledWith(
      expect.stringContaining('UPDATE user_games SET'),
      expect.arrayContaining([1]), // is_favorite = 1
    );
  });

  it('should import games via API', async () => {
    const importResult = { imported: 2, errors: [], games: [] };
    mockApiFetch.mockResolvedValueOnce(importResult);

    const { result } = renderHook(() => useUserGames());

    let res: any;
    await act(async () => {
      res = await result.current.importFromLocal([{ pgn: '1. e4 *' }]);
    });

    expect(res).toEqual(importResult);
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/games/import-local',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
