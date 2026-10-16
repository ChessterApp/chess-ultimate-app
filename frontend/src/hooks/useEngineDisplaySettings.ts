'use client';

import { useCallback, useSyncExternalStore } from 'react';

export const ENGINE_DISPLAY_STORAGE_KEY = 'chesster.engineDisplay.v1';
export const ENGINE_DEPTH_OPTIONS = [12, 16, 18, 20, 24] as const;
export const ENGINE_LINES_OPTIONS = [1, 2, 3, 4, 5] as const;

export interface EngineDisplaySettings {
  depth: number;
  lines: number;
}

const DEFAULTS: EngineDisplaySettings = { depth: 18, lines: 1 };

const listeners = new Set<() => void>();
let cachedRaw: string | null | undefined;
let cachedValue: EngineDisplaySettings = DEFAULTS;

function sanitize(value: unknown): EngineDisplaySettings {
  const v = (value ?? {}) as Partial<EngineDisplaySettings>;
  return {
    depth: (ENGINE_DEPTH_OPTIONS as readonly unknown[]).includes(v.depth) ? v.depth! : DEFAULTS.depth,
    lines: (ENGINE_LINES_OPTIONS as readonly unknown[]).includes(v.lines) ? v.lines! : DEFAULTS.lines,
  };
}

function readRaw(): string | null {
  try {
    return window.localStorage.getItem(ENGINE_DISPLAY_STORAGE_KEY);
  } catch {
    return null;
  }
}

function getSnapshot(): EngineDisplaySettings {
  const raw = readRaw();
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    try {
      cachedValue = raw ? sanitize(JSON.parse(raw)) : DEFAULTS;
    } catch {
      cachedValue = DEFAULTS;
    }
  }
  return cachedValue;
}

function getServerSnapshot(): EngineDisplaySettings {
  return DEFAULTS;
}

function notify() {
  listeners.forEach((l) => l());
}

function onStorage(e: StorageEvent) {
  if (e.key === ENGINE_DISPLAY_STORAGE_KEY || e.key === null) notify();
}

function subscribe(listener: () => void) {
  if (listeners.size === 0) window.addEventListener('storage', onStorage);
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) window.removeEventListener('storage', onStorage);
  };
}

function write(patch: Partial<EngineDisplaySettings>) {
  const next = sanitize({ ...getSnapshot(), ...patch });
  try {
    window.localStorage.setItem(ENGINE_DISPLAY_STORAGE_KEY, JSON.stringify(next));
  } catch {
    return; // storage unavailable — nothing to persist or broadcast
  }
  notify();
}

/**
 * Engine depth / line count shared by every engine panel, persisted in
 * localStorage and synced across mounted components and browser tabs.
 * Engine on/off is deliberately not stored here.
 */
export function useEngineDisplaySettings() {
  const { depth, lines } = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const setDepth = useCallback((value: number) => write({ depth: value }), []);
  const setLines = useCallback((value: number) => write({ lines: value }), []);
  return { depth, lines, setDepth, setLines };
}
