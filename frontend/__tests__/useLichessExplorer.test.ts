/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useLichessExplorer } from '@/hooks/useLichessExplorer';
import { explorerSessionCache } from '@/lib/explorer-session-cache';

// Mock the cache
vi.mock('@/lib/explorer-session-cache', () => ({
  explorerSessionCache: {
    lichess: {
      get: vi.fn(),
      set: vi.fn(),
    },
  },
}));

// Mock fetch
global.fetch = vi.fn();

describe('useLichessExplorer - Network-First Strategy', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch from network first for masters database', async () => {
    const mockResponse = {
      white: 1000,
      draws: 500,
      black: 800,
      moves: [
        { uci: 'e2e4', san: 'e4', white: 500, draws: 200, black: 300 },
        { uci: 'd2d4', san: 'd4', white: 400, draws: 250, black: 350 },
      ],
      topGames: [],
      opening: { eco: 'B01', name: 'Scandinavian Defense' },
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
      headers: new Headers(),
    });

    const { result } = renderHook(() =>
      useLichessExplorer({
        fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        database: 'masters',
        enabled: true,
      })
    );

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual(mockResponse);
    expect(result.current.error).toBeNull();

    // Verify network was called first (not cache)
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/explorer/masters'),
      expect.any(Object)
    );
  });

  it('should fallback to cache when network fails', async () => {
    const cachedData = {
      white: 1000,
      draws: 500,
      black: 800,
      moves: [{ uci: 'e2e4', san: 'e4', white: 500, draws: 200, black: 300 }],
      topGames: [],
      opening: null,
    };

    (global.fetch as any).mockRejectedValue(new Error('Network error'));
    (explorerSessionCache.lichess.get as any).mockReturnValue(cachedData);

    const { result } = renderHook(() =>
      useLichessExplorer({
        fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        database: 'masters',
        enabled: true,
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Should use cached data as fallback
    expect(result.current.data).toEqual(cachedData);
    expect(result.current.error).toBeNull();
    expect(explorerSessionCache.lichess.get).toHaveBeenCalled();
  });

  it('should show error when network fails and no cache exists', async () => {
    (global.fetch as any).mockRejectedValue(new Error('Network error'));
    (explorerSessionCache.lichess.get as any).mockReturnValue(null);

    const { result } = renderHook(() =>
      useLichessExplorer({
        fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        database: 'masters',
        enabled: true,
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe('Network error');
  });

  it('should cache successful network responses', async () => {
    const mockResponse = {
      white: 1000,
      draws: 500,
      black: 800,
      moves: [{ uci: 'e2e4', san: 'e4', white: 500, draws: 200, black: 300 }],
      topGames: [],
      opening: null,
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
      headers: new Headers(),
    });

    const { result } = renderHook(() =>
      useLichessExplorer({
        fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        database: 'masters',
        enabled: true,
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Verify cache was updated after successful fetch
    expect(explorerSessionCache.lichess.set).toHaveBeenCalledWith(
      expect.stringContaining('masters?'),
      mockResponse
    );
  });

  it('should fetch from network first for lichess database with filters', async () => {
    const mockResponse = {
      white: 2000,
      draws: 1000,
      black: 1500,
      moves: [{ uci: 'e2e4', san: 'e4', white: 1000, draws: 400, black: 600 }],
      topGames: [],
      opening: null,
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
      headers: new Headers(),
    });

    const { result } = renderHook(() =>
      useLichessExplorer({
        fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        database: 'lichess',
        enabled: true,
        ratings: '2200,2500',
        speeds: 'rapid,classical',
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual(mockResponse);

    // Verify correct parameters were passed
    const fetchCall = (global.fetch as any).mock.calls[0][0];
    expect(fetchCall).toContain('ratings=2200%2C2500');
    expect(fetchCall).toContain('speeds=rapid%2Cclassical');
  });

  it('should fetch from network first for player database', async () => {
    const mockResponse = {
      white: 100,
      draws: 50,
      black: 80,
      moves: [{ uci: 'e2e4', san: 'e4', white: 60, draws: 20, black: 40 }],
      topGames: [],
      opening: null,
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
      headers: new Headers(),
    });

    const { result } = renderHook(() =>
      useLichessExplorer({
        fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        database: 'player',
        enabled: true,
        player: 'testplayer',
        color: 'white',
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual(mockResponse);

    // Verify correct parameters were passed
    const fetchCall = (global.fetch as any).mock.calls[0][0];
    expect(fetchCall).toContain('/api/explorer/player');
    expect(fetchCall).toContain('player=testplayer');
    expect(fetchCall).toContain('color=white');
  });

  it('should detect upstream errors and set upstreamDown flag', async () => {
    const mockResponse = {
      white: 0,
      draws: 0,
      black: 0,
      moves: [],
      topGames: [],
      opening: null,
      _upstreamError: true,
    };

    const headers = new Headers();
    headers.set('X-Explorer-Status', 'upstream-error');

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
      headers,
    });

    const { result } = renderHook(() =>
      useLichessExplorer({
        fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        database: 'masters',
        enabled: true,
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.upstreamDown).toBe(true);
    expect(result.current.data).toEqual(mockResponse);
  });

  it('should not fetch when disabled', () => {
    const { result } = renderHook(() =>
      useLichessExplorer({
        fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        database: 'masters',
        enabled: false,
      })
    );

    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('should handle missing required player database params', async () => {
    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({}),
      headers: new Headers(),
    });

    const { result } = renderHook(() =>
      useLichessExplorer({
        fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        database: 'player',
        enabled: true,
        // Missing player and color
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Player and color are required for player database');
  });
});
