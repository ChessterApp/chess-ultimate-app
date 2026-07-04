/**
 * POST /api/chess-empire/link/confirm
 *
 * Called from the pending_confirm banner on the CE homepage. Flips the
 * caller's own pending_confirm row to `verified`. No body — the row is
 * resolved by the caller's Clerk user id. Idempotent (a second call once
 * the row is already verified returns 404 no_link).
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { auth, clerkClient } from '@clerk/nextjs/server';
import {
  confirmPendingLink,
  LinkNotFoundError,
} from '@/lib/chess-empire-link';

async function getPrimaryEmail(userId: string): Promise<string | null> {
  try {
    const client = await clerkClient();
    const user = await client.users.getUser(userId);
    const primaryId = user.primaryEmailAddressId;
    const hit = user.emailAddresses.find((e) => e.id === primaryId);
    return hit?.emailAddress ?? user.emailAddresses[0]?.emailAddress ?? null;
  } catch {
    return null;
  }
}

export async function POST() {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const email = await getPrimaryEmail(userId);
  try {
    const result = await confirmPendingLink(userId, email);
    return NextResponse.json({ ok: true, ...result });
  } catch (err) {
    if (err instanceof LinkNotFoundError) {
      return NextResponse.json({ error: 'not_found' }, { status: 404 });
    }
    console.error('[chess-empire/link/confirm] failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
}
