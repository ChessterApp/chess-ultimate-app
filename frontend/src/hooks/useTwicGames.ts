/**
 * useTwicGames — Hook for fetching master games from TWIC database by position
 *
 * Fetches games that reach a specific position via /api/openings/games/by-position
 */

import { useState, useEffect, useCallback } from 'react';

export interface TwicGame {
  id: number;
  white_name: string;
  black_name: string;
  white_elo: number | null;
  black_elo: number | null;
  result: string;
  date: string;
  event: string;
  site: string;
  eco: string | null;
  opening: string | null;
}

export interface TwicGamesResponse {
  games: TwicGame[];
  total: number;
  indexed: boolean;
  count_exact?: boolean;
}

export interface UseTwicGamesOptions {
  fen: string;
  enabled?: boolean;
  limit?: number;
  playerName?: string;
  playerColor?: 'white' | 'black' | '';
  sortBy?: 'rating' | 'date_desc' | 'date_asc' | 'elo_white' | 'elo_black';
  debounceMs?: number;
}

export interface UseTwicGamesResult {
  data: TwicGamesResponse | null;
  loading: boolean;
  error: string | null;
  retry: () => void;
}

export function useTwicGames({
  fen,
  enabled = true,
  limit = 10,
  playerName = '',
  playerColor = '',
  sortBy = 'rating',
  debounceMs = 300,
}: UseTwicGamesOptions): UseTwicGamesResult {
  const [data, setData] = useState<TwicGamesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryTrigger, setRetryTrigger] = useState(0);

  const retry = useCallback(() => {
    setRetryTrigger((prev) => prev + 1);
  }, []);

  useEffect(() => {
    if (!enabled || !fen) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    let timeoutId: NodeJS.Timeout | null = null;

    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        const params = new URLSearchParams();
        params.set('fen', fen);
        params.set('limit', Math.min(limit, 50).toString());

        if (playerName) {
          params.set('player_name', playerName);
        }

        if (playerColor) {
          params.set('player_color', playerColor);
        }

        params.set('sort_by', sortBy);

        const response = await fetch(`/api/openings/games/by-position?${params.toString()}`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        });

        if (!response.ok) {
          // Check if this is an auth error
          if (response.status === 401 || response.status === 403) {
            throw new Error('Authentication required for game search');
          }
          throw new Error(`Failed to fetch: ${response.status}`);
        }

        const result = await response.json();

        if (!cancelled) {
          setData({
            games: result.games || [],
            total: result.total || 0,
            indexed: result.indexed !== false,
            count_exact: result.count_exact,
          });
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to fetch TWIC games');
          setData(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    // Debounce the fetch
    timeoutId = setTimeout(() => {
      fetchData();
    }, debounceMs);

    return () => {
      cancelled = true;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [fen, enabled, limit, playerName, playerColor, sortBy, debounceMs, retryTrigger]);

  return { data, loading, error, retry };
}
