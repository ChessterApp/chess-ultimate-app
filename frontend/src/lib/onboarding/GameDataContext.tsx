'use client';

import React, { createContext, useContext, useState, useCallback, useRef } from 'react';
import {
  fetchAndAnalyzeGames,
  type OnboardingGameData,
  type PlayerStats,
  type ParsedGame,
} from './gameFetcher';

interface GameDataContextValue {
  gameData: OnboardingGameData | null;
  isLoading: boolean;
  error: string | null;
  fetchGames: (platform: 'lichess' | 'chessdotcom', username: string) => Promise<void>;
  reset: () => void;
}

const GameDataContext = createContext<GameDataContextValue | null>(null);

export function GameDataProvider({ children }: { children: React.ReactNode }) {
  const [gameData, setGameData] = useState<OnboardingGameData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef(false);

  const fetchGames = useCallback(
    async (platform: 'lichess' | 'chessdotcom', username: string) => {
      abortRef.current = false;
      setIsLoading(true);
      setError(null);
      setGameData(null);

      try {
        const result = await fetchAndAnalyzeGames(platform, username);
        if (abortRef.current) return;

        if (result.status === 'error') {
          setError(result.error || 'Unknown error');
          setGameData(null);
        } else {
          setGameData(result);
          setError(null);
        }
      } catch (err) {
        if (!abortRef.current) {
          setError(err instanceof Error ? err.message : 'Failed to fetch games');
        }
      } finally {
        if (!abortRef.current) setIsLoading(false);
      }
    },
    []
  );

  const reset = useCallback(() => {
    abortRef.current = true;
    setGameData(null);
    setIsLoading(false);
    setError(null);
  }, []);

  return (
    <GameDataContext.Provider value={{ gameData, isLoading, error, fetchGames, reset }}>
      {children}
    </GameDataContext.Provider>
  );
}

export function useGameData(): GameDataContextValue {
  const ctx = useContext(GameDataContext);
  if (!ctx) {
    throw new Error('useGameData must be used within a GameDataProvider');
  }
  return ctx;
}

// Re-export types for convenience
export type { OnboardingGameData, PlayerStats, ParsedGame } from './gameFetcher';
export type { OpeningStat } from './gameFetcher';
