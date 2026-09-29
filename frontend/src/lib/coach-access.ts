/**
 * The membership guard for the coach's per-message routes, remembered briefly.
 *
 * `requireApiAccess` looks the member up in Supabase on every call. Measured on
 * chesster.io (2026-09-30): a chat message spent ~0.22 s on it before the
 * coach even started (warm function; up to ~1 s on a cold one), and a voice
 * session repeats it on every tool call and every engine line. An ALLOWED
 * result is kept for a minute per user on this function instance; a denial is
 * never cached, so a restricted member is re-checked every time. A membership
 * frozen mid-conversation takes effect within a minute.
 */
import 'server-only';
import type { NextResponse } from 'next/server';
import { requireApiAccess } from '@/lib/require-api-access';

const ALLOWED_TTL_MS = 60_000;
const MAX_ENTRIES = 5_000;

const allowedUntil = new Map<string, number>();

export async function requireCoachAccess(userId: string): Promise<NextResponse | null> {
  const now = Date.now();
  if ((allowedUntil.get(userId) ?? 0) > now) return null;
  const denied = await requireApiAccess();
  if (denied) {
    allowedUntil.delete(userId);
    return denied;
  }
  if (allowedUntil.size >= MAX_ENTRIES) {
    for (const [id, until] of allowedUntil) {
      if (until <= now) allowedUntil.delete(id);
    }
    if (allowedUntil.size >= MAX_ENTRIES) allowedUntil.clear();
  }
  allowedUntil.set(userId, now + ALLOWED_TTL_MS);
  return null;
}

/** Tests only: forget every remembered result. */
export function resetCoachAccessCache(): void {
  allowedUntil.clear();
}
