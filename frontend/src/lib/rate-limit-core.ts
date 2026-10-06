/**
 * In-memory sliding-window rate limiter — the limiter itself, importable
 * from anywhere on the server.
 *
 * `in-memory-rate-limit.ts` re-exports it behind `import 'server-only'` for
 * the App Router routes. Pages Router API routes (`src/pages/api/*`) must
 * import this file instead: there the `server-only` package resolves to its
 * throwing entry, so every request to such a route failed with a 500 before
 * the handler ran — /api/convert-image and /api/convert-scoresheet were down
 * from 2026-09-21 to 2026-10-06 (photo of a board / of a scoresheet).
 *
 * A single process, a single map, no eviction thread (entries cap themselves
 * by trimming on access).
 */

interface Bucket {
  /** Timestamps (ms since epoch) of attempts within the window. */
  hits: number[];
}

const buckets: Map<string, Bucket> = new Map();

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  retryAfterSeconds: number;
}

export function rateLimit(
  key: string,
  limit: number,
  windowMs: number,
  now: number = Date.now(),
): RateLimitResult {
  const cutoff = now - windowMs;
  const bucket = buckets.get(key) ?? { hits: [] };
  bucket.hits = bucket.hits.filter((t) => t > cutoff);

  if (bucket.hits.length >= limit) {
    const oldest = bucket.hits[0];
    const retryAfterMs = Math.max(0, oldest + windowMs - now);
    buckets.set(key, bucket);
    return {
      allowed: false,
      remaining: 0,
      retryAfterSeconds: Math.ceil(retryAfterMs / 1000),
    };
  }

  bucket.hits.push(now);
  buckets.set(key, bucket);
  return {
    allowed: true,
    remaining: limit - bucket.hits.length,
    retryAfterSeconds: 0,
  };
}

/** Test/debug hook — wipes all buckets. */
export function _resetRateLimitForTests(): void {
  buckets.clear();
}
