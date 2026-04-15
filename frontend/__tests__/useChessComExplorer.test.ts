/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useChessComExplorer } from '@/hooks/useChessComExplorer';

// Mock fetch
global.fetch = vi.fn();

describe('useChessComExplorer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch games from network', async () => {
    const mockArchives = {
      archives: ['https://api.chess.com/pub/player/testuser/games/2024/03'],
    };
    const mockGames = {
      games: [
        {
          url: 'https://chess.com/game/1',
          pgn: '[Event "Test"]\n1. e4 e5',
          time_control: '600',
          end_time: 1710000000,
          rated: true,
          fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
          time_class: 'rapid',
          rules: 'chess',
          white: { username: 'player1', rating: 1500, result: 'win' },
          black: { username: 'player2', rating: 1400, result: 'checkmated' },
        },
      ],
    };

    (global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockArchives,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockGames,
      });

    const { result } = renderHook(() =>
      useChessComExplorer({ username: 'testuser', enabled: true })
    );

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.games).toHaveLength(1);
    expect(result.current.games[0].white).toBe('player1');
    expect(result.current.error).toBeNull();
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('should show error when network fails', async () => {
    (global.fetch as any).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() =>
      useChessComExplorer({ username: 'testuser', enabled: true })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.games).toEqual([]);
    expect(result.current.error).toBe('Network error');
  });

  it('should handle 404 player not found error', async () => {
    (global.fetch as any).mockResolvedValue({
      ok: false,
      status: 404,
    });

    const { result } = renderHook(() =>
      useChessComExplorer({ username: 'nonexistent', enabled: true })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Player not found');
    expect(result.current.games).toEqual([]);
  });

  it('should not fetch when disabled', () => {
    const { result } = renderHook(() =>
      useChessComExplorer({ username: 'testuser', enabled: false })
    );

    expect(result.current.loading).toBe(false);
    expect(result.current.games).toEqual([]);
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
