import { NextRequest, NextResponse } from 'next/server';
import {
  chesscomCache,
  chesscomRateLimiter,
  chesscomCircuitBreaker,
  EMPTY_CHESSCOM_RESPONSE,
} from '@/lib/chesscom-cache';

/**
 * Chess.com API proxy with production-grade caching and rate limiting
 *
 * Features:
 * - Server-side LRU cache with 24-hour TTL
 * - Token bucket rate limiting (5 req/s to upstream)
 * - Stale-while-revalidate pattern
 * - Circuit breaker for upstream failures
 *
 * Endpoints:
 * - GET /api/chesscom/pub/player/{username}/games/archives → List of month URLs
 * - GET /api/chesscom/pub/player/{username}/games/{YYYY}/{MM} → Monthly PGN games
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    // Extract path segments (e.g., ['pub', 'player', 'username', 'games', 'archives'])
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path;

    if (!pathSegments || pathSegments.length === 0) {
      return NextResponse.json(
        { error: 'Invalid path' },
        { status: 400 }
      );
    }

    // Build cache key from full URL path
    const path = pathSegments.join('/');
    const cacheKey = `chesscom:${path}`;

    // Check cache first
    const cached = chesscomCache.get(cacheKey);

    if (cached && !cached.isStale) {
      // Fresh cache hit - return immediately
      return NextResponse.json(cached.value, {
        status: 200,
        headers: {
          'Cache-Control': 'public, max-age=86400', // 24 hours
          'X-Cache': 'HIT',
        },
      });
    }

    // If cache is stale but exists, serve stale data and revalidate in background
    if (cached && cached.isStale) {
      // Start background revalidation (fire and forget)
      backgroundRevalidate(cacheKey, path).catch(() => {
        // Ignore background errors
      });

      // Return stale data immediately
      return NextResponse.json(cached.value, {
        status: 200,
        headers: {
          'Cache-Control': 'public, max-age=3600', // 1 hour
          'X-Cache': 'STALE',
        },
      });
    }

    // Cache miss or no stale data - fetch from upstream
    try {
      // Check circuit breaker
      if (chesscomCircuitBreaker.isOpen()) {
        // Circuit is open - return cached data if available, or empty fallback
        const fallbackData = cached?.value || EMPTY_CHESSCOM_RESPONSE;
        return NextResponse.json(fallbackData, {
          status: 200,
          headers: {
            'Cache-Control': 'public, max-age=60',
            'X-Cache': 'CIRCUIT_OPEN',
          },
        });
      }

      // Acquire rate limit token (will wait if necessary)
      await chesscomRateLimiter.acquire();

      // Fetch from upstream with circuit breaker
      const data = await chesscomCircuitBreaker.execute(async () => {
        const targetUrl = `https://api.chess.com/${path}`;

        const response = await fetch(targetUrl, {
          method: 'GET',
          headers: {
            Accept: 'application/json',
            'User-Agent':
              'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
          },
          signal: AbortSignal.timeout(15000), // 15s timeout
        });

        if (!response.ok) {
          throw new Error(`Upstream error: ${response.status}`);
        }

        return response.json();
      });

      // Cache the result
      chesscomCache.set(cacheKey, data);

      return NextResponse.json(data, {
        status: 200,
        headers: {
          'Cache-Control': 'public, max-age=86400', // 24 hours
          'X-Cache': 'MISS',
        },
      });
    } catch (error) {
      // On error, return cached data if available, or empty fallback
      const fallbackData = cached?.value || EMPTY_CHESSCOM_RESPONSE;
      return NextResponse.json(fallbackData, {
        status: 200,
        headers: {
          'Cache-Control': 'public, max-age=60',
          'X-Cache': 'ERROR',
        },
      });
    }
  } catch (error) {
    // Outer error handler - return empty response
    return NextResponse.json(EMPTY_CHESSCOM_RESPONSE, {
      status: 200,
      headers: {
        'Cache-Control': 'public, max-age=60',
        'X-Cache': 'ERROR',
      },
    });
  }
}

/**
 * Background revalidation for stale-while-revalidate pattern
 */
async function backgroundRevalidate(
  cacheKey: string,
  path: string
): Promise<void> {
  try {
    // Skip if circuit breaker is open
    if (chesscomCircuitBreaker.isOpen()) {
      return;
    }

    // Acquire rate limit token
    await chesscomRateLimiter.acquire();

    // Fetch fresh data
    const data = await chesscomCircuitBreaker.execute(async () => {
      const targetUrl = `https://api.chess.com/${path}`;

      const response = await fetch(targetUrl, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          'User-Agent':
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        },
        signal: AbortSignal.timeout(15000),
      });

      if (!response.ok) {
        throw new Error(`Upstream error: ${response.status}`);
      }

      return response.json();
    });

    // Update cache with fresh data
    chesscomCache.set(cacheKey, data);
  } catch {
    // Ignore errors in background revalidation
  }
}
