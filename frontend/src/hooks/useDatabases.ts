/**
 * useDatabases — Hook for managing the user's game databases (collections).
 *
 * Mirrors the auth/fetch/optimistic conventions of useUserGames (legacy path):
 * a Clerk bearer token per request, the shared apiFetch, optimistic list
 * mutations that roll back on error. A 409 duplicate-name surfaces as a
 * friendly inline `error` string rather than a throw, so the pill-row UI can
 * keep its inline input open.
 *
 * Phase 3 adds soft-delete (optimistic pill removal), restore, and listing the
 * recently-deleted databases for the restore panel.
 */

import { useState, useRef, useCallback } from 'react';
import { useAuth } from '@clerk/nextjs';
import { apiFetch as globalApiFetch } from '@/lib/api';

const API_BASE = '/api/databases';

// ─── Types ───────────────────────────────

export interface UserDatabase {
  id: string;
  name: string;
  is_default: boolean;
  game_count: number;
  created_at?: string;
  updated_at?: string;
}

/** A soft-deleted database still within its 30-day recovery window. */
export interface DeletedDatabase {
  id: string;
  name: string;
  deleted_at: string;
  game_count: number;
  days_left: number;
}

const DUPLICATE_NAME_MESSAGE = 'A database with that name already exists.';

/** True for a 409 Conflict (duplicate name) from apiFetch's ApiError. */
function isConflict(e: unknown): boolean {
  return (e as { status?: number })?.status === 409;
}

export function useDatabases() {
  const { getToken } = useAuth();

  const [databases, setDatabasesState] = useState<UserDatabase[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Mirror the list into a ref so optimistic mutations can read the prior state
  // synchronously (a state-updater closure runs too late to capture it reliably).
  const databasesRef = useRef<UserDatabase[]>([]);
  const setDatabases = useCallback(
    (updater: UserDatabase[] | ((prev: UserDatabase[]) => UserDatabase[])) => {
      setDatabasesState(prev => {
        const next = typeof updater === 'function' ? updater(prev) : updater;
        databasesRef.current = next;
        return next;
      });
    },
    [],
  );

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

  const refresh = useCallback(async (): Promise<UserDatabase[] | null> => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchWithAuth<UserDatabase[]>('');
      setDatabases(data);
      return data;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load databases';
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth, setDatabases]);

  const createDatabase = useCallback(async (name: string): Promise<UserDatabase | null> => {
    setError(null);
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Name is required');
      return null;
    }
    try {
      const created = await fetchWithAuth<UserDatabase>('', {
        method: 'POST',
        body: JSON.stringify({ name: trimmed }),
      });
      // Append after the default (which is always first), before refetch.
      setDatabases(prev => [...prev, created]);
      return created;
    } catch (e: unknown) {
      if (isConflict(e)) {
        setError(DUPLICATE_NAME_MESSAGE);
      } else {
        setError(e instanceof Error ? e.message : 'Failed to create database');
      }
      return null;
    }
  }, [fetchWithAuth, setDatabases]);

  const renameDatabase = useCallback(async (id: string, name: string): Promise<UserDatabase | null> => {
    setError(null);
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Name is required');
      return null;
    }
    // Optimistic rename, keep the previous name to roll back on failure.
    const previousName = databasesRef.current.find(db => db.id === id)?.name;
    setDatabases(prev => prev.map(db => (db.id === id ? { ...db, name: trimmed } : db)));
    try {
      const updated = await fetchWithAuth<UserDatabase>(`/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ name: trimmed }),
      });
      setDatabases(prev => prev.map(db => (db.id === id ? { ...db, ...updated } : db)));
      return updated;
    } catch (e: unknown) {
      // Roll back the optimistic rename.
      if (previousName !== undefined) {
        setDatabases(prev => prev.map(db => (db.id === id ? { ...db, name: previousName } : db)));
      }
      if (isConflict(e)) {
        setError(DUPLICATE_NAME_MESSAGE);
      } else {
        setError(e instanceof Error ? e.message : 'Failed to rename database');
      }
      return null;
    }
  }, [fetchWithAuth, setDatabases]);

  const deleteDatabase = useCallback(async (id: string): Promise<boolean> => {
    setError(null);
    // Optimistic removal; keep the prior list to roll back on failure.
    const previous = databasesRef.current;
    setDatabases(prev => prev.filter(db => db.id !== id));
    try {
      await fetchWithAuth<{ success: boolean }>(`/${id}`, { method: 'DELETE' });
      return true;
    } catch (e: unknown) {
      setDatabases(previous); // roll back the optimistic removal
      setError(e instanceof Error ? e.message : 'Failed to delete database');
      return false;
    }
  }, [fetchWithAuth, setDatabases]);

  const restoreDatabase = useCallback(async (id: string): Promise<UserDatabase | null> => {
    setError(null);
    try {
      const restored = await fetchWithAuth<UserDatabase>(`/${id}/restore`, { method: 'POST' });
      // Re-fetch so the restored pill lands in its canonical (default-first) slot
      // with an up-to-date game_count.
      await refresh();
      return restored;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to restore database');
      return null;
    }
  }, [fetchWithAuth, refresh]);

  const listDeleted = useCallback(async (): Promise<DeletedDatabase[]> => {
    try {
      return await fetchWithAuth<DeletedDatabase[]>('/deleted');
    } catch {
      return [];
    }
  }, [fetchWithAuth]);

  return {
    databases,
    loading,
    error,
    refresh,
    createDatabase,
    renameDatabase,
    deleteDatabase,
    restoreDatabase,
    listDeleted,
  };
}
