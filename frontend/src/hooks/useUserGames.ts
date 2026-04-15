/**
 * useUserGames — Hook for managing user's saved games
 * Supports both legacy fetch and PowerSync/TanStack DB live queries.
 * Controlled by LOCAL_FIRST_GAMES feature flag.
 */

import { useState, useCallback, useMemo } from 'react';
import { useAuth } from '@clerk/nextjs';
import { apiFetch as globalApiFetch } from '@/lib/api';
import { LOCAL_FIRST_GAMES } from '@/lib/feature-flags';
import { usePowerSyncContext } from '@/lib/powersync/PowerSyncProvider';
import { useLiveQuery } from '@tanstack/react-db';
import { eq } from '@tanstack/db';

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

// ─── Row → UserGame conversion ──────────

function rowToUserGame(row: Record<string, unknown>): UserGame {
  let tags: string[] = [];
  if (typeof row.tags === 'string') {
    try { tags = JSON.parse(row.tags as string); } catch { tags = []; }
  }

  return {
    id: row.id as string,
    user_id: row.user_id as string,
    title: (row.title as string) ?? null,
    white: (row.white as string) ?? '',
    black: (row.black as string) ?? '',
    white_elo: row.white_elo as number | null,
    black_elo: row.black_elo as number | null,
    result: (row.result as string) ?? '',
    date: (row.date as string) ?? null,
    event: (row.event as string) ?? null,
    eco: (row.eco as string) ?? null,
    opening_name: (row.opening_name as string) ?? null,
    pgn: (row.pgn as string) ?? '',
    notes: (row.notes as string) ?? null,
    tags,
    is_favorite: row.is_favorite === 1 || row.is_favorite === true,
    source: (row.source as string) ?? '',
    created_at: (row.created_at as string) ?? '',
    updated_at: (row.updated_at as string) ?? '',
  };
}

// ─── PowerSync-backed hook ──────────────

function useUserGamesPowerSync() {
  const { userId, getToken } = useAuth();
  const { collections, isReady, database } = usePowerSyncContext();

  const [error, setError] = useState<string | null>(null);

  const { data: rawData, isLoading } = useLiveQuery(
    (q) => {
      if (!collections || !isReady || !userId) return null;
      return q
        .from({ g: collections.userGames })
        .where(({ g }) => eq(g.user_id, userId))
        .select(({ g }) => ({
          id: g.id,
          user_id: g.user_id,
          title: g.title,
          white: g.white,
          black: g.black,
          white_elo: g.white_elo,
          black_elo: g.black_elo,
          result: g.result,
          date: g.date,
          event: g.event,
          eco: g.eco,
          opening_name: g.opening_name,
          pgn: g.pgn,
          notes: g.notes,
          tags: g.tags,
          is_favorite: g.is_favorite,
          source: g.source,
          created_at: g.created_at,
          updated_at: g.updated_at,
        }));
    },
    [collections, isReady, userId],
  );

  const games = useMemo(
    () => (rawData ?? []).map(rowToUserGame).sort(
      (a, b) => (b.created_at || '').localeCompare(a.created_at || ''),
    ),
    [rawData],
  );

  const fetchWithAuth = useCallback(async <T,>(
    path: string,
    options?: RequestInit & { timeout?: number }
  ): Promise<T> => {
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

  // For PowerSync mode, fetchGames is a no-op since data comes from live query.
  // But we return a compatible signature for callers that call it imperatively.
  const fetchGames = useCallback(async (
    _pageNum = 1,
    _itemsPerPage = 20,
    _filters?: ListGamesFilters,
  ) => {
    return {
      games,
      total: games.length,
      page: 1,
      per_page: games.length,
    } as ListGamesResponse;
  }, [games]);

  const getGame = useCallback(async (id: string): Promise<UserGame | null> => {
    // Try local first
    const local = games.find(g => g.id === id);
    if (local) return local;
    // Fallback to API for games not yet synced
    try {
      return await fetchWithAuth<UserGame>(`/${id}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to fetch game';
      setError(msg);
      return null;
    }
  }, [games, fetchWithAuth]);

  const createGame = useCallback(async (
    pgn: string,
    metadata?: Partial<Omit<UserGame, 'id' | 'user_id' | 'created_at' | 'updated_at'>>
  ): Promise<UserGame | null> => {
    setError(null);
    try {
      // Write through API — PowerSync will sync back via CDC
      const game = await fetchWithAuth<UserGame>('', {
        method: 'POST',
        body: JSON.stringify({ pgn, ...metadata }),
      });
      return game;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to create game';
      setError(msg);
      return null;
    }
  }, [fetchWithAuth]);

  const updateGame = useCallback(async (
    id: string,
    updates: Partial<Omit<UserGame, 'id' | 'user_id' | 'created_at'>>
  ): Promise<UserGame | null> => {
    setError(null);
    try {
      if (database && collections) {
        // Optimistic update via PowerSync local write
        const dbUpdates: Record<string, unknown> = {};
        if (updates.title !== undefined) dbUpdates.title = updates.title;
        if (updates.notes !== undefined) dbUpdates.notes = updates.notes;
        if (updates.is_favorite !== undefined) dbUpdates.is_favorite = updates.is_favorite ? 1 : 0;
        if (updates.tags !== undefined) dbUpdates.tags = JSON.stringify(updates.tags);
        if (updates.pgn !== undefined) dbUpdates.pgn = updates.pgn;
        dbUpdates.updated_at = new Date().toISOString();

        await database.execute(
          `UPDATE user_games SET ${Object.keys(dbUpdates).map(k => `${k} = ?`).join(', ')} WHERE id = ?`,
          [...Object.values(dbUpdates), id],
        );

        const updated = games.find(g => g.id === id);
        return updated ? { ...updated, ...updates } as UserGame : null;
      }
      // Fallback to API
      const updated = await fetchWithAuth<UserGame>(`/${id}`, {
        method: 'PUT',
        body: JSON.stringify(updates),
      });
      return updated;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to update game';
      setError(msg);
      return null;
    }
  }, [fetchWithAuth, database, collections, games]);

  const deleteGame = useCallback(async (id: string): Promise<boolean> => {
    setError(null);
    try {
      if (database) {
        await database.execute('DELETE FROM user_games WHERE id = ?', [id]);
        return true;
      }
      await fetchWithAuth<{ success: boolean }>(`/${id}`, { method: 'DELETE' });
      return true;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to delete game';
      setError(msg);
      return false;
    }
  }, [fetchWithAuth, database]);

  const toggleFavorite = useCallback(async (id: string): Promise<boolean> => {
    const game = games.find(g => g.id === id);
    if (!game) return false;
    const result = await updateGame(id, { is_favorite: !game.is_favorite });
    return result !== null;
  }, [games, updateGame]);

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
    games,
    total: games.length,
    page: 1,
    perPage: games.length,
    loading: isLoading,
    error,
    fetchGames,
    getGame,
    createGame,
    updateGame,
    deleteGame,
    toggleFavorite,
    importFromLocal,
  };
}

// ─── Legacy fetch-based hook ────────────

function useUserGamesLegacy() {
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
    const token = await getToken();
    if (!token) {
      throw new Error('Not authenticated');
    }
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    };
    return globalApiFetch<T>(`${API_BASE}${path}`, {
      ...options,
      headers: { ...headers, ...options?.headers },
    });
  }, [getToken]);

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

  const toggleFavorite = useCallback(async (id: string): Promise<boolean> => {
    const game = games.find(g => g.id === id);
    if (!game) return false;

    const result = await updateGame(id, { is_favorite: !game.is_favorite });
    return result !== null;
  }, [games, updateGame]);

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
    games,
    total,
    page,
    perPage,
    loading,
    error,
    fetchGames,
    getGame,
    createGame,
    updateGame,
    deleteGame,
    toggleFavorite,
    importFromLocal,
  };
}

// ─── Exported hook ──────────────────────

export function useUserGames() {
  // PowerSync path disabled: @tanstack/react-db useLiveQuery lacks
  // getServerSnapshot for SSR, causing HTTP 500. Re-enable when fixed.
  return useUserGamesLegacy();
}
