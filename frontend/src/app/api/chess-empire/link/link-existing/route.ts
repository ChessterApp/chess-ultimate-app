/**
 * POST /api/chess-empire/link/link-existing
 *
 * Same-branch instant family link. The parent has picked a student from the
 * roster search (scoped to their own branch); this endpoint validates the pick
 * server-side and writes the verified `organization_members` row in one call —
 * no invite JWT round-trip, no email, no accept step. It is the consolidation of
 * the older search → verify → claim dance for the in-app "add family member" flow.
 *
 * The parent's own branch + org are resolved from their VERIFIED membership, not
 * from the public branch invite token (a pre-signup artifact). A `branchToken`
 * may still be supplied for back-compat: when it resolves to a valid token, its
 * org+branch are used; when absent OR unresolvable, we fall back to the caller's
 * verified membership. Either way the net invariant holds — a caller can only
 * ever link a student that is in the caller's OWN verified branch.
 *
 * Consent is implicit here: the target is a roster student inside the parent's
 * own branch (we reject any student whose CE branch doesn't match). Cross-branch
 * / online→branch adds go through the email-consent invite flow instead.
 *
 * Rate-limited per IP + per user, consistent with the other invite endpoints.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { rateLimit } from '@/lib/in-memory-rate-limit';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { upsertMemberLink } from '@/lib/chess-empire-jwt-link';
import { getVerifiedMembersForUser } from '@/lib/chess-empire-member';
import { createAutoAcceptedFamilyEdge } from '@/lib/family-link-invite';
import {
  getStudentProfile,
  getStudentDisplayName,
  ChessEmpireAPIError,
} from '@/lib/chess-empire-client';

const PER_IP_LIMIT = 20;
const PER_USER_LIMIT = 10;
const RATE_WINDOW_MS = 60 * 60 * 1000;

interface BranchTokenRow {
  id: string;
  organization_id: string;
  external_branch_id: string;
  expires_at: string | null;
  revoked_at: string | null;
}

interface LinkExistingBody {
  branchToken?: string;
  studentId?: string;
  relationship?: string;
}

function clientIp(req: NextRequest): string {
  const forwarded = req.headers.get('x-forwarded-for');
  if (forwarded) return forwarded.split(',')[0]!.trim();
  return req.headers.get('x-real-ip') ?? 'unknown';
}

async function resolveBranchToken(token: string): Promise<BranchTokenRow | null> {
  const { data, error } = await supabaseAdmin
    .from('branch_invite_tokens')
    .select('id, organization_id, external_branch_id, expires_at, revoked_at')
    .eq('token', token)
    .maybeSingle();
  if (error || !data) return null;
  const row = data as BranchTokenRow;
  if (row.revoked_at) return null;
  if (row.expires_at && new Date(row.expires_at).getTime() < Date.now()) return null;
  return row;
}

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const ip = clientIp(req);
  const ipLimit = rateLimit(`ce-link-existing-ip:${ip}`, PER_IP_LIMIT, RATE_WINDOW_MS);
  if (!ipLimit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(ipLimit.retryAfterSeconds) } },
    );
  }
  const userLimit = rateLimit(`ce-link-existing-user:${userId}`, PER_USER_LIMIT, RATE_WINDOW_MS);
  if (!userLimit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(userLimit.retryAfterSeconds) } },
    );
  }

  let body: LinkExistingBody;
  try {
    body = (await req.json()) as LinkExistingBody;
  } catch {
    return NextResponse.json({ error: 'invalid_body' }, { status: 400 });
  }

  const branchToken = body.branchToken?.trim() ?? '';
  const studentId = body.studentId?.trim() ?? '';
  // Only guardian links come through here; anything else falls back to 'child'.
  const relationship = body.relationship === 'other' ? 'other' : 'child';
  if (!studentId) {
    return NextResponse.json({ error: 'missing_fields' }, { status: 400 });
  }

  // Resolve the caller's org + own branch. A supplied token that resolves wins
  // (back-compat); otherwise — absent or unresolvable — fall back to the
  // caller's VERIFIED membership so an in-app link never depends on a public
  // pre-signup token existing.
  let organizationId: string;
  let expectedBranchId: string;
  // The caller's OWN CE student id, when they have one — stamped onto an
  // auto-accept edge so the family link is bidirectional. Best-effort.
  let callerStudentId: string | null = null;
  const token = branchToken ? await resolveBranchToken(branchToken) : null;
  if (token) {
    organizationId = token.organization_id;
    expectedBranchId = token.external_branch_id;
    const members = await getVerifiedMembersForUser(userId).catch(() => []);
    callerStudentId =
      (members.find((m) => m.relationship === 'self' && m.studentId) ??
        members.find((m) => m.studentId))?.studentId ?? null;
  } else {
    const members = await getVerifiedMembersForUser(userId);
    const primary =
      members.find((m) => m.relationship === 'self' && m.studentId) ??
      members.find((m) => m.studentId) ??
      null;
    if (!primary?.studentId || !primary.orgId) {
      return NextResponse.json({ error: 'no_membership' }, { status: 401 });
    }
    organizationId = primary.orgId;
    callerStudentId = primary.studentId;
    try {
      const callerProfile = await getStudentProfile(primary.studentId);
      expectedBranchId = callerProfile.branch_id;
    } catch (err) {
      if (err instanceof ChessEmpireAPIError) {
        return NextResponse.json({ error: 'upstream_error' }, { status: 502 });
      }
      throw err;
    }
    if (!expectedBranchId) {
      return NextResponse.json({ error: 'branch_mismatch' }, { status: 401 });
    }
  }

  // Look up any existing member row for this external student (per org, source).
  // The one unique member row per student is NEVER stolen — how we proceed
  // depends on who owns it.
  const { data: existing } = await supabaseAdmin
    .from('organization_members')
    .select('id, user_id, link_status')
    .eq('organization_id', organizationId)
    .eq('external_source', 'chess_empire')
    .eq('external_student_id', studentId)
    .in('link_status', ['verified', 'frozen'])
    .maybeSingle();
  const existingRow = existing as
    | { id: string; user_id: string | null; link_status: string | null }
    | null;

  // The caller ALREADY owns this student's row → idempotent success. A frozen
  // row is reactivated to verified; a verified row is a no-op.
  if (existingRow && existingRow.user_id === userId) {
    if (existingRow.link_status === 'frozen') {
      const name = await getStudentDisplayName(studentId).catch(() => null);
      try {
        await upsertMemberLink({
          orgId: organizationId,
          clerkUserId: userId,
          studentId,
          linkStatus: 'verified',
          linkSource: 'claim',
          relationship,
          externalSource: 'chess_empire',
          name,
        });
      } catch (err) {
        console.error('[chess-empire/link/link-existing] reactivate failed', err);
        return NextResponse.json({ error: 'server_error' }, { status: 500 });
      }
    }
    return NextResponse.json({ ok: true, studentId, relationship, via: 'existing' });
  }

  // Confirm the student is real, active, and in the parent's own branch — the
  // same-branch precondition gates BOTH the row mint and the auto-accept edge.
  let branchId: string;
  let status: string | null;
  try {
    const profile = await getStudentProfile(studentId);
    branchId = profile.branch_id;
    status = profile.status;
  } catch (err) {
    if (err instanceof ChessEmpireAPIError) {
      const notFound = err.statusCode === 404;
      return NextResponse.json(
        { error: notFound ? 'not_found' : 'upstream_error' },
        { status: notFound ? 404 : 502 },
      );
    }
    throw err;
  }

  if (branchId !== expectedBranchId) {
    return NextResponse.json({ error: 'branch_mismatch' }, { status: 401 });
  }
  if (status !== 'active') {
    return NextResponse.json({ error: 'inactive' }, { status: 401 });
  }

  const name = await getStudentDisplayName(studentId).catch(() => null);

  // The student is owned by a DIFFERENT account (self-registered). We do NOT
  // steal or duplicate their row — instead we mint an auto-accepted family edge
  // (same branch = trusted), granting the caller register rights with no second
  // member row. The student keeps their own account.
  if (existingRow) {
    try {
      await createAutoAcceptedFamilyEdge({
        inviterUserId: userId,
        inviterOrgId: organizationId,
        inviterStudentId: callerStudentId,
        accepterUserId: existingRow.user_id,
        targetStudentId: studentId,
        targetOrgId: organizationId,
        targetName: name,
        relationship,
      });
    } catch (err) {
      console.error('[chess-empire/link/link-existing] edge create failed', err);
      return NextResponse.json({ error: 'server_error' }, { status: 500 });
    }
    return NextResponse.json({ ok: true, studentId, relationship, via: 'edge' });
  }

  // Unlinked student in the caller's own branch → mint a member row (now
  // multi-row safe once the (org,user_id) unique constraint is dropped).
  try {
    await upsertMemberLink({
      orgId: organizationId,
      clerkUserId: userId,
      studentId,
      linkStatus: 'verified',
      linkSource: 'claim',
      relationship,
      externalSource: 'chess_empire',
      name,
    });
  } catch (err) {
    console.error('[chess-empire/link/link-existing] upsert failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }

  return NextResponse.json({ ok: true, studentId, relationship });
}
