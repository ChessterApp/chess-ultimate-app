import { useState, useCallback } from 'react';
import { GameReviewTheme } from '@/lib/themes/helper';
import { apiFetch, ApiError } from '@/lib/api';

interface UseGameThemeReturn {
  gameReviewTheme: GameReviewTheme | null;
  isLoading: boolean;
  error: string | null;
  analyzeGameTheme: (pgn: string, criticalMomentThreshold?: number) => Promise<void>;
  reset: () => void;
}

export function useGameTheme(): UseGameThemeReturn {
  const [gameReviewTheme, setGameReviewTheme] = useState<GameReviewTheme | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analyzeGameTheme = useCallback(async (
    pgn: string, 
  ) => {
    // Reset previous state
    setError(null);
    setIsLoading(true);

    try {
      const data = await apiFetch<GameReviewTheme>('/api/gametheme', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          pgn: pgn
        }),
      });
      setGameReviewTheme(data);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An unexpected error occurred';
      setError(errorMessage);
      setGameReviewTheme(null);
      console.error('Error analyzing game:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setGameReviewTheme(null);
    setError(null);
    setIsLoading(false);
  }, []);

  return {
    gameReviewTheme,
    isLoading,
    error,
    analyzeGameTheme,
    reset,
  };
}
