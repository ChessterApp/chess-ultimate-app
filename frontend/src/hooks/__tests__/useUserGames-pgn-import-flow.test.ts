/**
 * @vitest-environment jsdom
 *
 * Integration test: create game via PGN import → verify it appears in list
 *
 * Tests the full flow of:
 * 1. Creating a game with PGN (simulating import)
 * 2. Verifying it appears in the hook's games state
 * 3. Fetching the games list and confirming the new game is included
 * 4. Verifying PGN header auto-extraction populates metadata
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useUserGames } from '../useUserGames';
import type { UserGame, ListGamesResponse } from '../useUserGames';

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
  usePowerSyncContext: () => ({ database: null, isReady: false }),
}));

vi.mock('@powersync/react', () => ({
  useQuery: () => ({ data: undefined, isLoading: false, error: undefined }),
}));

// ─── Fixtures ────────────────────────────

const IMPORT_PGN = `[Event "Candidates 2024"]
[White "Gukesh D"]
[Black "Nakamura, Hikaru"]
[Result "1-0"]
[Date "2024.04.05"]
[WhiteElo "2758"]
[BlackElo "2794"]
[ECO "C48"]
[Opening "Four Knights Game"]

1. e4 e5 2. Nf3 Nc6 3. Nc3 Nf6 4. Bb5 Nd4 5. Nxd4 exd4 6. e5 dxc3 7. exf6 Qxf6 8. dxc3 Qe5+ 1-0`;

const CREATED_GAME: UserGame = {
  id: 'pgn-import-001',
  user_id: 'user-1',
  title: null,
  white: 'Gukesh D',
  black: 'Nakamura, Hikaru',
  white_elo: 2758,
  black_elo: 2794,
  result: '1-0',
  date: '2024.04.05',
  event: 'Candidates 2024',
  eco: 'C48',
  opening_name: 'Four Knights Game',
  pgn: IMPORT_PGN,
  notes: null,
  tags: [],
  is_favorite: false,
  source: 'pgn_import',
  created_at: '2024-04-05T12:00:00Z',
  updated_at: '2024-04-05T12:00:00Z',
};

const EXISTING_GAME: UserGame = {
  id: 'existing-game-001',
  user_id: 'user-1',
  title: 'Old Game',
  white: 'Player A',
  black: 'Player B',
  white_elo: 1500,
  black_elo: 1600,
  result: '0-1',
  date: '2024.01.01',
  event: 'Club Match',
  eco: 'B01',
  opening_name: 'Scandinavian Defense',
  pgn: '1. e4 d5 2. exd5 Qxd5 0-1',
  notes: null,
  tags: [],
  is_favorite: false,
  source: 'manual',
  created_at: '2024-01-01T10:00:00Z',
  updated_at: '2024-01-01T10:00:00Z',
};

// ─── Tests ───────────────────────────────

describe('PGN Import → Game Appears in List (Integration)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockResolvedValue('test-token');
  });

  it('should create game via PGN import and have it appear in state immediately', async () => {
    // Backend returns the created game with auto-extracted headers
    mockApiFetch.mockResolvedValueOnce(CREATED_GAME);

    const { result } = renderHook(() => useUserGames());

    // Verify initial empty state
    expect(result.current.games).toEqual([]);
    expect(result.current.total).toBe(0);

    // Create the game via PGN import
    let created: UserGame | null = null;
    await act(async () => {
      created = await result.current.createGame(IMPORT_PGN, {
        source: 'pgn_import',
      });
    });

    // Verify game was created successfully
    expect(created).not.toBeNull();
    expect(created!.id).toBe('pgn-import-001');
    expect(created!.source).toBe('pgn_import');

    // Verify the game appears in the list immediately (optimistic update)
    expect(result.current.games).toHaveLength(1);
    expect(result.current.games[0].id).toBe('pgn-import-001');
    expect(result.current.total).toBe(1);
  });

  it('should prepend PGN-imported game before existing games', async () => {
    // First, populate with existing games
    const listResponse: ListGamesResponse = {
      games: [EXISTING_GAME],
      total: 1,
      page: 1,
      per_page: 20,
    };
    mockApiFetch.mockResolvedValueOnce(listResponse);

    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.fetchGames();
    });

    expect(result.current.games).toHaveLength(1);
    expect(result.current.games[0].id).toBe('existing-game-001');

    // Now import a new game via PGN
    mockApiFetch.mockResolvedValueOnce(CREATED_GAME);

    await act(async () => {
      await result.current.createGame(IMPORT_PGN, { source: 'pgn_import' });
    });

    // New game should be at the top (prepended)
    expect(result.current.games).toHaveLength(2);
    expect(result.current.games[0].id).toBe('pgn-import-001');
    expect(result.current.games[1].id).toBe('existing-game-001');
    expect(result.current.total).toBe(2);
  });

  it('should send PGN and metadata in the create request body', async () => {
    mockApiFetch.mockResolvedValueOnce(CREATED_GAME);

    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.createGame(IMPORT_PGN, {
        source: 'pgn_import',
        white: 'Gukesh D',
        black: 'Nakamura, Hikaru',
        white_elo: 2758,
        black_elo: 2794,
        result: '1-0',
        date: '2024.04.05',
        event: 'Candidates 2024',
      });
    });

    // Verify API was called with correct payload
    expect(mockApiFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockApiFetch.mock.calls[0];
    expect(url).toBe('/api/games');
    expect(options.method).toBe('POST');

    const body = JSON.parse(options.body);
    expect(body.pgn).toBe(IMPORT_PGN);
    expect(body.source).toBe('pgn_import');
    expect(body.white).toBe('Gukesh D');
    expect(body.black).toBe('Nakamura, Hikaru');
    expect(body.white_elo).toBe(2758);
    expect(body.black_elo).toBe(2794);
    expect(body.result).toBe('1-0');
  });

  it('should include auth token in create request', async () => {
    mockApiFetch.mockResolvedValueOnce(CREATED_GAME);

    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.createGame(IMPORT_PGN, { source: 'pgn_import' });
    });

    const options = mockApiFetch.mock.calls[0][1];
    expect(options.headers.Authorization).toBe('Bearer test-token');
  });

  it('should show imported game with extracted metadata in the list', async () => {
    mockApiFetch.mockResolvedValueOnce(CREATED_GAME);

    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.createGame(IMPORT_PGN, { source: 'pgn_import' });
    });

    // Verify the game in the list has all the extracted metadata
    const game = result.current.games[0];
    expect(game.white).toBe('Gukesh D');
    expect(game.black).toBe('Nakamura, Hikaru');
    expect(game.white_elo).toBe(2758);
    expect(game.black_elo).toBe(2794);
    expect(game.result).toBe('1-0');
    expect(game.date).toBe('2024.04.05');
    expect(game.event).toBe('Candidates 2024');
    expect(game.eco).toBe('C48');
    expect(game.opening_name).toBe('Four Knights Game');
    expect(game.pgn).toContain('1. e4 e5');
  });

  it('should handle create failure without corrupting the game list', async () => {
    // First load existing games
    const listResponse: ListGamesResponse = {
      games: [EXISTING_GAME],
      total: 1,
      page: 1,
      per_page: 20,
    };
    mockApiFetch.mockResolvedValueOnce(listResponse);

    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.fetchGames();
    });

    expect(result.current.games).toHaveLength(1);

    // Now simulate a failed PGN import
    mockApiFetch.mockRejectedValueOnce(new Error('Invalid PGN'));

    const created = await act(async () => {
      return await result.current.createGame('not valid pgn', { source: 'pgn_import' });
    });

    // Create should return null
    expect(created).toBeNull();

    // Existing list should remain unchanged
    expect(result.current.games).toHaveLength(1);
    expect(result.current.games[0].id).toBe('existing-game-001');
    expect(result.current.total).toBe(1);
    expect(result.current.error).toBe('Invalid PGN');
  });

  it('should allow fetching games list after PGN import and find the game', async () => {
    // Step 1: Create game
    mockApiFetch.mockResolvedValueOnce(CREATED_GAME);

    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.createGame(IMPORT_PGN, { source: 'pgn_import' });
    });

    expect(result.current.games).toHaveLength(1);

    // Step 2: Simulate fetching from server (server returns the game)
    const serverList: ListGamesResponse = {
      games: [CREATED_GAME, EXISTING_GAME],
      total: 2,
      page: 1,
      per_page: 20,
    };
    mockApiFetch.mockResolvedValueOnce(serverList);

    await act(async () => {
      await result.current.fetchGames();
    });

    // The fetched list should include the imported game
    expect(result.current.games).toHaveLength(2);
    expect(result.current.total).toBe(2);
    const importedGame = result.current.games.find(g => g.id === 'pgn-import-001');
    expect(importedGame).toBeDefined();
    expect(importedGame!.source).toBe('pgn_import');
    expect(importedGame!.white).toBe('Gukesh D');
  });

  it('should handle minimal PGN with no headers', async () => {
    const minimalPgn = '1. e4 e5 2. Nf3 Nc6 *';
    const minimalGame: UserGame = {
      ...CREATED_GAME,
      id: 'minimal-001',
      title: null,
      white: '?',
      black: '?',
      white_elo: null,
      black_elo: null,
      result: '*',
      date: null,
      event: null,
      eco: null,
      opening_name: null,
      pgn: minimalPgn,
    };

    mockApiFetch.mockResolvedValueOnce(minimalGame);

    const { result } = renderHook(() => useUserGames());

    let created: UserGame | null = null;
    await act(async () => {
      created = await result.current.createGame(minimalPgn, { source: 'pgn_import' });
    });

    expect(created).not.toBeNull();
    expect(result.current.games).toHaveLength(1);
    expect(result.current.games[0].pgn).toBe(minimalPgn);
    expect(result.current.games[0].white).toBe('?');
    expect(result.current.games[0].result).toBe('*');
  });

  it('should handle multiple sequential PGN imports', async () => {
    const game1: UserGame = { ...CREATED_GAME, id: 'import-1' };
    const game2: UserGame = {
      ...CREATED_GAME,
      id: 'import-2',
      white: 'Carlsen, Magnus',
      black: 'Firouzja, Alireza',
      result: '1/2-1/2',
    };
    const game3: UserGame = {
      ...CREATED_GAME,
      id: 'import-3',
      white: 'Caruana, Fabiano',
      black: 'Ding, Liren',
      result: '0-1',
    };

    mockApiFetch
      .mockResolvedValueOnce(game1)
      .mockResolvedValueOnce(game2)
      .mockResolvedValueOnce(game3);

    const { result } = renderHook(() => useUserGames());

    await act(async () => {
      await result.current.createGame('1. e4 e5 *', { source: 'pgn_import' });
    });
    await act(async () => {
      await result.current.createGame('1. d4 d5 *', { source: 'pgn_import' });
    });
    await act(async () => {
      await result.current.createGame('1. c4 e5 *', { source: 'pgn_import' });
    });

    // All three should be in the list, newest first
    expect(result.current.games).toHaveLength(3);
    expect(result.current.games[0].id).toBe('import-3');
    expect(result.current.games[1].id).toBe('import-2');
    expect(result.current.games[2].id).toBe('import-1');
    expect(result.current.total).toBe(3);
  });
});
