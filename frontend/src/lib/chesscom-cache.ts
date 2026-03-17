/**
 * Production-grade caching and rate limiting for Chess.com API proxy
 *
 * Features:
 * - LRU cache with TTL (24 hours for player game archives)
 * - Token bucket rate limiter (~5 req/s to respect Chess.com rate limits)
 * - Stale-while-revalidate pattern
 * - Circuit breaker for upstream failures
 */

import {
  LRUCache,
  TokenBucketRateLimiter,
  CircuitBreaker,
} from './explorer-cache';

// ============================================================================
// Singleton Instances for Chess.com
// ============================================================================

// Cache with 24-hour TTL and max 5000 entries (player game archives are stable)
export const chesscomCache = new LRUCache<any>(5000, 24 * 60 * 60 * 1000);

// Rate limiter: 5 requests/second (Chess.com is stricter than Lichess)
export const chesscomRateLimiter = new TokenBucketRateLimiter(5, 5);

// Circuit breaker: 5 failures in 30s → open for 60s
export const chesscomCircuitBreaker = new CircuitBreaker(5, 30000, 60000, 2);

// ============================================================================
// Empty Fallback Response
// ============================================================================

export const EMPTY_CHESSCOM_RESPONSE = {
  archives: [],
  games: [],
};
