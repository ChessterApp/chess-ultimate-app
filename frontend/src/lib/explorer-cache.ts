/**
 * Production-grade caching and rate limiting for Lichess Opening Explorer proxy
 *
 * Features:
 * - LRU cache with TTL (1-6 hours for opening data)
 * - Token bucket rate limiter (~10 req/s)
 * - Stale-while-revalidate pattern
 * - Circuit breaker for upstream failures
 */

// ============================================================================
// LRU Cache with TTL
// ============================================================================

interface CacheEntry<T> {
  value: T;
  expiresAt: number;
  createdAt: number;
}

export class LRUCache<T> {
  private cache = new Map<string, CacheEntry<T>>();
  private maxSize: number;
  private ttlMs: number;

  constructor(maxSize: number = 1000, ttlMs: number = 3600000) {
    this.maxSize = maxSize;
    this.ttlMs = ttlMs;
  }

  get(key: string): { value: T; isStale: boolean } | null {
    const entry = this.cache.get(key);
    if (!entry) return null;

    const now = Date.now();
    const isStale = now > entry.expiresAt;

    // Move to end (most recently used)
    this.cache.delete(key);
    this.cache.set(key, entry);

    return { value: entry.value, isStale };
  }

  set(key: string, value: T): void {
    // Remove oldest entry if at capacity
    if (this.cache.size >= this.maxSize && !this.cache.has(key)) {
      const firstKey = this.cache.keys().next().value;
      if (firstKey) {
        this.cache.delete(firstKey);
      }
    }

    const now = Date.now();
    this.cache.set(key, {
      value,
      expiresAt: now + this.ttlMs,
      createdAt: now,
    });
  }

  delete(key: string): void {
    this.cache.delete(key);
  }

  clear(): void {
    this.cache.clear();
  }

  size(): number {
    return this.cache.size;
  }
}

// ============================================================================
// Token Bucket Rate Limiter
// ============================================================================

export class TokenBucketRateLimiter {
  private tokens: number;
  private maxTokens: number;
  private refillRate: number; // tokens per second
  private lastRefill: number;
  private queue: Array<() => void> = [];
  private processing = false;

  constructor(maxTokens: number = 10, refillRate: number = 10) {
    this.tokens = maxTokens;
    this.maxTokens = maxTokens;
    this.refillRate = refillRate;
    this.lastRefill = Date.now();
  }

  private refill(): void {
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000; // seconds
    const tokensToAdd = elapsed * this.refillRate;

    this.tokens = Math.min(this.maxTokens, this.tokens + tokensToAdd);
    this.lastRefill = now;
  }

  async acquire(): Promise<void> {
    return new Promise((resolve) => {
      this.queue.push(resolve);
      this.processQueue();
    });
  }

  private async processQueue(): Promise<void> {
    if (this.processing) return;
    this.processing = true;

    while (this.queue.length > 0) {
      this.refill();

      if (this.tokens >= 1) {
        this.tokens -= 1;
        const resolve = this.queue.shift();
        if (resolve) resolve();
      } else {
        // Wait before checking again (100ms intervals)
        await new Promise((r) => setTimeout(r, 100));
      }
    }

    this.processing = false;
  }

  getAvailableTokens(): number {
    this.refill();
    return this.tokens;
  }
}

// ============================================================================
// Circuit Breaker
// ============================================================================

enum CircuitState {
  CLOSED = 'CLOSED', // Normal operation
  OPEN = 'OPEN', // Blocking requests
  HALF_OPEN = 'HALF_OPEN', // Testing if service recovered
}

export class CircuitBreaker {
  private state: CircuitState = CircuitState.CLOSED;
  private failures = 0;
  private lastFailureTime = 0;
  private successCount = 0;

  private readonly failureThreshold: number;
  private readonly failureWindow: number; // ms
  private readonly cooldownPeriod: number; // ms
  private readonly halfOpenSuccessThreshold: number;

  constructor(
    failureThreshold: number = 5,
    failureWindow: number = 30000,
    cooldownPeriod: number = 60000,
    halfOpenSuccessThreshold: number = 2
  ) {
    this.failureThreshold = failureThreshold;
    this.failureWindow = failureWindow;
    this.cooldownPeriod = cooldownPeriod;
    this.halfOpenSuccessThreshold = halfOpenSuccessThreshold;
  }

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    const now = Date.now();

    // Reset failures if outside failure window
    if (now - this.lastFailureTime > this.failureWindow) {
      this.failures = 0;
    }

    // Check if we should transition from OPEN to HALF_OPEN
    if (
      this.state === CircuitState.OPEN &&
      now - this.lastFailureTime > this.cooldownPeriod
    ) {
      this.state = CircuitState.HALF_OPEN;
      this.successCount = 0;
    }

    // Block requests if circuit is open
    if (this.state === CircuitState.OPEN) {
      throw new Error('Circuit breaker is OPEN');
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  private onSuccess(): void {
    if (this.state === CircuitState.HALF_OPEN) {
      this.successCount++;
      if (this.successCount >= this.halfOpenSuccessThreshold) {
        this.state = CircuitState.CLOSED;
        this.failures = 0;
      }
    } else if (this.state === CircuitState.CLOSED) {
      // Reset on success
      this.failures = 0;
    }
  }

  private onFailure(): void {
    this.failures++;
    this.lastFailureTime = Date.now();

    if (this.failures >= this.failureThreshold) {
      this.state = CircuitState.OPEN;
    }
  }

  getState(): CircuitState {
    return this.state;
  }

  isOpen(): boolean {
    return this.state === CircuitState.OPEN;
  }

  reset(): void {
    this.state = CircuitState.CLOSED;
    this.failures = 0;
    this.successCount = 0;
  }
}

// ============================================================================
// Singleton Instances
// ============================================================================

// Cache with 6-hour TTL and max 2000 entries
export const explorerCache = new LRUCache<any>(2000, 6 * 60 * 60 * 1000);

// Rate limiter: 10 requests/second
export const rateLimiter = new TokenBucketRateLimiter(10, 10);

// Circuit breaker for masters/lichess: 5 failures in 30s → open for 60s
export const circuitBreaker = new CircuitBreaker(5, 30000, 60000, 2);

// Separate circuit breaker for player endpoint (slower, queue-based)
// Higher tolerance: 10 failures in 60s → open for 120s
export const playerCircuitBreaker = new CircuitBreaker(10, 60000, 120000, 2);

// ============================================================================
// Empty Fallback Response
// ============================================================================

export const EMPTY_EXPLORER_RESPONSE = {
  white: 0,
  draws: 0,
  black: 0,
  moves: [],
  topGames: [],
  opening: null,
};
