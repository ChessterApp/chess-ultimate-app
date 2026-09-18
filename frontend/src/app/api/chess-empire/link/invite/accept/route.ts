/**
 * POST /api/chess-empire/link/invite/accept
 *
 * The consent step of the cross-branch / online→branch "join family" flow. The
 * target opens the emailed link, signs in, and lands here. On accept we stamp
 * the target's own REAL student id/org onto the invite row (the family edge) —
 * no placeholder person, and the link exists ONLY because the target opted in.
 *
 * `{ token, action?: 'accept' | 'reject' }`. The email-consent guard lives in
 * `acceptFamilyLinkInvite`: an email-targeted invite may only be accepted by an
 * account whose primary email matches.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth, clerkClient } from '@clerk/nextjs/server';
import { rateLimit } from '@/lib/in-memory-rate-limit';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { getVerifiedMembersForUser } from '@/lib/chess-empire-member';
import {
  acceptFamilyLinkInvite,
  rejectFamilyLinkInvite,
  InviteNotFoundError,
  InviteNotPendingError,
  InviteEmailMismatchError,
} from '@/lib/family-link-invite';

const PER_USER_LIMIT = 20;
const RATE_WINDOW_MS = 60 * 60 * 1000;

interface AcceptBody {
  token?: string;
  action?: string;
}

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

async function resolveOrgId(
  userId: string,
  studentId: string,
): Promise<string | null> {
  const { data, error } = await supabaseAdmin
    .from('organization_members')
    .select('organization_id')
    .eq('user_id', userId)
    .eq('external_student_id', studentId)
    .limit(1);
  if (error || !data || data.length === 0) return null;
  return (data[0] as { organization_id: string }).organization_id ?? null;
}

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const limit = rateLimit(`ce-family-accept-user:${userId}`, PER_USER_LIMIT, RATE_WINDOW_MS);
  if (!limit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(limit.retryAfterSeconds) } },
    );
  }

  let body: AcceptBody;
  try {
    body = (await req.json()) as AcceptBody;
  } catch {
    return NextResponse.json({ error: 'invalid_body' }, { status: 400 });
  }
  const token = body.token?.trim() ?? '';
  if (!token) {
    return NextResponse.json({ error: 'missing_token' }, { status: 400 });
  }

  if (body.action === 'reject') {
    try {
      await rejectFamilyLinkInvite(token);
    } catch (err) {
      console.error('[chess-empire/link/invite/accept] reject failed', err);
      return NextResponse.json({ error: 'server_error' }, { status: 500 });
    }
    return NextResponse.json({ ok: true, status: 'rejected' });
  }

  // The accepter needs their own real CE student id to form the edge.
  let members;
  try {
    members = await getVerifiedMembersForUser(userId);
  } catch (err) {
    console.error('[chess-empire/link/invite/accept] member lookup failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
  const self =
    members.find((m) => m.relationship === 'self' && m.studentId) ??
    members.find((m) => m.studentId);
  if (!self?.studentId) {
    return NextResponse.json({ error: 'accepter_not_linked' }, { status: 403 });
  }
  const orgId = await resolveOrgId(userId, self.studentId);
  if (!orgId) {
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }

  const email = await getPrimaryEmail(userId);
  try {
    await acceptFamilyLinkInvite({
      token,
      accepterUserId: userId,
      accepterEmail: email,
      accepterStudentId: self.studentId,
      accepterOrgId: orgId,
    });
  } catch (err) {
    if (err instanceof InviteNotFoundError) {
      return NextResponse.json({ error: 'not_found' }, { status: 404 });
    }
    if (err instanceof InviteNotPendingError) {
      return NextResponse.json({ error: 'not_pending' }, { status: 409 });
    }
    if (err instanceof InviteEmailMismatchError) {
      return NextResponse.json({ error: 'email_mismatch' }, { status: 403 });
    }
    console.error('[chess-empire/link/invite/accept] accept failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }

  return NextResponse.json({ ok: true, status: 'accepted' });
}
