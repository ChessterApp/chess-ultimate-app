import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { ExplorerSessionCache } from '../explorer-session-cache';

describe('ExplorerSessionCache', () => {
  let cache: ExplorerSessionCache;
  let storage: Record<string, string>;

  beforeEach(() => {
    // Mock sessionStorage
    storage = {};
    const mockStorage = {
      getItem: (key: string) => storage[key] || null,
      setItem: (key: string, value: string) => { storage[key] = value; },
      removeItem: (key: string) => { delete storage[key]; },
      clear: () => { Object.keys(storage).forEach(k => delete storage[k]); },
      length: 0,
      key: () => null,
    };

    // Make Object.keys work on the mock storage
    Object.setPrototypeOf(mockStorage, storage);

    vi.stubGlobal('sessionStorage', new Proxy(mockStorage, {
      ownKeys: () => Object.keys(storage),
      getOwnPropertyDescriptor: (target, prop) => {
        if (prop in storage) {
          return { enumerable: true, configurable: true };
        }
        return Object.getOwnPropertyDescriptor(target, prop);
      }
    }));

    // Mock window object
    vi.stubGlobal('window', { sessionStorage: globalThis.sessionStorage });

    cache = new ExplorerSessionCache();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('should store and retrieve values with namespace', () => {
    cache.set('lichess', 'test-key', { data: 'test-value' });
    const result = cache.get('lichess', 'test-key');

    expect(result).toEqual({ data: 'test-value' });
  });

  it('should return null for missing keys', () => {
    const result = cache.get('lichess', 'nonexistent');
    expect(result).toBeNull();
  });

  it('should respect TTL and expire entries', () => {
    vi.useFakeTimers();

    cache.set('lichess', 'key1', 'value1', 1000); // 1s TTL
    expect(cache.get('lichess', 'key1')).toBe('value1');

    // Fast-forward 500ms (not expired)
    vi.advanceTimersByTime(500);
    expect(cache.get('lichess', 'key1')).toBe('value1');

    // Fast-forward another 600ms (expired)
    vi.advanceTimersByTime(600);
    expect(cache.get('lichess', 'key1')).toBeNull();

    vi.useRealTimers();
  });

  it('should delete entries', () => {
    cache.set('lichess', 'key1', 'value1');
    expect(cache.get('lichess', 'key1')).toBe('value1');

    cache.delete('lichess', 'key1');
    expect(cache.get('lichess', 'key1')).toBeNull();
  });

  it('should clear all explorer cache entries', () => {
    cache.set('lichess', 'key1', 'value1');
    cache.set('twic', 'key2', 'value2');

    // Verify they exist
    expect(cache.get('lichess', 'key1')).toBe('value1');
    expect(cache.get('twic', 'key2')).toBe('value2');

    cache.clear();

    // After clear, they should be null
    expect(cache.get('lichess', 'key1')).toBeNull();
    expect(cache.get('twic', 'key2')).toBeNull();
  });

  it('should handle JSON parse errors gracefully', () => {
    // Manually corrupt the storage
    storage['explorer_lichess_test'] = 'invalid-json';

    const result = cache.get('lichess', 'test');
    expect(result).toBeNull();
  });

  it('should use default TTL when not specified', () => {
    vi.useFakeTimers();

    cache.set('lichess', 'key1', 'value1'); // Should use lichess TTL (5min)
    expect(cache.get('lichess', 'key1')).toBe('value1');

    // Fast-forward 4 minutes (not expired)
    vi.advanceTimersByTime(4 * 60 * 1000);
    expect(cache.get('lichess', 'key1')).toBe('value1');

    // Fast-forward another 2 minutes (expired)
    vi.advanceTimersByTime(2 * 60 * 1000);
    expect(cache.get('lichess', 'key1')).toBeNull();

    vi.useRealTimers();
  });

  it('should clear entries for a specific namespace only', () => {
    cache.set('lichess', 'key1', 'value1');
    cache.set('twic', 'key2', 'value2');

    cache.clearNamespace('lichess');

    expect(cache.get('lichess', 'key1')).toBeNull();
    expect(cache.get('twic', 'key2')).toBe('value2');
  });

  it('should provide convenience methods for namespaces', () => {
    cache.lichess.set('key1', 'lichess-value');
    cache.twic.set('key1', 'twic-value');

    expect(cache.lichess.get('key1')).toBe('lichess-value');
    expect(cache.twic.get('key1')).toBe('twic-value');

    cache.lichess.delete('key1');
    expect(cache.lichess.get('key1')).toBeNull();
    expect(cache.twic.get('key1')).toBe('twic-value');
  });
});
