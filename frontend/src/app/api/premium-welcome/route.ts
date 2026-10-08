import { NextResponse } from 'next/server';
import { auth, clerkClient } from '@clerk/nextjs/server';

/**
 * GET/POST /api/premium-welcome — the one-time "Welcome to Premium" seen flag.
 *
 * The flag lives on the caller's Clerk `publicMetadata.premiumWelcomeSeen`, so
 * it follows the user across devices without a Supabase round-trip. Both verbs
 * resolve the caller server-side via Clerk `auth()` — we never accept a userId
 * from the request, so a user can only read/write their own flag.
 *
 *  - Not authenticated → 401
 *  - GET  → { seen: boolean }   (defaults to false when the key is absent)
 *  - POST → { ok: true }        (sets premiumWelcomeSeen = true, merging into
 *                                existing publicMetadata so no other key is lost)
 */
export async function GET() {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const client = await clerkClient();
  const user = await client.users.getUser(userId);
  const seen = (user.publicMetadata as Record<string, unknown>)?.premiumWelcomeSeen === true;
  return NextResponse.json({ seen });
}

export async function POST() {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const client = await clerkClient();
  // updateUserMetadata shallow-merges the top-level publicMetadata keys, so
  // only premiumWelcomeSeen is touched; any other metadata keys are preserved.
  await client.users.updateUserMetadata(userId, {
    publicMetadata: { premiumWelcomeSeen: true },
  });
  return NextResponse.json({ ok: true });
}
