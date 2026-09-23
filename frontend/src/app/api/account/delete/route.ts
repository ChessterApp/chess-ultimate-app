import { NextResponse } from 'next/server';
import { auth, clerkClient } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';

/**
 * Self-service account deletion (Google Play Data-safety compliance).
 *
 * POST only. The caller is resolved server-side via Clerk `auth()` — we NEVER
 * accept a userId from the request body, so a signed-in user can only ever
 * delete their own account.
 *
 * Deleting the Clerk user fires the `user.deleted` webhook, which cascades the
 * Supabase data purge (see src/app/api/webhooks/clerk/route.ts).
 *
 * Org ownership guard: org ownership is expressed as an `organization_members`
 * row with `role='owner'` (there is no owner column on `organizations`).
 * Deleting an owner would orphan their org, so we block deletion and tell them
 * to transfer ownership first rather than silently orphaning it.
 */
export async function POST() {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const { data: ownedOrgs, error } = await supabaseAdmin
      .from('organization_members')
      .select('organization_id')
      .eq('user_id', userId)
      .eq('role', 'owner');
    if (error) throw error;
    if (ownedOrgs && ownedOrgs.length > 0) {
      return NextResponse.json(
        {
          error:
            'You still own an organization. Please transfer ownership to another member before deleting your account.',
          code: 'owns_organization',
        },
        { status: 409 },
      );
    }
  } catch (err) {
    console.error('[account-delete] org-ownership check failed:', err);
    return NextResponse.json(
      { error: 'Could not verify account state. Please try again.' },
      { status: 500 },
    );
  }

  try {
    const client = await clerkClient();
    await client.users.deleteUser(userId);
  } catch (err) {
    console.error('[account-delete] clerk deleteUser failed:', err);
    return NextResponse.json({ error: 'Failed to delete account.' }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}
