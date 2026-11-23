/**
 * The voice pipeline's direct path (23.11): a short pass the page shows Hermes itself, instead of every hot request
 * going through this site's proxy (~0.5 s a request on chesster.io, two a spoken turn).
 *
 * The pass says who the student is, their plan and until when — what the proxies otherwise send as X-User-Id and
 * x-subscription-tier — signed with COACH_DIRECT_SECRET, which only this server and Hermes hold
 * (hermes/src/direct_access.py checks it). Hermes takes the student and the plan from the pass alone.
 * COACH_DIRECT_URL is Hermes' public address (only its /direct/ prefix is reachable there). Without both the path is
 * off and the page goes through the site as before.
 */
import 'server-only';
import { createHmac } from 'node:crypto';

export const DIRECT_AUDIENCE = 'coach-direct';
/** Short: access and plan are checked again when it is renewed (the proxies' own caches hold a minute). */
export const DIRECT_PASS_TTL_S = 300;

export type DirectPass = { url: string; token: string; expiresAt: number };

function b64url(data: Buffer | string): string {
  return Buffer.from(data).toString('base64url');
}

export function signDirectPass(payload: Record<string, unknown>, secret: string): string {
  const body = b64url(JSON.stringify(payload));
  const mac = createHmac('sha256', secret).update(`v1.${body}`).digest();
  return `v1.${body}.${b64url(mac)}`;
}

/** The pass for this student and plan, or null when the direct path is not set up on this deployment. */
export function mintDirectPass(userId: string, tier: string, nowMs: number = Date.now(), floor?: number): DirectPass | null {
  const url = (process.env.COACH_DIRECT_URL || '').trim().replace(/\/+$/, '');
  const secret = (process.env.COACH_DIRECT_SECRET || '').trim();
  if (!url || !secret || !userId) return null;
  const exp = Math.floor(nowMs / 1000) + DIRECT_PASS_TTL_S;
  // The Chess Empire level /learn's locks open courses by (src/lib/coach/learn-floor.ts) rides in the pass as the plan.
  const payload = { sub: userId, tier, exp, aud: DIRECT_AUDIENCE, ...(floor ? { floor } : {}) };
  return { url, token: signDirectPass(payload, secret), expiresAt: exp * 1000 };
}
