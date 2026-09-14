'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import { createClerkSupabaseClient } from '@/lib/supabase';
import type { WheelPreset, WheelSegment } from '@/lib/wheel/types';
import { defaultPreset, presetFromRow, serializeSegments } from '@/lib/wheel/presets';

// Bumped to -v2 to invalidate the pre-20-tile default cached in returning
// users' localStorage. Old keys (unversioned) are cleared once on mount below.
const CACHE_KEY = 'wheel-presets-cache-v2';
const CURRENT_KEY = 'wheel-current-preset-id-v2';
const LEGACY_KEYS = ['wheel-presets-cache', 'wheel-current-preset-id'];
const TABLE = 'wheel_presets';

/** One-time removal of pre-v2 cache so the new default is not shadowed by it. */
function clearLegacyCache(): void {
  if (typeof window === 'undefined') return;
  try {
    for (const k of LEGACY_KEYS) localStorage.removeItem(k);
  } catch {
    /* storage disabled — non-fatal */
  }
}

function readCache(): WheelPreset[] | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as WheelPreset[]) : null;
  } catch {
    return null;
  }
}

function writeCache(presets: WheelPreset[], currentId: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(presets));
    if (currentId) localStorage.setItem(CURRENT_KEY, currentId);
  } catch {
    /* storage full / disabled — non-fatal */
  }
}

function readCurrentId(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(CURRENT_KEY);
  } catch {
    return null;
  }
}

function newId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return `local-${Date.now()}`;
}

export interface UsePresets {
  presets: WheelPreset[];
  current: WheelPreset | null;
  currentId: string | null;
  loading: boolean;
  offline: boolean;
  selectPreset: (id: string) => void;
  createPreset: (name: string) => Promise<void>;
  duplicatePreset: (id: string) => Promise<void>;
  deletePreset: (id: string) => Promise<void>;
  savePreset: (name: string, segments: WheelSegment[]) => Promise<void>;
}

export function usePresets(): UsePresets {
  const { userId, getToken } = useAuth();
  const client = useMemo(
    () => createClerkSupabaseClient(() => getToken({ template: 'supabase' })),
    [getToken],
  );

  // Seed synchronously from cache (or the built-in default) so the wheel renders
  // instantly even with no network.
  const [presets, setPresets] = useState<WheelPreset[]>(() => {
    const cached = readCache();
    return cached && cached.length ? cached : [defaultPreset()];
  });
  const [currentId, setCurrentId] = useState<string | null>(() => {
    const saved = readCurrentId();
    if (saved) return saved;
    const cached = readCache();
    return (cached && cached[0]?.id) || 'default';
  });
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    clearLegacyCache();
    return () => {
      mounted.current = false;
    };
  }, []);

  const commit = useCallback((next: WheelPreset[], nextCurrent: string | null) => {
    setPresets(next);
    setCurrentId(nextCurrent);
    writeCache(next, nextCurrent);
  }, []);

  // Initial load from Supabase.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data, error } = await client
          .from(TABLE)
          .select('*')
          .order('created_at', { ascending: true });
        if (error) throw error;
        if (cancelled || !mounted.current) return;
        const rows = (data ?? []).map(presetFromRow);
        if (rows.length > 0) {
          const savedId = readCurrentId();
          const keep = rows.find((r) => r.id === savedId)?.id ?? rows[0].id;
          commit(rows, keep);
        }
        setOffline(false);
      } catch {
        // Keep the cached/default presets; mark offline so the UI can hint.
        if (!cancelled && mounted.current) setOffline(true);
      } finally {
        if (!cancelled && mounted.current) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, commit]);

  const selectPreset = useCallback(
    (id: string) => {
      if (presets.some((p) => p.id === id)) commit(presets, id);
    },
    [presets, commit],
  );

  const insertRow = useCallback(
    async (name: string, segments: WheelSegment[]): Promise<WheelPreset> => {
      const optimistic: WheelPreset = {
        id: newId(),
        name,
        segments,
        createdBy: userId ?? null,
      };
      try {
        const { data, error } = await client
          .from(TABLE)
          .insert({ name, segments: serializeSegments(segments) })
          .select('*')
          .single();
        if (error) throw error;
        return presetFromRow(data);
      } catch {
        setOffline(true);
        return optimistic; // local-only fallback
      }
    },
    [client, userId],
  );

  const createPreset = useCallback(
    async (name: string) => {
      const created = await insertRow(name, defaultPreset().segments);
      commit([...presets, created], created.id);
    },
    [insertRow, presets, commit],
  );

  const duplicatePreset = useCallback(
    async (id: string) => {
      const src = presets.find((p) => p.id === id);
      if (!src) return;
      const created = await insertRow(`${src.name} (copy)`, src.segments);
      commit([...presets, created], created.id);
    },
    [insertRow, presets, commit],
  );

  const deletePreset = useCallback(
    async (id: string) => {
      const remaining = presets.filter((p) => p.id !== id);
      const fallback = remaining[0]?.id ?? null;
      try {
        const { error } = await client.from(TABLE).delete().eq('id', id);
        if (error) throw error;
      } catch {
        setOffline(true);
      }
      commit(remaining.length ? remaining : [defaultPreset()], remaining.length ? fallback : 'default');
    },
    [client, presets, commit],
  );

  const savePreset = useCallback(
    async (name: string, segments: WheelSegment[]) => {
      const current = presets.find((p) => p.id === currentId);
      const ownedByMe = !!current && !!userId && current.createdBy === userId;

      if (!current || !ownedByMe) {
        // Editing the seeded default or someone else's preset → fork my own copy.
        const created = await insertRow(name, segments);
        commit([...presets, created], created.id);
        return;
      }

      const updated: WheelPreset = { ...current, name, segments };
      const next = presets.map((p) => (p.id === current.id ? updated : p));
      commit(next, current.id);
      try {
        const { error } = await client
          .from(TABLE)
          .update({ name, segments: serializeSegments(segments) })
          .eq('id', current.id);
        if (error) throw error;
      } catch {
        setOffline(true);
      }
    },
    [presets, currentId, userId, insertRow, commit, client],
  );

  const current = useMemo(
    () => presets.find((p) => p.id === currentId) ?? presets[0] ?? null,
    [presets, currentId],
  );

  return {
    presets,
    current,
    currentId,
    loading,
    offline,
    selectPreset,
    createPreset,
    duplicatePreset,
    deletePreset,
    savePreset,
  };
}
