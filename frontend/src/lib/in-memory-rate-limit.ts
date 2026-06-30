/**
 * In-memory sliding-window rate limiter.
 *
 * Phase 1 of the Chess Empire → Chesster onboarding arc. The search +
 * verify routes need lightweight per-IP throttling; the Python backend's
 * Redis-backed limiter isn't reachable from the Next.js API edge layer.
 * This is intentionally tiny: a single process, a single map, no eviction
 * thread (entries cap themselves by trimming on access). Good enough for
 * pre-signup public endpoints; revisit if we ever go multi-region.
 */
import 'server-only';

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
