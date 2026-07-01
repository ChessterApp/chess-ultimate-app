/**
 * Student claim → invite JWT.
 *
 * Phase 1 of the Chess Empire → Chesster onboarding arc. POST with
 * `{ branchToken, studentId }`. On success the server issues a
 * 15-minute HS256 JWT carrying the student/branch/org context — the
 * sign-up page then forwards it through Clerk so the webhook can write
 * the `external_student_id` link on the new member row.
 *
 * Rate limits:
 *  - 3 failed attempts per (studentId, IP) per hour
 *  - 10 failed attempts per IP per hour (across all students)
 *
 * Every attempt — success or failure — is written to
 * `student_verify_attempts` for audit + anomaly alerts.
 */
import 'server-only';

import { NextRequest, NextResponse } from 'next/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import {
  getStudentProfile,
  ChessEmpireAPIError,
  type CEStudentProfile,
} from '@/lib/chess-empire-client';
import { signInviteJwt } from '@/lib/invite-jwt';
import { rateLimit } from '@/lib/in-memory-rate-limit';

const PER_STUDENT_LIMIT = 3;
const PER_IP_LIMIT = 10;
const RATE_WINDOW_MS = 60 * 60 * 1000;

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
  if (!branchToken || !studentId) {
    return NextResponse.json({ error: 'missing_fields' }, { status: 400 });
  }

  const token = await resolveBranchToken(branchToken);
  if (!token) {
    return NextResponse.json({ error: 'invalid_token' }, { status: 401 });
  }

  // Rate-limit BEFORE we touch the CE API to avoid burning the upstream
  // budget on flood traffic. Failed attempts count; successes don't.
  const ipLimit = rateLimit(`ce-verify-ip:${ip}`, PER_IP_LIMIT, RATE_WINDOW_MS);
  if (!ipLimit.allowed) {
    await logAttempt({
      organizationId: token.organization_id,
      branchTokenId: token.id,
      externalStudentId: studentId,
      ip,
      success: false,
      reason: 'rate_limited_ip',
    });
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(ipLimit.retryAfterSeconds) } },
    );
  }
  const studentLimit = rateLimit(
    `ce-verify-stu:${studentId}:${ip}`,
    PER_STUDENT_LIMIT,
    RATE_WINDOW_MS,
  );
  if (!studentLimit.allowed) {
    await logAttempt({
      organizationId: token.organization_id,
      branchTokenId: token.id,
      externalStudentId: studentId,
      ip,
      success: false,
      reason: 'rate_limited_student',
    });
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(studentLimit.retryAfterSeconds) } },
    );
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

  let profile: CEStudentProfile;
  try {
    profile = await getStudentProfile(studentId);
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

  if (profile.branch_id !== token.external_branch_id) {
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

  if (profile.status !== 'active') {
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
  });

  await logAttempt({
    organizationId: token.organization_id,
    branchTokenId: token.id,
    externalStudentId: studentId,
    ip,
    success: true,
    reason: null,
  });

  return NextResponse.json({ inviteJwt });
}
