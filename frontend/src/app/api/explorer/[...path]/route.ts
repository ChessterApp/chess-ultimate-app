import { NextRequest, NextResponse } from 'next/server';
import {
  explorerCache,
  rateLimiter,
  circuitBreaker,
  playerCircuitBreaker,
  EMPTY_EXPLORER_RESPONSE,
} from '@/lib/explorer-cache';

/**
 * Lichess Opening Explorer proxy with production-grade caching and rate limiting
 *
 * Features:
 * - Server-side LRU cache with 6-hour TTL
 * - Token bucket rate limiting (10 req/s to upstream)
 * - Stale-while-revalidate pattern
 * - Circuit breaker for upstream failures
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    // Extract path segments (e.g., ['masters'] or ['lichess'])
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path;

    if (!pathSegments || pathSegments.length === 0) {
      return NextResponse.json(
        { error: 'Invalid path' },
        { status: 400 }
      );
    }

    // Build cache key from full URL path + query string
    const path = pathSegments.join('/');
    const searchParams = request.nextUrl.searchParams;
    const queryString = searchParams.toString();
    const cacheKey = `${path}?${queryString}`;

    // Check cache first
    const cached = explorerCache.get(cacheKey);

    if (cached && !cached.isStale) {
      // Fresh cache hit - return immediately
      return NextResponse.json(cached.value, {
        status: 200,
        headers: {
          'Cache-Control': 'public, max-age=3600',
          'X-Cache': 'HIT',
        },
      });
    }

    // If cache is stale but exists, serve stale data and revalidate in background
    if (cached && cached.isStale) {
      // Start background revalidation (fire and forget)
      backgroundRevalidate(cacheKey, path, queryString).catch(() => {
        // Ignore background errors
      });

      // Return stale data immediately
      return NextResponse.json(cached.value, {
        status: 200,
        headers: {
          'Cache-Control': 'public, max-age=300',
          'X-Cache': 'STALE',
        },
      });
    }

    // Cache miss or no stale data - fetch from upstream
    try {
      // Select circuit breaker based on endpoint type
      const isPlayerEndpoint = path === 'player';
      const breaker = isPlayerEndpoint ? playerCircuitBreaker : circuitBreaker;

      // Check circuit breaker
      if (breaker.isOpen()) {
        // Circuit is open - return cached data if available, or empty fallback
        const fallbackData = cached?.value || EMPTY_EXPLORER_RESPONSE;
        return NextResponse.json(fallbackData, {
          status: 200,
          headers: {
            'Cache-Control': 'public, max-age=60',
            'X-Cache': 'CIRCUIT_OPEN',
          },
        });
      }

      // Acquire rate limit token (will wait if necessary)
      await rateLimiter.acquire();

      // Fetch from upstream with circuit breaker
      const data = await breaker.execute(async () => {
        const targetUrl = `https://explorer.lichess.org/${path}${queryString ? `?${queryString}` : ''}`;

        const fetchHeaders: Record<string, string> = {
            Accept: 'application/json',
            'User-Agent':
              'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            Referer: 'https://lichess.org/',
            Origin: 'https://lichess.org',
          };
          if (process.env.LICHESS_API_TOKEN) {
            fetchHeaders['Authorization'] = `Bearer ${process.env.LICHESS_API_TOKEN}`;
          }

          // Player endpoint needs longer timeout (60s) for queue processing
          const timeout = isPlayerEndpoint ? 60000 : 10000;

          const response = await fetch(targetUrl, {
          method: 'GET',
          headers: fetchHeaders,
          signal: AbortSignal.timeout(timeout),
        });

        if (!response.ok) {
          throw new Error(`Upstream error: ${response.status}`);
        }

        // Player endpoint returns NDJSON (newline-delimited JSON streaming)
        // Parse all lines and return the last non-empty one (final result)
        if (isPlayerEndpoint) {
          const text = await response.text();
          const lines = text.split('\n').filter(line => line.trim());
          if (lines.length === 0) {
            throw new Error('Empty NDJSON response');
          }
          // Parse the last line (final result with all data)
          const finalResult = JSON.parse(lines[lines.length - 1]);
          // Normalize: map recentGames to topGames for frontend compatibility
          if (finalResult.recentGames && !finalResult.topGames) {
            finalResult.topGames = finalResult.recentGames;
          }
          return finalResult;
        }

        // For lichess/masters endpoints: merge recentGames into topGames
        const jsonData = await response.json();
        if (jsonData.recentGames && Array.isArray(jsonData.recentGames)) {
          // Merge recentGames into topGames, deduplicating by game ID
          const topGames = jsonData.topGames || [];
          const existingIds = new Set(topGames.map((g: any) => g.id));
          const newGames = jsonData.recentGames.filter((g: any) => !existingIds.has(g.id));
          jsonData.topGames = [...topGames, ...newGames];
        }
        return jsonData;
      });

      // Cache only successful responses (never cache errors)
      explorerCache.set(cacheKey, data);

      return NextResponse.json(data, {
        status: 200,
        headers: {
          'Cache-Control': 'public, max-age=3600',
          'X-Cache': 'MISS',
        },
      });
    } catch (error) {
      // On error, return cached data if available, or empty fallback
      // Do NOT cache error responses — let the next request retry fresh
      const fallbackData = { ...(cached?.value || EMPTY_EXPLORER_RESPONSE), _upstreamError: true };
      return NextResponse.json(fallbackData, {
        status: 200,
        headers: {
          'Cache-Control': 'no-cache',
          'X-Cache': 'ERROR',
          'X-Explorer-Status': 'upstream-error',
        },
      });
    }
  } catch (error) {
    // Outer error handler - return empty response
    return NextResponse.json({ ...EMPTY_EXPLORER_RESPONSE, _upstreamError: true }, {
      status: 200,
      headers: {
        'Cache-Control': 'public, max-age=60',
        'X-Cache': 'ERROR',
        'X-Explorer-Status': 'upstream-error',
      },
    });
  }
}

/**
 * Background revalidation for stale-while-revalidate pattern
 */
async function backgroundRevalidate(
  cacheKey: string,
  path: string,
  queryString: string
): Promise<void> {
  try {
    const isPlayerEndpoint = path === 'player';
    const breaker = isPlayerEndpoint ? playerCircuitBreaker : circuitBreaker;

    // Skip if circuit breaker is open
    if (breaker.isOpen()) {
      return;
    }

    // Acquire rate limit token
    await rateLimiter.acquire();

    // Fetch fresh data
    const data = await breaker.execute(async () => {
      const targetUrl = `https://explorer.lichess.org/${path}${queryString ? `?${queryString}` : ''}`;

      const revalidateHeaders: Record<string, string> = {
        Accept: 'application/json',
        'User-Agent':
          'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        Referer: 'https://lichess.org/',
        Origin: 'https://lichess.org',
      };
      if (process.env.LICHESS_API_TOKEN) {
        revalidateHeaders['Authorization'] = `Bearer ${process.env.LICHESS_API_TOKEN}`;
      }

      // Player endpoint needs longer timeout (60s) for queue processing
      const timeout = isPlayerEndpoint ? 60000 : 10000;

      const response = await fetch(targetUrl, {
        method: 'GET',
        headers: revalidateHeaders,
        signal: AbortSignal.timeout(timeout),
      });

      if (!response.ok) {
        throw new Error(`Upstream error: ${response.status}`);
      }

      // Player endpoint returns NDJSON (newline-delimited JSON streaming)
      if (isPlayerEndpoint) {
        const text = await response.text();
        const lines = text.split('\n').filter(line => line.trim());
        if (lines.length === 0) {
          throw new Error('Empty NDJSON response');
        }
        const finalResult = JSON.parse(lines[lines.length - 1]);
        if (finalResult.recentGames && !finalResult.topGames) {
          finalResult.topGames = finalResult.recentGames;
        }
        return finalResult;
      }

      // For lichess/masters endpoints: merge recentGames into topGames
      const jsonData = await response.json();
      if (jsonData.recentGames && Array.isArray(jsonData.recentGames)) {
        const topGames = jsonData.topGames || [];
        const existingIds = new Set(topGames.map((g: any) => g.id));
        const newGames = jsonData.recentGames.filter((g: any) => !existingIds.has(g.id));
        jsonData.topGames = [...topGames, ...newGames];
      }
      return jsonData;
    });

    // Update cache with fresh data
    explorerCache.set(cacheKey, data);
  } catch {
    // Ignore errors in background revalidation
  }
}
