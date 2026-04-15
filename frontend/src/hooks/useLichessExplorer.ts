/**
 * useLichessExplorer — Hook for fetching Lichess Opening Explorer data
 *
 * Fetches data via /api/explorer/ proxy. Caching is handled by the
 * Service Worker (stale-while-revalidate, 5min TTL).
 */

import { useState, useEffect, useCallback } from 'react';

export interface LichessMove {
  uci: string;
  san: string;
  white: number;
  draws: number;
  black: number;
  averageRating?: number;
}

export interface LichessTopGame {
  id: string;
  white: {
    name: string;
    rating: number;
  };
  black: {
    name: string;
    rating: number;
  };
  winner?: 'white' | 'black';
  year?: number;
  month?: string;
}

export interface LichessExplorerResponse {
  white: number;
  draws: number;
  black: number;
  moves: LichessMove[];
  topGames: LichessTopGame[];
  opening?: {
    eco: string;
    name: string;
  } | null;
}

export interface UseLichessExplorerOptions {
  fen: string;
  database: 'masters' | 'lichess' | 'player';
  enabled?: boolean;
  // Lichess Players DB options
  ratings?: string; // e.g., "2200,2500"
  speeds?: string; // e.g., "rapid,classical"
  // Lichess Player options
  player?: string; // Lichess username
  color?: 'white' | 'black'; // Required for player database
  modes?: string; // e.g., "rated,casual"
  recentGames?: number; // Number of recent games to return (default 8)
}

export interface UseLichessExplorerResult {
  data: LichessExplorerResponse | null;
  loading: boolean;
  error: string | null;
  upstreamDown: boolean;
  retry: () => void;
}

export function useLichessExplorer({
  fen,
  database,
  enabled = true,
  ratings = '2200,2500',
  speeds = 'rapid,classical',
  player,
  color,
  modes,
  recentGames = 8,
}: UseLichessExplorerOptions): UseLichessExplorerResult {
  const [data, setData] = useState<LichessExplorerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [upstreamDown, setUpstreamDown] = useState(false);
  const [retryTrigger, setRetryTrigger] = useState(0);

  const retry = useCallback(() => {
    setRetryTrigger((prev) => prev + 1);
  }, []);

  useEffect(() => {
    if (!enabled || !fen) {
      setData(null);
      setLoading(false);
      setError(null);
      setUpstreamDown(false);
      return;
    }

    let cancelled = false;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      setUpstreamDown(false);

      try {
        const params = new URLSearchParams();
        params.set('fen', fen);

        if (database === 'player') {
          if (!player || !color) {
            throw new Error('Player and color are required for player database');
          }
          params.set('player', player);
          params.set('color', color);
          params.set('recentGames', recentGames.toString());
          if (speeds) {
            params.set('speeds', speeds);
          }
          if (modes) {
            params.set('modes', modes);
          }
        } else {
          params.set('topGames', '50');
          params.set('moves', '12');

          if (database === 'lichess') {
            params.set('ratings', ratings);
            params.set('speeds', speeds);
          }
        }

        const endpoint = database === 'masters' ? 'masters' : database === 'player' ? 'player' : 'lichess';

        const response = await fetch(`/api/explorer/${endpoint}?${params.toString()}`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to fetch: ${response.status}`);
        }

        const result = await response.json();

        if (!cancelled) {
          const explorerStatus = response.headers.get('X-Explorer-Status');
          const hasUpstreamError = explorerStatus?.includes('upstream-error') || result._upstreamError === true;

          if (hasUpstreamError) {
            setUpstreamDown(true);
          }

          setData(result);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to fetch explorer data');
          setData(null);
          setUpstreamDown(false);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      cancelled = true;
    };
  }, [fen, database, enabled, ratings, speeds, player, color, modes, recentGames, retryTrigger]);

  return { data, loading, error, upstreamDown, retry };
}
