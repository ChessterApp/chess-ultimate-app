/**
 * Shared server-side guard for gated Next.js API routes (Phase 3).
 *
 * Call at the top of a gated route handler and early-return its result:
 *
 *   const denied = await requireApiAccess();
 *   if (denied) return denied;
 *
 * Returns a 403 `NextResponse` with a machine-readable body when the caller is
 * a restricted (frozen/expired) member without the personal-subscription
 * override, and `null` when they may proceed. This is the API-layer mirror of
 * the `requireAccess` page guard — the primary defense is still the Phase 1
 * route guard; this catches direct API calls and stale tabs.
 *
 * It reuses `resolveAccessPolicy`, so the personal-subscription override applies
 * identically here. Best-effort: any resolution failure yields full access, so
 * a transient Supabase blip never 403s a paying user.
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { resolveAccessPolicy } from '@/lib/access-membership';

export async function requireApiAccess(): Promise<NextResponse | null> {
  const policy = await resolveAccessPolicy();
  if (policy.mode !== 'restricted') return null;
  return NextResponse.json(
    {
      error: 'MEMBERSHIP_RESTRICTED',
      reason: policy.reason,
      upgradePath: policy.upgradePath,
    },
    { status: 403 },
  );
}
