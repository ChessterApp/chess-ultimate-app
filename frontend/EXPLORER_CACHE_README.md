# Lichess Opening Explorer Caching System

This document describes the production-grade caching and rate limiting system for the Lichess Opening Explorer proxy.

## Features

### 1. **In-Memory LRU Cache with TTL**
- **Location**: `src/lib/explorer-cache.ts` - `LRUCache` class
- **Configuration**:
  - Max size: 2000 entries
  - TTL: 6 hours
- **Behavior**:
  - Cache key = full URL path + query string
  - Evicts least recently used entries when capacity is reached
  - Returns `{ value, isStale }` to support stale-while-revalidate

### 2. **Token Bucket Rate Limiter**
- **Location**: `src/lib/explorer-cache.ts` - `TokenBucketRateLimiter` class
- **Configuration**:
  - Max tokens: 10
  - Refill rate: 10 tokens/second
- **Behavior**:
  - Queues requests when rate limit is exceeded
  - Prevents overwhelming the Lichess API with hundreds of concurrent requests
  - Automatically refills tokens over time

### 3. **Stale-While-Revalidate**
- **Location**: `src/app/api/explorer/[...path]/route.ts` - `backgroundRevalidate()` function
- **Behavior**:
  - If cache entry is stale (> 6 hours old), serve it immediately
  - Trigger background refresh to update cache
  - User gets instant response with slightly outdated data

### 4. **Circuit Breaker**
- **Location**: `src/lib/explorer-cache.ts` - `CircuitBreaker` class
- **Configuration**:
  - Failure threshold: 5 failures
  - Failure window: 30 seconds
  - Cooldown period: 60 seconds
  - Half-open success threshold: 2 successes
- **Behavior**:
  - **CLOSED** (normal): All requests pass through
  - **OPEN** (failures detected): Block all upstream requests, serve cached data or empty fallback
  - **HALF_OPEN** (testing recovery): Allow limited requests to test if upstream recovered

### 5. **Empty Fallback Response**
- **Location**: `src/lib/explorer-cache.ts` - `EMPTY_EXPLORER_RESPONSE`
- **Structure**:
  ```json
  {
    "white": 0,
    "draws": 0,
    "black": 0,
    "moves": [],
    "topGames": [],
    "opening": null
  }
  ```
- **Usage**: Returned when upstream fails and no cached data is available

## Cache Headers

The API returns an `X-Cache` header to indicate cache status:

- **HIT**: Fresh cache entry served (< 6 hours old)
- **MISS**: No cache entry, fetched from upstream
- **STALE**: Stale cache entry served (> 6 hours old), background refresh triggered
- **CIRCUIT_OPEN**: Circuit breaker is open, serving cached data or empty fallback
- **ERROR**: Upstream error, serving cached data or empty fallback

## Testing

### Unit Tests
```bash
npm test
```

Tests cover:
- LRU cache eviction and TTL
- Token bucket rate limiting
- Circuit breaker state transitions
- Route integration with mocked fetch

### Manual Testing

1. **Test cache hit/miss**:
   ```bash
   # First request (MISS)
   curl -D - "http://localhost:3000/api/explorer/masters?fen=rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR%20w%20KQkq%20-%200%201" | grep x-cache

   # Second request (HIT)
   curl -D - "http://localhost:3000/api/explorer/masters?fen=rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR%20w%20KQkq%20-%200%201" | grep x-cache
   ```

2. **Test circuit breaker**:
   The circuit breaker will open if Lichess API returns errors consistently. When open, you'll see `x-cache: CIRCUIT_OPEN` headers.

3. **Test rate limiting**:
   Make 20+ concurrent requests - they should all succeed but be throttled to ~10 req/s.

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│  Next.js API Route                  │
│  /api/explorer/[...path]           │
│                                     │
│  1. Check Cache (LRU)              │
│     ├─ HIT (fresh) → Return        │
│     └─ STALE → Return + Revalidate │
│                                     │
│  2. Check Circuit Breaker          │
│     └─ OPEN → Return cached/empty  │
│                                     │
│  3. Acquire Rate Limit Token       │
│                                     │
│  4. Fetch from Upstream            │
│     └─ Update Cache                │
└─────────────┬───────────────────────┘
              │
              ▼
       ┌──────────────┐
       │ Lichess API  │
       └──────────────┘
```

## Performance Benefits

1. **Reduced latency**: Cache hits return in < 1ms vs 100-500ms for upstream requests
2. **Reduced load on Lichess**: Cache hit rate should be 80-90% for common positions
3. **Graceful degradation**: System continues working even if Lichess API is down
4. **Rate limit protection**: Prevents 429 errors from Lichess API
5. **Scalability**: Can handle hundreds of concurrent users without overwhelming upstream

## Monitoring

To monitor cache performance, add logging:

```typescript
console.log('Cache size:', explorerCache.size());
console.log('Circuit breaker state:', circuitBreaker.getState());
console.log('Available rate limit tokens:', rateLimiter.getAvailableTokens());
```

## Future Improvements

1. **Redis cache**: Replace in-memory cache with Redis for multi-instance deployments
2. **Metrics**: Add Prometheus metrics for cache hit rate, circuit breaker state, etc.
3. **Configurable TTL**: Different TTL for masters vs lichess database
4. **Warmup**: Pre-populate cache with common opening positions
5. **Cache invalidation**: Webhook to invalidate cache when new games are added to Lichess DB
