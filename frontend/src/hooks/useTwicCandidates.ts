/**
 * useTwicCandidates — Hook for fetching TWIC candidate moves from local database
 *
 * Fetches candidate moves from our 100M+ TWIC move_stats database via /api/openings/positions/candidates
 */

import { useState, useEffect, useCallback } from 'react';

export interface TwicCandidate {
  san: string;
  uci: string;
  games: number;
  white_wins: number;
  draws: number;
  black_wins: number;
  avg_white_elo: number;
  avg_black_elo: number;
  avg_year: number;
  win_rate?: number;
  draw_rate?: number;
  loss_rate?: number;
}

export interface TwicCandidatesResponse {
  moves: TwicCandidate[];
  total_games: number;
  position_found: boolean;
}

export interface UseTwicCandidatesOptions {
  fen: string;
  enabled?: boolean;
  debounceMs?: number;
}

export interface UseTwicCandidatesResult {
  data: TwicCandidatesResponse | null;
  loading: boolean;
  error: string | null;
  retry: () => void;
}

export function useTwicCandidates({
  fen,
  enabled = true,
  debounceMs = 300,
}: UseTwicCandidatesOptions): UseTwicCandidatesResult {
  const [data, setData] = useState<TwicCandidatesResponse | null>(null);
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

        const response = await fetch(`/api/openings/positions/candidates?${params.toString()}`, {
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
          // Calculate percentages if not already present
          const movesWithPercentages = result.moves?.map((move: TwicCandidate) => {
            const total = move.games || 1;
            return {
              ...move,
              win_rate: ((move.white_wins || 0) / total) * 100,
              draw_rate: ((move.draws || 0) / total) * 100,
              loss_rate: ((move.black_wins || 0) / total) * 100,
            };
          }) || [];

          setData({
            moves: movesWithPercentages,
            total_games: result.total_games || 0,
            position_found: result.position_found !== false,
          });
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to fetch TWIC candidates');
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
  }, [fen, enabled, debounceMs, retryTrigger]);

  return { data, loading, error, retry };
}
