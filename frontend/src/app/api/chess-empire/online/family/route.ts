/**
 * POST /api/chess-empire/online/family — mint an online family member.
 *
 * The online counterpart of the branch "add family member" flow. A branch-linked
 * parent adds a child by searching the CE roster; an online parent has no roster
 * to search, so instead we MINT a fresh synthetic online student under the
 * caller's own Clerk account — exactly the trick the online self-link already
 * uses, but writing `relationship='child'|'other'` instead of 'self'. The
 * parent's family bar becomes the online "roster".
 *
 * Preconditions: a signed-in Clerk user who already owns ≥1 VERIFIED member with
 * `external_source='online'` (their own self-link). A branch-only or unlinked
 * account is rejected `403 not_online` — this endpoint never creates the first
 * link, only additional family members off an existing online account.
 *
 * The new row is written through the SAME shared writer as the webhook / claim
 * path (`upsertMemberLink`), keeping the unique
 * `(organization_id, external_student_id, external_source)` key intact and
 * avoiding a duplicated claim implementation. `access_expires_at` is stamped
 * `now() + 72h`, matching the trial mint (decision locked in the Phase 4 brief:
 * a fresh 72h window per member, computed from creation).
 *
 * Rate-limited per IP consistent with `online/trial` (20 / hour).
 */
import 'server-only';

import { NextRequest, NextResponse } from 'next/server';
import { randomUUID } from 'node:crypto';
import { auth } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { rateLimit } from '@/lib/in-memory-rate-limit';
import { getVerifiedMembersForUser } from '@/lib/chess-empire-member';
import { upsertMemberLink } from '@/lib/chess-empire-jwt-link';

const PER_IP_LIMIT = 20;
const RATE_WINDOW_MS = 60 * 60 * 1000;
// Fresh 72h window per minted member, from creation (Phase 4 decision).
const ONLINE_MEMBER_TTL_HOURS = 72;

type Relationship = 'child' | 'other';

interface FamilyBody {
  name?: string;
  relationship?: string;
}

function clientIp(req: NextRequest): string {
  const forwarded = req.headers.get('x-forwarded-for');
  if (forwarded) return forwarded.split(',')[0]!.trim();
  return req.headers.get('x-real-ip') ?? 'unknown';
}

/**
 * Resolve the caller's own online member row → its `organization_id`, so the new
 * family member is minted under the same org (and the unique key holds). Scoped
 * to the caller's verified online self-link student id; returns null if the row
 * has vanished between the precondition check and here.
 */
async function resolveOnlineOrgId(
  userId: string,
  studentId: string,
): Promise<string | null> {
  const { data, error } = await supabaseAdmin
    .from('organization_members')
    .select('organization_id')
    .eq('user_id', userId)
    .eq('external_student_id', studentId)
    .eq('external_source', 'online')
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
  const limit = rateLimit(`ce-online-family-ip:${ip}`, PER_IP_LIMIT, RATE_WINDOW_MS);
  if (!limit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(limit.retryAfterSeconds) } },
    );
  }

  let body: FamilyBody;
  try {
    body = (await req.json()) as FamilyBody;
  } catch {
    return NextResponse.json({ error: 'invalid_body' }, { status: 400 });
  }

  const name = body.name?.trim() ?? '';
  const relationship = body.relationship;
  if (!name) {
    return NextResponse.json({ error: 'missing_fields' }, { status: 400 });
  }
  if (relationship !== 'child' && relationship !== 'other') {
    return NextResponse.json({ error: 'invalid_relationship' }, { status: 400 });
  }

  // Precondition: the caller must already be an online account. The canonical
  // membership lib applies the online-window expiry downgrade, so an expired
  // self-link no longer counts as verified here.
  let members;
  try {
    members = await getVerifiedMembersForUser(userId);
  } catch (err) {
    console.error('[chess-empire/online/family] member lookup failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
  const onlineSelf = members.find((m) => m.source === 'online' && m.studentId);
  if (!onlineSelf?.studentId) {
    return NextResponse.json({ error: 'not_online' }, { status: 403 });
  }

  const orgId = await resolveOnlineOrgId(userId, onlineSelf.studentId);
  if (!orgId) {
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }

  // Each online family member is its own synthetic student so the unique
  // (org, external_student_id, source) key holds — no CE record to point at.
  const studentId = randomUUID();
  try {
    await upsertMemberLink({
      orgId,
      clerkUserId: userId,
      studentId,
      linkStatus: 'verified',
      linkSource: 'claim',
      memberType: 'student',
      externalSource: 'online',
      accessTtlHours: ONLINE_MEMBER_TTL_HOURS,
      relationship: relationship as Relationship,
      name,
    });
  } catch (err) {
    console.error('[chess-empire/online/family] mint failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }

  return NextResponse.json({ ok: true, studentId, relationship });
}
