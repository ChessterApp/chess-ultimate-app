# Stale-While-Revalidate Implementation

## Overview
This document describes the stale-while-revalidate caching pattern implementation across the Chesster application. The pattern serves cached content immediately while fetching fresh data in the background.

## Pattern Description
**Stale-while-revalidate** is a caching strategy that:
1. Serves cached content immediately to the user (fast response)
2. Fetches fresh content from the source in the background
3. Updates the cache with fresh content for the next request

This provides the best of both worlds:
- **Performance**: Users get instant responses from cache
- **Freshness**: Content is updated in the background
- **Reliability**: Works even when the network is slow or temporarily unavailable

## Implementation Locations

### 1. Service Worker (`public/sw.js`)
**Location**: Lines 45-58
**Scope**: Navigation requests (HTML pages)

```javascript
// Stale-while-revalidate for navigation (HTML pages)
// Pattern: serve cached version immediately, fetch fresh in background, update cache
if (event.request.mode === 'navigate') {
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const fetchPromise = fetch(event.request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return response;
      }).catch(() => null); // Ignore fetch errors in background update

      // Return cached immediately if available, otherwise wait for network
      // If cached exists, fetchPromise runs in background to update cache
      return cached || fetchPromise;
    })
  );
  return;
}
```

**Behavior**:
- If cached page exists: Serves cached HTML instantly, fetches fresh version in background
- If no cache: Waits for network fetch
- Failed background fetches are ignored (user still gets cached content)

**Test Coverage**: `__tests__/sw.test.js` (7 tests, all passing)

### 2. Lichess Explorer Hook (`src/hooks/useLichessExplorer.ts`)
**Location**: Lines 137-147
**Scope**: Opening explorer data from Lichess (masters, lichess, player databases)

```typescript
// Stale-while-revalidate: serve cached immediately, fetch fresh in background
const cached = explorerSessionCache.lichess.get<LichessExplorerResponse>(cacheKey);
if (cached && !cancelled) {
  setData(cached);
  setLoading(false);
  // Continue to fetch fresh data in background (don't return)
}

// Fetch from API (runs in background if cached data was served)
const response = await fetch(`/api/explorer/${endpoint}?${params.toString()}`, {
  method: 'GET',
  headers: {
    'Content-Type': 'application/json',
  },
});
```

**Behavior**:
- If cached data exists: Shows cached data immediately (`loading: false`), fetches fresh in background
- If no cache: Shows loading state, fetches from API
- Cache is updated with fresh data after fetch completes

**Cache TTL**: 5 minutes (configurable in `explorer-session-cache.ts`)

### 3. Chess.com Explorer Hook (`src/hooks/useChessComExplorer.ts`)
**Location**: Lines 138-147
**Scope**: Player game archives from Chess.com

```typescript
// Stale-while-revalidate: serve cached immediately, fetch fresh in background
const cacheKey = username;
const cached = explorerSessionCache.chesscom.get<GameSearchResult[]>(cacheKey);
if (cached && !cancelled) {
  setGames(cached);
  setLoading(false);
  // Continue to fetch fresh data in background (don't return)
}

// Step 1: Fetch archives list
const archivesRes = await fetch(`/api/chesscom/pub/player/${username}/games/archives`, {
  signal: controller.signal,
});
```

**Behavior**:
- If cached games exist: Shows cached games immediately, fetches fresh in background
- If no cache: Shows loading state, progressively fetches monthly archives
- Cache is updated after all months are fetched

**Cache TTL**: 10 minutes (configurable in `explorer-session-cache.ts`)

### 4. Server-Side Cache (`src/lib/explorer-cache.ts`)
**Location**: Already implements stale-while-revalidate
**Scope**: Server-side LRU cache with TTL for API proxy

The `LRUCache` class returns `{ value, isStale }` to indicate when cached data has expired. The API routes use this to:
1. Serve stale data immediately
2. Trigger background revalidation
3. Update cache with fresh data

**Used by**:
- `src/app/api/explorer/[...path]/route.ts` (Lichess proxy)
- `src/app/api/chesscom/[...path]/route.ts` (Chess.com proxy)

## Benefits

### Performance
- **Instant page loads**: Cached HTML served immediately (service worker)
- **No loading spinners**: Cached data shown while fetching fresh (hooks)
- **Reduced perceived latency**: Users see content instantly, updates happen in background

### User Experience
- **Progressive enhancement**: App feels faster without compromising data freshness
- **Offline resilience**: Cached content works even when network is slow/offline
- **Smooth updates**: Fresh data appears seamlessly without interrupting user flow

### Network Efficiency
- **Reduced redundant fetches**: Cached data served without hitting network
- **Background updates**: Fresh data fetched at lower priority
- **Graceful degradation**: Works even if background fetch fails

## Cache Configuration

### Service Worker
- **Cache name**: `chesster-v4`
- **Scope**: Navigation requests (HTML pages)
- **TTL**: Controlled by browser cache eviction policy
- **Max size**: Browser-dependent

### Session Storage (Browser)
- **Prefix**: `explorer_`
- **Lichess TTL**: 5 minutes
- **Chess.com TTL**: 10 minutes
- **TWIC TTL**: 15 minutes
- **Max size**: ~5-10MB (browser-dependent)

### Server-Side LRU Cache
- **Lichess TTL**: 6 hours
- **Chess.com TTL**: 24 hours
- **Max entries**: 2000 (Lichess), 5000 (Chess.com)
- **Rate limiting**: 10 req/s (Lichess), 5 req/s (Chess.com)

## Testing

### Service Worker Tests
**File**: `__tests__/sw.test.js`
**Coverage**:
- ✅ Returns cached response immediately for navigation
- ✅ Fetches from network if no cache exists
- ✅ Updates cache in background
- ✅ Network-first for API calls
- ✅ Fallback to cache when offline
- ✅ Different strategies for navigation vs API

**Run tests**: `npm test -- __tests__/sw.test.js`

## Monitoring

### Client-Side
Check browser DevTools:
- **Network tab**: Look for instant responses (from cache)
- **Application tab → Cache Storage**: Verify `chesster-v4` cache
- **Application tab → Session Storage**: Check `explorer_*` keys

### Server-Side
Response headers indicate cache status:
- `X-Cache: HIT` - Fresh cache hit
- `X-Cache: STALE` - Stale data served (revalidating in background)
- `X-Cache: MISS` - Cache miss (fetched from upstream)
- `X-Cache: ERROR` - Upstream error (served fallback)

## Trade-offs

### Advantages
✅ Instant user experience
✅ Reduced server load
✅ Better offline experience
✅ Graceful handling of slow networks

### Considerations
⚠️ Users may briefly see stale data (seconds to minutes old)
⚠️ Increased memory usage (cache storage)
⚠️ Complexity in debugging (harder to tell if data is cached or fresh)

## Future Improvements

1. **Cache versioning**: Add version field to detect schema changes
2. **Selective invalidation**: Allow manual cache invalidation for specific keys
3. **Metrics tracking**: Measure cache hit rates and performance gains
4. **User preference**: Allow users to disable caching or force refresh
5. **Smarter TTL**: Adjust TTL based on data volatility (e.g., longer TTL for historical games)

## References

- [HTTP Caching (MDN)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching)
- [Service Worker Cache Strategies](https://web.dev/offline-cookbook/)
- [Stale-While-Revalidate RFC](https://datatracker.ietf.org/doc/html/rfc5861)
