/**
 * useRepertoire Hook
 * Manages user's opening repertoire collection
 * Provides CRUD operations for openings and variations
 */

import { useState, useCallback, useEffect } from 'react';
import { useAuth } from '@clerk/nextjs';
import {
  RepertoireOpening,
  OpeningVariation,
  AddOpeningRequest,
  UpdateOpeningRequest,
  AddVariationRequest,
  UseRepertoireReturn,
} from '@/types/repertoire';
import { apiFetch, ApiError } from '@/lib/api';

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'https://api.chesster.io';

export function useRepertoire(): UseRepertoireReturn {
  const { getToken } = useAuth();

  const [repertoire, setRepertoire] = useState<RepertoireOpening[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /**
   * Helper function to make authenticated API calls
   */
  const fetchWithAuth = useCallback(
    async (endpoint: string, options: RequestInit = {}) => {
      const token = await getToken();
      if (!token) {
        throw new Error('Authentication required');
      }

      const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...options.headers,
      };

      return apiFetch<any>(`${API_URL}${endpoint}`, {
        ...options,
        headers,
      });
    },
    [getToken]
  );

  /**
   * Fetch user's entire repertoire from server
   */
  const fetchRepertoire = useCallback(
    async (color?: 'white' | 'black') => {
      setLoading(true);
      try {
        const params = color ? `?color=${color}` : '';
        const data = await fetchWithAuth(`/api/repertoire${params}`);
        setRepertoire(data);
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch repertoire';
        setError(message);
        console.error('Error fetching repertoire:', err);
      } finally {
        setLoading(false);
      }
    },
    [fetchWithAuth]
  );

  /**
   * Add opening to user's repertoire
   */
  const addToRepertoire = useCallback(
    async (opening: AddOpeningRequest): Promise<RepertoireOpening> => {
      try {
        const data = await fetchWithAuth('/api/repertoire', {
          method: 'POST',
          body: JSON.stringify(opening),
        });

        // Add to local state immediately
        setRepertoire((prev) => [data, ...prev]);
        setError(null);
        return data;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to add opening';
        setError(message);
        throw err;
      }
    },
    [fetchWithAuth]
  );

  /**
   * Update opening in repertoire
   */
  const updateOpening = useCallback(
    async (openingId: string, updates: UpdateOpeningRequest): Promise<void> => {
      try {
        const data = await fetchWithAuth(`/api/repertoire/${openingId}`, {
          method: 'PUT',
          body: JSON.stringify(updates),
        });

        // Update local state
        setRepertoire((prev) =>
          prev.map((o) => (o.opening_id === openingId ? data : o))
        );
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to update opening';
        setError(message);
        throw err;
      }
    },
    [fetchWithAuth]
  );

  /**
   * Remove opening from repertoire
   */
  const removeFromRepertoire = useCallback(
    async (openingId: string): Promise<void> => {
      try {
        await fetchWithAuth(`/api/repertoire/${openingId}`, {
          method: 'DELETE',
        });

        // Remove from local state
        setRepertoire((prev) => prev.filter((o) => o.opening_id !== openingId));
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to remove opening';
        setError(message);
        throw err;
      }
    },
    [fetchWithAuth]
  );

  /**
   * Add variation to an opening
   */
  const addVariation = useCallback(
    async (repertoireId: string, variation: AddVariationRequest): Promise<OpeningVariation> => {
      try {
        const data = await fetchWithAuth(`/api/repertoire/${repertoireId}/variations`, {
          method: 'POST',
          body: JSON.stringify(variation),
        });

        setError(null);
        return data;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to add variation';
        setError(message);
        throw err;
      }
    },
    [fetchWithAuth]
  );

  /**
   * Get all variations for an opening
   */
  const getVariations = useCallback(
    async (repertoireId: string): Promise<OpeningVariation[]> => {
      try {
        const data = await fetchWithAuth(`/api/repertoire/${repertoireId}/variations`);
        setError(null);
        return data;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch variations';
        setError(message);
        throw err;
      }
    },
    [fetchWithAuth]
  );

  /**
   * Load repertoire on mount
   */
  useEffect(() => {
    fetchRepertoire();
  }, [fetchRepertoire]);

  return {
    // State
    repertoire,
    loading,
    error,
    // Operations
    fetchRepertoire,
    addToRepertoire,
    updateOpening,
    removeFromRepertoire,
    addVariation,
    getVariations,
  };
}
