/**
 * Browser-side sessionStorage cache for Lichess Explorer data
 *
 * Provides fast client-side caching with TTL to reduce redundant
 * API calls during the user's session
 */

interface SessionCacheEntry<T> {
  value: T;
  expiresAt: number;
}

const CACHE_PREFIX = 'explorer_';
const DEFAULT_TTL_MS = 5 * 60 * 1000; // 5 minutes

export class ExplorerSessionCache {
  private isAvailable: boolean;

  constructor() {
    // Check if sessionStorage is available
    this.isAvailable = typeof window !== 'undefined' && typeof sessionStorage !== 'undefined';
  }

  get<T>(key: string): T | null {
    if (!this.isAvailable) return null;

    try {
      const item = sessionStorage.getItem(CACHE_PREFIX + key);
      if (!item) return null;

      const entry: SessionCacheEntry<T> = JSON.parse(item);
      const now = Date.now();

      if (now > entry.expiresAt) {
        // Expired - remove and return null
        this.delete(key);
        return null;
      }

      return entry.value;
    } catch {
      // Parse error or other issue - return null
      return null;
    }
  }

  set<T>(key: string, value: T, ttlMs: number = DEFAULT_TTL_MS): void {
    if (!this.isAvailable) return;

    try {
      const entry: SessionCacheEntry<T> = {
        value,
        expiresAt: Date.now() + ttlMs,
      };
      sessionStorage.setItem(CACHE_PREFIX + key, JSON.stringify(entry));
    } catch {
      // Storage full or other error - silently fail
    }
  }

  delete(key: string): void {
    if (!this.isAvailable) return;

    try {
      sessionStorage.removeItem(CACHE_PREFIX + key);
    } catch {
      // Silently fail
    }
  }

  clear(): void {
    if (!this.isAvailable) return;

    try {
      // Remove only explorer cache keys
      const keys = Object.keys(sessionStorage);
      for (const key of keys) {
        if (key.startsWith(CACHE_PREFIX)) {
          sessionStorage.removeItem(key);
        }
      }
    } catch {
      // Silently fail
    }
  }
}

// Singleton instance
export const explorerSessionCache = new ExplorerSessionCache();
