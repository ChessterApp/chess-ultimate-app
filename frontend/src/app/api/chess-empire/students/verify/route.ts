/**
 * Student claim → invite JWT.
 *
 * Phase 1 of the Chess Empire → Chesster onboarding arc. POST with
 * `{ branchToken, studentId }`. On success the server issues a
 * 60-minute HS256 JWT carrying the student/branch/org context — the
 * sign-up page then forwards it through Clerk so the webhook can write
 * the `external_student_id` link on the new member row.
 *
 * Every attempt — success or failure — is written to
 * `student_verify_attempts` for audit + anomaly alerts.
 */
import 'server-only';

import { NextRequest, NextResponse } from 'next/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import {
  getStudentProfile,
  getCoachProfile,
  ChessEmpireAPIError,
} from '@/lib/chess-empire-client';
import {
  signInviteJwt,
  type MemberType,
  type LinkRelationship,
} from '@/lib/invite-jwt';
import {
  insertPendingRegistration,
  CE_PENDING_COOKIE,
  PENDING_COOKIE_MAX_AGE_SECONDS,
} from '@/lib/pending-registration';

interface BranchTokenRow {
  id: string;
  organization_id: string;
  external_branch_id: string;
  branch_name: string;
  expires_at: string | null;
  revoked_at: string | null;
}

interface VerifyBody {
  branchToken?: string;
  studentId?: string;
  /** Optional; `'coach'` claims a CE coach instead of a student. */
  type?: string;
  /**
   * Optional family link type for the resulting member row. Only `'child'` /
   * `'other'` are honoured (the "add family member" flow); anything else —
   * including `'self'` or absent — leaves the JWT legacy-shaped so the resulting
   * row keeps the DB default of `'self'`.
   */
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
    .select('id, organization_id, external_branch_id, branch_name, expires_at, revoked_at')
    .eq('token', token)
    .maybeSingle();
  if (error || !data) return null;
  const row = data as BranchTokenRow;
  if (row.revoked_at) return null;
  if (row.expires_at && new Date(row.expires_at).getTime() < Date.now()) return null;
  return row;
}

async function logAttempt(args: {
  organizationId: string;
  branchTokenId: string;
  externalStudentId: string | null;
  ip: string;
  success: boolean;
  reason: string | null;
}): Promise<void> {
  const { error } = await supabaseAdmin.from('student_verify_attempts').insert({
    organization_id: args.organizationId,
    external_student_id: args.externalStudentId,
    branch_token_id: args.branchTokenId,
    ip: args.ip,
    success: args.success,
    reason: args.reason,
  });
  if (error) {
    console.error('[ce-verify] failed to log attempt:', error);
  }
}

export async function POST(req: NextRequest) {
  const ip = clientIp(req);
  let body: VerifyBody;
  try {
    body = (await req.json()) as VerifyBody;
  } catch {
    return NextResponse.json({ error: 'invalid_body' }, { status: 400 });
  }

  const branchToken = body.branchToken?.trim() ?? '';
  const studentId = body.studentId?.trim() ?? '';
  const memberType: MemberType = body.type === 'coach' ? 'coach' : 'student';
  // Guardian links only ever come from the authenticated add-family-member flow;
  // a second 'self' is meaningless here so only 'child'/'other' are accepted.
  const relationship: LinkRelationship | undefined =
    body.relationship === 'child' || body.relationship === 'other'
      ? body.relationship
      : undefined;
  if (!branchToken || !studentId) {
    return NextResponse.json({ error: 'missing_fields' }, { status: 400 });
  }

  const token = await resolveBranchToken(branchToken);
  if (!token) {
    return NextResponse.json({ error: 'invalid_token' }, { status: 401 });
  }

  // Duplicate-account pre-check. Race-safe write-side is the unique index.
  const { data: existing } = await supabaseAdmin
    .from('organization_members')
    .select('id')
    .eq('organization_id', token.organization_id)
    .eq('external_source', 'chess_empire')
    .eq('external_student_id', studentId)
    .in('link_status', ['verified', 'frozen'])
    .maybeSingle();
  if (existing) {
    await logAttempt({
      organizationId: token.organization_id,
      branchTokenId: token.id,
      externalStudentId: studentId,
      ip,
      success: false,
      reason: 'already_registered',
    });
    return NextResponse.json(
      { error: 'ALREADY_REGISTERED' },
      { status: 409 },
    );
  }

  // Coaches live in a separate CE table with no `status` column, so we fetch
  // their profile (for the branch-match check) via getCoachProfile and skip
  // the active-status gate entirely.
  let branchId: string;
  let status: string | null;
  try {
    if (memberType === 'coach') {
      const coach = await getCoachProfile(studentId);
      branchId = coach.branch_id;
      status = null;
    } else {
      const profile = await getStudentProfile(studentId);
      branchId = profile.branch_id;
      status = profile.status;
    }
  } catch (err) {
    if (err instanceof ChessEmpireAPIError) {
      const reason = err.statusCode === 404 ? 'not_found' : 'upstream_error';
      await logAttempt({
        organizationId: token.organization_id,
        branchTokenId: token.id,
        externalStudentId: studentId,
        ip,
        success: false,
        reason,
      });
      return NextResponse.json(
        { error: reason },
        { status: err.statusCode === 404 ? 404 : 502 },
      );
    }
    throw err;
  }

  if (branchId !== token.external_branch_id) {
    await logAttempt({
      organizationId: token.organization_id,
      branchTokenId: token.id,
      externalStudentId: studentId,
      ip,
      success: false,
      reason: 'branch_mismatch',
    });
    return NextResponse.json({ error: 'branch_mismatch' }, { status: 401 });
  }

  // Students must be active; coaches have no status and skip this check.
  if (memberType === 'student' && status !== 'active') {
    await logAttempt({
      organizationId: token.organization_id,
      branchTokenId: token.id,
      externalStudentId: studentId,
      ip,
      success: false,
      reason: 'inactive',
    });
    return NextResponse.json({ error: 'inactive' }, { status: 401 });
  }

  const inviteJwt = signInviteJwt({
    student_id: studentId,
    branch_id: token.external_branch_id,
    branch_token_id: token.id,
    org_id: token.organization_id,
    // Omit for students so legacy-shaped tokens stay identical (back-compat).
    ...(memberType === 'coach' ? { member_type: 'coach' as const } : {}),
    // Omit for self-claims so legacy-shaped tokens stay identical (back-compat).
    ...(relationship ? { relationship } : {}),
  });

  // Durable pending link: persist the row + drop an httpOnly cookie carrying
  // the raw JWT so completion survives dropped OAuth metadata and the short
  // JWT TTL. Best-effort — the JWT itself is still the primary carrier.
  await insertPendingRegistration({
    rawJwt: inviteJwt,
    studentId,
    orgId: token.organization_id,
    memberType,
  });

  await logAttempt({
    organizationId: token.organization_id,
    branchTokenId: token.id,
    externalStudentId: studentId,
    ip,
    success: true,
    reason: null,
  });

  const res = NextResponse.json({ inviteJwt });
  res.cookies.set(CE_PENDING_COOKIE, inviteJwt, {
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    path: '/',
    maxAge: PENDING_COOKIE_MAX_AGE_SECONDS,
  });
  return res;
}
