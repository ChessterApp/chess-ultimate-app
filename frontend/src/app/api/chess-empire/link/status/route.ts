/**
 * GET /api/chess-empire/link/status
 *
 * Returns the current Clerk user's Chess Empire link state
 * (`no_link` | `pending_confirm` | `verified`). No params — the row is
 * resolved by the caller's Clerk session. Polled by the `no_link` view on the
 * dashboard to detect when the async webhook (or the client claim) has written
 * the member row, so it can `router.refresh()` into the personalized page.
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { getMembershipStateForUser } from '@/lib/chess-empire-member';

export async function GET() {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const membership = await getMembershipStateForUser(userId);
    return NextResponse.json({ state: membership.state, role: membership.role });
  } catch (err) {
    console.error('[chess-empire/link/status] lookup failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
}
