/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from 'vitest';

// Node 25+ ships its own global localStorage/sessionStorage (undefined without
// --localstorage-file). Vitest's jsdom environment skips globals Node already
// has, so the tests saw Node's empty getter instead of jsdom's Storage (28.10).
describe('jsdom web storage', () => {
  it.each(['localStorage', 'sessionStorage'] as const)('%s is jsdom Storage', (name) => {
    const storage = globalThis[name];
    expect(storage).toBeDefined();
    expect(storage).toBeInstanceOf(window.Storage);
    storage.setItem('k', 'v');
    expect(storage.getItem('k')).toBe('v');
    storage.clear();
    expect(storage.length).toBe(0);
  });
});
