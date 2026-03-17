/**
 * Browser-side sessionStorage cache for all Explorer data (Lichess, Chess.com, TWIC)
 *
 * Provides fast client-side caching with TTL to reduce redundant
 * API calls during the user's session
 *
 * Cache key structure:
 * - Lichess: explorer_lichess_{masters|lichess}_{fen_hash}
 * - Chess.com: explorer_chesscom_{username}
 * - TWIC: explorer_twic_{fen_hash}
 * - Explorer state: explorer_state_{key}
 */

interface SessionCacheEntry<T> {
  value: T;
  expiresAt: number;
}

const CACHE_PREFIX = 'explorer_';
const DEFAULT_TTL_MS = 5 * 60 * 1000; // 5 minutes

// TTL configurations for different data types
const TTL_CONFIG = {
  lichess: 5 * 60 * 1000,      // 5 minutes
  chesscom: 10 * 60 * 1000,    // 10 minutes (player games change less frequently)
  twic: 15 * 60 * 1000,        // 15 minutes (master games are static)
  state: 60 * 60 * 1000,       // 1 hour (UI state like active tab, filters)
};

export class ExplorerSessionCache {
  private isAvailable: boolean;

  constructor() {
    // Check if sessionStorage is available
    this.isAvailable = typeof window !== 'undefined' && typeof sessionStorage !== 'undefined';
  }

  /**
   * Generate a cache key with namespace
   */
  private makeKey(namespace: string, key: string): string {
    return `${CACHE_PREFIX}${namespace}_${key}`;
  }

  /**
   * Get cached value with namespace
   */
  get<T>(namespace: string, key: string): T | null {
    if (!this.isAvailable) return null;

    try {
      const fullKey = this.makeKey(namespace, key);
      const item = sessionStorage.getItem(fullKey);
      if (!item) return null;

      const entry: SessionCacheEntry<T> = JSON.parse(item);
      const now = Date.now();

      if (now > entry.expiresAt) {
        // Expired - remove and return null
        this.delete(namespace, key);
        return null;
      }

      return entry.value;
    } catch {
      // Parse error or other issue - return null
      return null;
    }
  }

  /**
   * Set cached value with namespace and custom TTL
   */
  set<T>(namespace: string, key: string, value: T, ttlMs?: number): void {
    if (!this.isAvailable) return;

    try {
      const fullKey = this.makeKey(namespace, key);
      const ttl = ttlMs || TTL_CONFIG[namespace as keyof typeof TTL_CONFIG] || DEFAULT_TTL_MS;
      const entry: SessionCacheEntry<T> = {
        value,
        expiresAt: Date.now() + ttl,
      };
      sessionStorage.setItem(fullKey, JSON.stringify(entry));
    } catch {
      // Storage full or other error - silently fail
    }
  }

  /**
   * Delete cached value with namespace
   */
  delete(namespace: string, key: string): void {
    if (!this.isAvailable) return;

    try {
      const fullKey = this.makeKey(namespace, key);
      sessionStorage.removeItem(fullKey);
    } catch {
      // Silently fail
    }
  }

  /**
   * Clear all cache entries for a specific namespace
   */
  clearNamespace(namespace: string): void {
    if (!this.isAvailable) return;

    try {
      const prefix = `${CACHE_PREFIX}${namespace}_`;
      const keys = Object.keys(sessionStorage);
      for (const key of keys) {
        if (key.startsWith(prefix)) {
          sessionStorage.removeItem(key);
        }
      }
    } catch {
      // Silently fail
    }
  }

  /**
   * Clear all explorer cache entries
   */
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

  /**
   * Convenience methods for common namespaces
   */
  lichess = {
    get: <T>(key: string) => this.get<T>('lichess', key),
    set: <T>(key: string, value: T) => this.set('lichess', key, value),
    delete: (key: string) => this.delete('lichess', key),
    clear: () => this.clearNamespace('lichess'),
  };

  chesscom = {
    get: <T>(key: string) => this.get<T>('chesscom', key),
    set: <T>(key: string, value: T) => this.set('chesscom', key, value),
    delete: (key: string) => this.delete('chesscom', key),
    clear: () => this.clearNamespace('chesscom'),
  };

  twic = {
    get: <T>(key: string) => this.get<T>('twic', key),
    set: <T>(key: string, value: T) => this.set('twic', key, value),
    delete: (key: string) => this.delete('twic', key),
    clear: () => this.clearNamespace('twic'),
  };

  state = {
    get: <T>(key: string) => this.get<T>('state', key),
    set: <T>(key: string, value: T) => this.set('state', key, value),
    delete: (key: string) => this.delete('state', key),
    clear: () => this.clearNamespace('state'),
  };
}

// Singleton instance
export const explorerSessionCache = new ExplorerSessionCache();
