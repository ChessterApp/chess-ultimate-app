/**
 * In-memory sliding-window rate limiter.
 *
 * Phase 1 of the Chess Empire → Chesster onboarding arc. The search +
 * verify routes need lightweight per-IP throttling; the Python backend's
 * Redis-backed limiter isn't reachable from the Next.js API edge layer.
 * This is intentionally tiny: a single process, a single map, no eviction
 * thread (entries cap themselves by trimming on access). Good enough for
 * pre-signup public endpoints; revisit if we ever go multi-region.
 *
 * The limiter lives in `rate-limit-core.ts`; this module keeps the
 * `server-only` guard for App Router code. Pages Router API routes import
 * the core directly (the guard throws there).
 */
import 'server-only';

export { rateLimit, _resetRateLimitForTests } from './rate-limit-core';
export type { RateLimitResult } from './rate-limit-core';
