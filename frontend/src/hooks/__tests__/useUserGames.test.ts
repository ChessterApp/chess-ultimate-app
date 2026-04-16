/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useUserGames } from '../useUserGames';
import type { UserGame, ListGamesResponse, ImportResult } from '../useUserGames';

// ─── Mocks ───────────────────────────────

const mockGetToken = vi.fn().mockResolvedValue('test-token');

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: mockGetToken }),
}));

const mockApiFetch = vi.fn();

vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
    }
  },
}));

// Feature flag off → legacy mode
vi.mock('@/lib/feature-flags', () => ({
  LOCAL_FIRST_GAMES: false,
}));

vi.mock('@/lib/powersync/PowerSyncProvider', () => ({
  usePowerSyncContext: () => ({ database: null, collections: null, isReady: false }),
}));

vi.mock('@powersync/react', () => ({
  useQuery: () => ({ data: undefined, isLoading: false, error: undefined }),
}));

// ─── Fixtures ────────────────────────────

const GAME_1: UserGame = {
  id: 'game-1',
  user_id: 'user-1',
  title: 'Game vs Magnus',
  white: 'Magnus Carlsen',
  black: 'Test User',
  white_elo: 2830,
  black_elo: 1500,
  result: '1-0',
  date: '2024-06-01',
  event: 'Online Blitz',
  eco: 'C50',
  opening_name: 'Italian Game',
  pgn: '1. e4 e5 2. Nf3 Nc6 3. Bc4 *',
  notes: null,
  tags: ['blitz'],
  is_favorite: false,
  source: 'manual',
  created_at: '2024-06-01T10:00:00Z',
  updated_at: '2024-06-01T10:00:00Z',
};

const GAME_2: UserGame = {
  id: 'game-2',
  user_id: 'user-1',
  title: 'Game vs Hikaru',
  white: 'Test User',
  black: 'Hikaru Nakamura',
  white_elo: 1500,
  black_elo: 2750,
  result: '0-1',
  date: '2024-06-02',
  event: 'Rapid Championship',
  eco: 'B90',
  opening_name: 'Sicilian Najdorf',
  pgn: '1. e4 c5 2. Nf3 d6 *',
  notes: 'Good try',
  tags: ['rapid', 'tactics'],
  is_favorite: true,
  source: 'manual',
  created_at: '2024-06-02T10:00:00Z',
  updated_at: '2024-06-02T10:00:00Z',
};

const LIST_RESPONSE: ListGamesResponse = {
  games: [GAME_2, GAME_1],
  total: 2,
  page: 1,
  per_page: 20,
};

// ─── Tests ───────────────────────────────

describe('useUserGames', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockResolvedValue('test-token');
  });

  it('should start with empty state', () => {
    const { result } = renderHook(() => useUserGames());

    expect(result.current.games).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('should fetch and set games', async () => {
    mockApiFetch.mockResolvedValueOnce(LIST_RESPONSE);
    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.fetchGames();
    });

    expect(result.current.games).toEqual([GAME_2, GAME_1]);
    expect(result.current.total).toBe(2);
    expect(result.current.page).toBe(1);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('should pass pagination params', async () => {
    mockApiFetch.mockResolvedValueOnce({ games: [], total: 0, page: 3, per_page: 10 });
    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.fetchGames(3, 10);
    });

    const url = mockApiFetch.mock.calls[0][0] as string;
    expect(url).toContain('page=3');
    expect(url).toContain('per_page=10');
  });

  it('should pass filter params', async () => {
    mockApiFetch.mockResolvedValueOnce({ games: [], total: 0, page: 1, per_page: 20 });
    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.fetchGames(1, 20, {
        q: 'Magnus',
        result: '1-0',
        favorite: true,
        tag: 'blitz',
      });
    });

    const url = mockApiFetch.mock.calls[0][0] as string;
    expect(url).toContain('q=Magnus');
    expect(url).toContain('result=1-0');
    expect(url).toContain('favorite=true');
    expect(url).toContain('tag=blitz');
  });

  it('should set error on fetch failure', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('Network error'));
    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.fetchGames();
    });

    expect(result.current.error).toBe('Network error');
    expect(result.current.games).toEqual([]);
  });

  it('should fetch a single game by id', async () => {
    mockApiFetch.mockResolvedValueOnce(GAME_1);
    const { result } = renderHook(() => useUserGames());

    let game: UserGame | null = null;
    await act(async () => {
      game = await result.current.getGame('game-1');
    });

    expect(game).toEqual(GAME_1);
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/games/game-1',
      expect.any(Object)
    );
  });

  it('should set error on getGame failure', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('Not found'));
    const { result } = renderHook(() => useUserGames());

    let game: UserGame | null = null;
    await act(async () => {
      game = await result.current.getGame('nonexistent');
    });

    expect(game).toBeNull();
    expect(result.current.error).toBe('Not found');
  });

  it('should create a game and prepend to list', async () => {
    const newGame: UserGame = { ...GAME_1, id: 'game-new' };
    mockApiFetch.mockResolvedValueOnce(newGame);
    const { result } = renderHook(() => useUserGames());

    let created: UserGame | null = null;
    await act(async () => {
      created = await result.current.createGame('1. e4 e5 *');
    });

    expect(created).toEqual(newGame);
    expect(result.current.games[0]).toEqual(newGame);
    expect(result.current.total).toBe(1);
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/games',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ pgn: '1. e4 e5 *' }),
      })
    );
  });

  it('should pass optional metadata when creating', async () => {
    mockApiFetch.mockResolvedValueOnce(GAME_1);
    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.createGame('1. e4 e5 *', {
        title: 'My Game',
        tags: ['blitz'],
      });
    });

    const body = JSON.parse(mockApiFetch.mock.calls[0][1].body);
    expect(body.pgn).toBe('1. e4 e5 *');
    expect(body.title).toBe('My Game');
    expect(body.tags).toEqual(['blitz']);
  });

  it('should set error on create failure', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('Invalid PGN'));
    const { result } = renderHook(() => useUserGames());

    const created = await act(async () => {
      return await result.current.createGame('bad pgn');
    });

    expect(created).toBeNull();
    expect(result.current.error).toBe('Invalid PGN');
  });

  it('should update a game and reflect in state', async () => {
    mockApiFetch
      .mockResolvedValueOnce(LIST_RESPONSE)
      .mockResolvedValueOnce({ ...GAME_1, notes: 'Updated notes' });
    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.fetchGames();
    });

    await act(async () => {
      await result.current.updateGame('game-1', { notes: 'Updated notes' });
    });

    const updated = result.current.games.find(g => g.id === 'game-1');
    expect(updated?.notes).toBe('Updated notes');
  });

  it('should set error on update failure', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('Update failed'));
    const { result } = renderHook(() => useUserGames());

    const updated = await act(async () => {
      return await result.current.updateGame('game-1', { notes: 'test' });
    });

    expect(updated).toBeNull();
    expect(result.current.error).toBe('Update failed');
  });

  it('should soft-delete a game and remove from state', async () => {
    mockApiFetch
      .mockResolvedValueOnce(LIST_RESPONSE)
      .mockResolvedValueOnce({ success: true });
    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.fetchGames();
    });
    expect(result.current.games).toHaveLength(2);

    let success = false;
    await act(async () => {
      success = await result.current.deleteGame('game-1');
    });

    expect(success).toBe(true);
    expect(result.current.games).toHaveLength(1);
    expect(result.current.games.find(g => g.id === 'game-1')).toBeUndefined();
    expect(result.current.total).toBe(1);
  });

  it('should set error on delete failure', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('Delete failed'));
    const { result } = renderHook(() => useUserGames());

    const success = await act(async () => {
      return await result.current.deleteGame('game-1');
    });

    expect(success).toBe(false);
    expect(result.current.error).toBe('Delete failed');
  });

  it('should toggle favorite status', async () => {
    const toggledGame = { ...GAME_1, is_favorite: true };
    mockApiFetch
      .mockResolvedValueOnce(LIST_RESPONSE)
      .mockResolvedValueOnce(toggledGame);
    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.fetchGames();
    });

    // GAME_1 has is_favorite: false — toggle should send true
    let success = false;
    await act(async () => {
      success = await result.current.toggleFavorite('game-1');
    });

    expect(success).toBe(true);
    const putCall = mockApiFetch.mock.calls[1];
    const body = JSON.parse(putCall[1].body);
    expect(body.is_favorite).toBe(true);
  });

  it('should return false when toggling nonexistent game', async () => {
    const { result } = renderHook(() => useUserGames());

    let success = true;
    await act(async () => {
      success = await result.current.toggleFavorite('nonexistent');
    });

    expect(success).toBe(false);
  });

  it('should import games from localStorage format', async () => {
    const importResult: ImportResult = {
      imported: 2,
      errors: [],
      games: [GAME_1, GAME_2],
    };
    mockApiFetch.mockResolvedValueOnce(importResult);
    const { result } = renderHook(() => useUserGames());

    let res: ImportResult | null = null;
    await act(async () => {
      res = await result.current.importFromLocal([
        { pgn: '1. e4 e5 *' },
        { pgn: '1. d4 d5 *' },
      ]);
    });

    expect(res).toEqual(importResult);
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/games/import-local',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('should set error on import failure', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('Import failed'));
    const { result } = renderHook(() => useUserGames());

    const res = await act(async () => {
      return await result.current.importFromLocal([{ pgn: '1. e4 *' }]);
    });

    expect(res).toBeNull();
    expect(result.current.error).toBe('Import failed');
  });

  it('should include auth token in requests', async () => {
    mockApiFetch.mockResolvedValueOnce(LIST_RESPONSE);
    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.fetchGames();
    });

    const options = mockApiFetch.mock.calls[0][1];
    expect(options.headers.Authorization).toBe('Bearer test-token');
  });

  it('should error when getToken returns null', async () => {
    mockGetToken.mockResolvedValueOnce(null);
    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.fetchGames();
    });

    expect(result.current.error).toBe('Not authenticated');
  });
});
