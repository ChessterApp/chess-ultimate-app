/**
 * POST /api/chess-empire/link/invite
 *
 * Cross-branch / online→branch "join family" invite. The caller (a verified
 * Chess Empire family member) enters the NAME or EMAIL of someone in another
 * branch — or a branch player they want to link from an online account. We
 * create a pending invite and email the target a consent link. NO link forms
 * and NO placeholder person is minted here: the reciprocal family edge only
 * appears once the target accepts (`/api/chess-empire/link/invite/accept`).
 *
 * Rate-limited per IP + per user, consistent with the other invite endpoints.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { rateLimit } from '@/lib/in-memory-rate-limit';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { getVerifiedMembersForUser } from '@/lib/chess-empire-member';
import { getStudentDisplayName } from '@/lib/chess-empire-client';
import { createFamilyLinkInvite } from '@/lib/family-link-invite';
import {
  sendFamilyInviteEmail,
  familyInviteAcceptUrl,
} from '@/lib/family-invite-email';

const PER_IP_LIMIT = 20;
const PER_USER_LIMIT = 10;
const RATE_WINDOW_MS = 60 * 60 * 1000;

// Deliberately permissive — a full RFC check is not worth it; we only need to
// avoid obvious garbage before handing the address to Resend.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface InviteBody {
  name?: string;
  email?: string;
  relationship?: string;
}

function clientIp(req: NextRequest): string {
  const forwarded = req.headers.get('x-forwarded-for');
  if (forwarded) return forwarded.split(',')[0]!.trim();
  return req.headers.get('x-real-ip') ?? 'unknown';
}

/** The inviter's own org id for the primary verified student (edge back-ref). */
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

  const ip = clientIp(req);
  const ipLimit = rateLimit(`ce-family-invite-ip:${ip}`, PER_IP_LIMIT, RATE_WINDOW_MS);
  if (!ipLimit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(ipLimit.retryAfterSeconds) } },
    );
  }
  const userLimit = rateLimit(`ce-family-invite-user:${userId}`, PER_USER_LIMIT, RATE_WINDOW_MS);
  if (!userLimit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(userLimit.retryAfterSeconds) } },
    );
  }

  let body: InviteBody;
  try {
    body = (await req.json()) as InviteBody;
  } catch {
    return NextResponse.json({ error: 'invalid_body' }, { status: 400 });
  }

  const name = body.name?.trim() || null;
  const email = body.email?.trim() || null;
  const relationship = body.relationship === 'other' ? 'other' : 'child';
  if (!name && !email) {
    return NextResponse.json({ error: 'missing_fields' }, { status: 400 });
  }
  if (email && !EMAIL_RE.test(email)) {
    return NextResponse.json({ error: 'invalid_email' }, { status: 400 });
  }

  // The inviter must be a real verified member — you can't build a family off an
  // unlinked account. Pick the primary verified student (self wins, else first).
  let members;
  try {
    members = await getVerifiedMembersForUser(userId);
  } catch (err) {
    console.error('[chess-empire/link/invite] member lookup failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
  const primary =
    members.find((m) => m.relationship === 'self' && m.studentId) ??
    members.find((m) => m.studentId);
  if (!primary?.studentId) {
    return NextResponse.json({ error: 'not_linked' }, { status: 403 });
  }

  const inviterOrgId = await resolveOrgId(userId, primary.studentId);
  const inviterName = await getStudentDisplayName(primary.studentId).catch(() => null);

  let invite;
  try {
    invite = await createFamilyLinkInvite({
      inviterUserId: userId,
      inviterOrgId,
      inviterStudentId: primary.studentId,
      targetName: name,
      targetEmail: email,
      relationship,
    });
  } catch (err) {
    console.error('[chess-empire/link/invite] create failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }

  let emailSent = false;
  if (email) {
    emailSent = await sendFamilyInviteEmail({
      toEmail: email,
      inviterName: inviterName ?? '',
      acceptUrl: familyInviteAcceptUrl(invite.token),
    });
  }

  return NextResponse.json({ ok: true, emailSent, targetEmail: email });
}
