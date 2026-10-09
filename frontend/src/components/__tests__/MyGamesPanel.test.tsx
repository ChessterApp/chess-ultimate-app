// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { UserGame, ListGamesFilters } from '@/hooks/useUserGames';

/**
 * MyGamesPanel — Component structure and logic tests + shared read-only mode.
 */

// ─── Mocks for the shared-mode render tests ───
const getTokenMock = vi.fn(async () => 'clerk-token');
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: getTokenMock }),
}));

vi.mock('next-intl', () => ({
  // Interpolate {name} so the owner header is assertable; otherwise echo the key.
  useTranslations: () => (key: string, params?: Record<string, unknown>) =>
    params && 'name' in params ? `${params.name}'s games` : key,
}));

// Owner-mode hook stub — shared mode never reads from it, but it must resolve.
vi.mock('@/hooks/useUserGames', () => ({
  useUserGames: () => ({
    games: [],
    total: 0,
    page: 1,
    perPage: 20,
    loading: false,
    error: null,
    fetchGames: vi.fn(),
    createGame: vi.fn(),
    updateGame: vi.fn(),
    deleteGame: vi.fn(),
    toggleFavorite: vi.fn(),
  }),
}));

// Child mutation components are never rendered in shared mode; stub to avoid
// pulling their (heavy) transitive deps into the test transform.
vi.mock('@/components/openings/AddGameModal', () => ({ default: () => null }));
vi.mock('@/components/openings/EditGameModal', () => ({ default: () => null }));
vi.mock('@/components/openings/ShareMyGameButton', () => ({
  default: () => <button aria-label="share game" />,
}));

const apiFetchMock = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}));

import MyGamesPanel from '@/components/openings/MyGamesPanel';

function makeGame(overrides: Partial<UserGame> = {}): UserGame {
  return {
    id: 'g1',
    user_id: '',
    title: null,
    white: 'Carlsen',
    black: 'Nakamura',
    white_elo: 2855,
    black_elo: 2780,
    result: '1-0',
    date: '2024.01.02',
    event: 'Test',
    eco: 'B90',
    opening_name: null,
    pgn: '1. e4 c5 *',
    notes: null,
    tags: [],
    is_favorite: false,
    source: 'manual',
    created_at: '2024-01-02T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  };
}

class ApiError extends Error {
  status: number;
  constructor(status: number) {
    super(`status ${status}`);
    this.status = status;
  }
}

describe('MyGamesPanel Filter Logic', () => {
  function buildFilters(
    searchQuery: string,
    resultFilter: string,
    favoriteFilter: boolean
  ): ListGamesFilters {
    const filters: ListGamesFilters = {};
    if (searchQuery.trim()) filters.q = searchQuery.trim();
    if (resultFilter) filters.result = resultFilter;
    if (favoriteFilter) filters.favorite = true;
    return filters;
  }

  it('should build empty filters when no filters are active', () => {
    const filters = buildFilters('', '', false);
    expect(filters).toEqual({});
  });

  it('should include search query in filters', () => {
    const filters = buildFilters('Carlsen', '', false);
    expect(filters).toEqual({ q: 'Carlsen' });
  });

  it('should trim whitespace from search query', () => {
    const filters = buildFilters('  Carlsen  ', '', false);
    expect(filters).toEqual({ q: 'Carlsen' });
  });

  it('should ignore whitespace-only search query', () => {
    const filters = buildFilters('   ', '', false);
    expect(filters).toEqual({});
  });

  it('should include result filter', () => {
    const filters = buildFilters('', '1-0', false);
    expect(filters).toEqual({ result: '1-0' });
  });

  it('should include favorite filter', () => {
    const filters = buildFilters('', '', true);
    expect(filters).toEqual({ favorite: true });
  });

  it('should combine all filters', () => {
    const filters = buildFilters('Kasparov', '0-1', true);
    expect(filters).toEqual({ q: 'Kasparov', result: '0-1', favorite: true });
  });
});

describe('MyGamesPanel Result Filters', () => {
  const resultFilters = [
    { value: '', label: 'All' },
    { value: '1-0', label: '1-0' },
    { value: '0-1', label: '0-1' },
    { value: '1/2-1/2', label: '½-½' },
  ];

  it('should have 4 result filter options', () => {
    expect(resultFilters).toHaveLength(4);
  });

  it('should have empty string value for "All" filter', () => {
    expect(resultFilters[0].value).toBe('');
  });

  it('should include all three result types', () => {
    const values = resultFilters.map((f) => f.value);
    expect(values).toContain('1-0');
    expect(values).toContain('0-1');
    expect(values).toContain('1/2-1/2');
  });
});

describe('MyGamesPanel Pagination', () => {
  it('should calculate total pages correctly', () => {
    const total = 45;
    const perPage = 20;
    const totalPages = Math.ceil(total / perPage);
    expect(totalPages).toBe(3);
  });

  it('should handle exact page boundaries', () => {
    const total = 40;
    const perPage = 20;
    const totalPages = Math.ceil(total / perPage);
    expect(totalPages).toBe(2);
  });

  it('should handle zero games', () => {
    const total = 0;
    const perPage = 20;
    const totalPages = Math.ceil(total / perPage);
    expect(totalPages).toBe(0);
  });

  it('should handle single page', () => {
    const total = 15;
    const perPage = 20;
    const totalPages = Math.ceil(total / perPage);
    expect(totalPages).toBe(1);
  });
});

describe('MyGamesPanel GameRow Result Color', () => {
  function getResultColor(result: string): string {
    return result === '1-0' ? '#f0f0f0' :
           result === '0-1' ? '#333' :
           '#888';
  }

  it('should return light color for white wins', () => {
    expect(getResultColor('1-0')).toBe('#f0f0f0');
  });

  it('should return dark color for black wins', () => {
    expect(getResultColor('0-1')).toBe('#333');
  });

  it('should return gray for draws', () => {
    expect(getResultColor('1/2-1/2')).toBe('#888');
  });

  it('should return gray for unknown results', () => {
    expect(getResultColor('*')).toBe('#888');
  });
});

describe('UserGame Type Shape', () => {
  it('should define all required fields on UserGame interface', () => {
    const game: UserGame = {
      id: 'abc-123',
      user_id: 'user-1',
      title: 'World Championship Game 6',
      white: 'Carlsen, Magnus',
      black: 'Nepomniachtchi, Ian',
      white_elo: 2855,
      black_elo: 2782,
      result: '1-0',
      date: '2021.12.03',
      event: 'World Championship',
      eco: 'D02',
      opening_name: "Queen's Pawn Game",
      pgn: '1. d4 Nf6 2. Nf3 d5 *',
      notes: 'Brilliant endgame',
      tags: ['world-championship', 'favorite'],
      is_favorite: true,
      source: 'manual',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    };

    expect(game.id).toBe('abc-123');
    expect(game.white).toBe('Carlsen, Magnus');
    expect(game.tags).toContain('world-championship');
    expect(game.is_favorite).toBe(true);
  });

  it('should allow nullable fields', () => {
    const game: UserGame = {
      id: 'abc-456',
      user_id: 'user-1',
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
      pgn: '1. e4 e5 *',
      notes: null,
      tags: [],
      is_favorite: false,
      source: 'manual',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    };

    expect(game.title).toBeNull();
    expect(game.white_elo).toBeNull();
    expect(game.tags).toHaveLength(0);
  });
});

describe('MyGamesPanel shared read-only mode', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    getTokenMock.mockClear();
  });
  afterEach(() => cleanup());

  it('fetches the collection from the shared endpoint and shows the owner header', async () => {
    apiFetchMock.mockResolvedValueOnce({
      games: [makeGame()],
      total: 1,
      page: 1,
      per_page: 20,
      owner_name: 'Alice',
    });

    await act(async () => {
      render(<MyGamesPanel sharedToken="tok-abc" />);
    });

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled());
    const url = apiFetchMock.mock.calls[0][0] as string;
    expect(url).toContain('/api/games/collection/shared/tok-abc');
    expect(await screen.findByText("Alice's games")).toBeTruthy();
    expect(screen.getByText('Carlsen')).toBeTruthy();
  });

  it('hides all mutation UI in shared mode', async () => {
    apiFetchMock.mockResolvedValueOnce({
      games: [makeGame()],
      total: 1,
      page: 1,
      per_page: 20,
      owner_name: 'Alice',
    });

    await act(async () => {
      render(<MyGamesPanel sharedToken="tok-abc" onOpenGame={vi.fn()} />);
    });

    await screen.findByText('Carlsen');
    // No add / edit / delete / per-row share / favorite-toggle controls.
    expect(screen.queryByText('myGames.addGame')).toBeNull();
    expect(screen.queryByText('myGames.searchPlaceholder')).toBeNull();
    expect(screen.queryByLabelText('edit game')).toBeNull();
    expect(screen.queryByLabelText('delete game')).toBeNull();
    expect(screen.queryByLabelText('toggle favorite')).toBeNull();
    expect(screen.queryByLabelText('share game')).toBeNull();
  });

  it('opens a game via the shared per-game endpoint on row click', async () => {
    const onOpenGame = vi.fn();
    apiFetchMock
      .mockResolvedValueOnce({ games: [makeGame()], total: 1, page: 1, per_page: 20, owner_name: 'Alice' })
      .mockResolvedValueOnce(makeGame({ pgn: '1. e4 c5 2. Nf3 *' }));

    await act(async () => {
      render(<MyGamesPanel sharedToken="tok-abc" onOpenGame={onOpenGame} />);
    });

    const row = await screen.findByText('Carlsen');
    await act(async () => {
      fireEvent.click(row);
    });

    await waitFor(() => expect(onOpenGame).toHaveBeenCalled());
    const detailUrl = apiFetchMock.mock.calls[1][0] as string;
    expect(detailUrl).toContain('/api/games/collection/shared/tok-abc/games/g1');
  });

  it('renders a friendly empty state for an empty collection', async () => {
    apiFetchMock.mockResolvedValueOnce({
      games: [],
      total: 0,
      page: 1,
      per_page: 20,
      owner_name: 'Alice',
    });

    await act(async () => {
      render(<MyGamesPanel sharedToken="tok-abc" />);
    });

    expect(await screen.findByText('myGames.sharedEmpty')).toBeTruthy();
  });

  it('renders the revoked state when the token 404s', async () => {
    apiFetchMock.mockRejectedValueOnce(new ApiError(404));

    await act(async () => {
      render(<MyGamesPanel sharedToken="tok-gone" />);
    });

    expect(await screen.findByText('myGames.sharedUnavailable')).toBeTruthy();
  });
});
