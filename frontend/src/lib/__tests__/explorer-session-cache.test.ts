import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { ExplorerSessionCache, explorerSessionCache } from '../explorer-session-cache';

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

  it('should store and retrieve values', () => {
    cache.set('test-key', { data: 'test-value' });
    const result = cache.get('test-key');

    expect(result).toEqual({ data: 'test-value' });
  });

  it('should return null for missing keys', () => {
    const result = cache.get('nonexistent');
    expect(result).toBeNull();
  });

  it('should respect TTL and expire entries', () => {
    vi.useFakeTimers();

    cache.set('key1', 'value1', 1000); // 1s TTL
    expect(cache.get('key1')).toBe('value1');

    // Fast-forward 500ms (not expired)
    vi.advanceTimersByTime(500);
    expect(cache.get('key1')).toBe('value1');

    // Fast-forward another 600ms (expired)
    vi.advanceTimersByTime(600);
    expect(cache.get('key1')).toBeNull();

    vi.useRealTimers();
  });

  it('should delete entries', () => {
    cache.set('key1', 'value1');
    expect(cache.get('key1')).toBe('value1');

    cache.delete('key1');
    expect(cache.get('key1')).toBeNull();
  });

  it('should clear all explorer cache entries', () => {
    cache.set('key1', 'value1');
    cache.set('key2', 'value2');

    // Verify they exist
    expect(cache.get('key1')).toBe('value1');
    expect(cache.get('key2')).toBe('value2');

    cache.clear();

    // After clear, they should be null
    expect(cache.get('key1')).toBeNull();
    expect(cache.get('key2')).toBeNull();
  });

  it('should handle JSON parse errors gracefully', () => {
    // Manually corrupt the storage
    storage['explorer_test'] = 'invalid-json';

    const result = cache.get('test');
    expect(result).toBeNull();
  });

  it('should use default TTL when not specified', () => {
    vi.useFakeTimers();

    cache.set('key1', 'value1'); // Should use default 5min TTL
    expect(cache.get('key1')).toBe('value1');

    // Fast-forward 4 minutes (not expired)
    vi.advanceTimersByTime(4 * 60 * 1000);
    expect(cache.get('key1')).toBe('value1');

    // Fast-forward another 2 minutes (expired)
    vi.advanceTimersByTime(2 * 60 * 1000);
    expect(cache.get('key1')).toBeNull();

    vi.useRealTimers();
  });
});
