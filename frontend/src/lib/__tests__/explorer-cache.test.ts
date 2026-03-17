import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  LRUCache,
  TokenBucketRateLimiter,
  CircuitBreaker,
  EMPTY_EXPLORER_RESPONSE,
} from '../explorer-cache';

// ============================================================================
// LRU Cache Tests
// ============================================================================

describe('LRUCache', () => {
  let cache: LRUCache<string>;

  beforeEach(() => {
    cache = new LRUCache<string>(3, 1000); // 3 items, 1s TTL
  });

  it('should store and retrieve values', () => {
    cache.set('key1', 'value1');
    const result = cache.get('key1');

    expect(result).not.toBeNull();
    expect(result?.value).toBe('value1');
    expect(result?.isStale).toBe(false);
  });

  it('should return null for missing keys', () => {
    const result = cache.get('nonexistent');
    expect(result).toBeNull();
  });

  it('should evict oldest entry when capacity is reached', () => {
    cache.set('key1', 'value1');
    cache.set('key2', 'value2');
    cache.set('key3', 'value3');
    cache.set('key4', 'value4'); // Should evict key1

    expect(cache.get('key1')).toBeNull();
    expect(cache.get('key2')?.value).toBe('value2');
    expect(cache.get('key3')?.value).toBe('value3');
    expect(cache.get('key4')?.value).toBe('value4');
  });

  it('should update LRU order on access', () => {
    cache.set('key1', 'value1');
    cache.set('key2', 'value2');
    cache.set('key3', 'value3');

    // Access key1 (makes it most recent)
    cache.get('key1');

    // Add key4 - should evict key2 (oldest)
    cache.set('key4', 'value4');

    expect(cache.get('key1')?.value).toBe('value1');
    expect(cache.get('key2')).toBeNull();
    expect(cache.get('key3')?.value).toBe('value3');
    expect(cache.get('key4')?.value).toBe('value4');
  });

  it('should mark entries as stale after TTL expires', async () => {
    cache = new LRUCache<string>(10, 100); // 100ms TTL
    cache.set('key1', 'value1');

    const fresh = cache.get('key1');
    expect(fresh?.isStale).toBe(false);

    // Wait for TTL to expire
    await new Promise((resolve) => setTimeout(resolve, 150));

    const stale = cache.get('key1');
    expect(stale?.isStale).toBe(true);
    expect(stale?.value).toBe('value1'); // Still accessible
  });

  it('should handle cache clear', () => {
    cache.set('key1', 'value1');
    cache.set('key2', 'value2');

    cache.clear();

    expect(cache.get('key1')).toBeNull();
    expect(cache.get('key2')).toBeNull();
    expect(cache.size()).toBe(0);
  });

  it('should handle cache delete', () => {
    cache.set('key1', 'value1');
    cache.set('key2', 'value2');

    cache.delete('key1');

    expect(cache.get('key1')).toBeNull();
    expect(cache.get('key2')?.value).toBe('value2');
    expect(cache.size()).toBe(1);
  });

  it('should report correct size', () => {
    expect(cache.size()).toBe(0);

    cache.set('key1', 'value1');
    expect(cache.size()).toBe(1);

    cache.set('key2', 'value2');
    expect(cache.size()).toBe(2);

    cache.delete('key1');
    expect(cache.size()).toBe(1);
  });
});

// ============================================================================
// Token Bucket Rate Limiter Tests
// ============================================================================

describe('TokenBucketRateLimiter', () => {
  it('should allow requests within rate limit', async () => {
    const limiter = new TokenBucketRateLimiter(10, 10);

    const start = Date.now();
    await limiter.acquire();
    await limiter.acquire();
    await limiter.acquire();
    const elapsed = Date.now() - start;

    // Should complete quickly (within 100ms)
    expect(elapsed).toBeLessThan(100);
  });

  it('should throttle requests exceeding burst capacity', async () => {
    const limiter = new TokenBucketRateLimiter(2, 10); // 2 tokens max, 10/s refill

    const start = Date.now();

    // First 2 should be immediate
    await limiter.acquire();
    await limiter.acquire();

    // Third should wait
    await limiter.acquire();

    const elapsed = Date.now() - start;

    // Should have waited at least ~100ms for refill
    expect(elapsed).toBeGreaterThan(80);
  });

  it('should refill tokens over time', async () => {
    const limiter = new TokenBucketRateLimiter(1, 10);

    await limiter.acquire(); // Use 1 token

    // Wait for refill (100ms = 1 token at 10/s)
    await new Promise((resolve) => setTimeout(resolve, 150));

    const start = Date.now();
    await limiter.acquire(); // Should be immediate
    const elapsed = Date.now() - start;

    expect(elapsed).toBeLessThan(50);
  });

  it('should report available tokens', () => {
    const limiter = new TokenBucketRateLimiter(10, 10);

    const available = limiter.getAvailableTokens();
    expect(available).toBeCloseTo(10, 0);
  });

  it('should handle concurrent requests', async () => {
    const limiter = new TokenBucketRateLimiter(5, 10);

    const promises = Array.from({ length: 10 }, () => limiter.acquire());

    const start = Date.now();
    await Promise.all(promises);
    const elapsed = Date.now() - start;

    // 10 requests with 5 burst capacity should take at least 400-500ms
    expect(elapsed).toBeGreaterThan(300);
  });
});

// ============================================================================
// Circuit Breaker Tests
// ============================================================================

describe('CircuitBreaker', () => {
  it('should execute successfully when closed', async () => {
    const breaker = new CircuitBreaker(3, 1000, 1000);

    const result = await breaker.execute(async () => 'success');

    expect(result).toBe('success');
    expect(breaker.getState()).toBe('CLOSED');
  });

  it('should open after threshold failures', async () => {
    const breaker = new CircuitBreaker(3, 1000, 1000);

    // Trigger 3 failures
    for (let i = 0; i < 3; i++) {
      try {
        await breaker.execute(async () => {
          throw new Error('fail');
        });
      } catch {
        // Expected
      }
    }

    expect(breaker.getState()).toBe('OPEN');
    expect(breaker.isOpen()).toBe(true);
  });

  it('should reject requests when open', async () => {
    const breaker = new CircuitBreaker(2, 1000, 1000);

    // Trigger failures to open circuit
    for (let i = 0; i < 2; i++) {
      try {
        await breaker.execute(async () => {
          throw new Error('fail');
        });
      } catch {
        // Expected
      }
    }

    // Circuit should be open
    await expect(
      breaker.execute(async () => 'should not run')
    ).rejects.toThrow('Circuit breaker is OPEN');
  });

  it('should transition to half-open after cooldown', async () => {
    const breaker = new CircuitBreaker(2, 1000, 100); // 100ms cooldown

    // Open the circuit
    for (let i = 0; i < 2; i++) {
      try {
        await breaker.execute(async () => {
          throw new Error('fail');
        });
      } catch {
        // Expected
      }
    }

    expect(breaker.getState()).toBe('OPEN');

    // Wait for cooldown
    await new Promise((resolve) => setTimeout(resolve, 150));

    // Next request should transition to HALF_OPEN
    try {
      await breaker.execute(async () => 'success');
    } catch {
      // May fail
    }

    // Should be in HALF_OPEN or CLOSED state
    expect(['HALF_OPEN', 'CLOSED']).toContain(breaker.getState());
  });

  it('should close after successful requests in half-open state', async () => {
    const breaker = new CircuitBreaker(2, 1000, 100, 2); // Need 2 successes

    // Open the circuit
    for (let i = 0; i < 2; i++) {
      try {
        await breaker.execute(async () => {
          throw new Error('fail');
        });
      } catch {
        // Expected
      }
    }

    // Wait for cooldown
    await new Promise((resolve) => setTimeout(resolve, 150));

    // Execute 2 successful requests
    await breaker.execute(async () => 'success');
    await breaker.execute(async () => 'success');

    expect(breaker.getState()).toBe('CLOSED');
  });

  it('should reset failure count after time window', async () => {
    const breaker = new CircuitBreaker(3, 100, 1000); // 100ms window

    // 2 failures (below threshold)
    for (let i = 0; i < 2; i++) {
      try {
        await breaker.execute(async () => {
          throw new Error('fail');
        });
      } catch {
        // Expected
      }
    }

    // Wait for window to expire
    await new Promise((resolve) => setTimeout(resolve, 150));

    // Another 2 failures - should not open (reset happened)
    for (let i = 0; i < 2; i++) {
      try {
        await breaker.execute(async () => {
          throw new Error('fail');
        });
      } catch {
        // Expected
      }
    }

    expect(breaker.getState()).toBe('CLOSED');
  });

  it('should reset to closed state', async () => {
    const breaker = new CircuitBreaker(2, 1000, 1000);

    // Open the circuit
    for (let i = 0; i < 2; i++) {
      try {
        await breaker.execute(async () => {
          throw new Error('fail');
        });
      } catch {
        // Expected
      }
    }

    expect(breaker.getState()).toBe('OPEN');

    breaker.reset();

    expect(breaker.getState()).toBe('CLOSED');
    expect(breaker.isOpen()).toBe(false);
  });
});

// ============================================================================
// EMPTY_EXPLORER_RESPONSE Tests
// ============================================================================

describe('EMPTY_EXPLORER_RESPONSE', () => {
  it('should have correct structure', () => {
    expect(EMPTY_EXPLORER_RESPONSE).toEqual({
      white: 0,
      draws: 0,
      black: 0,
      moves: [],
      topGames: [],
      opening: null,
    });
  });
});
