/**
 * useUserGames — Hook for managing user's saved games
 * Communicates with /api/games backend endpoints (CRUD + bulk import)
 */

import { useState, useCallback } from 'react';
import { useAuth } from '@clerk/nextjs';
import { apiFetch as globalApiFetch } from '@/lib/api';

const API_BASE = '/api/games';

// ─── Types ───────────────────────────────

export interface UserGame {
  id: string;
  user_id: string;
  title: string | null;
  white: string;
  black: string;
  white_elo: number | null;
  black_elo: number | null;
  result: string;
  date: string | null;
  event: string | null;
  eco: string | null;
  opening_name: string | null;
  pgn: string;
  notes: string | null;
  tags: string[];
  is_favorite: boolean;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface ListGamesResponse {
  games: UserGame[];
  total: number;
  page: number;
  per_page: number;
}

export interface ListGamesFilters {
  q?: string;
  result?: string;
  favorite?: boolean;
  tag?: string;
}

export interface ImportResult {
  imported: number;
  errors: { index: number; error: string }[];
  games: UserGame[];
}

// ─── Hook ────────────────────────────────

export function useUserGames() {
  const { getToken } = useAuth();

  const [games, setGames] = useState<UserGame[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchWithAuth = useCallback(async <T,>(
    path: string,
    options?: RequestInit & { timeout?: number }
  ): Promise<T> => {
    const token = await getToken() || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJsb2NhbF91c2VyIn0.FakeTokenForLocalDev';
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    };
    return globalApiFetch<T>(`${API_BASE}${path}`, {
      ...options,
      headers: { ...headers, ...options?.headers },
    });
  }, [getToken]);

  // ── List games with pagination & filters ──

  const fetchGames = useCallback(async (
    pageNum = 1,
    itemsPerPage = 20,
    filters?: ListGamesFilters
  ) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: String(pageNum),
        per_page: String(itemsPerPage),
      });
      if (filters?.q) params.set('q', filters.q);
      if (filters?.result) params.set('result', filters.result);
      if (filters?.favorite) params.set('favorite', 'true');
      if (filters?.tag) params.set('tag', filters.tag);

      const data = await fetchWithAuth<ListGamesResponse>(`?${params}`);
      setGames(data.games);
      setTotal(data.total);
      setPage(data.page);
      setPerPage(data.per_page);
      return data;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to fetch games';
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth]);

  // ── Get single game ──

  const getGame = useCallback(async (id: string): Promise<UserGame | null> => {
    setError(null);
    try {
      return await fetchWithAuth<UserGame>(`/${id}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to fetch game';
      setError(msg);
      return null;
    }
  }, [fetchWithAuth]);

  // ── Create game ──

  const createGame = useCallback(async (
    pgn: string,
    metadata?: Partial<Omit<UserGame, 'id' | 'user_id' | 'created_at' | 'updated_at'>>
  ): Promise<UserGame | null> => {
    setError(null);
    try {
      const game = await fetchWithAuth<UserGame>('', {
        method: 'POST',
        body: JSON.stringify({ pgn, ...metadata }),
      });
      setGames(prev => [game, ...prev]);
      setTotal(prev => prev + 1);
      return game;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to create game';
      setError(msg);
      return null;
    }
  }, [fetchWithAuth]);

  // ── Update game ──

  const updateGame = useCallback(async (
    id: string,
    updates: Partial<Omit<UserGame, 'id' | 'user_id' | 'created_at'>>
  ): Promise<UserGame | null> => {
    setError(null);
    try {
      const updated = await fetchWithAuth<UserGame>(`/${id}`, {
        method: 'PUT',
        body: JSON.stringify(updates),
      });
      setGames(prev => prev.map(g => g.id === id ? updated : g));
      return updated;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to update game';
      setError(msg);
      return null;
    }
  }, [fetchWithAuth]);

  // ── Delete game (soft) ──

  const deleteGame = useCallback(async (id: string): Promise<boolean> => {
    setError(null);
    try {
      await fetchWithAuth<{ success: boolean }>(`/${id}`, { method: 'DELETE' });
      setGames(prev => prev.filter(g => g.id !== id));
      setTotal(prev => prev - 1);
      return true;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to delete game';
      setError(msg);
      return false;
    }
  }, [fetchWithAuth]);

  // ── Toggle favorite ──

  const toggleFavorite = useCallback(async (id: string): Promise<boolean> => {
    const game = games.find(g => g.id === id);
    if (!game) return false;

    const result = await updateGame(id, { is_favorite: !game.is_favorite });
    return result !== null;
  }, [games, updateGame]);

  // ── Bulk import from localStorage ──

  const importFromLocal = useCallback(async (
    gamesToImport: Array<{ pgn: string; [key: string]: unknown }>
  ): Promise<ImportResult | null> => {
    setError(null);
    try {
      return await fetchWithAuth<ImportResult>('/import-local', {
        method: 'POST',
        body: JSON.stringify({ games: gamesToImport }),
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to import games';
      setError(msg);
      return null;
    }
  }, [fetchWithAuth]);

  return {
    // State
    games,
    total,
    page,
    perPage,
    loading,
    error,
    // Operations
    fetchGames,
    getGame,
    createGame,
    updateGame,
    deleteGame,
    toggleFavorite,
    importFromLocal,
  };
}
