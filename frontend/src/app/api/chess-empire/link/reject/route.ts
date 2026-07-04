/**
 * POST /api/chess-empire/link/reject
 *
 * Called from the pending_confirm banner on the CE homepage when the user
 * says "no, that's not me". Deletes the pending_confirm row so the next
 * page load renders `no_link`, and logs a `no_match` link_attempt so admin
 * sees the user still needs manual linking.
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { auth, clerkClient } from '@clerk/nextjs/server';
import {
  rejectPendingLink,
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
    const result = await rejectPendingLink(userId, email);
    return NextResponse.json({ ok: true, ...result });
  } catch (err) {
    if (err instanceof LinkNotFoundError) {
      return NextResponse.json({ error: 'not_found' }, { status: 404 });
    }
    console.error('[chess-empire/link/reject] failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
}
