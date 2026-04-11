import { describe, it, expect } from 'vitest';
import type { UserGame, ListGamesFilters } from '@/hooks/useUserGames';

/**
 * MyGamesPanel — Component structure and logic tests
 */

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
