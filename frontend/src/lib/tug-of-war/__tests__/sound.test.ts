import { describe, it, expect } from 'vitest';
import { loadMuted, saveMuted, MUTE_STORAGE_KEY } from '../sound';

/** Minimal in-memory Storage stand-in for the pure mute helpers. */
function makeStorage(initial: Record<string, string> = {}) {
  const map = new Map(Object.entries(initial));
  return {
    getItem: (k: string) => (map.has(k) ? map.get(k)! : null),
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    get raw() {
      return map;
    },
  };
}

describe('mute persistence', () => {
  it('defaults to unmuted (sound ON) when nothing is stored', () => {
    expect(loadMuted(makeStorage())).toBe(false);
  });

  it('reads a persisted muted flag', () => {
    expect(loadMuted(makeStorage({ [MUTE_STORAGE_KEY]: '1' }))).toBe(true);
  });

  it('treats any non-"1" value as unmuted', () => {
    expect(loadMuted(makeStorage({ [MUTE_STORAGE_KEY]: '0' }))).toBe(false);
    expect(loadMuted(makeStorage({ [MUTE_STORAGE_KEY]: 'true' }))).toBe(false);
  });

  it('saves the muted flag as "1"', () => {
    const s = makeStorage();
    saveMuted(true, s);
    expect(s.raw.get(MUTE_STORAGE_KEY)).toBe('1');
    expect(loadMuted(s)).toBe(true);
  });

  it('removes the key when unmuting', () => {
    const s = makeStorage({ [MUTE_STORAGE_KEY]: '1' });
    saveMuted(false, s);
    expect(s.raw.has(MUTE_STORAGE_KEY)).toBe(false);
    expect(loadMuted(s)).toBe(false);
  });

  it('round-trips a save then load', () => {
    const s = makeStorage();
    saveMuted(true, s);
    expect(loadMuted(s)).toBe(true);
    saveMuted(false, s);
    expect(loadMuted(s)).toBe(false);
  });

  it('is a no-op (returns default) with no storage available', () => {
    // No explicit storage + node env (no window) → graceful default.
    expect(loadMuted()).toBe(false);
    expect(() => saveMuted(true)).not.toThrow();
  });
});
