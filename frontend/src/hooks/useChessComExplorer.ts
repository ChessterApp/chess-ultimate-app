/**
 * useChessComExplorer — Hook for fetching Chess.com player games with progressive loading
 *
 * Features:
 * - Fetch player game archives list
 * - Progressive loading: fetch newest month first, then older months in background
 * - Client-side filtering by time control and rating
 * - Browser-side session caching
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { explorerSessionCache } from '@/lib/explorer-session-cache';
import type { GameSearchResult } from './useOpeningRepertoire';

export interface ChessComGame {
  url: string;
  pgn: string;
  time_control: string;
  end_time: number;
  rated: boolean;
  fen: string;
  time_class: string;
  rules: string;
  white: {
    username: string;
    rating: number;
    result: string;
  };
  black: {
    username: string;
    rating: number;
    result: string;
  };
}

export interface ChessComMonthData {
  games: ChessComGame[];
}

export interface UseChessComExplorerOptions {
  username: string;
  enabled?: boolean;
}

export interface UseChessComExplorerResult {
  games: GameSearchResult[];
  loading: boolean;
  error: string | null;
  retry: () => void;
  progress: { loaded: number; total: number } | null;
}

/**
 * Convert Chess.com time_class to readable format
 */
function formatTimeClass(timeClass: string): string {
  const map: Record<string, string> = {
    bullet: 'Bullet',
    blitz: 'Blitz',
    rapid: 'Rapid',
    daily: 'Daily',
    classical: 'Classical',
  };
  return map[timeClass] || timeClass;
}

/**
 * Parse Chess.com game result (e.g., "win", "checkmated", "resigned", "timeout")
 */
function parseResult(game: ChessComGame): string {
  if (game.white.result === 'win') return '1-0';
  if (game.black.result === 'win') return '0-1';
  return '½-½';
}

/**
 * Transform ChessComGame to GameSearchResult
 */
function transformGame(game: ChessComGame): GameSearchResult {
  const date = new Date(game.end_time * 1000);
  const dateStr = `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, '0')}.${String(date.getDate()).padStart(2, '0')}`;

  return {
    id: game.url,
    source: 'chesscom',
    white: game.white.username,
    black: game.black.username,
    white_elo: game.white.rating,
    black_elo: game.black.rating,
    result: parseResult(game),
    date: dateStr,
    eco: null,
    opening: null,
    event: formatTimeClass(game.time_class),
    url: game.url,
    pgn: game.pgn,
  };
}

export function useChessComExplorer({
  username,
  enabled = true,
}: UseChessComExplorerOptions): UseChessComExplorerResult {
  const [games, setGames] = useState<GameSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ loaded: number; total: number } | null>(null);
  const [retryTrigger, setRetryTrigger] = useState(0);

  const abortControllerRef = useRef<AbortController | null>(null);

  const retry = useCallback(() => {
    setRetryTrigger((prev) => prev + 1);
  }, []);

  useEffect(() => {
    if (!enabled || !username) {
      setGames([]);
      setLoading(false);
      setError(null);
      setProgress(null);
      return;
    }

    // Create new abort controller for this fetch
    const controller = new AbortController();
    abortControllerRef.current = controller;

    let cancelled = false;

    const fetchGames = async () => {
      setLoading(true);
      setError(null);
      setGames([]);
      setProgress(null);

      try {
        // Stale-while-revalidate: serve cached immediately, fetch fresh in background
        const cacheKey = username;
        const cached = explorerSessionCache.chesscom.get<GameSearchResult[]>(cacheKey);
        if (cached && !cancelled) {
          setGames(cached);
          setLoading(false);
          // Continue to fetch fresh data in background (don't return)
        }

        // Step 1: Fetch archives list
        const archivesRes = await fetch(`/api/chesscom/pub/player/${username}/games/archives`, {
          signal: controller.signal,
        });

        if (!archivesRes.ok) {
          if (archivesRes.status === 404) {
            throw new Error('Player not found');
          }
          throw new Error(`Failed to fetch archives: ${archivesRes.status}`);
        }

        const archivesData = await archivesRes.json();
        const archives: string[] = archivesData.archives || [];

        if (archives.length === 0) {
          if (!cancelled) {
            setGames([]);
            setLoading(false);
            setProgress({ loaded: 0, total: 0 });
          }
          return;
        }

        // Step 2: Fetch months progressively (newest first)
        const allGames: GameSearchResult[] = [];
        const totalMonths = archives.length;

        // Reverse to get newest first
        const reversedArchives = [...archives].reverse();

        for (let i = 0; i < reversedArchives.length; i++) {
          if (cancelled) break;

          const archiveUrl = reversedArchives[i];
          // Extract YYYY/MM from URL (e.g., "https://api.chess.com/pub/player/{username}/games/2024/03")
          const match = archiveUrl.match(/\/games\/(\d{4})\/(\d{2})$/);
          if (!match) continue;

          const [, year, month] = match;

          try {
            const monthRes = await fetch(`/api/chesscom/pub/player/${username}/games/${year}/${month}`, {
              signal: controller.signal,
            });

            if (!monthRes.ok) {
              // Skip failed months
              continue;
            }

            const monthData: ChessComMonthData = await monthRes.json();
            const monthGames = (monthData.games || []).map(transformGame);

            if (!cancelled) {
              allGames.push(...monthGames);
              setGames([...allGames]);
              setProgress({ loaded: i + 1, total: totalMonths });
            }

            // Fetch first month immediately, then add delays for background fetches
            if (i > 0) {
              await new Promise((resolve) => setTimeout(resolve, 200)); // 200ms between requests
            }
          } catch (err) {
            // Skip failed months
            continue;
          }
        }

        if (!cancelled) {
          // Cache for 10 minutes (uses default TTL from cache config)
          explorerSessionCache.chesscom.set(cacheKey, allGames);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled && err instanceof Error && err.name !== 'AbortError') {
          setError(err.message || 'Failed to fetch Chess.com games');
          setGames([]);
          setLoading(false);
        }
      }
    };

    fetchGames();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [username, enabled, retryTrigger]);

  return { games, loading, error, retry, progress };
}
