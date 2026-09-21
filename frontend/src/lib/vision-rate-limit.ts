/**
 * Throttle for the two vision proxies (`/api/convert-image`, `/api/convert-scoresheet`).
 *
 * Both fan out to paid Gemini vision calls (a scoresheet scan is three Pro
 * passes) and both must stay reachable without sign-in: guests use the photo
 * scanner on the public /position page and the mobile app calls them without
 * a token. So instead of an auth gate: a per-user budget for signed-in
 * callers and a tighter per-IP budget for anonymous ones, on the same
 * in-memory limiter the Chess Empire onboarding routes use.
 */
import type { NextApiRequest } from 'next';
import { getAuth } from '@clerk/nextjs/server';
import { rateLimit } from '@/lib/in-memory-rate-limit';

export interface VisionLimits {
  /** Requests per window for a signed-in user. */
  perUser: number;
  /** Requests per window for an anonymous IP. */
  perIp: number;
  windowMs: number;
}

export const CONVERT_IMAGE_LIMITS: VisionLimits = {
  perUser: 120,
  perIp: 30,
  windowMs: 60 * 60 * 1000,
};

export const CONVERT_SCORESHEET_LIMITS: VisionLimits = {
  perUser: 40,
  perIp: 10,
  windowMs: 60 * 60 * 1000,
};

export function clientIp(req: NextApiRequest): string {
  const forwarded = req.headers['x-forwarded-for'];
  const first = Array.isArray(forwarded) ? forwarded[0] : forwarded;
  if (first) return first.split(',')[0]!.trim();
  const real = req.headers['x-real-ip'];
  return (Array.isArray(real) ? real[0] : real) ?? req.socket?.remoteAddress ?? 'unknown';
}

export interface VisionRateDecision {
  allowed: boolean;
  retryAfterSeconds: number;
  /** Who the budget was charged to — for logs. */
  subject: string;
}

export function checkVisionRateLimit(
  req: NextApiRequest,
  name: string,
  limits: VisionLimits,
): VisionRateDecision {
  let userId: string | null = null;
  try {
    userId = getAuth(req).userId ?? null;
  } catch {
    userId = null;
  }

  const key = userId ? `vision:${name}:user:${userId}` : `vision:${name}:ip:${clientIp(req)}`;
  const limit = userId ? limits.perUser : limits.perIp;
  const result = rateLimit(key, limit, limits.windowMs);
  return {
    allowed: result.allowed,
    retryAfterSeconds: result.retryAfterSeconds,
    subject: key,
  };
}
