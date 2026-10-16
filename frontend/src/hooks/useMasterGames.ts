/**
 * useMasterGames — authenticated access to the Master (TWIC) games database:
 * games / candidate moves for a position, and single-game PGNs.
 */

import { useCallback } from 'react';
import { useAuth } from '@clerk/nextjs';
import { apiFetch as globalApiFetch } from '@/lib/api';

const API_BASE = '/api/openings';

// ─── Types ───────────────────────────────

export interface GameSearchResult {
  id: string | number;
  source: string;
  white: string;
  black: string;
  white_name?: string;
  black_name?: string;
  white_elo: number | null;
  black_elo: number | null;
  result: string;
  date: string;
  year?: number | string;
  eco: string | null;
  opening: string | null;
  event: string | null;
  pgn?: string;
  pgn_offset?: number;
  pgn_length?: number;
  url?: string;
}

export interface MoveCandidate {
  uci: string;
  san: string;
  count: number;
  percentage: number;
  white_wins: number;
  draws: number;
  black_wins: number;
  avg_elo: number | null;
  avg_year: number | null;
  score: string;
  winrate: string;
}

export interface CandidatesResponse {
  status: string;
  total_games: number;
  moves: MoveCandidate[];
}

export interface GamesByPositionFilters {
  playerColor?: string;
  playerName?: string;
  sortBy?: string;
  opponentName?: string;
  result?: string;
  whiteEloMin?: number;
  whiteEloMax?: number;
  blackEloMin?: number;
  blackEloMax?: number;
  dateFrom?: string;
  dateTo?: string;
  ecoCode?: string;
  eventName?: string;
}

export interface GamesByPositionResponse {
  games: GameSearchResult[];
  total: number;
  indexed: boolean;
  count_exact?: boolean;
}

// ─── Hook ────────────────────────────────

export function useMasterGames() {
  const { getToken } = useAuth();

  const fetchWithAuth = useCallback(async <T>(path: string, options?: RequestInit & { timeout?: number }): Promise<T> => {
    const token = await getToken();
    if (!token) throw new Error('Not authenticated');
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    };
    return globalApiFetch<T>(`${API_BASE}${path}`, {
      ...options,
      headers: { ...headers, ...options?.headers },
    });
  }, [getToken]);

  const fetchGamesByPosition = useCallback(async (
    fen: string,
    limit: number,
    f: GamesByPositionFilters = {},
  ): Promise<GamesByPositionResponse> => {
    const params = new URLSearchParams({ fen, limit: String(limit) });
    if (f.playerColor) params.set('player_color', f.playerColor);
    if (f.playerName) params.set('player_name', f.playerName);
    if (f.opponentName) params.set('opponent_name', f.opponentName);
    if (f.sortBy && f.sortBy !== 'date_desc') params.set('sort_by', f.sortBy);
    if (f.result) params.set('result', f.result);
    if (f.whiteEloMin) params.set('white_elo_min', String(f.whiteEloMin));
    if (f.whiteEloMax !== undefined && f.whiteEloMax !== 3500) params.set('white_elo_max', String(f.whiteEloMax));
    if (f.blackEloMin) params.set('black_elo_min', String(f.blackEloMin));
    if (f.blackEloMax !== undefined && f.blackEloMax !== 3500) params.set('black_elo_max', String(f.blackEloMax));
    if (f.dateFrom) params.set('date_from', f.dateFrom);
    if (f.dateTo) params.set('date_to', f.dateTo);
    if (f.ecoCode) params.set('eco_code', f.ecoCode);
    if (f.eventName) params.set('event_name', f.eventName);
    const data = await fetchWithAuth<GamesByPositionResponse>(`/games/by-position?${params}`, { timeout: 120000 });
    return {
      ...data,
      games: Array.isArray(data.games) ? data.games : [],
      total: typeof data.total === 'number' ? data.total : 0,
    };
  }, [fetchWithAuth]);

  const fetchPositionCount = useCallback(async (fen: string): Promise<number> => {
    const params = new URLSearchParams({ fen });
    const data = await fetchWithAuth<{ count: number }>(`/games/position-count?${params}`);
    return data.count;
  }, [fetchWithAuth]);

  const fetchCandidateMoves = useCallback(async (fen: string): Promise<CandidatesResponse> => {
    const params = new URLSearchParams({ fen, limit: '20' });
    const data = await fetchWithAuth<Partial<CandidatesResponse>>(`/positions/candidates?${params}`, { timeout: 60000 });
    return {
      status: data.status || 'ok',
      total_games: data.total_games || 0,
      moves: Array.isArray(data.moves) ? data.moves : [],
    };
  }, [fetchWithAuth]);

  const fetchGamePgn = useCallback(async (gameId: number): Promise<string> => {
    const data = await fetchWithAuth<{ pgn: string }>(`/games/${gameId}/pgn`);
    return data.pgn;
  }, [fetchWithAuth]);

  const fetchLichessPgn = useCallback(async (gameId: string): Promise<string> => {
    const data = await fetchWithAuth<{ pgn: string }>(`/games/lichess/${gameId}/pgn`);
    return data.pgn;
  }, [fetchWithAuth]);

  return { fetchGamesByPosition, fetchPositionCount, fetchCandidateMoves, fetchGamePgn, fetchLichessPgn };
}
