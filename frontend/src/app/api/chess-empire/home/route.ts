/**
 * GET /api/chess-empire/home
 *
 * Read-only JSON twin of the Chess Empire personalized homepage (`/dashboard`
 * on chess-empire.chesster.io) for the mobile app, which cannot read a server
 * component's props. Runs the SAME pipeline as `renderEmpireHomepage`: Clerk
 * session → pending-cookie auto-claim → `loadEmpireHomeData`, then returns a
 * trimmed copy (`toEmpireHomeJson`) — no date_of_birth, e-mail, or ids beyond
 * the coach roster's row id.
 *
 *  - 400 `not_ce_host` off the chess-empire tenant host (no CE home there).
 *  - 401 without a Clerk session.
 *  - 500 `lookup_error` when a required lookup fails (the page shows
 *    `EmpireError` in that case).
 *  - 200 `{ kind: 'no_link' | 'frozen' | 'expired' | 'online' |
 *    'pending_confirm' | 'coach' | 'student', ... }` otherwise.
 *
 * The restricted-hub level framing (frozen/expired) is not included: it
 * depends on the caller's Learn progress, which the app already resolves.
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { headers } from 'next/headers';
import { auth } from '@clerk/nextjs/server';
import { autoClaimPendingCookie } from '@/lib/pending-registration';
import { loadEmpireHomeData, toEmpireHomeJson } from '@/lib/empire-home-data';

export const dynamic = 'force-dynamic';

export async function GET() {
  const headersList = await headers();
  const orgId = headersList.get('x-org-id');
  const orgSlug = headersList.get('x-org-slug');
  if (!orgId || orgSlug !== 'chess-empire') {
    return NextResponse.json({ error: 'not_ce_host' }, { status: 400 });
  }

  // Same as the page: a throwing auth() (stale/rotated token) is treated as
  // no session, so the caller re-authenticates instead of seeing a 500.
  let userId: string | null = null;
  try {
    userId = (await auth()).userId ?? null;
  } catch (err) {
    console.error('[chess-empire/home] auth() threw', err);
  }
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  // Same best-effort server-side auto-claim the page runs before reading
  // membership.
  try {
    await autoClaimPendingCookie(userId);
  } catch (err) {
    console.error('[chess-empire/home] pending auto-claim threw', err);
  }

  try {
    const data = await loadEmpireHomeData(orgId, userId);
    return NextResponse.json(toEmpireHomeJson(data));
  } catch {
    // The loader already logged the failing step.
    return NextResponse.json({ error: 'lookup_error' }, { status: 500 });
  }
}
